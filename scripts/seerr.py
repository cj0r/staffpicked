"""Requesting films and shows through Seerr (or Overseerr or Jellyseerr, which share its API), one at a time.

Settings in staffpicked.env (REQUEST_SERVICE=seerr, the default):
  SEERR_URL       as you open it in a browser, e.g. http://192.168.1.10:5055
  SEERR_API_KEY   Seerr > Settings > General > API Key

Seerr sends each request on to the Radarr or Sonarr it's set up with, and requests made with
the API key count as the admin's, so they're approved straight away."""
import concurrent.futures, http.cookies, json, urllib.parse, urllib.request
from urllib.error import HTTPError
from .arr import AVAILABLE, MISSING, REQUESTED
from .util import USER_AGENT, ServiceError, describe, http_error, request

def message(e):
    """The message in a Seerr error reply ({"message": ...}), or the raw text."""
    try:
        text = e.read().decode("utf-8", "replace").strip()
    except Exception:
        return ""
    try:
        return str(json.loads(text).get("message") or text)
    except (ValueError, AttributeError):
        return text[:300]


# Seerr's media status: 2 pending, 3 processing, 4 partly available, 5 available (others: not there)
STATUS = {2: REQUESTED, 3: REQUESTED, 4: AVAILABLE, 5: AVAILABLE}


class Seerr:
    NAME = "Seerr"

    def __init__(self, env):
        self.url = (env.get("SEERR_URL") or "").strip().rstrip("/")
        self.key = (env.get("SEERR_API_KEY") or "").strip()
        if not self.url or not self.key:
            raise ServiceError("Set the Seerr URL and API key in Settings")

    def call(self, method, path, headers=None, **kw):
        try:
            return request(method, f"{self.url}/api/v1{path}", headers={"X-Api-Key": self.key, **(headers or {})},
                           timeout=30, **kw)
        except HTTPError as e:
            if e.code == 401:
                raise ServiceError("Seerr turned down the API key") from e
            if e.code == 403:   # a valid key Seerr won't let do this: say what Seerr said
                why = message(e)
                if "csrf" in why.lower() and method != "GET" and not headers:
                    return self.call(method, path, headers=self.csrf(), **kw)
                raise ServiceError(f"Seerr said no: {why}" if why else "Seerr turned down the API key") from e
            raise

    def csrf(self):
        """With CSRF Protection on (Seerr > Settings > Network), Seerr refuses any change that doesn't
        carry the token it hands out in cookies, API key or not. Fetch them and send them back."""
        req = urllib.request.Request(f"{self.url}/api/v1/status", headers={"X-Api-Key": self.key, "User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as r:
            jar = http.cookies.SimpleCookie()
            for line in r.headers.get_all("Set-Cookie") or []:
                jar.load(line)
        token = jar.get("XSRF-TOKEN")
        if not token:
            raise ServiceError("Seerr's CSRF Protection turned the request down and gave no token; "
                               "turn CSRF Protection off in Seerr > Settings > Network")
        return {"Cookie": "; ".join(f"{k}={m.value}" for k, m in jar.items()),
                "X-XSRF-TOKEN": urllib.parse.unquote(token.value)}

    def status(self):
        """{version, user} for Settings: which Seerr answered, and whose name requests go in."""
        info = self.call("GET", "/status") or {}
        me = self.call("GET", "/auth/me") or {}
        return {"version": info.get("version", ""),
                "user": me.get("displayName") or me.get("username") or me.get("plexUsername") or me.get("email") or ""}

    def lookup(self, imdb, show=None):
        """The film or show with this IMDb ID as Seerr knows it ({id, mediaType, mediaInfo...}), or None.
        Seerr finds IMDb IDs itself (through TMDB); a film or show sharing the ID goes by `show`."""
        query = urllib.parse.quote(f"imdb:{imdb}", safe="")
        found = (self.call("GET", f"/search?query={query}&page=1") or {}).get("results") or []
        found = [r for r in found if r.get("mediaType") in ("movie", "tv")]
        want = "tv" if show else "movie"
        return next((r for r in found if r["mediaType"] == want), found[0] if found else None)

    @staticmethod
    def state(found):
        info = (found or {}).get("mediaInfo") or {}
        return STATUS.get(info.get("status")) or STATUS.get(info.get("status4k")) or MISSING

    @staticmethod
    def name(found, imdb):
        title = found.get("title") or found.get("name") or imdb
        year = (found.get("releaseDate") or found.get("firstAirDate") or "")[:4]
        return f"{title} ({year})" if year else title

    def states(self, items):
        """{imdb: requested | available | missing} for [(imdb, show)], a few lookups at a time."""
        def one(pair):
            try:
                return pair[0], self.state(self.lookup(*pair))
            except ServiceError:
                raise
            except Exception:
                return pair[0], None   # unknown: the page keeps it as missing
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            return {imdb: st for imdb, st in pool.map(one, items) if st}

    def add(self, imdb, show=None):
        """Request one title Seerr doesn't have yet: {result: added | already | failed, name, state, error}."""
        try:
            found = self.lookup(imdb, show)
            if not found:
                return {"result": "failed", "name": imdb, "error": "Seerr couldn't find it"}
            name, state = self.name(found, imdb), self.state(found)
            if state != MISSING:
                return {"result": "already", "name": name, "state": state}
            body = {"mediaType": found["mediaType"], "mediaId": found["id"]}
            if found["mediaType"] == "tv":
                body["seasons"] = "all"
            self.call("POST", "/request", json_body=body)
            return {"result": "added", "name": name, "state": REQUESTED}
        except ServiceError:
            raise
        except HTTPError as e:
            text = http_error(e)
        except Exception as e:
            text = describe(e)
        if text.startswith("HTTP 409") or "already" in text.lower():
            return {"result": "already", "name": imdb, "state": REQUESTED}
        return {"result": "failed", "name": imdb, "error": text}
