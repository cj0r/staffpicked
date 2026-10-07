"""Films and shows just added to a media server, so the lists that were missing them can sync
straight away instead of waiting for the next scheduled sync.

The web UI asks every NEW_FILM_CHECK (default 15 minutes; "off" turns it off) for the newest
items on each server. Anything it hasn't seen before, with an IMDb ID, is looked up in the
last sync's results: each collection or playlist that listed it as missing syncs again.
Nothing is set up on the media server, so it works the same on Emby and Jellyfin."""
import datetime, re
from . import results, settings
from .server import connect

DEFAULT = 15
EVERY = re.compile(r"^(?:(\d+)\s*h)?\s*(?:(\d+)\s*m?)?$", re.I)
RECENT = 50                     # newest items read per check
SETTLE = datetime.timedelta(hours=1)   # an item still without an IMDb ID after this is ignored


def minutes(env):
    """How often to check, in minutes; 0 when it's off."""
    raw = str(env.get("NEW_FILM_CHECK") or "").strip().lower()
    if not raw:
        return DEFAULT
    if raw in ("off", "0", "false", "no", "never"):
        return 0
    m = EVERY.match(raw)
    if not m or not (m[1] or m[2]):
        return DEFAULT
    return max(5, int(m[1] or 0) * 60 + int(m[2] or 0))


def imdb_of(item):
    for k, v in (item.get("ProviderIds") or {}).items():
        if k.lower() == "imdb" and v:
            return str(v).lower()
    return None


def _created(item):
    try:
        return datetime.datetime.fromisoformat(str(item.get("DateCreated", "")).replace("Z", "+00:00")[:32])
    except ValueError:
        return None


class Watch:
    """Remembers what each server held at the last check. The first check only takes note."""

    def __init__(self):
        self.seen = {}     # server URL -> item ids already accounted for

    def poll(self, env, connect_=connect):
        """{imdb id: title} of the items new on any server since the last check."""
        found, now = {}, datetime.datetime.now(datetime.timezone.utc)
        for s in settings.servers(env):
            senv = s["env"]
            if not senv.get("SERVER_URL") or not senv.get("SERVER_API_KEY"):
                continue
            server = connect_(senv, s["id"])
            uid = server.user(senv.get("SERVER_USER"))["Id"]
            items = server.recent(uid, RECENT)
            first = server.url not in self.seen
            seen = self.seen.setdefault(server.url, set())
            for it in items:
                if it["Id"] in seen:
                    continue
                imdb, made = imdb_of(it), _created(it)
                if not imdb and made and now - made < SETTLE:
                    continue        # its metadata may not be in yet; look again next time
                seen.add(it["Id"])
                if imdb and not first:
                    found[imdb] = it.get("Name") or imdb
            if len(seen) > RECENT * 20:      # only the newest matter
                self.seen[server.url] = {it["Id"] for it in items}
        return found


def wanting(base_dir, imdbs):
    """{kind: [entry names]} of the collections and playlists whose last sync was missing any
    of these IMDb IDs."""
    want, out = {i.lower() for i in imdbs}, {}
    for kind in ("collection", "playlist"):
        for per_server in results.load(base_dir, kind).values():
            rows = [r for r in per_server.values() if isinstance(r, dict)] if isinstance(per_server, dict) else []
            if any(want & {(m.get("imdb") or "").lower() for m in r.get("missing") or []} for r in rows):
                name = next((r.get("name") for r in rows if r.get("name")), None)
                if name:
                    out.setdefault(kind, []).append(name)
    return out
