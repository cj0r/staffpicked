#!/usr/bin/env python3
"""Web UI for StaffPicked, the Emby/Jellyfin collection & playlist generator. Standard library only.

Serves public/ and a small JSON API that edits the settings and config files,
runs the generator scripts (see backend.py), streams their output over
Server-Sent Events, and runs them on a schedule.

  PORT        default 9343
  CONFIG_DIR  default ./config (the image uses /config)
"""
import collections, concurrent.futures, datetime, hashlib, hmac, http.server, json, mimetypes, os, queue, re
import secrets, signal, socketserver, subprocess, sys, threading, time, urllib.parse, urllib.request

import backend, builder, notify, security
from scripts import __version__ as VERSION    # backend puts the app folder on the path

PORT = int(os.environ.get("PORT", "9343"))
PUBLIC_DIR = os.path.join(backend.HERE, "public")
WEB_FILE = os.path.join(backend.WEB_DIR, "web.json")
LOG_DIR = os.path.join(backend.WEB_DIR, "logs")
HISTORY_FILE = os.path.join(backend.WEB_DIR, "history.json")
RUN_LOG_DIR = os.path.join(LOG_DIR, "runs")     # each run's own output, opened from Recent Runs
RUN_LOGS_KEPT = 60
SESSION_DAYS = 30
mimetypes.add_type("font/woff2", ".woff2")
LOCK = threading.RLock()


# ---------------------------------------------------------------- small stores

def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, data, private=False):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    if private:
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def web_settings():
    s = read_json(WEB_FILE, {})
    s.setdefault("auth", {})
    return s


def save_web_settings(s):
    write_json(WEB_FILE, s, private=True)


# ---------------------------------------------------------------- env file

ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")


def read_env():
    env = {}
    try:
        with open(backend.ENV_FILE, encoding="utf-8") as f:
            for line in f:
                m = ENV_LINE.match(line)
                if m and not line.lstrip().startswith("#"):
                    v = m.group(2).strip()
                    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                        v = v[1:-1]
                    env[m.group(1)] = v
    except OSError:
        pass
    return env


NEXT_TO = {"SYNC_EVERY": "SYNC_TIME"}


def write_env(changes):
    """Set or clear keys, keeping comments, order and unknown keys. A value of None takes the key's line out."""
    try:
        with open(backend.ENV_FILE, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    done = set()
    for i, line in enumerate(lines):
        m = ENV_LINE.match(line)
        if m and not line.lstrip().startswith("#") and m.group(1) in changes:
            v = changes[m.group(1)]
            lines[i] = None if v is None else f"{m.group(1)}={v}"
            done.add(m.group(1))
    lines = [line for line in lines if line is not None]
    for k, v in changes.items():
        if k in done or not v:    # a blank key that isn't in the file is already blank
            continue
        # a new key goes next to the setting it belongs with (SYNC_EVERY after SYNC_TIME), else last
        at = next((i + 1 for i, line in enumerate(lines) if (m := ENV_LINE.match(line))
                   and not line.lstrip().startswith("#") and m.group(1) == NEXT_TO.get(k)), len(lines))
        lines.insert(at, f"{k}={v}")
    tmp = backend.ENV_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, backend.ENV_FILE)


def mode():
    return backend.mode_from_env(read_env())


# ---------------------------------------------------------------- events (SSE)

class Hub:
    def __init__(self):
        self.clients = set()
        self.lock = threading.Lock()

    def subscribe(self):
        q = queue.Queue(maxsize=2000)
        with self.lock:
            self.clients.add(q)
        return q

    def unsubscribe(self, q):
        with self.lock:
            self.clients.discard(q)

    def publish(self, event, data):
        msg = f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()
        with self.lock:
            for q in list(self.clients):
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    self.clients.discard(q)  # a stuck client; it reconnects and reloads


HUB = Hub()


# ---------------------------------------------------------------- job runner

def mask(text, secrets_):
    for s in secrets_:
        if s and len(s) >= 4:
            text = text.replace(s, "••••")
    return text


class Job:
    def __init__(self, name):
        self.name = name
        self.proc = None
        self.run = None          # the current or last run: dict
        self.lines = collections.deque(maxlen=3000)
        self.aborted = False
        self.on_done = None      # called with the run's status when it ends

    @property
    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def state(self):
        return {"name": self.name, "label": backend.JOBS[self.name]["label"],
                "description": backend.JOBS[self.name]["description"],
                "installed": backend.installed(),
                "supports_only": True,
                "running": self.running, "run": self.run}

    def start(self, action, dry_run=False, only=None, trigger="manual", on_done=None, server=None, allow_removals=False):
        with LOCK:
            if self.running:
                raise ValueError(f"{backend.JOBS[self.name]['label']} is already running")
            if not backend.installed():
                raise ValueError(f"StaffPicked is not installed in {backend.APP_ROOT}")
            fileenv = read_env()
            time_zone()      # so the run uses the time zone picked in Settings
            env = {**os.environ, **backend.job_env(self.name),
                   "PYTHONUNBUFFERED": "1", "DRY_RUN": "1" if dry_run else "0"}
            cmd = backend.command(self.name, action, dry_run, only, server, allow_removals)
            self.aborted = False
            self.on_done = on_done
            self.run = {"id": run_id(self.name), "action": action, "dry_run": bool(dry_run), "only": only or "",
                        "server": server or "", "trigger": trigger, "started": now(), "ended": None, "exit": None,
                        "status": "running",
                        "servers": {},    # each server's result, from the run's "[server] name: ok" lines
                        "summary": None,  # films added and removed and errors, from its "[summary]" line
                        # which list it's on: one step per list per server it goes to
                        "progress": {"done": 0, "total": backend.run_steps(self.name, only, server), "current": ""}}
            self.run_lines, self.run_changes = [], []
            self.lines.clear()
            os.makedirs(LOG_DIR, exist_ok=True)
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                                         cwd=backend.CONFIG_DIR, text=True, bufsize=1, errors="replace",
                                         start_new_session=True)
            hidden = backend.secret_values(fileenv)
            threading.Thread(target=self._pump, args=(hidden,), daemon=True).start()
        self._emit_line(f"=== {now()} {action}{' (dry run)' if dry_run else ''}{' --only ' + only if only else ''}"
                        f"{' --allow-removals' if allow_removals and action == 'sync' else ''}"
                        f"{' --server ' + server if server else ''} [{trigger}] ===")
        HUB.publish("status", self.state())

    def _emit_line(self, line):
        self.lines.append(line)
        if getattr(self, "run_lines", None) is not None:
            self.run_lines.append(line)
        try:
            with open(os.path.join(LOG_DIR, f"{self.name}.log"), "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass
        HUB.publish("log", {"job": self.name, "line": line})

    def _pump(self, hidden):
        proc = self.proc
        for line in proc.stdout:
            line = mask(line.rstrip("\n"), hidden)
            m = SERVER_RESULT.match(line)
            if m:
                self.run["servers"][m[1]] = "ok" if m[2] == "ok" else "failed"
            m = SUMMARY.match(line)
            if m:
                try:
                    self.run["summary"] = json.loads(m[1])
                except ValueError:
                    pass
                continue      # for the UI, not for people reading the log
            m = DIFF.match(line)
            if m:
                try:
                    self.run_changes.append(json.loads(m[1]))
                    self.run["changed"] = len(self.run_changes)
                except ValueError:
                    pass
                continue
            m = STEP.match(line)
            if m and self.run["action"] != "check":
                p = self.run["progress"]
                p["done"] = min(p["done"] + 1, max(p["total"], p["done"] + 1))
                p["total"] = max(p["total"], p["done"])
                p["current"] = m[2]
                HUB.publish("progress", {"task": "sync", "job": self.name, **p})
            self._emit_line(line)
        code = proc.wait()
        with LOCK:
            status = "aborted" if self.aborted else ("ok" if code == 0 else "failed")
            self.run.update(ended=now(), exit=code, status=status)
            hist = read_json(HISTORY_FILE, [])
            hist.append({"job": self.name, **{k: v for k, v in self.run.items() if k != "progress"}})
            write_json(HISTORY_FILE, hist[-200:])
        self._emit_line(f"=== {status} (exit {code}) ===")
        save_run_log(self.run["id"], self.run_lines, self.run_changes)
        self.run_lines = None
        if self.on_done:
            try:
                self.on_done(status)
            except Exception as e:
                self._emit_line(f"error: {e}")
        HUB.publish("status", self.state())

    def abort(self):
        with LOCK:
            if not self.running:
                return False
            self.aborted = True
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
            except OSError:
                pass
            proc = self.proc

        def reap():
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except OSError:
                    pass
        threading.Thread(target=reap, daemon=True).start()
        return True


JOBS = {name: Job(name) for name in backend.JOBS}
SERVER_RESULT = re.compile(r"^\[server\] (.+): (ok|\d+ error\(s\))$")
SUMMARY = re.compile(r"^\[summary\] (\{.*\})$")
DIFF = re.compile(r"^\[diff\] (\{.*\})$")
STEP = re.compile(r"^\[(collection|playlist|genre)\] (.+)$")
RUN_ID = re.compile(r"^[a-z]+-\d{8}-\d{6}-[0-9a-f]{4}$")


def run_id(job):
    return f"{job}-{datetime.datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def save_run_log(rid, lines, changes=()):
    """Keep one run's output on its own, for Recent Runs, with what it changed on each list
    (<id>.changes.json); only the newest RUN_LOGS_KEPT runs stay."""
    try:
        os.makedirs(RUN_LOG_DIR, exist_ok=True)
        with open(os.path.join(RUN_LOG_DIR, f"{rid}.log"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        if changes:
            write_json(os.path.join(RUN_LOG_DIR, f"{rid}.changes.json"), list(changes))
        logs = sorted((n for n in os.listdir(RUN_LOG_DIR) if n.endswith(".log")),
                      key=lambda n: os.path.getmtime(os.path.join(RUN_LOG_DIR, n)))
        for old in logs[:-RUN_LOGS_KEPT]:
            for name in (old, old[:-4] + ".changes.json"):
                try:
                    os.remove(os.path.join(RUN_LOG_DIR, name))
                except FileNotFoundError:
                    pass
    except OSError:
        pass


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


BATCHES = {"running": 0}   # Run All and scheduled syncs still going, so the scheduler waits for them


def run_all(trigger, dry_run=None):
    """Run each job the mode allows, one after another, in a background thread."""
    return run_batch(backend.jobs_for_mode(mode(), read_env()), trigger, dry_run)


def run_batch(names, trigger, dry_run=None, only=None):
    """Sync these jobs one after another in a background thread; only is {job: list name} for a
    job that syncs just one of its lists. Waits for anything already running to end first."""
    if dry_run is None:
        dry_run = read_env().get("DRY_RUN", "0").strip().lower() in ("1", "true", "yes", "on")
    only = only or {}
    BATCHES["running"] += 1

    def go():
        try:
            batch()
        finally:
            BATCHES["running"] -= 1

    def batch():
        runs = []
        for n in names:
            while JOBS[n].running:
                time.sleep(1)
            try:
                JOBS[n].start("sync", dry_run=dry_run, trigger=trigger, only=only.get(n))
            except ValueError as e:
                HUB.publish("log", {"job": n, "line": f"Skipped: {e}"})
                continue
            run = JOBS[n].run
            while JOBS[n].running or not run.get("ended"):
                time.sleep(1)
            runs.append({"job": n, **run})
        notify_runs(runs, trigger)
    threading.Thread(target=go, daemon=True).start()
    return names


def notify_runs(runs, trigger):
    """Send NOTIFY_URL a one-line summary when NOTIFY_ON asks for one."""
    env = read_env()
    if not notify.wanted(env, runs, trigger):
        return
    title, text = notify.message(runs, trigger)
    try:
        notify.send(env["NOTIFY_URL"].strip(), title, text, failure=notify.failed(runs))
    except Exception as e:
        line = f"Could not send the notification: {mask(str(e), [env.get('NOTIFY_URL', '')])}"
        print(line, file=sys.stderr)
        HUB.publish("log", {"job": runs[-1]["job"], "line": line})


_next = {"at": None, "setting": None}
_last = {"at": None}               # when the scheduler last started a sync; SYNC_EVERY counts from it
HEARTBEAT = {"at": time.time()}   # the scheduler's last pass, for /api/health


def schedule_text():
    """The schedule in words, for the dashboard: "Every 6 hours", "Daily at 06:00 and 18:00"."""
    return backend.settings_module().describe_schedule(read_env())


def time_zone():
    """The time zone SYNC_TIME is read in: TIME_ZONE from Settings, else the container's TZ.
    It's applied to this process, so runs it starts use it too."""
    return backend.settings_module().apply_time_zone(read_env())


_zones = []


def time_zones():
    """Every time zone name this system knows, for the Settings picker."""
    if not _zones:
        import zoneinfo
        _zones.extend(sorted(z for z in zoneinfo.available_timezones() if "/" in z or z == "UTC"))
    return _zones


def next_run():
    """When the scheduler syncs next; follows edits to SYNC_TIME, SYNC_EVERY and TIME_ZONE."""
    env = read_env()
    setting = (env.get("SYNC_TIME", ""), env.get("SYNC_EVERY", ""), time_zone())
    if _next["setting"] != setting or _next["at"] is None:
        now = datetime.datetime.now().astimezone()
        _next.update(setting=setting, at=backend.settings_module().next_sync(env, now, _last["at"]))
    return _next["at"].isoformat(timespec="minutes")


def scheduler():
    """Same behavior as `python -m scripts schedule`: sync once at start unless
    SYNC_ON_START=false, then at each SYNC_TIME, or every SYNC_EVERY when that's set,
    re-reading the settings each time. A sync that's still running holds the next one
    until it ends. It runs here instead so scheduled runs show up in the UI like any other."""
    time_zone()
    _last["at"] = datetime.datetime.now().astimezone()
    _next["at"] = None
    if needs_setup():
        print("No media server is set up yet, so nothing syncs until one is. Open the web UI to set one up.", flush=True)
    elif backend.truthy(read_env().get("SYNC_ON_START", "true")):
        run_all("start")
    while True:
        HEARTBEAT["at"] = time.time()
        time.sleep(15)
        try:
            next_run()
            now = datetime.datetime.now().astimezone()
            if now >= _next["at"] and not BATCHES["running"] and not any(j.running for j in JOBS.values()):
                _last["at"], _next["at"] = now, None
                if not needs_setup():    # a placeholder server would only fail
                    run_all("schedule")
                next_run()
            new_films()
        except Exception as e:  # never let the scheduler thread die
            print(f"scheduler: {e}", file=sys.stderr)


ARRIVALS = {"watch": None, "at": 0.0, "busy": False}


def new_films():
    """Every NEW_FILM_CHECK, look for films just added to the servers and sync the lists that
    were missing them (see scripts/arrivals.py). The check runs on its own thread, so a slow
    server never holds up the scheduler."""
    env = read_env()
    every = backend.arrivals_module().minutes(env)
    if ARRIVALS["busy"] or not every or needs_setup(env) or time.time() - ARRIVALS["at"] < every * 60:
        return
    ARRIVALS.update(at=time.time(), busy=True)

    def go():
        try:
            check_new_films(env)
        except Exception as e:
            print(f"new film check: {mask(str(e), backend.secret_values(env))}", file=sys.stderr)
        finally:
            ARRIVALS["busy"] = False
    threading.Thread(target=go, daemon=True).start()


def check_new_films(env):
    arrivals = backend.arrivals_module()
    if ARRIVALS["watch"] is None:
        ARRIVALS["watch"] = arrivals.Watch()
    found = ARRIVALS["watch"].poll(env)
    if not found:
        return
    wanted = arrivals.wanting(backend.CONFIG_DIR, found)
    on = backend.jobs_for_mode(backend.mode_from_env(env), env)
    jobs = {job: wanted[info["kind"]] for job, info in backend.JOBS.items()
            if info["kind"] in wanted and job in on}
    titles = "; ".join(found.values())
    if not jobs:
        print(f"New on the server: {titles}. No list was missing it.", flush=True)
        return
    for job, names in jobs.items():
        JOBS[job]._emit_line(f"New on the server: {titles}. Syncing {', '.join(names)}.")
    run_batch(list(jobs), "arrival", only={job: names[0] for job, names in jobs.items() if len(names) == 1})


def needs_setup(env=None):
    """True until some media server is set up; the first-run screen shows and nothing syncs."""
    return not backend.settings_module().any_server_ready(read_env() if env is None else env)


# ---------------------------------------------------------------- Emby

_status_cache = {}    # (type, url, key) -> (time, result)
_request_cache = {}   # imdb -> (time, service setup, state): request states, so reopening a list is quick
REQUEST_TTL = 120
IMDB = re.compile(r"tt\d+")


def request_states(rq, env, items):
    """{states: {imdb: state}, errors: {service: message}}, asking only about titles not looked up lately."""
    now, setup = time.time(), json.dumps(rq.setup(env), sort_keys=True)
    states, ask = {}, []
    for imdb, show in items:
        hit = _request_cache.get(imdb)
        if hit and now - hit[0] < REQUEST_TTL and hit[1] == setup:
            states[imdb] = hit[2]
        else:
            ask.append((imdb, show))
    errors = {}
    if ask:
        fresh, errors = rq.states(env, ask)
        for imdb, st in fresh.items():
            _request_cache[imdb] = (now, setup, st)
        states.update(fresh)
    return {"states": states, "errors": errors}


def server_list(env=None):
    """[{id, name, type, env}] for every server in the env file."""
    return backend.settings_module().servers(read_env() if env is None else env)


def server_status(s, force=False):
    url, key = s["env"].get("SERVER_URL", "").rstrip("/"), s["env"].get("SERVER_API_KEY", "")
    base = {"id": s["id"], "name": s["name"], "type": s["type"]}
    if not url or not key:
        return {**base, "ok": False, "error": "Set the server URL and API key in Settings."}
    hit = _status_cache.get((s["type"], url, key))
    if not force and hit and time.time() - hit[0] < 30:
        return {**base, **hit[1]}
    try:
        # Jellyfin 12 no longer takes Emby's token header, only its own
        auth = {"Authorization": f'MediaBrowser Token="{key}"'} if s["type"] == "jellyfin" else {"X-Emby-Token": key}
        req = urllib.request.Request(f"{url}/System/Info", headers={**auth, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=6) as r:
            info = json.load(r)
        value = {"ok": True, "server": info.get("ServerName", ""), "version": info.get("Version", "")}
    except Exception as e:
        value = {"ok": False, "error": mask(str(e), [key])}
    _status_cache[(s["type"], url, key)] = (time.time(), value)
    return {**base, **value}


def servers_status(force=False):
    """Every server's connection, checked side by side."""
    found = server_list()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(found))) as pool:
        out = list(pool.map(lambda s: server_status(s, force), found))
    return {"ok": all(x["ok"] for x in out), "servers": out}


# ---------------------------------------------------------------- auth

class Sessions:
    """Signed-in browsers, kept in web.json so a restart or update doesn't sign anyone out.
    Only a SHA-256 of each token is stored, so the file can't be used to sign in."""

    def __init__(self):
        self.lock = threading.Lock()

    @staticmethod
    def _key(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def _load(self):
        s = web_settings()
        now = time.time()
        live = {k: v for k, v in (s.get("sessions") or {}).items() if isinstance(v, (int, float)) and v > now}
        return s, live

    def _save(self, s, live):
        s["sessions"] = live
        save_web_settings(s)

    def new(self):
        token = secrets.token_urlsafe(32)
        with self.lock:
            s, live = self._load()
            live[self._key(token)] = time.time() + SESSION_DAYS * 86400
            self._save(s, live)
        return token

    def valid(self, token):
        return bool(token) and self._load()[1].get(self._key(token), 0) > time.time()

    def drop(self, token):
        with self.lock:
            s, live = self._load()
            if live.pop(self._key(token or ""), None) is not None or len(live) != len(s.get("sessions") or {}):
                self._save(s, live)

    def clear(self):
        with self.lock:
            s, _ = self._load()
            self._save(s, {})


SESSIONS = Sessions()


def check_password(pw):
    """Whether pw is the UI's password. A hash saved with fewer rounds is redone on a match."""
    auth = web_settings()["auth"]
    if not auth.get("hash"):
        return True
    if not security.password_matches(pw, auth):
        return False
    if int(auth.get("rounds") or security.OLD_ROUNDS) < security.PBKDF2_ROUNDS:
        stronger = security.hash_password(pw)
        with LOCK:
            s = web_settings()
            if s["auth"].get("hash") == auth["hash"]:
                s["auth"].update(stronger)
                save_web_settings(s)
    return True


def auth_enabled():
    return bool(web_settings()["auth"].get("hash"))


def mfa_on(auth=None):
    return bool((auth if auth is not None else web_settings()["auth"]).get("totp", {}).get("secret"))


def check_code(code):
    """An authenticator code or an unused recovery code, for the UI's two-factor sign-in.
    A recovery code is used up, and so is the code's time step, so neither works twice.
    Returns "totp", "recovery" or None."""
    code = str(code or "").strip()
    with LOCK:
        s = web_settings()
        auth = s["auth"]
        totp = auth.get("totp") or {}
        if not totp.get("secret") or not code:
            return None
        step = security.totp_check(totp["secret"], code, totp.get("last_step"))
        if step is not None:
            totp["last_step"] = step
            save_web_settings(s)
            return "totp"
        left = security.recovery_use(code, auth.get("recovery"))
        if left is not None:
            auth["recovery"] = left
            save_web_settings(s)
            return "recovery"
    return None


class Limiter:
    """Failed sign-ins, codes and password checks per client address: after LIMIT failures in
    WINDOW seconds that address waits out the window. Every failure is logged with its address
    (for fail2ban and the like)."""
    LIMIT, WINDOW, MAX_ADDRESSES = 5, 300, 10000

    def __init__(self):
        self.fails = {}
        self.lock = threading.Lock()

    def _recent(self, ip, now):
        return [t for t in self.fails.get(ip, ()) if t > now - self.WINDOW]

    def check(self, ip):
        with self.lock:
            if len(self._recent(ip, time.time())) >= self.LIMIT:
                raise Error(429, "Too many attempts. Try again in a few minutes.")

    def fail(self, ip, what):
        now = time.time()
        with self.lock:
            if len(self.fails) > self.MAX_ADDRESSES:
                self.fails = {k: v for k, v in self.fails.items() if self._recent(k, now)}
            self.fails[ip] = self._recent(ip, now) + [now]
        print(f"[auth] {what} from {ip}", file=sys.stderr, flush=True)
        time.sleep(0.5)    # slows guessing a little more without holding anyone else up

    def clear(self, ip):
        with self.lock:
            self.fails.pop(ip, None)


LIMITER = Limiter()


def web_options(env=None):
    """URL_BASE and TRUSTED_PROXIES, from the container's environment or staffpicked.env
    (the environment wins, like every other setting)."""
    env = read_env() if env is None else env
    get = lambda k: os.environ.get(k) or env.get(k, "")
    base = security.clean_base(get("URL_BASE"))
    nets, bad = security.parse_networks(get("TRUSTED_PROXIES"))
    key = (get("URL_BASE"), get("TRUSTED_PROXIES"))
    if bad and _warned.get("proxies") != key:
        print(f"TRUSTED_PROXIES: ignoring {', '.join(bad)} (not an address or range)", file=sys.stderr, flush=True)
    if base is None and _warned.get("base") != key:
        print(f"URL_BASE: {get('URL_BASE')!r} isn't a path like /staffpicked, so it's ignored", file=sys.stderr, flush=True)
    _warned["proxies"] = _warned["base"] = key
    return {"base": base or "", "trusted": nets}


_warned = {}
_options = {"stamp": None, "value": None}


def options():
    """web_options(), read again only when staffpicked.env changes."""
    try:
        stamp = os.stat(backend.ENV_FILE).st_mtime_ns
    except OSError:
        stamp = 0
    if _options["stamp"] != stamp:
        _options.update(stamp=stamp, value=web_options())
    return _options["value"]


# ---------------------------------------------------------------- HTTP

class Error(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


PUBLIC_PATHS = {"/login.html", "/login.js", "/style.css", "/app.css", "/theme.css", "/favicon.svg", "/manifest.json",
                "/api/login", "/api/auth", "/api/health"}
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "font-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; "
       "form-action 'self'; frame-ancestors 'none'")
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": CSP,
    "X-Frame-Options": "DENY",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
}
LOCAL_ONLY = ("StaffPicked has no password yet, so it only opens for browsers on your local network that "
              "connect to it directly (by its IP address or a local name like tower or nas.local). "
              "Open it that way and set a password in Settings to use it from anywhere else.")
LOCAL_ONLY_PAGE = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>StaffPicked</title>
<meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="background:#0b0f19;color:#f3f4f6;font-family:sans-serif;max-width:36rem;margin:15vh auto;padding:0 1rem">
<h1>Set a password first</h1><p>{LOCAL_ONLY}</p></body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "StaffPicked"
    protocol_version = "HTTP/1.1"
    timeout = 120                    # a client that stops sending is dropped instead of holding a thread
    ip, https, proxied = "", False, False

    def version_string(self):
        return self.server_version      # without the Python version

    def log_message(self, fmt, *args):
        if os.environ.get("WEB_ACCESS_LOG"):
            # with the real client's address when it came through a trusted proxy
            sys.stderr.write(f"{self.ip or self.client_address[0]} - [{self.log_date_time_string()}] {fmt % args}\n")

    # -- helpers
    def client_ip(self):
        return self.ip or self.client_address[0]

    def session(self):
        for part in self.headers.get("Cookie", "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "session" and SESSIONS.valid(v):
                return v
        return None

    def authed(self):
        return not auth_enabled() or self.session() is not None

    def local_ok(self):
        """Without a password, only a browser on the local network that connects directly (no
        proxy in between) and by a local name gets in; see security.local_host on why the name."""
        return (not self.proxied and security.local_address(self.client_ip())
                and security.local_host(self.headers.get("Host")))

    def cookie(self, token):
        """The sign-in cookie: Secure when the browser reached StaffPicked over HTTPS (through a
        trusted proxy that says so), so it's never sent over plain HTTP afterwards."""
        secure = "; Secure" if self.https else ""
        if not token:
            return f"session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0{secure}"
        return f"session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_DAYS * 86400}{secure}"

    def security_headers(self):
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)

    def send(self, code, body=b"", ctype="application/json", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if "Cache-Control" not in (headers or {}):
            self.send_header("Cache-Control", "no-store")
        self.security_headers()
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def length(self, limit):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise Error(400, "Bad Content-Length")
        if n < 0:
            raise Error(400, "Bad Content-Length")
        if n > limit:
            raise Error(413, "Too large")
        return n

    def body(self):
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            raise Error(415, "Expected JSON")  # also forces a CORS preflight, so other sites can't post here
        n = self.length(5_000_000)
        try:
            b = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            raise Error(400, "Bad JSON")
        if not isinstance(b, dict):
            raise Error(400, "Expected a JSON object")
        return b

    # -- dispatch
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def do_PUT(self):
        self.route("PUT")

    def do_DELETE(self):
        self.route("DELETE")

    def route(self, method):
        url = urllib.parse.urlsplit(self.path)
        path, qs = url.path, urllib.parse.parse_qs(url.query)
        try:
            opts = options()
            self.ip, self.https, self.proxied = security.client(self.client_address[0], self.headers, opts["trusted"])
            base = opts["base"]
            if base:
                # behind a proxy at https://host/staffpicked/: the proxy may pass the prefix on or
                # strip it; both work. The page's own links are relative, so they follow along.
                if path == base:
                    return self.send(301, "", "text/plain", {"Location": base + "/" + (f"?{url.query}" if url.query else "")})
                if path.startswith(base + "/"):
                    path = path[len(base):]
            if path == "/api/health":
                return self.api(method, path, qs)
            if not auth_enabled() and not self.local_ok():
                if path.startswith("/api/"):
                    raise Error(403, LOCAL_ONLY)
                if path in PUBLIC_PATHS - {"/login.html"} or path.startswith("/vendor/"):
                    return self.static(path)
                return self.send(403, LOCAL_ONLY_PAGE, "text/html; charset=utf-8")
            # another site's page can't make the browser act here (SameSite cookies and JSON-only
            # bodies already stop it; this is a third lock for browsers that send the header)
            if self.headers.get("Sec-Fetch-Site", "").lower() == "cross-site" and (
                    method not in ("GET", "HEAD") or path.startswith("/api/")):
                raise Error(403, "Requests from other sites aren't allowed")
            if path.startswith("/api/"):
                if path not in PUBLIC_PATHS and not self.authed():
                    raise Error(401, "Sign in first")
                return self.api(method, path, qs)
            if method not in ("GET", "HEAD"):
                raise Error(405, "Method not allowed")
            if path == "/":
                path = "/index.html"
            # relative redirects, so they work under any URL_BASE or proxy prefix
            if path not in PUBLIC_PATHS and not path.startswith("/vendor/") and not self.authed():
                return self.send(302, "", "text/plain", {"Location": "login.html"})
            if path == "/login.html" and not auth_enabled():
                return self.send(302, "", "text/plain", {"Location": "./"})
            return self.static(path)
        except Error as e:
            if method not in ("GET", "HEAD"):
                self.close_connection = True   # its body may not have been read
            self.send(e.code, {"error": str(e)})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            print(f"error on {method} {path}: {e!r}", file=sys.stderr)
            self.send(500, {"error": "Internal error; see the container log."})

    def static(self, path):
        full = os.path.realpath(os.path.join(PUBLIC_DIR, path.lstrip("/")))
        if not full.startswith(os.path.realpath(PUBLIC_DIR) + os.sep) or not os.path.isfile(full):
            raise Error(404, "Not found")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        with open(full, "rb") as f:
            self.send(200, f.read(), ctype)

    def api(self, method, path, qs):
        parts = path.strip("/").split("/")[1:]
        key = (method, parts[0] if parts else "")

        if key == ("GET", "auth"):
            return self.send(200, {"enabled": auth_enabled(), "signed_in": self.authed()})
        if key == ("GET", "health"):
            # for Docker's HEALTHCHECK: the web server answers and the scheduler is still going
            ago = time.time() - HEARTBEAT["at"]
            ok = ago < 120
            return self.send(200 if ok else 503, {"ok": ok, "version": VERSION, "scheduler_seconds_ago": round(ago)})
        if key == ("POST", "login"):
            return self.login(self.body())
        if key == ("POST", "logout"):
            self.body()
            SESSIONS.drop(self.session())
            return self.send(200, {"ok": True}, headers={"Set-Cookie": self.cookie(None)})
        if key[1] == "mfa":
            return self.mfa(method, parts[1] if len(parts) == 2 else "", self.body() if method == "POST" else {})

        if key == ("GET", "status"):
            return self.send(200, self.status())
        if key == ("GET", "events"):
            return self.events()
        if key == ("GET", "emby") or key == ("POST", "emby"):
            if method == "POST":
                self.body()   # read it, or it's taken as the start of the next request on this connection
            return self.send(200, servers_status(force=method == "POST"))

        if key == ("POST", "jobs") and len(parts) == 3:
            name, verb = parts[1], parts[2]
            if name == "all" and verb == "run":
                b = self.body()
                return self.send(200, {"started": run_all("manual", b.get("dry_run"))})
            job = JOBS.get(name) or self.missing()
            if verb == "run":
                b = self.body()
                action = b.get("action", "sync")
                if action not in backend.ACTIONS:
                    raise Error(400, "Unknown action")
                try:
                    job.start(action, bool(b.get("dry_run")), (b.get("only") or "").strip() or None,
                              server=(b.get("server") or "").strip() or None,
                              allow_removals=bool(b.get("allow_removals")))
                except ValueError as e:
                    raise Error(409, str(e))
                return self.send(200, job.state())
            if verb == "abort":
                self.body()
                return self.send(200, {"aborted": job.abort()})
            self.missing()
        if key == ("GET", "logs") and len(parts) == 2:
            job = JOBS.get(parts[1]) or self.missing()
            if qs.get("download"):
                try:
                    with open(os.path.join(LOG_DIR, f"{job.name}.log"), "rb") as f:
                        data = f.read()[-5_000_000:]
                except OSError:
                    data = b""
                return self.send(200, data, "text/plain; charset=utf-8",
                                 {"Content-Disposition": f'attachment; filename="{job.name}.log"'})
            return self.send(200, {"lines": list(job.lines)})
        if key == ("DELETE", "logs") and len(parts) == 2:
            job = JOBS.get(parts[1]) or self.missing()
            job.lines.clear()
            try:
                os.remove(os.path.join(LOG_DIR, f"{job.name}.log"))
            except OSError:
                pass
            return self.send(200, {"ok": True})
        if key == ("GET", "history"):
            rows = read_json(HISTORY_FILE, [])[-50:][::-1]
            for r in rows:   # whether its own log can still be opened
                r["has_log"] = bool(r.get("id") and os.path.isfile(os.path.join(RUN_LOG_DIR, f"{r['id']}.log")))
            return self.send(200, rows)
        if key == ("GET", "runs") and len(parts) == 3 and parts[2] == "log":
            if not RUN_ID.match(parts[1]):
                self.missing()
            try:
                with open(os.path.join(RUN_LOG_DIR, f"{parts[1]}.log"), encoding="utf-8", errors="replace") as f:
                    lines = f.read().splitlines()
            except OSError:
                raise Error(404, "That run's log is no longer kept")
            run = next((r for r in read_json(HISTORY_FILE, []) if r.get("id") == parts[1]), None)
            changes = read_json(os.path.join(RUN_LOG_DIR, f"{parts[1]}.changes.json"), [])
            return self.send(200, {"run": run, "lines": lines[-5000:], "changes": changes})
        if key == ("GET", "backups"):
            return self.backups((qs.get("job") or [""])[0], (qs.get("name") or [""])[0], (qs.get("id") or [""])[0])

        if key == ("GET", "config") and parts[1:] == ["download"]:
            return self.config_download()
        if key == ("POST", "config") and parts[1:] == ["restore"]:
            return self.config_restore()
        if key == ("POST", "setup") and len(parts) <= 2:
            return self.first_run(parts[1] if len(parts) == 2 else "finish", self.body())

        if key == ("GET", "settings"):
            return self.send(200, self.settings())
        if key == ("PUT", "settings"):
            return self.save_settings(self.body())
        if key == ("POST", "requests") and len(parts) == 2 and parts[1] in ("test", "status", "add"):
            return self.requests(parts[1], self.body())
        if key == ("POST", "notify") and len(parts) == 2 and parts[1] == "test":
            return self.notify_test(self.body())
        if key == ("PUT", "password"):
            return self.set_password(self.body())

        if (method == "GET" and len(parts) == 4 and parts[0] == "builder" and parts[1] in backend.JOBS
                and parts[2].isdigit() and parts[3] == "items"):
            try:   # reads MDBList and Trakt, so it doesn't wait on file edits
                return self.send(200, builder.list_items(
                    parts[1], int(parts[2]), read_env(),
                    lambda d: HUB.publish("progress", {"task": "list", "job": parts[1], "index": int(parts[2]), **d})))
            except builder.Invalid as e:
                return self.send(422, {"error": str(e), "problems": e.problems})
        if (method == "POST" and len(parts) == 4 and parts[0] == "builder" and parts[1] in backend.JOBS
                and parts[2].isdigit() and parts[3] == "export"):
            b, job, index = self.body(), parts[1], int(parts[2])
            try:   # reads the lists live first, outside the lock, like the list window
                data, films = builder.export_items(job, index, read_env())
            except builder.Invalid as e:
                return self.send(422, {"error": str(e), "problems": e.problems})
            out = self.builder_call(builder.export_list, job, index, data, films, bool(b.get("use_it")), read_env())
            if out is not None:
                HUB.publish("files", {})
                self.send(200, out)
            return
        if parts and parts[0] == "builder" and len(parts) in (2, 3) and parts[1] in backend.JOBS:
            return self.build(method, parts[1], parts[2] if len(parts) == 3 else None, qs)
        if key == ("GET", "watchlist") or key == ("PUT", "watchlist"):
            return self.watchlist(method, (qs.get("name") or [""])[0])
        if key == ("GET", "images"):
            if len(parts) == 2 and parts[1] == "file":
                p = builder.image_path((qs.get("name") or [""])[0]) or self.missing()
                with open(p, "rb") as f:
                    return self.send(200, f.read(), mimetypes.guess_type(p)[0] or "application/octet-stream",
                                     {"Cache-Control": "private, max-age=300"})
            out = self.builder_call(builder.images)
            return out is not None and self.send(200, {"images": out})
        if key == ("POST", "images") and len(parts) == 2 and parts[1] == "upload":
            # raw image bytes; a non-JSON, non-form type also forces a CORS preflight
            if self.headers.get("Content-Type", "").split(";")[0].strip() not in builder.UPLOAD_TYPES:
                raise Error(415, "Upload a JPEG, PNG or WebP image")
            n = self.length(1 << 40)
            if n > builder.UPLOAD_LIMIT:
                raise Error(413, "That image is over 30 MB")
            data = self.rfile.read(n)
            out = self.builder_call(builder.save_upload, (qs.get("name") or [""])[0], data)
            return out is not None and self.send(200, out)
        if key == ("POST", "images") and len(parts) == 2 and parts[1] == "delete":
            out = self.builder_call(builder.delete_images, self.body().get("names"))
            return out is not None and self.send(200, out)
        if key == ("GET", "import"):
            try:   # reads the server only, so it doesn't wait on file edits
                return self.send(200, builder.import_scan(
                    read_env(), lambda d: HUB.publish("progress", {"task": "scan", **d}),
                    (qs.get("server") or [""])[0] or None))
            except builder.Invalid as e:
                return self.send(422, {"error": str(e), "problems": e.problems})
        if key == ("POST", "import"):
            b = self.body()
            out = self.builder_call(builder.import_adopt, b.get("picks"), read_env(),
                                   lambda d: HUB.publish("progress", {"task": "import", **d}), b.get("server") or None)
            if out is not None:
                HUB.publish("files", {"job": "collections"})
                HUB.publish("files", {"job": "playlists"})
                HUB.publish("files", {"job": "genres"})
                self.send(200, out)
            return
        if key == ("GET", "search"):
            return self.search(qs)
        if key == ("GET", "genres"):
            try:   # reads the server only, so it doesn't wait on file edits
                return self.send(200, builder.server_genres(read_env()))
            except builder.Invalid as e:
                return self.send(422, {"error": str(e), "problems": e.problems})
        if key == ("GET", "users"):
            try:   # reads the servers only, so it doesn't wait on file edits
                return self.send(200, builder.server_users(read_env()))
            except builder.Invalid as e:
                return self.send(422, {"error": str(e), "problems": e.problems})
        if parts and parts[0] == "files" and len(parts) >= 2 and parts[1] in backend.JOBS:
            return self.files(method, parts[1], urllib.parse.unquote("/".join(parts[2:])))
        self.missing()

    def missing(self):
        raise Error(404, "Not found")

    # -- API bodies
    def status(self):
        tz = time_zone()
        today = datetime.date.today()
        env = read_env()
        jobs = []
        for name in backend.JOBS:
            st = JOBS[name].state()
            try:
                st["items"] = backend.items(name, today)
            except Exception as e:
                st["items"], st["items_error"] = [], str(e)
            st["enabled"] = name in backend.jobs_for_mode(backend.mode_from_env(env), env)
            jobs.append(st)
        return {"version": VERSION, "mode": backend.mode_from_env(env), "auth": auth_enabled(), "jobs": jobs,
                "servers": [{"id": x["id"], "name": x["name"], "type": x["type"]} for x in server_list(env)],
                "next_run": next_run(), "schedule": schedule_text(), "time_zone": tz,
                "requests": backend.requests_module().setup(env), "today": today.isoformat(),
                "setup": {"needed": needs_setup(env), "skipped": bool(web_settings().get("setup_skipped"))}}

    def events(self):
        q = HUB.subscribe()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")    # nginx: pass events on as they come
        self.security_headers()
        self.end_headers()
        self.close_connection = True
        try:
            self.wfile.write(b"retry: 3000\n\n")
            self.wfile.flush()
            while True:
                try:
                    msg = q.get(timeout=15)
                except queue.Empty:
                    msg = b": ping\n\n"
                self.wfile.write(msg)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            HUB.unsubscribe(q)

    def settings(self):
        env = read_env()
        fields = []
        for group, k, label, hint, secret, choices in backend.ENV_FIELDS:
            f = {"group": group, "key": k, "label": label, "hint": hint, "secret": secret,
                 "choices": list(choices) if choices else None}
            if secret:
                f["set"] = bool(env.get(k))
            else:
                f["value"] = env.get(k, "")
            if k == "TIME_ZONE":
                f["suggest"] = time_zones()
                f["placeholder"] = backend.settings_module().CONTAINER_TZ
            if k == "REMOVAL_LIMIT":
                f["placeholder"] = "50"
            fields.append(f)
        return {"fields": fields, "servers": self.server_forms(env), "server_fields": [
                    {"field": f, "label": label, "hint": hint, "secret": secret, "choices": list(choices) if choices else None}
                    for f, label, hint, secret, choices in backend.SERVER_FORM],
                "auth": auth_enabled(), "config_dir": backend.CONFIG_DIR}

    def server_forms(self, env):
        """Each server's settings for its card. Secrets only say whether they're set."""
        sm = backend.settings_module()
        out = []
        for x in sm.servers(env):
            values, saved = {}, {}
            for f, *_rest in backend.SERVER_FORM:
                v = env.get(sm.server_key(x["id"], f), "")
                if f in backend.SERVER_SECRETS:
                    saved[f] = bool(v)
                else:
                    values[f] = v
            out.append({"id": x["id"], "name": x["name"], "type": x["type"], "values": values, "set": saved})
        return out

    def server_changes(self, b, env):
        """staffpicked.env changes from the Servers cards: {"servers": [{id, values}], "removed": [id]}.
        A new card has no id and gets the next free number."""
        sm = backend.settings_module()
        fields = {f[0]: f for f in backend.SERVER_FORM}
        current = [x["id"] for x in sm.servers(env)]
        cards, removed = b.get("servers"), [str(r) for r in (b.get("removed_servers") or [])]
        if not isinstance(cards, list):
            raise Error(400, "servers must be a list")
        changes = {}
        for sid in removed:
            if sid not in current:
                raise Error(400, f"There's no server {sid}")
            for f in fields:   # server 1's lines stay, empty, as in the example file
                changes[sm.server_key(sid, f)] = "" if sid == "1" else None
        used = set(current) - set(removed)
        for card in cards:
            sid = str(card.get("id") or "")
            if not sid:   # the lowest free number
                sid = next(str(n) for n in range(1, 1000) if str(n) not in used)
                used.add(sid)
            elif sid not in current or sid in removed:
                raise Error(400, f"There's no server {sid}")
            for f, v in (card.get("values") or {}).items():
                if f not in fields:
                    raise Error(400, f"Unknown server setting {f}")
                if v is None:
                    continue
                v = str(v).strip()
                if "\n" in v or "\r" in v:
                    raise Error(400, f"{fields[f][1]} can't contain a line break")
                if fields[f][4] and v and v not in fields[f][4]:
                    raise Error(400, f"{fields[f][1]} must be one of: {', '.join(fields[f][4])}")
                if v or sm.server_key(sid, f) in env:   # no empty lines for settings never used
                    changes[sm.server_key(sid, f)] = v
        merged = {**env, **{k: v for k, v in changes.items() if v is not None}}
        for k in [k for k, v in changes.items() if v is None]:
            merged.pop(k, None)
        given = [(merged.get(sm.server_key(x["id"], "NAME")) or "").strip().lower() for x in sm.servers(merged)]
        names = [n for n in given if n]
        if len(names) != len(set(names)):
            raise Error(400, "Two servers have the same name; give each its own")
        return changes

    def save_settings(self, b):
        allowed = {f[1] for f in backend.ENV_FIELDS}
        changes = {}
        for k, v in (b.get("env") or {}).items():
            if k not in allowed:
                raise Error(400, f"Unknown setting {k}")
            v = "" if v is None else str(v).strip()
            if "\n" in v or "\r" in v:
                raise Error(400, f"{k} can't contain a line break")
            changes[k] = v
        sm = backend.settings_module()
        try:
            if "SYNC_TIME" in changes:
                changes["SYNC_TIME"] = ", ".join(sm.sync_times(changes["SYNC_TIME"]))
            sm.sync_every(changes.get("SYNC_EVERY"))
        except sm.ConfigError as e:
            raise Error(400, str(e))
        if changes.get("TIME_ZONE") and not backend.settings_module().valid_time_zone(changes["TIME_ZONE"]):
            raise Error(400, f"Unknown time zone {changes['TIME_ZONE']!r}; pick one from the list, like America/Chicago")
        if changes.get("REMOVAL_LIMIT"):
            changes["REMOVAL_LIMIT"] = changes["REMOVAL_LIMIT"].rstrip("%").strip()
            if not changes["REMOVAL_LIMIT"].isdigit() or int(changes["REMOVAL_LIMIT"]) > 100:
                raise Error(400, "Removal limit must be a percent from 0 to 100, or blank for 50")
        if changes.get("NOTIFY_ON") and changes["NOTIFY_ON"] not in ("failures", "always"):
            raise Error(400, "Notify me must be failures or always")
        if "URL_BASE" in changes:
            base = security.clean_base(changes["URL_BASE"])
            if base is None:
                raise Error(400, "URL base is a path like /staffpicked: letters, numbers, - _ . ~ and /")
            changes["URL_BASE"] = base
        if changes.get("TRUSTED_PROXIES"):
            nets, bad = security.parse_networks(changes["TRUSTED_PROXIES"])
            if bad:
                raise Error(400, f"Trusted proxies takes IP addresses and ranges like 172.16.0.0/12, not {', '.join(bad)}")
            changes["TRUSTED_PROXIES"] = ", ".join(str(n) if n.num_addresses > 1 else str(n.network_address) for n in nets)
        if "servers" in b:
            changes.update(self.server_changes(b, read_env()))
        if "mode" in b:
            if b["mode"] not in backend.MODES:
                raise Error(400, "Mode must be both, playlists or collections")
            changes.update(backend.env_for_mode(b["mode"]))
        with LOCK:
            if changes:
                write_env(changes)
        _status_cache.clear()
        _request_cache.clear()
        HUB.publish("settings", {})
        return self.send(200, self.settings())

    def requests(self, what, b):
        """test: check one service's settings (typed ones over the saved ones). status: whether each
        missing title is requested, available or missing in the chosen service. add: request one title."""
        rq = backend.requests_module()
        env = read_env()
        if what == "test":
            name = b.get("service")
            if name not in rq.CLIENTS:
                raise Error(400, "service must be seerr, radarr or sonarr")
            prefix = name.upper() + "_"
            env.update({k: str(v).strip() for k, v in (b.get("env") or {}).items()
                        if k.startswith(prefix) and v not in (None, "")})
        secrets_ = [env.get(f"{p}_API_KEY", "") for p in ("SEERR", "RADARR", "SONARR")]
        try:
            if what == "test":
                return self.send(200, rq.CLIENTS[name](env).status())
            if what == "status":
                items = b.get("items")
                if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
                    raise Error(400, "items must be [{imdb, show}]")
                # a title without a real IMDb ID can't be looked up; the rest still can
                items = [i for i in items if isinstance(i.get("imdb"), str) and IMDB.fullmatch(i["imdb"])]
                return self.send(200, request_states(rq, env, [(i["imdb"], bool(i.get("show"))) for i in items[:500]]))
            imdb = b.get("imdb")   # one title at a time: whole lists are never requested
            if not isinstance(imdb, str) or not IMDB.fullmatch(imdb):
                raise Error(400, "imdb must be one IMDb ID")
            out = rq.add(env, imdb, bool(b.get("show")))
            _request_cache.pop(imdb, None)
            return self.send(200, out)
        except rq.ServiceError as e:
            raise Error(400, str(e))
        except Error:
            raise
        except Exception as e:
            raise Error(502, f"Couldn't reach the request service: {mask(rq.describe(e), secrets_)}")

    def config_download(self):
        """The whole config folder as one zip (see backend.config_zip), sent as it's written."""
        import tempfile
        with tempfile.TemporaryFile() as tmp:
            with LOCK:
                backend.config_zip(tmp)
            size = tmp.tell()
            tmp.seek(0)
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.security_headers()
            self.send_header("Content-Disposition",
                             f'attachment; filename="staffpicked-config-{datetime.date.today():%Y-%m-%d}.zip"')
            self.end_headers()
            if self.command != "HEAD":
                while chunk := tmp.read(1 << 20):
                    self.wfile.write(chunk)

    def config_restore(self):
        """Put a config zip back (see backend.restore_zip). The zip type also forces a CORS
        preflight, so another site can't post one here."""
        import tempfile
        if self.headers.get("Content-Type", "").split(";")[0].strip() not in ("application/zip", "application/x-zip-compressed"):
            raise Error(415, "Upload a .zip from Download Config")
        n = self.length(1 << 40)
        if n > backend.MAX_RESTORE_BYTES:
            raise Error(413, "That file is too big")
        with tempfile.TemporaryFile() as tmp:
            left = n
            while left > 0:
                chunk = self.rfile.read(min(left, 1 << 20))
                if not chunk:
                    break
                tmp.write(chunk)
                left -= len(chunk)
            tmp.seek(0)
            if any(j.running for j in JOBS.values()):
                raise Error(409, "Wait for the running sync to finish first")
            try:
                with LOCK:
                    count, safety = backend.restore_zip(tmp)
            except backend.RestoreError as e:
                raise Error(400, str(e))
        _status_cache.clear()
        _request_cache.clear()
        HUB.publish("settings", {})
        for job in backend.JOBS:
            HUB.publish("files", {"job": job})
        return self.send(200, {"ok": True, "files": count, "saved": safety})

    def first_run(self, what, b):
        """The first-run setup screen. test: try a server's URL and key. skip: don't show the
        screen again. finish: save the server (and any list keys), set or skip a password, and
        start the first sync."""
        if what == "skip":
            with LOCK:
                s = web_settings()
                s["setup_skipped"] = True
                save_web_settings(s)
            return self.send(200, {"ok": True})
        server = b.get("server") or {}
        kind = str(server.get("type") or "emby").strip().lower()
        url, key = str(server.get("url") or "").strip().rstrip("/"), str(server.get("key") or "").strip()
        if kind not in ("emby", "jellyfin"):
            raise Error(400, "Server type must be emby or jellyfin")
        if not url or not key:
            raise Error(400, "Enter the server URL and API key")
        if any(c in v for v in (url, key) for c in "\r\n"):
            raise Error(400, "The URL and key can't contain line breaks")
        if not re.match(r"^https?://", url, re.I):
            raise Error(400, "The URL starts with http:// or https://, like http://192.168.1.10:8096")
        result = server_status({"id": "1", "name": "Server", "type": kind,
                                "env": {"SERVER_URL": url, "SERVER_API_KEY": key}}, force=True)
        if what == "test":
            return self.send(200, result)
        if what != "finish":
            self.missing()
        if not result["ok"]:
            raise Error(400, f"Couldn't connect: {result.get('error')}")
        password = str(b.get("password") or "")
        if password and len(password) < 8:
            raise Error(400, "Use at least 8 characters for the password")
        changes = {"SERVER_TYPE": kind, "SERVER_URL": url, "SERVER_API_KEY": key}
        for k in ("MDBLIST_API_KEY", "TRAKT_CLIENT_ID"):
            v = str((b.get("keys") or {}).get(k) or "").strip()
            if "\n" in v or "\r" in v:
                raise Error(400, f"{k} can't contain a line break")
            if v:
                changes[k] = v
        headers = {}
        with LOCK:
            write_env(changes)
            s = web_settings()
            s["setup_skipped"] = True
            if password and not auth_enabled():
                s["auth"] = security.hash_password(password)
                save_web_settings(s)
                SESSIONS.clear()
                headers["Set-Cookie"] = self.cookie(SESSIONS.new())
            else:
                save_web_settings(s)
        _status_cache.clear()
        names = backend.jobs_for_mode(mode(), read_env())
        # answered before anything is announced, so the browser has its sign-in cookie before
        # the events make it reload
        self.send(200, {"ok": True, "server": result, "auth": auth_enabled(), "started": names}, headers=headers)
        HUB.publish("settings", {})
        run_all("setup")

    def notify_test(self, b):
        """Send a test message to the URL typed in Settings, or the saved one."""
        url = str(b.get("url") or "").strip() or (read_env().get("NOTIFY_URL") or "").strip()
        if not url:
            raise Error(400, "Enter a webhook URL first")
        try:
            notify.send(url, "StaffPicked: test", "Notifications work. You'll hear from StaffPicked here.")
        except Exception as e:
            raise Error(502, f"The webhook didn't take it: {mask(str(e), [url])}")
        return self.send(200, {"ok": True})

    def login(self, b):
        """Password, then (with two-factor on) an authenticator or recovery code. Without a code,
        a right password answers {"mfa": true} so the page asks for one and sends both again."""
        ip = self.client_ip()
        LIMITER.check(ip)
        if not auth_enabled():
            return self.send(200, {"ok": True})
        if not check_password(str(b.get("password", ""))):
            LIMITER.fail(ip, "wrong password")
            raise Error(401, "Wrong password")
        if mfa_on():
            code = str(b.get("code") or "").strip()
            if not code:
                return self.send(401, {"error": "Enter the code from your authenticator app", "mfa": True})
            used = check_code(code)
            if not used:
                LIMITER.fail(ip, "wrong two-factor code")
                return self.send(401, {"error": "That code didn't work", "mfa": True})
            if used == "recovery":
                print(f"[auth] signed in with a recovery code from {ip}", file=sys.stderr, flush=True)
        LIMITER.clear(ip)
        return self.send(200, {"ok": True}, headers={"Set-Cookie": self.cookie(SESSIONS.new())})

    def confirm(self, b, code=True):
        """For changes to the sign-in itself: the current password, and with two-factor on, a code."""
        ip = self.client_ip()
        LIMITER.check(ip)
        if auth_enabled() and not check_password(str(b.get("current", ""))):
            LIMITER.fail(ip, "wrong current password")
            raise Error(403, "Current password is wrong")
        if code and mfa_on() and not check_code(b.get("code")):
            LIMITER.fail(ip, "wrong two-factor code")
            raise Error(403, "Enter a current code from your authenticator app (or a recovery code)")

    def set_password(self, b):
        new = str(b.get("new", ""))
        if new and len(new) < 8:
            raise Error(400, "Use at least 8 characters")
        self.confirm(b)
        hashed = security.hash_password(new) if new else {}
        with LOCK:
            s = web_settings()
            # no password means no two-factor either; a new password keeps it
            s["auth"] = {k: v for k, v in s["auth"].items() if k in ("totp", "recovery")} if new else {}
            s["auth"].update(hashed)
            s.pop("totp_pending", None)
            save_web_settings(s)
            SESSIONS.clear()
        headers = {}
        if new:  # keep the person who set it signed in
            headers["Set-Cookie"] = self.cookie(SESSIONS.new())
        return self.send(200, {"auth": bool(new), "mfa": mfa_on()}, headers=headers)

    def mfa(self, method, what, b):
        """Two-factor sign-in with an authenticator app.
        GET mfa: whether it's on and how many recovery codes are left.
        POST mfa/setup {current}: a new secret to scan (kept aside until it's confirmed).
        POST mfa/enable {code}: turn it on with a code from the app; answers the recovery codes.
        POST mfa/recovery {current, code}: new recovery codes (the old ones stop working).
        POST mfa/disable {current, code}: turn it off."""
        if method == "GET" and not what:
            auth = web_settings()["auth"]
            return self.send(200, {"enabled": mfa_on(auth), "recovery_left": len(auth.get("recovery") or []),
                                   "password": bool(auth.get("hash"))})
        if method != "POST":
            raise Error(405, "Method not allowed")
        if not auth_enabled():
            raise Error(400, "Set a password first; two-factor sign-in adds a code to it")
        if what == "setup":
            if mfa_on():
                raise Error(409, "Two-factor sign-in is already on")
            self.confirm(b, code=False)
            secret = security.new_totp_secret()
            with LOCK:
                s = web_settings()
                s["totp_pending"] = {"secret": secret, "until": time.time() + 900}
                save_web_settings(s)
            return self.send(200, {"secret": secret, "uri": security.totp_uri(secret)})
        if what == "enable":
            ip = self.client_ip()
            LIMITER.check(ip)
            pending = web_settings().get("totp_pending") or {}
            if not pending.get("secret") or pending.get("until", 0) < time.time():
                raise Error(400, "Start the setup again; that one ran out")
            step = security.totp_check(pending["secret"], b.get("code"))
            if step is None:
                LIMITER.fail(ip, "wrong code while turning on two-factor")
                raise Error(400, "That code didn't match. Check the app's clock and try the newest code.")
            with LOCK:
                s = web_settings()
                if (s.get("totp_pending") or {}).get("secret") != pending["secret"]:
                    raise Error(409, "The setup was started again somewhere else; use the newest one")
                codes, hashes = security.new_recovery_codes()
                s["auth"]["totp"] = {"secret": pending["secret"], "last_step": step}
                s["auth"]["recovery"] = hashes
                s.pop("totp_pending", None)
                save_web_settings(s)
                SESSIONS.clear()       # every other browser signs in again, with a code
            return self.send(200, {"enabled": True, "recovery_codes": codes},
                             headers={"Set-Cookie": self.cookie(SESSIONS.new())})
        if what == "recovery":
            if not mfa_on():
                raise Error(400, "Two-factor sign-in is off")
            self.confirm(b)
            codes, hashes = security.new_recovery_codes()
            with LOCK:
                s = web_settings()
                s["auth"]["recovery"] = hashes
                save_web_settings(s)
            return self.send(200, {"recovery_codes": codes})
        if what == "disable":
            if not mfa_on():
                return self.send(200, {"enabled": False})
            self.confirm(b)
            with LOCK:
                s = web_settings()
                s["auth"].pop("totp", None)
                s["auth"].pop("recovery", None)
                save_web_settings(s)
            return self.send(200, {"enabled": False})
        self.missing()

    # -- builder: collections and playlists as forms, watchlists as film lists
    def builder_call(self, fn, *args):
        try:
            with LOCK:
                return fn(*args)
        except builder.Invalid as e:
            self.send(422, {"error": str(e), "problems": e.problems, "warnings": e.warnings})
        except builder.Conflict as e:
            self.send(409, {"error": str(e)})
        return None

    def build(self, method, job, index, qs):
        if index is not None and not index.isdigit():
            self.missing()
        index = None if index is None else int(index)
        if method == "GET" and index is None:
            out = self.builder_call(builder.entries, job)
            return out is not None and self.send(200, out)
        if method in ("POST", "PUT") and (index is None) == (method == "POST"):
            b = self.body()
            out = self.builder_call(builder.save_entry, job, index, b.get("entry"), b.get("version"),
                                    read_env(), b.get("new_watchlist"))
        elif method == "DELETE" and index is not None and (qs.get("server") or [""])[0] == "1":
            # Remove it from the media server first (that needs the entry), then from the config.
            name = self.builder_call(builder.entry_name, job, index, (qs.get("version") or [""])[0])
            if name is None:
                return

            def done(st):
                if st == "ok":
                    with LOCK:
                        builder.delete_entry_named(job, name)
                    JOBS[job]._emit_line(f"deleted '{name}' from {backend.JOBS[job]['config']}")
                    HUB.publish("files", {"job": job})
                else:
                    JOBS[job]._emit_line(f"'{name}' is still in {backend.JOBS[job]['config']}, because removing it from the server didn't finish")
            try:
                JOBS[job].start("remove", False, name, on_done=done)
            except ValueError as e:
                raise Error(409, str(e))
            return self.send(200, {"pending": True, "name": name})
        elif method == "DELETE" and index is not None:
            out = self.builder_call(builder.delete_entry, job, index, (qs.get("version") or [""])[0])
        else:
            raise Error(405, "Method not allowed")
        if out is not None:
            HUB.publish("files", {"job": job})
            self.send(200, out)

    def watchlist(self, method, name):
        if method == "GET":
            try:
                out = self.builder_call(builder.read_watchlist, name)
            except FileNotFoundError:
                self.missing()
            return out is not None and self.send(200, out)
        b = self.body()
        out = self.builder_call(builder.save_watchlist, name, b.get("rows"), b.get("version"))
        if out is not None:
            HUB.publish("files", {"job": "playlists"})
            self.send(200, out)

    def search(self, qs):
        try:
            results = builder.search((qs.get("q") or [""])[0], (qs.get("type") or ["movie"])[0], read_env())
        except builder.Invalid as e:
            return self.send(422, {"error": str(e), "problems": e.problems})
        return self.send(200, {"results": results})

    def backups(self, job, name, version_id):
        """The saved copies of one config file, newest first; with an id, that copy's text."""
        if job not in backend.JOBS or not name:
            raise Error(400, "Which file?")
        p = backend.resolve_file(job, name, create=True)   # a deleted list file can still come back
        if not p:
            self.missing()
        rel = os.path.relpath(p, backend.CONFIG_DIR).replace(os.sep, "/")
        mod = backend.backups_module()
        if version_id:
            try:
                return self.send(200, {"id": version_id, "text": mod.read(backend.CONFIG_DIR, rel, version_id)})
            except (FileNotFoundError, UnicodeDecodeError):
                self.missing()
        return self.send(200, {"name": name, "versions": mod.versions(backend.CONFIG_DIR, rel)})

    def files(self, method, job, name):
        if not name:
            if method != "GET":
                raise Error(405, "Method not allowed")
            return self.send(200, {"files": [{"name": f["name"], "syntax": f["syntax"]} for f in backend.config_files(job)],
                                   "can_create": backend.new_file_allowed(job)})
        if method == "GET":
            if name == "_template":
                return self.send(200, {"text": backend.template_text(job)})
            p = backend.resolve_file(job, name) or self.missing()
            with open(p, encoding="utf-8") as f:
                return self.send(200, {"name": name, "text": f.read()})
        if method == "PUT":
            b = self.body()
            p = backend.resolve_file(job, name, create=bool(b.get("create")))
            if not p:
                raise Error(400, "That file name isn't allowed here (letters, numbers, spaces, . _ - and ending in .md)")
            if b.get("create") and os.path.exists(p):
                raise Error(409, f"{name} already exists")
            text = str(b.get("text", ""))
            problems = backend.validate(job, name, text)
            if problems:
                raise Error(422, "; ".join(problems))
            with LOCK:
                os.makedirs(os.path.dirname(p), exist_ok=True)
                backend.backups_module().keep(backend.CONFIG_DIR, p)
                tmp = p + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(text)
                os.replace(tmp, p)
            HUB.publish("files", {"job": job})
            return self.send(200, {"ok": True})
        if method == "DELETE":
            p = backend.resolve_file(job, name) or self.missing()
            if not backend.deletable(job, name):
                raise Error(400, "This file can't be deleted")
            with LOCK:
                backend.backups_module().keep(backend.CONFIG_DIR, p)   # so it can come back
                os.remove(p)
            HUB.publish("files", {"job": job})
            return self.send(200, {"ok": True})
        raise Error(405, "Method not allowed")


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def reset_login():
    """`staffpicked reset-login`: take off the UI's password and two-factor sign-in and sign every
    browser out, for when the password or the authenticator is lost."""
    s = web_settings()
    s["auth"] = {}
    s.pop("totp_pending", None)
    s["sessions"] = {}
    save_web_settings(s)
    print("The web UI's password and two-factor sign-in are off, and every browser is signed out.\n"
          "Until you set a new password in Settings, the UI only opens from your local network.")


def main():
    if sys.argv[1:] == ["reset-login"]:
        return reset_login()
    try:
        backend.seed_config()
        os.makedirs(LOG_DIR, exist_ok=True)
    except PermissionError as e:
        sys.exit(f"ERROR: StaffPicked can't write to {backend.CONFIG_DIR} ({e.strerror}: {e.filename}).\n"
                 f"It runs as user {os.getuid()}, group {os.getgid()}. In Docker, set PUID and PGID to the "
                 "owner of your config folder (see \"Permissions\" in the README), or make the folder "
                 "writable for that user.")
    time_zone()
    threading.Thread(target=scheduler, daemon=True).start()
    srv = Server(("", PORT), Handler)
    opts = options()
    print(f"StaffPicked UI v{VERSION} on http://0.0.0.0:{PORT}{opts['base']}/ (config: {backend.CONFIG_DIR})",
          flush=True)
    if not auth_enabled():
        print("No web UI password is set, so the UI only opens for browsers on your local network. "
              "Set one in Settings.", flush=True)
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        for job in JOBS.values():
            job.abort()


if __name__ == "__main__":
    main()
