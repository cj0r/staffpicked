"""Everything the web UI knows about StaffPicked, the generator package in staffpicked/.

The UI runs `python -m scripts sync|check|remove` on the config folder
(the /config volume in Docker), which holds:

  staffpicked.env    shared settings, API keys and the media servers
  collections.toml   one [[collection]] per collection
  playlists.toml     one [[playlist]] per playlist
  genres.toml        one [[genre]] per genre whose artwork StaffPicked sets
  collections/*.md   your own lists that collections use as sources
  playlists/*.md     your own ranked lists that playlists use as sources
  images/            posters, thumbs and backdrops the configs point at
  cache/             StaffPicked's state
  web/               the UI's own files (password hash, run history, logs)
"""
import glob, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
# The folder that holds the scripts package: the repo root, or /app in the image.
APP_ROOT = os.environ.get("APP_ROOT") or os.path.dirname(HERE)
PKG = "scripts"          # the StaffPicked package folder
APP = "staffpicked"      # name of the settings file (staffpicked.env)
# Example config to seed an empty config folder from: config/ in the repo, /app/defaults in the image.
DEFAULTS_DIR = os.environ.get("STAFFPICKED_DEFAULTS") or os.path.join(APP_ROOT, "config")


def _config_dir():
    # same choice as StaffPicked itself: $STAFFPICKED_CONFIG, else /config if it exists, else the repo's config/
    if os.environ.get("STAFFPICKED_CONFIG"):
        return os.environ["STAFFPICKED_CONFIG"]
    return "/config" if os.path.isdir("/config") else os.path.join(APP_ROOT, "config")


CONFIG_DIR = _config_dir()
ENV_FILE = os.path.join(CONFIG_DIR, f"{APP}.env")
# each job keeps its own list files in a folder named after it: collections/, playlists/
LIST_DIRS = {job: os.path.join(CONFIG_DIR, job) for job in ("collections", "playlists")}
TEMPLATE = "list-template.md"
WEB_DIR = os.path.join(CONFIG_DIR, "web")

if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

# Mode in the UI <-> StaffPicked's two switches. Genre artwork has its own (ENABLE_GENRES, in Settings).
MODES = ("both", "playlists", "collections")
FLAGS = {"collections": "ENABLE_COLLECTIONS", "playlists": "ENABLE_PLAYLISTS"}
JOB_FLAGS = {**FLAGS, "genres": "ENABLE_GENRES"}


def truthy(v):
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def mode_from_env(env):
    on = [job for job, key in FLAGS.items() if truthy(env.get(key, ""))]
    if not any(env.get(k) for k in FLAGS.values()) or len(on) == 2:
        return "both"   # StaffPicked runs both when neither switch is set
    return on[0] if on else "both"


def env_for_mode(mode):
    return {key: "true" if mode in ("both", job) else "false" for job, key in FLAGS.items()}


# Settings shown in the UI, in order. secret=True values never leave the server.
ENV_FIELDS = [
    # group, key, label, hint, secret, choices
    ("List Sources", "MDBLIST_API_KEY", "MDBList API key", "mdblist.com/preferences, under API Access. Your private lists work with it too.", True, None),
    ("List Sources", "TRAKT_CLIENT_ID", "Trakt client ID", "From an app at trakt.tv/oauth/applications. Enough for public lists.", True, None),
    ("List Sources", "TRAKT_ACCESS_TOKEN", "Trakt access token", "Only for private Trakt lists and watchlists.", True, None),
    ("Artwork Sources", "TMDB_API_TOKEN", "TMDB read access token", "themoviedb.org/settings/api: the long v4 'API Read Access Token'.", True, None),
    ("Artwork Sources", "FANARTTV_API_KEY", "fanart.tv API key", "fanart.tv/get-an-api-key", True, None),
    ("Artwork Sources", "MEDIUX_API_TOKEN", "MediUX API token", "Your own token from your MediUX account, for mediux: images by movie, collection or set.", True, None),
    ("Schedule", "SYNC_TIME", "Sync at", "Every day at these times, in the time zone below. Runs whatever the mode turns on.", False, None),
    ("Schedule", "SYNC_EVERY", "Sync every", "Counted from the last scheduled sync (or from start). At least 15 minutes.", False, None),
    ("Schedule", "TIME_ZONE", "Time zone", "Where you are, e.g. America/Chicago. Used for the sync time and for which lists are in season. Blank = the container's TZ.", False, None),
    ("Schedule", "SYNC_ON_START", "Sync on start", "Also sync once when the container starts.", False, ("true", "false")),
    ("Options", "ENABLE_GENRES", "Genre artwork", "Set the artwork in genres.toml on the server's genres, whatever the mode.", False, ("true", "false")),
    ("Notifications", "NOTIFY_URL", "Webhook URL", "Discord or Slack webhook, Gotify (…/message?token=…), ntfy topic, or any URL that takes a JSON post.", True, None),
    ("Notifications", "NOTIFY_ON", "Notify me", "After the startup and scheduled syncs. Runs you start yourself never notify.", False, ("failures", "always")),
    ("Requests", "REQUEST_SERVICE", "Request with", "Where a missing film or show goes when you press its Request button in a list window.", False, ("seerr", "arr")),
    ("Seerr", "SEERR_URL", "Seerr URL", "As you open it in a browser, e.g. http://192.168.1.10:5055. Overseerr and Jellyseerr work too.", False, None),
    ("Seerr", "SEERR_API_KEY", "Seerr API key", "Seerr > Settings > General > API Key. Requests go in as the admin, so they're approved straight away.", True, None),
    ("Radarr", "RADARR_URL", "Radarr URL", "For films. As you open it in a browser, e.g. http://192.168.1.10:7878.", False, None),
    ("Radarr", "RADARR_API_KEY", "Radarr API key", "Radarr > Settings > General > API Key.", True, None),
    ("Radarr", "RADARR_QUALITY_PROFILE", "Quality profile", "Picked from Radarr's profiles once it connects. Blank = Radarr's first one.", False, None),
    ("Radarr", "RADARR_ROOT_FOLDER", "Root folder", "Picked from Radarr's root folders once it connects. Blank = Radarr's first one.", False, None),
    ("Radarr", "RADARR_SEARCH", "Search when added", "Start looking for each film as soon as it's added.", False, ("true", "false")),
    ("Sonarr", "SONARR_URL", "Sonarr URL", "For TV shows. As you open it in a browser, e.g. http://192.168.1.10:8989.", False, None),
    ("Sonarr", "SONARR_API_KEY", "Sonarr API key", "Sonarr > Settings > General > API Key.", True, None),
    ("Sonarr", "SONARR_QUALITY_PROFILE", "Quality profile", "Picked from Sonarr's profiles once it connects. Blank = Sonarr's first one.", False, None),
    ("Sonarr", "SONARR_ROOT_FOLDER", "Root folder", "Picked from Sonarr's root folders once it connects. Blank = Sonarr's first one.", False, None),
    ("Sonarr", "SONARR_SEARCH", "Search when added", "Start looking for each show's episodes as soon as it's added.", False, ("true", "false")),
    ("Options", "REMOVAL_LIMIT", "Removal limit", "Hold back a sync that would take more than this percent of a list's films off the server, like a list that came back empty. 0 = never hold back. Blank = 50.", False, None),
    ("Options", "NEW_FILM_CHECK", "Check for new films", "How often to look for films just added to the server, and sync right away the lists that were missing them. Blank = every 15 minutes.", False, ("15m", "5m", "30m", "1h", "off")),
    ("Options", "DRY_RUN", "Dry run by default", "Preview only: scheduled runs change nothing on the server.", False, ("0", "1")),
    ("Reverse Proxy", "TRUSTED_PROXIES", "Trusted proxies", "IP addresses or ranges of your reverse proxy, e.g. 172.18.0.0/16. Only these may pass on the browser's address and https (X-Forwarded-For, X-Forwarded-Proto). Blank = none.", False, None),
    ("Reverse Proxy", "URL_BASE", "URL base", "When the proxy serves StaffPicked under a path, like https://example.com/staffpicked, that path: /staffpicked. Blank = at the root.", False, None),
]
SECRET_KEYS = {f[1] for f in ENV_FIELDS if f[4]}

# Each media server's settings, shown as one card per server in Settings. Server 1 keeps the
# plain keys (SERVER_URL...); others are numbered (SERVER_2_URL...). See settings.SERVER_FIELDS.
SERVER_FORM = [
    # field, label, hint, secret, choices
    ("NAME", "Name", "How StaffPicked calls it, and what a list's Servers setting picks. Blank = its type.", False, None),
    ("TYPE", "Server type", "Emby or Jellyfin.", False, ("emby", "jellyfin")),
    ("URL", "Server URL", "As you open it in a browser, e.g. http://192.168.1.10:8096", False, None),
    ("API_KEY", "API key", "Emby: Manage Emby Server > Advanced > API Keys. Jellyfin: Dashboard > API Keys.", True, None),
    ("USER", "Admin user", "Name or ID. It owns the shared playlists. Blank = the first admin.", False, None),
    ("PASSWORD", "Admin password", "Used only to share playlists (Emby and Jellyfin only accept sharing from the owner signed in) and, on Jellyfin, to reorder them. Blank if none.", True, None),
    ("WATCHED_BY", "Watched by", "Comma-separated users whose viewing drops a film from shared playlists. Blank = the admin user only.", False, None),
    ("PLAYLIST_USERS", "Per-person playlists", "Comma-separated users who each get a private copy hiding only what they watched.", False, None),
    ("LINKED_USERS", "Linked users", "Users who share watched status: 'a, b; c, d'.", False, None),
]
SERVER_SECRETS = {f[0] for f in SERVER_FORM if f[3]}


def settings_module():
    import importlib
    return importlib.import_module(f"{PKG}.settings")


def requests_module():
    import importlib
    return importlib.import_module(f"{PKG}.requests_to")


def arrivals_module():
    import importlib
    return importlib.import_module(f"{PKG}.arrivals")


def backups_module():
    import importlib
    return importlib.import_module(f"{PKG}.backups")


def secret_values(env):
    """Every secret in the settings, numbered servers' keys and passwords included, so logs can hide them."""
    sm = settings_module()
    out = [env.get(k, "") for k in SECRET_KEYS]
    for k, v in env.items():
        m = sm.NUMBERED.match(k)
        if (m and m[2] in SERVER_SECRETS) or k in ("SERVER_API_KEY", "SERVER_PASSWORD"):
            out.append(v)
    return out

JOBS = {
    # Order matters for "Run all": collections first, then playlists.
    "collections": {"label": "Collections", "description": "MDBList and Trakt lists to collections",
                    "config": "collections.toml", "kind": "collection"},
    "playlists": {"label": "Playlists", "description": "Your ranked lists, MDBList and Trakt lists to playlists",
                  "config": "playlists.toml", "kind": "playlist"},
    "genres": {"label": "Genres", "description": "Your artwork on the server's own genres",
               "config": "genres.toml", "kind": "genre"},
}
ACTIONS = ("sync", "check", "remove")


def installed():
    return os.path.isfile(os.path.join(APP_ROOT, PKG, "__main__.py"))


def jobs_for_mode(mode, env=None):
    """Jobs that run on schedule and from Run All: what the mode picks, and genres unless
    ENABLE_GENRES is false."""
    genres = truthy((env or {}).get("ENABLE_GENRES") or "true")
    picked = [j for j in FLAGS if mode in ("both", "", None) or mode == j]
    return picked + (["genres"] if genres else [])


def command(job, action, dry_run=False, only=None, server=None, allow_removals=False):
    cmd = [sys.executable, "-u", "-m", PKG, action, "--env", ENV_FILE, "--config", CONFIG_DIR]
    if dry_run and action != "check":
        cmd.append("--dry-run")
    if allow_removals and action == "sync":
        cmd.append("--allow-removals")
    if only:
        cmd += ["--only", only]
    if server:
        cmd += ["--server", server]
    return cmd


def job_env(job):
    """Extra environment for one job's process: StaffPicked reads these ahead of staffpicked.env,
    so a job runs only its own half whatever the mode says."""
    return {"PYTHONPATH": APP_ROOT, **{key: "true" if j == job else "false" for j, key in JOB_FLAGS.items()}}


# ---------------------------------------------------------------- config files

def config_files(job):
    """Editable files for a job: [{name, path, syntax}]. Names are relative to CONFIG_DIR."""
    files = [{"name": JOBS[job]["config"], "path": os.path.join(CONFIG_DIR, JOBS[job]["config"]), "syntax": "toml"}]
    lists = sorted(glob.glob(os.path.join(LIST_DIRS[job], "*.md"))) if job in LIST_DIRS else []   # genres have none
    for p in lists:
        files.append({"name": f"{job}/{os.path.basename(p)}", "path": p, "syntax": "markdown"})
    return files


def new_file_allowed(job):
    return job in LIST_DIRS


SAFE_NAME = re.compile(r"^(collections|playlists|watchlists)/[A-Za-z0-9][A-Za-z0-9 ._-]{0,100}\.md$")


def resolve_file(job, name, create=False):
    """Map a file name from the UI to a path, or None if it isn't one of the job's files."""
    for f in config_files(job):
        if f["name"] == name:
            return f["path"]
    if create and new_file_allowed(job) and SAFE_NAME.match(name) and ".." not in name:
        if name.startswith(job + "/"):
            return os.path.join(LIST_DIRS[job], name.split("/", 1)[1])
    return None


def deletable(job, name):
    return new_file_allowed(job) and name.startswith(job + "/")


def template_text(job):
    """Starting text for a new list file."""
    for p in (os.path.join(CONFIG_DIR, TEMPLATE), os.path.join(DEFAULTS_DIR, TEMPLATE)):
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                return f.read()
    return "# My List\n\n- tt0084787 | The Thing (1982)\n"


def validate(job, name, text):
    """Syntax check before saving. Returns a list of problems (empty = fine)."""
    if name.endswith(".toml"):
        import tomllib
        try:
            tomllib.loads(text)
        except tomllib.TOMLDecodeError as e:
            return [f"TOML: {e}"]
    return []


# ---------------------------------------------------------------- items for the dashboard

def last_sync(results, entry, servers):
    """What the last sync found for one entry, for its shelf row: the first of its servers that
    has a result (the one the list window describes too), plus whether any server had errors."""
    mine = results.get(entry.name.lower()) or {}
    rows = [(s, mine[s]) for s in servers if entry.on(s) and isinstance(mine.get(s), dict)]
    if not rows:
        return None
    server, first = rows[0]
    bad = [(s, r) for s, r in rows if r.get("errors")]
    out = {"server": server, "at": max(r.get("at", "") for _, r in rows), "errors": sum(r.get("errors", 0) for _, r in rows),
           "error": next((f"{s}: {r.get('error')}" if len(rows) > 1 else r.get("error") for s, r in bad if r.get("error")), ""),
           "warning": first.get("warning", ""), "held": any(r.get("held") for _, r in rows)}
    for k in ("listed", "in_library", "members", "added", "removed", "off_season"):
        if k in first:
            out[k] = first[k]
    return out


def poster_image(artwork, entry):
    """The poster as an image in the config folder the page can show (the file itself, or the
    copy the last sync saved of a URL or provider poster), or None."""
    import builder   # the web UI's own rules for which images it serves
    spec = (entry.poster or "").strip()
    if not spec:
        return None
    if artwork.is_remote(spec):
        stem = artwork.copy_name(entry.what, entry.name, "poster", 0)
        return next((f"images/{stem}{ext}" for ext in artwork.IMAGE_TYPES if builder.image_path(f"images/{stem}{ext}")), None)
    return spec if builder.image_path(spec) else None


def run_steps(job, only=None, server=None):
    """How many lists a run of this job works through: each entry once per server it goes to."""
    import importlib
    try:
        settings = importlib.import_module(f"{PKG}.settings")
        env = settings.load_env(ENV_FILE if os.path.isfile(ENV_FILE) else None)
        names = [s["name"] for s in settings.pick_servers(env, server)]
        cfg = settings.Config(JOBS[job]["kind"], os.path.join(CONFIG_DIR, JOBS[job]["config"]))
    except Exception:
        return 0
    return sum(1 for e in cfg.entries if not only or e.name.lower() == only.lower() for n in names if e.on(n))


def items(job, today):
    """What a job manages, for the dashboard: [{name, window, active, detail, file, poster, last}]."""
    import importlib   # imported late so a missing package only hides the list
    settings, util, artwork, results = (importlib.import_module(f"{PKG}.{m}")
                                        for m in ("settings", "util", "artwork", "results"))
    path = os.path.join(CONFIG_DIR, JOBS[job]["config"])
    if not os.path.isfile(path):
        return []
    cfg = settings.Config(JOBS[job]["kind"], path)
    found = results.load(CONFIG_DIR, JOBS[job]["kind"])
    try:
        servers = [s["name"] for s in settings.servers(settings.load_env(ENV_FILE if os.path.isfile(ENV_FILE) else None))]
    except Exception:
        servers = []
    out = []
    for e in cfg.entries:
        extra = {"poster": poster_image(artwork, e), "last": last_sync(found, e, servers)}
        if e.what == "genre":
            art = [w for w, v in (("poster", e.poster), ("thumb", e.thumb)) if v]
            if e.backdrops:
                art.append(f"{len(e.backdrops)} backdrop{'s' if len(e.backdrops) != 1 else ''}")
            out.append({"name": e.name or "(no name)", "window": "", "active": True, "kind": "genre",
                        "detail": ", ".join(art).capitalize() or "No artwork set", "file": JOBS[job]["config"],
                        "servers": e.servers, **extra})
            continue
        try:
            active = util.is_active(e.active, today)
        except util.ConfigError:
            active = None
        files = [s for s in e.sources if s.lower().endswith(".md") and "://" not in s]
        n = len(e.sources)
        out.append({"name": e.name or "(no name)", "window": e.active, "active": active,
                    "detail": f"{n} source{'s' if n != 1 else ''}", "servers": e.servers,
                    "file": files[0] if len(files) == 1 and n == 1 else JOBS[job]["config"], **extra})
    return out


def seed_config():
    """First start: create the data folder from StaffPicked's examples so the UI has something to edit."""
    import importlib, shutil
    importlib.import_module(f"{PKG}.settings").migrate_lists(CONFIG_DIR)   # old watchlists/ folder
    for d in (*LIST_DIRS.values(), WEB_DIR, os.path.join(CONFIG_DIR, "images"), os.path.join(CONFIG_DIR, "cache")):
        os.makedirs(d, exist_ok=True)
    if not os.path.exists(ENV_FILE):
        example = os.path.join(DEFAULTS_DIR, f"{APP}.env.example")
        if os.path.isfile(example):
            shutil.copyfile(example, ENV_FILE)
        else:
            with open(ENV_FILE, "w", encoding="utf-8") as f:
                f.write("ENABLE_COLLECTIONS=true\nENABLE_PLAYLISTS=true\nSERVER_TYPE=emby\n")
        os.chmod(ENV_FILE, 0o600)
    new = []
    for name, job in JOBS.items():
        dst = os.path.join(CONFIG_DIR, job["config"])
        src = os.path.join(DEFAULTS_DIR, job["config"] + ".example")
        if not os.path.exists(dst):
            new.append(name)
            if os.path.isfile(src):
                shutil.copyfile(src, dst)
            else:
                with open(dst, "w", encoding="utf-8") as f:
                    f.write("[settings]\n")
    # an example config points at its bundled example list, so bring that (and the template) along
    for job in (j for j in new if j in LIST_DIRS):
        src, dst = os.path.join(DEFAULTS_DIR, job, "example-list.md"), os.path.join(LIST_DIRS[job], "example-list.md")
        if os.path.isfile(src) and not os.path.exists(dst):
            shutil.copyfile(src, dst)
    template = os.path.join(DEFAULTS_DIR, TEMPLATE)
    if set(new) & set(LIST_DIRS) and not os.path.exists(os.path.join(CONFIG_DIR, TEMPLATE)) and os.path.isfile(template):
        shutil.copyfile(template, os.path.join(CONFIG_DIR, TEMPLATE))


# ---------------------------------------------------------------- the whole config as one zip

ZIP_SKIP = ("cache/", "backups/", "web/logs/")   # rebuilt or kept by StaffPicked itself
WEB_JSON = "web/web.json"


def zip_skipped(rel):
    return rel.startswith(ZIP_SKIP) or rel.endswith(".tmp") or "/__pycache__/" in f"/{rel}"


def config_zip(out):
    """Write the config folder to out as a zip: settings, configs, list files, images and the
    UI's own settings. Sign-ins aren't included, nor what StaffPicked rebuilds by itself."""
    import json, zipfile
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(CONFIG_DIR):
            dirs.sort()
            for name in sorted(files):
                full = os.path.join(root, name)
                rel = os.path.relpath(full, CONFIG_DIR).replace(os.sep, "/")
                if zip_skipped(rel) or os.path.islink(full):
                    continue
                if rel == WEB_JSON:
                    try:
                        with open(full, encoding="utf-8") as f:
                            data = json.load(f)
                    except (OSError, ValueError):
                        continue
                    data.pop("sessions", None)
                    z.writestr(rel, json.dumps(data, indent=2))
                    continue
                z.write(full, rel)


MAX_RESTORE_FILES = 20000
MAX_RESTORE_BYTES = 4 * 1024 ** 3


class RestoreError(ValueError):
    pass


def restore_zip(src):
    """Put a zip from config_zip back into the config folder. Files in the zip replace the ones
    there; files it doesn't have are left alone. The current config is saved first as
    backups/restores/<time>.zip. Returns (files restored, that safety copy's path)."""
    import datetime, json, shutil, zipfile
    try:
        z = zipfile.ZipFile(src)
    except zipfile.BadZipFile:
        raise RestoreError("That isn't a zip file")
    with z:
        infos = [i for i in z.infolist() if not i.is_dir()]
        names = {i.filename for i in infos}
        if f"{APP}.env" not in names:
            raise RestoreError(f"That zip has no {APP}.env, so it isn't a StaffPicked config download")
        if len(infos) > MAX_RESTORE_FILES or sum(i.file_size for i in infos) > MAX_RESTORE_BYTES:
            raise RestoreError("That zip is too big to be a StaffPicked config")
        root = os.path.realpath(CONFIG_DIR)
        picks = []
        for i in infos:
            rel = i.filename.replace("\\", "/")
            target = os.path.realpath(os.path.join(root, rel))
            if rel.startswith("/") or ".." in rel.split("/") or ":" in rel or not target.startswith(root + os.sep):
                raise RestoreError(f"That zip has a file outside the config folder ({i.filename})")
            if not zip_skipped(rel):
                picks.append((i, rel, target))
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        safety = os.path.join(CONFIG_DIR, "backups", "restores", f"before-restore-{stamp}.zip")
        os.makedirs(os.path.dirname(safety), exist_ok=True)
        with open(safety, "wb") as f:
            config_zip(f)
        for i, rel, target in picks:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if rel == WEB_JSON:   # keep whoever is signed in now signed in
                try:
                    data = json.loads(z.read(i))
                except ValueError:
                    continue
                if not isinstance(data, dict):
                    continue
                try:
                    with open(target, encoding="utf-8") as f:
                        data["sessions"] = json.load(f).get("sessions", {})
                except (OSError, ValueError, AttributeError):
                    data.pop("sessions", None)
                tmp = target + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                os.chmod(tmp, 0o600)
                os.replace(tmp, target)
                continue
            tmp = target + ".tmp"
            with z.open(i) as r, open(tmp, "wb") as w:
                shutil.copyfileobj(r, w)
            if rel == f"{APP}.env":
                os.chmod(tmp, 0o600)
            os.replace(tmp, target)
    return len(picks), os.path.relpath(safety, CONFIG_DIR).replace(os.sep, "/")
