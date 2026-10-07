"""Loading staffpicked.env and the two TOML configs, and checking them for mistakes."""
import datetime, os, re, time, tomllib, zoneinfo
from . import artwork, sources
from .util import ConfigError, parse_window, truthy

ENV_KEYS = ("SERVER_NAME", "SERVER_TYPE", "SERVER_URL", "SERVER_API_KEY", "SERVER_USER", "SERVER_PASSWORD",
            "ENABLE_COLLECTIONS", "ENABLE_PLAYLISTS", "ENABLE_GENRES", "WATCHED_BY", "PLAYLIST_USERS", "LINKED_USERS",
            "MDBLIST_API_KEY", "TRAKT_CLIENT_ID", "TRAKT_ACCESS_TOKEN", "TMDB_API_TOKEN",
            "FANARTTV_API_KEY", "MEDIUX_API_TOKEN", "DRY_RUN",
            "SYNC_TIME", "SYNC_EVERY", "SYNC_ON_START", "STAFFPICKED_CONFIG", "TZ", "TIME_ZONE", "NOTIFY_URL", "NOTIFY_ON",
            "REQUEST_SERVICE", "SEERR_URL", "SEERR_API_KEY",
            "RADARR_URL", "RADARR_API_KEY", "RADARR_QUALITY_PROFILE", "RADARR_ROOT_FOLDER", "RADARR_SEARCH",
            "SONARR_URL", "SONARR_API_KEY", "SONARR_QUALITY_PROFILE", "SONARR_ROOT_FOLDER", "SONARR_SEARCH",
            "REMOVAL_LIMIT", "NEW_FILM_CHECK", "TRUSTED_PROXIES", "URL_BASE")

# Media servers: server 1 uses the plain keys above; more servers use the same settings with a
# number, SERVER_2_URL, SERVER_2_API_KEY, SERVER_2_WATCHED_BY and so on.
SERVER_FIELDS = {"NAME": "SERVER_NAME", "TYPE": "SERVER_TYPE", "URL": "SERVER_URL", "API_KEY": "SERVER_API_KEY",
                 "USER": "SERVER_USER", "PASSWORD": "SERVER_PASSWORD", "WATCHED_BY": "WATCHED_BY",
                 "PLAYLIST_USERS": "PLAYLIST_USERS", "LINKED_USERS": "LINKED_USERS"}
NUMBERED = re.compile(r"^SERVER_([2-9]|[1-9]\d+)_(" + "|".join(SERVER_FIELDS) + r")$")
SERVER_NAMES = {"emby": "Emby", "jellyfin": "Jellyfin"}

COMMON = {"name", "source", "sources", "active", "poster", "backdrop", "backdrops", "servers"}
SHAPES = {
    "collection": (COMMON | {"description", "sort_name", "display_order"},
                   {"use_list_descriptions", "refresh_new_releases", "new_release_added_days",
                    "new_release_released_days"}),
    "playlist": (COMMON | {"include_watched", "watched_by", "share"},
                 {"include_watched", "share"}),
    # Genres already exist on the server: StaffPicked only sets their artwork.
    "genre": ({"name", "poster", "thumb", "backdrop", "backdrops", "servers"}, set()),
}
SHARE_MODES = ("view", "private")
# A collection's display order: the default order of its films on Emby and Jellyfin alike.
DISPLAY_ORDERS = {"release_date": "PremiereDate", "sort_name": "SortName"}


def load_env(path=None):
    """Settings from the environment, plus an env file (KEY=value lines; quotes, "export" and
    Windows line endings are fine) if given.
    Values set in the environment win, so Docker's --env-file works the same; empty ones don't."""
    env = {}
    if path:
        if not os.path.isfile(path):
            raise ConfigError(f"env file not found: {path}")
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k.startswith("export "):
                        k = k[7:].strip()
                    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                        v = v[1:-1]
                    env[k] = v
    env.update({k: v for k, v in os.environ.items()
                if (k in ENV_KEYS or k in env or NUMBERED.match(k)) and v != ""})
    return env


def valid_time_zone(name):
    """Whether name is a time zone this system knows, like America/Chicago."""
    if not name or name.startswith(("/", ".")) or ".." in name:
        return False
    try:
        zoneinfo.ZoneInfo(name)
        return True
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        return False


CONTAINER_TZ = os.environ.get("TZ") or "UTC"    # the container's own, used when TIME_ZONE is blank


def apply_time_zone(env):
    """Use TIME_ZONE (set in the web UI) for this process and what it starts, over the
    container's TZ. Returns the time zone in use."""
    name = (env.get("TIME_ZONE") or "").strip()
    if not valid_time_zone(name):
        name = CONTAINER_TZ
    if os.environ.get("TZ") != name:
        os.environ["TZ"] = name
        time.tzset()
    return name


CLOCK = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
EVERY = re.compile(r"^(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?$", re.I)
MIN_EVERY = 15                 # minutes; the shortest SYNC_EVERY
DEFAULT_TIME = "06:00"


def sync_times(value):
    """SYNC_TIME as sorted HH:MM times: one ("06:00") or several ("06:00, 18:00").
    Raises ConfigError naming the first one that isn't a time."""
    times = set()
    for part in re.split(r"[,\s]+", (value or "").strip()):
        if not part:
            continue
        m = CLOCK.match(part)
        if not m:
            raise ConfigError(f"Sync time {part!r} must be HH:MM (24-hour)")
        times.add(f"{int(m[1]):02d}:{m[2]}")
    return sorted(times)


def sync_every(value):
    """SYNC_EVERY in minutes ("6h", "90m", "1h30m"), or None when blank. Raises ConfigError."""
    value = (value or "").strip()
    if not value:
        return None
    m = EVERY.match(value)
    if not m or not (m[1] or m[2]):
        raise ConfigError(f"Sync every {value!r} must be hours and/or minutes, like 6h, 90m or 1h30m")
    minutes = int(m[1] or 0) * 60 + int(m[2] or 0)
    if minutes < MIN_EVERY:
        raise ConfigError(f"Sync every must be at least {MIN_EVERY} minutes")
    return minutes


def sync_schedule(env):
    """("every", minutes) when SYNC_EVERY is set, else ("times", [HH:MM, ...]). A bad setting
    falls back to the 06:00 default; the third value says what was wrong, else it's None."""
    try:
        minutes = sync_every(env.get("SYNC_EVERY"))
        if minutes:
            return "every", minutes, None
    except ConfigError as e:
        return "times", [DEFAULT_TIME], f"{e}; syncing daily at {DEFAULT_TIME}"
    try:
        return "times", sync_times(env.get("SYNC_TIME")) or [DEFAULT_TIME], None
    except ConfigError as e:
        return "times", [DEFAULT_TIME], f"{e}; syncing daily at {DEFAULT_TIME}"


def next_sync(env, now, last=None):
    """When the schedule syncs next after now. With SYNC_EVERY that's the interval after last
    (the previous scheduled or startup sync; now if there wasn't one), and never before now."""
    kind, value, _problem = sync_schedule(env)
    if kind == "every":
        return max((last or now) + datetime.timedelta(minutes=value), now)
    days = []
    for hhmm in value:
        hh, mm = (int(x) for x in hhmm.split(":"))
        at = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        days.append(at if at > now else at + datetime.timedelta(days=1))
    return min(days)


def describe_schedule(env):
    """The schedule in words: "Every 6 hours", "Daily at 06:00 and 18:00"."""
    kind, value, _problem = sync_schedule(env)
    if kind == "every":
        h, m = divmod(value, 60)
        parts = [f"{h} hour{'s' * (h != 1)}" if h else "", f"{m} minute{'s' * (m != 1)}" if m else ""]
        return "Every " + " ".join(p for p in parts if p)
    return "Daily at " + (", ".join(value[:-1]) + " and " + value[-1] if len(value) > 1 else value[0])


def server_key(sid, field):
    """The setting that holds one of a server's fields: SERVER_URL for server 1, SERVER_2_URL for server 2."""
    return SERVER_FIELDS[field] if str(sid) == "1" else f"SERVER_{sid}_{field}"


def server_ids(env):
    """The numbers of the configured servers, in order. Server 1 counts when it has a URL or key,
    or when nothing else is set up (so "SERVER_URL is not set" still shows)."""
    ids = {m[1] for k, v in env.items() if v and (m := NUMBERED.match(k)) and m[2] in ("URL", "API_KEY")}
    if any(env.get(SERVER_FIELDS[f]) for f in ("URL", "API_KEY")) or not ids:
        ids.add("1")
    return sorted(ids, key=int)


def servers(env):
    """Every configured media server: [{id, name, type, env}], where env is the settings with that
    server's own values in the plain keys (SERVER_URL, SERVER_USER, WATCHED_BY...), so everything
    that talks to one server reads it the same way. Names default to the server type, numbered
    when two would match ("Emby", "Emby 2")."""
    shared = {k: v for k, v in env.items() if k not in SERVER_FIELDS.values() and not NUMBERED.match(k)}
    out, taken = [], set()
    for sid in server_ids(env):
        sub = dict(shared)
        for field, plain in SERVER_FIELDS.items():
            value = env.get(server_key(sid, field), "")
            if value:
                sub[plain] = value
        kind = (sub.get("SERVER_TYPE") or "emby").strip().lower()
        base = (sub.get("SERVER_NAME") or "").strip() or SERVER_NAMES.get(kind, kind.title())
        name, n = base, 2
        while name.lower() in taken:
            name, n = f"{base} {n}", n + 1
        taken.add(name.lower())
        sub["SERVER_NAME"] = name
        out.append({"id": sid, "name": name, "type": kind, "env": sub})
    return out


def any_server_ready(env):
    """Whether some media server has a real URL and API key (the example's
    http://YOUR_SERVER:8096 doesn't count). Until one does, nothing is synced."""
    for s in servers(env):
        url, key = s["env"].get("SERVER_URL", ""), s["env"].get("SERVER_API_KEY", "")
        if url and key and "YOUR_SERVER" not in url.upper():
            return True
    return False


def pick_servers(env, want=None):
    """All servers, or just the one named (by name or number)."""
    found = servers(env)
    if not want:
        return found
    hits = [s for s in found if want.strip().lower() in (s["name"].lower(), s["id"])]
    if not hits:
        raise ConfigError(f"no server called {want!r}. Servers: {', '.join(s['name'] for s in found)}")
    return hits


def as_list(value):
    if value is None or value == "":
        return []
    return [str(v).strip() for v in (value if isinstance(value, list) else [value]) if str(v).strip()]


class Entry:
    """One collection or playlist from a config file, with the file's [settings] as defaults."""

    def __init__(self, what, raw, settings):
        self.what, self.raw = what, raw
        merged = {**settings, **raw}
        self.name = str(raw.get("name", "")).strip()
        self.sources = as_list(raw.get("sources", raw.get("source")))
        self.active = str(raw.get("active", "")).strip()
        self.poster = str(raw.get("poster", "")).strip()
        self.thumb = str(raw.get("thumb", "")).strip()
        self.backdrops = as_list(raw.get("backdrops", raw.get("backdrop")))
        self.description = str(raw.get("description", "")).strip()
        self.sort_name = str(raw.get("sort_name", "")).strip()
        self.display_order = str(raw.get("display_order", "")).strip().lower().replace(" ", "_").replace("-", "_")
        self.include_watched = truthy(merged.get("include_watched", False))
        self.share = str(merged.get("share", "view")).strip().lower()
        self.watched_by = ", ".join(as_list(raw.get("watched_by")))
        self.servers = as_list(raw.get("servers"))     # empty = every server

    def on(self, server_name):
        """Whether this entry goes to the server with this name."""
        return not self.servers or server_name.lower() in (s.lower() for s in self.servers)

    def server_problems(self, names):
        """Servers this entry names that aren't set up."""
        known = {n.lower() for n in names}
        return [f"no server called {s!r} (servers: {', '.join(names)})" for s in self.servers if s.lower() not in known]

    def problems(self, base_dir):
        out = []
        allowed = SHAPES[self.what][0]
        out += [f"unknown setting {k!r}" for k in self.raw if k not in allowed]
        if not self.name:
            out.append("no name")
        if not self.sources and self.what != "genre":
            out.append("no sources")
        for s in self.sources:
            try:
                sources.parse(s, base_dir)
            except ConfigError as e:
                out.append(str(e))
        try:
            parse_window(self.active)
        except ConfigError as e:
            out.append(str(e))
        if self.display_order and self.display_order not in DISPLAY_ORDERS:
            out.append(f"display_order must be one of: {', '.join(DISPLAY_ORDERS)}")
        if self.share not in SHARE_MODES:
            out.append(f"share must be one of: {', '.join(SHARE_MODES)}")
        for img in self.images():
            out += artwork.check(img, base_dir)
        return out

    def images(self):
        return [i for i in (self.poster, self.thumb) if i] + self.backdrops

    def env_problems(self, env):
        """API keys this entry's sources and images need that staffpicked.env doesn't have."""
        out = []
        for s in self.sources:
            try:
                kind, _ = sources.parse(s, "")
            except ConfigError:
                continue
            key = {"mdblist": "MDBLIST_API_KEY", "trakt": "TRAKT_CLIENT_ID"}.get(kind)
            if key and not env.get(key):
                out.append(f"{key} is needed for {s}")
        for img in self.images():
            key = {"tmdb": "TMDB_API_TOKEN", "fanart": "FANARTTV_API_KEY"}.get(img.split(":")[0].lower())
            if artwork.needs_mediux_token(img):
                key = "MEDIUX_API_TOKEN"
            if key and not env.get(key):
                out.append(f"{key} is needed for {img}")
        return out

    def warnings(self, base_dir):
        """Things that won't stop this entry syncing but will leave something out."""
        out = [f"image {i!r} not found; synced without it" for i in self.images() if artwork.missing_file(i, base_dir)]
        for s in self.sources:
            try:
                kind, where = sources.parse(s, base_dir)
            except ConfigError:
                continue
            if kind == "file" and os.path.isfile(where):
                out += [f"{os.path.basename(where)}: {i}" for i in sources.check_file(where)[1]]
            elif kind == "file":
                out.append(f"list file {s!r} not found")
        return out


LIST_DIRS = {"collection": "collections", "playlist": "playlists"}   # list files for each kind
TEMPLATE = "list-template.md"


def migrate_lists(config_dir):
    """Move list files out of the old shared watchlists/ folder: a file one config uses goes to
    collections/ or playlists/, and that config's path to it is updated; an unused list goes to
    playlists/. Files both configs use, or whose new name is taken, stay put. Nothing is deleted.
    Returns a line per change."""
    import re, shutil
    old = os.path.join(config_dir, "watchlists")
    if not os.path.isdir(old):
        return []
    files = {kind: os.path.join(config_dir, f"{folder}.toml") for kind, folder in LIST_DIRS.items()}
    texts = {}
    for kind, path in files.items():
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                texts[kind] = f.read()
    done, changed = [], set()
    for name in sorted(os.listdir(old)):
        src = os.path.join(old, name)
        if not os.path.isfile(src):
            continue
        if name == "watchlist-template.md":
            dst, kind = os.path.join(config_dir, TEMPLATE), None
        else:
            ref = re.compile(r"""(["'])watchlists/""" + re.escape(name) + r"""(["'])""")
            users = [k for k, t in texts.items() if ref.search(t)]
            if len(users) > 1 or (not users and not name.endswith(".md")):
                continue
            kind = users[0] if users else "playlist"
            dst = os.path.join(config_dir, LIST_DIRS[kind], name)
        if os.path.exists(dst):
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        rel = os.path.relpath(dst, config_dir).replace(os.sep, "/")
        if kind in texts and ref.search(texts[kind]):
            texts[kind] = ref.sub(lambda m: f"{m[1]}{rel}{m[2]}", texts[kind])
            changed.add(kind)
        done.append(f"moved watchlists/{name} to {rel}")
    for kind in changed:
        tmp = files[kind] + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(texts[kind])
        os.replace(tmp, files[kind])
        done.append(f"updated the paths in {os.path.basename(files[kind])}")
    if not os.listdir(old):
        os.rmdir(old)
    return done


def seed(config_dir):
    """Create collections.toml, playlists.toml and genres.toml from their .example copies when they're missing,
    looking in the config folder, then in $STAFFPICKED_DEFAULTS (the image's examples). A new
    example config brings its example list along, and the list template comes with either.
    Returns the names of the files created."""
    import shutil
    places = [config_dir] + ([os.environ["STAFFPICKED_DEFAULTS"]] if os.environ.get("STAFFPICKED_DEFAULTS") else [])
    made = []

    def copy(name):
        dst = os.path.join(config_dir, name)
        if os.path.exists(dst):
            return False
        for place in places:
            for src in (os.path.join(place, name + ".example"), os.path.join(place, name)):
                if src != dst and os.path.isfile(src):
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copyfile(src, dst)
                    made.append(name)
                    return True
        return False

    for kind, folder in LIST_DIRS.items():
        if copy(f"{folder}.toml"):      # the example config points at its example list
            copy(os.path.join(folder, "example-list.md"))
    if made:
        copy(TEMPLATE)
    copy("genres.toml")     # has no entries until you add some, so it changes nothing on its own
    return made


class Config:
    def __init__(self, what, path):
        self.what, self.path = what, path
        self.base_dir = os.path.dirname(os.path.abspath(path))   # the config folder; paths in configs start here
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except FileNotFoundError:
            raise ConfigError(f"{path} not found")
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"{path}: {e}")
        self.settings = data.pop("settings", {})
        self.entries = [Entry(what, raw, self.settings) for raw in data.pop(what, [])]
        self.unknown = [f"unknown section [{k}]" for k in data]
        self.unknown += [f"[settings] has unknown setting {k!r}" for k in self.settings if k not in SHAPES[what][1]]

    def get(self, key, default=None):
        return self.settings.get(key, default)

    def problems(self):
        """{entry name: [problems]}, with file-wide problems under ""."""
        out = {"": list(self.unknown)}
        names = [e.name.lower() for e in self.entries]
        for e in self.entries:
            issues = e.problems(self.base_dir)
            if e.name and names.count(e.name.lower()) > 1:
                issues.append(f"another {self.what} is also named {e.name!r}")
            out[e.name or "(no name)"] = issues
        return out
