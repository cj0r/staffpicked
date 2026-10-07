"""StaffPicked: Emby and Jellyfin collections and playlists from MDBList, Trakt and your own
lists, and your own artwork on the servers' genres, on one media server or several.

  python -m scripts schedule build everything now (SYNC_ON_START) and then at each
                                 SYNC_TIME, or every SYNC_EVERY; what the Docker container runs
  python -m scripts sync     build or update everything that's turned on in staffpicked.env, once
  python -m scripts check    validate staffpicked.env, the configs and list files (no server needed)
  python -m scripts remove   delete every configured collection and playlist now, and take
                                 StaffPicked's artwork off the configured genres
  python -m scripts import   list the server's own collections and playlists, and genres with
                                 artwork, and whether StaffPicked already manages them; with
                                 --adopt, bring them in

Everything lives in one config folder: staffpicked.env, collections.toml,
playlists.toml, genres.toml, collections/ and playlists/ (your list files), images/ and cache/. In Docker that's the /config volume.

Options:
  --config DIR      the config folder (default: $STAFFPICKED_CONFIG, else /config if it
                    exists, else config/ next to the scripts folder)
  --env FILE        settings file (default: staffpicked.env in the config folder)
  --only NAME       just this collection, playlist or genre
  --server NAME     just this media server (its name, or its number in staffpicked.env);
                    without it, every server gets everything meant for it
  --dry-run         show what would change without changing anything (or DRY_RUN=1)
  --date YYYY-MM-DD pretend it's this date, to test active windows
  --allow-removals  let this run take most of a list off the server; without it, a sync that
                    would remove more than REMOVAL_LIMIT percent of a list is held back
  --adopt NAME      with import: import this collection or playlist into StaffPicked, link it
                    if a StaffPicked entry has nearly the same name, or switch a fixed copy
                    from an earlier import to the list it was found to come from. Repeat for more; write
                    collection:NAME, playlist:NAME or genre:NAME for just one kind; "all" adopts everything
                    StaffPicked doesn't manage yet. Only the config folder is written.
"""
import argparse, copy, datetime, os, sys, time
from . import __version__, settings
from .artwork import Artwork
from .collection_sync import CollectionSync
from .genre_sync import GenreSync
from .importer import Importer
from .playlist_sync import PlaylistSync
from . import renames
from .results import Results
from .server import connect
from .sources import Sources
from .state import State
from .util import Brake, ConfigError, Log, describe, is_active, truthy

REPO_CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
KINDS = (("collection", "ENABLE_COLLECTIONS", "collections.toml"), ("playlist", "ENABLE_PLAYLISTS", "playlists.toml"),
         ("genre", "ENABLE_GENRES", "genres.toml"))


def enabled(env):
    """What staffpicked.env turns on: collections and playlists (both, if neither is set),
    and genre artwork (on unless ENABLE_GENRES is false)."""
    flags = {what: env.get(key) for what, key, _ in KINDS[:2]}
    if all(v in (None, "") for v in flags.values()):
        on = list(flags)
    else:
        on = [what for what, v in flags.items() if truthy(v)]
    if truthy(env.get("ENABLE_GENRES") or "true"):
        on.append("genre")
    return on


def load(args, env):
    configs = {}
    for what, _, filename in KINDS:
        path = os.path.join(args.config, filename)
        if what == "genre" and not os.path.isfile(path):
            continue      # genre artwork is optional; seed() creates the file on the next start
        if what in enabled(env):
            configs[what] = settings.Config(what, path)
    return configs


def check(args, env, today):
    problems = 0
    on = enabled(env)
    names = {"collection": "collections", "playlist": "playlists", "genre": "genre artwork"}
    print(f"staffpicked {__version__}: {', '.join(names[w] for w in on) or 'nothing'} turned on in staffpicked.env")
    if not on:
        print("PROBLEM: set ENABLE_COLLECTIONS, ENABLE_PLAYLISTS or ENABLE_GENRES to true")
        problems += 1
    found = settings.servers(env)
    names = [x["name"] for x in found]
    print(f"{len(found)} media server(s): {', '.join(names)}")
    for x in found:
        for field in ("URL", "API_KEY"):
            if not x["env"].get(settings.SERVER_FIELDS[field]):
                print(f"PROBLEM: {settings.server_key(x['id'], field)} is not set ({x['name']})")
                problems += 1
        if x["type"] not in ("emby", "jellyfin"):
            print(f"PROBLEM: {settings.server_key(x['id'], 'TYPE')} must be emby or jellyfin ({x['name']})")
            problems += 1
    problem = settings.sync_schedule(env)[2]
    print(f"Schedule: {settings.describe_schedule(env).lower()}")
    if problem:
        print(f"PROBLEM: {problem}")
        problems += 1
    for what, cfg in load(args, env).items():
        print(f"\n{os.path.basename(cfg.path)}")
        for name, issues in cfg.problems().items():
            entry = next((e for e in cfg.entries if e.name == name), None)
            if entry:
                warnings = entry.warnings(cfg.base_dir)
                issues = issues + entry.env_problems(env)
                warnings = warnings + entry.server_problems(names)
                state = "not valid" if issues else ("active today" if is_active(entry.active, today) else "inactive today")
                if what == "genre":
                    print(f"  {name}: {len(entry.images())} image(s)" + (", not valid" if issues else ""))
                else:
                    print(f"  {name}: {len(entry.sources)} source(s), {state}"
                          + (f", on {', '.join(entry.servers)} only" if entry.servers and len(names) > 1 else ""))
                for w in warnings:
                    print(f"    WARNING: {w}")
            for i in issues:
                print(f"    PROBLEM: {i}" if entry else f"  PROBLEM: {i}")
            problems += len(issues)
    print("\nOK" if not problems else f"\n{problems} problem(s) found")
    return problems


def run(args, env, today):
    log = Log(dry_run=args.dry_run)
    configs = load(args, env)
    # what each list found, for the web UI; a remove isn't a sync, so it records nothing
    results = Results(os.path.abspath(args.config), dry_run=args.dry_run or args.action != "sync")
    names = [s["name"] for s in settings.servers(env)]
    everything = {what: list(cfg.entries) for what, cfg in configs.items()}   # invalid ones too
    for what, cfg in configs.items():
        # an entry with a mistake is skipped (and counted as an error); the rest still run
        bad = {n: p for n, p in cfg.problems().items() if p}
        for e in cfg.entries:   # a server that's gone doesn't stop the entry going to the others
            for w in e.server_problems(names):
                log(f"[{what}] {e.name}")
                log.warn(f"{w}; it goes to the rest of its servers")
        for name, issues in bad.items():
            log(f"[{what}] {name or os.path.basename(cfg.path)}")
            log.error("skipped: " + "; ".join(issues) + " (python -m scripts check lists every problem)")
            entry = next((e for e in cfg.entries if e.name == name), None)
            if entry and name and (not args.only or name.lower() == args.only.lower()):
                for server_name in (n for n in names if entry.on(n)):
                    results.error(what, name, server_name, "Not synced: " + "; ".join(issues))
        cfg.entries = [e for e in cfg.entries if e.name not in bad]
    if not any(cfg.entries for cfg in configs.values()):
        results.save()
        print("Nothing to do: no collections, playlists or genres are configured." if not log.problems else "")
        log.summary()
        return log.problems
    targets = settings.pick_servers(env, args.server)
    base = os.path.abspath(args.config)     # paths in configs start here
    state = State(os.path.join(base, "cache", "state.json"), args.dry_run)
    src, art = Sources(env, base), Artwork(env, base)     # shared, so each list is read once
    records = renames.load(base)
    renamed = {what: renames.pending(records, what, [e.name for e in everything[what]])
               for what in ("collection", "playlist") if what in configs}
    outcome, done = [], {}
    for s in targets:
        if len(names) > 1:
            log(f"\n===== {s['name']} =====")
        before = log.problems
        try:
            done[s["env"].get("SERVER_URL")] = sync_server(args, s, configs, src, art, state, log, today, renamed,
                                                           results)
        except Exception as e:      # one server down doesn't stop the others
            message = str(e) if isinstance(e, ConfigError) else f"{s['name']}: {describe(e)}"
            log.error(message)
            for what, cfg in configs.items():   # every list meant for it missed this sync
                for entry in cfg.entries:
                    if entry.on(s["name"]) and (not args.only or entry.name.lower() == args.only.lower()):
                        results.error(what, entry.name, s["name"], message)
        outcome.append((s["name"], log.problems - before))
        state.save()
        results.save()
    if records and not args.dry_run:
        renames.finish(base, everything, settings.servers(env), done)
    print()
    for name, errors in outcome:    # read by the web UI for each server's result
        print(f"[server] {name}: " + (f"{errors} error(s)" if errors else "ok"))
    log.summary()
    print(f"\nDone, with {log.problems} error(s)." if log.problems else "\nDone.")
    return log.problems


def sync_server(args, s, configs, src, art, state, log, today, renamed=None, results=None):
    """Sync (or remove) the entries that go to one server. renamed is {kind: {new name:
    [old names]}}: their old copies come off this server too. Returns {kind: lower-cased names
    of the entries it handled, less any whose old copy couldn't be removed}."""
    renamed = renamed or {}
    mine = {}
    for what, cfg in configs.items():
        part = copy.copy(cfg)
        part.entries = [e for e in cfg.entries if e.on(s["name"])]
        if part.entries:
            mine[what] = part
    if not mine:
        log("  nothing here goes to this server")
        return {}
    env = s["env"]
    server = connect(env, s["id"])
    remove_all = args.action == "remove"
    failed = {}
    if "collection" in mine:
        admin = server.user(env.get("SERVER_USER"))
        sync = CollectionSync(server, admin["Id"], mine["collection"], src, art, state, log, results)
        sync.brake = Brake(env, args.allow_removals)
        sync.run(today, args.only, remove_all, renamed.get("collection"))
        failed["collection"] = sync.rename_failed
    if "playlist" in mine:
        sync = PlaylistSync(server, env, mine["playlist"], src, art, state, log, results)
        sync.brake = Brake(env, args.allow_removals)
        sync.run(today, args.only, remove_all, renamed.get("playlist"))
        failed["playlist"] = sync.rename_failed
    if "genre" in mine:
        admin = server.user(env.get("SERVER_USER"))
        GenreSync(server, admin["Id"], mine["genre"], art, state, log, results).run(args.only, remove_all)
    return {what: {e.name.lower() for e in cfg.entries if not args.only or e.name.lower() == args.only.lower()}
            - failed.get(what, set()) for what, cfg in mine.items()}


STATUS = {"managed": "managed by StaffPicked", "similar": "similar to StaffPicked's",
          "new": "not in StaffPicked", "duplicate": "another copy of"}


def import_(args, env):
    """Show what's on each server and, with --adopt, import or link the chosen ones."""
    failed = 0
    targets = settings.pick_servers(env, args.server)
    for s in targets:
        if len(targets) > 1:
            print(f"\n===== {s['name']} =====")
        try:
            failed += import_from(args, s)
        except ConfigError as e:
            print(f"ERROR: {s['name']}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {s['name']}: {describe(e)}")
            failed += 1
    return failed


def import_from(args, s):
    imp = Importer(connect(s["env"], s["id"]), s["env"], os.path.abspath(args.config))
    scan = imp.scan()
    for kind, rows in scan.items():
        print(f"\n{kind.capitalize()}s {'with artwork ' if kind == 'genre' else ''}on the server ({len(rows)}):")
        for r in rows:
            count = f", {r['count']} items" if r["count"] is not None else ""
            if r.get("art"):
                count = f", has {', '.join(r['art'])}"
            match = f" '{r['entry']}'" if r["entry"] and r["status"] != "managed" else ""
            print(f"  {r['name']}{count}: {STATUS[r['status']]}{match}")
            if r["source"]:
                verb = "can switch to" if r["action"] == "source" else "imports as"
                print(f"      {verb} {' + '.join(r['source']['sources'])} ({r['source']['how']})")
            elif r["action"] == "import" and kind == "collection":
                print("      no list found; imports as a fixed list"
                      + (" (set MDBLIST_API_KEY to look for it on MDBList)" if r.get("no_key") else ""))
    if not args.adopt:
        print("\nNothing changed. Add --adopt NAME (or --adopt all) to bring one in.")
        return 0
    picks = []
    for want in args.adopt:
        kind, _, name = want.partition(":") if want.split(":")[0] in scan else ("", "", want)
        hits = [r for k, rows in scan.items() if kind in ("", k) for r in rows
                if r["action"] and (name.lower() == "all" or r["name"].lower() == name.lower())]
        if not hits:
            print(f"\nNothing to adopt for {want!r}: no such name, or StaffPicked already manages it.")
        picks += [{"kind": r["kind"], "id": r["id"], "action": r["action"]} for r in hits]
    print()
    results = imp.adopt(picks, dry_run=args.dry_run)
    for line in results:
        print(line)
    return sum(line.startswith("Failed") for line in results)


def default_config():
    if os.environ.get("STAFFPICKED_CONFIG"):
        return os.environ["STAFFPICKED_CONFIG"]
    return "/config" if os.path.isdir("/config") else REPO_CONFIG


def schedule(args):
    """Sync on the schedule: at each SYNC_TIME, or every SYNC_EVERY when that's set (in
    TIME_ZONE, else the container's TZ), and once at start unless SYNC_ON_START=false.
    Settings and configs are re-read before every run, so edits take effect without a
    restart. Errors are logged and the schedule carries on."""
    first, last = True, None
    while True:
        env = {}
        try:
            env = settings.load_env(args.env)
            settings.apply_time_zone(env)
            problem = settings.sync_schedule(env)[2]
            if problem:
                print(f"ERROR: {problem}", flush=True)
            if not settings.any_server_ready(env):
                print("No media server is set up yet, so nothing syncs. Set SERVER_URL and SERVER_API_KEY "
                      "(or use the web UI's setup screen).", flush=True)
            elif not first or truthy(env.get("SYNC_ON_START", "true")):
                last = datetime.datetime.now().astimezone()
                print(f"\n===== StaffPicked sync {last:%Y-%m-%d %H:%M} =====", flush=True)
                args.dry_run = truthy(env.get("DRY_RUN", ""))
                run(args, env, datetime.date.today())
        except Exception as e:
            print(f"ERROR: {e if isinstance(e, ConfigError) else describe(e)}", flush=True)
        now = datetime.datetime.now().astimezone()
        if first and last is None:
            last = now      # an interval counts from start when there's no startup sync
        first = False
        when = settings.next_sync(env, now, last)
        wait = (when - now).total_seconds()
        print(f"Next sync at {when:%Y-%m-%d %H:%M} ({wait / 3600:.1f} hours from now; "
              f"{settings.describe_schedule(env).lower()}).", flush=True)
        time.sleep(wait)


def main():
    p = argparse.ArgumentParser(prog="staffpicked", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"staffpicked {__version__}")
    p.add_argument("action", choices=["schedule", "sync", "check", "remove", "import"])
    p.add_argument("--config", default=default_config())
    p.add_argument("--env")
    p.add_argument("--only")
    p.add_argument("--server")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--date")
    p.add_argument("--adopt", action="append", default=[])
    p.add_argument("--allow-removals", action="store_true")
    args = p.parse_args()
    if not args.env:
        candidate = os.path.join(args.config, "staffpicked.env")
        args.env = candidate if os.path.isfile(candidate) else None
    for line in settings.migrate_lists(args.config):
        print(line)
    if args.action != "remove":
        for name in settings.seed(args.config):
            print(f"created {name} from the example; edit it to make it your own")
    if args.action == "schedule":
        schedule(args)
    try:
        env = settings.load_env(args.env)
        settings.apply_time_zone(env)
        args.dry_run = args.dry_run or truthy(env.get("DRY_RUN", ""))
        today = datetime.date.fromisoformat(args.date) if args.date else datetime.date.today()
        if args.action == "check":
            failed = check(args, env, today)
        elif args.action == "import":
            failed = import_(args, env)
        else:
            failed = run(args, env, today)
    except ConfigError as e:
        sys.exit(f"ERROR: {e}")
    except Exception as e:
        sys.exit(f"ERROR: {describe(e)}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
