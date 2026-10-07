"""Small stand-ins for Radarr and Sonarr (v3 API) and Seerr (v1 API): enough to look titles up,
list what they have, and add or request them."""
import json, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

API_KEY = "radarr-key"
SONARR_KEY = "sonarr-key"
SEERR_KEY = "seerr-key"
KNOWN = {"tt0084787": {"title": "The Thing", "year": 1982, "tmdbId": 1091, "titleSlug": "the-thing-1091"},
         "tt0080749": {"title": "The Fog", "year": 1980, "tmdbId": 790, "titleSlug": "the-fog-790"}}
SHOWS = {"tt0108778": {"title": "Friends", "year": 1994, "tvdbId": 79168, "titleSlug": "friends",
                       "seasons": [{"seasonNumber": 1, "monitored": True}]}}


class Fake:
    key = API_KEY

    def __init__(self):
        self.posts = []

    def start(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                fake.serve(self, "GET")

            def do_POST(self):
                fake.serve(self, "POST")

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def serve(self, h, method):
        u = urlsplit(h.path)
        qs = {k: v[0] for k, v in parse_qs(u.query).items()}
        n = int(h.headers.get("Content-Length") or 0)
        body = json.loads(h.rfile.read(n)) if n else None
        if h.headers.get("X-Api-Key") != self.key:
            return self.reply(h, 401, {"message": "Unauthorized"})
        out = self.check(h, method) or self.handle(method, u.path, qs, body)
        self.reply(h, *(out or (404, {"message": "NotFound"})))

    def check(self, h, method):
        return None

    def reply(self, h, code, data, cookies=()):
        raw = json.dumps(data).encode()
        h.send_response(code)
        for c in cookies:
            h.send_header("Set-Cookie", c)
        h.send_header("Content-Type", "application/json")
        h.send_header("Content-Length", str(len(raw)))
        h.end_headers()
        h.wfile.write(raw)


class FakeArr(Fake):
    def __init__(self):
        super().__init__()
        self.have = {}       # imdb -> body posted (or seeded)

    def handle(self, method, p, qs, body):
        if p == "/api/v3/system/status":
            return 200, {"version": self.VERSION}
        if p == "/api/v3/qualityprofile":
            return 200, [{"id": 1, "name": "Any"}, {"id": 4, "name": "HD-1080p"}]
        if p == "/api/v3/rootfolder":
            return 200, [{"id": 1, "path": self.ROOT}, {"id": 2, "path": self.ROOT + "-4k"}]
        return self.more(method, p, qs, body)


class FakeRadarr(FakeArr):
    VERSION, ROOT = "5.9.1", "/movies"

    def more(self, method, p, qs, body):
        if p == "/api/v3/movie/lookup/imdb":
            imdb = qs.get("imdbId")
            if imdb not in KNOWN:
                return 404, {"message": "NotFound"}
            m = {**KNOWN[imdb], "imdbId": imdb, "images": []}
            if imdb in self.have:
                m["id"] = 7
            return 200, m
        if p == "/api/v3/movie" and method == "GET":
            return 200, [{**m, "id": 7, "hasFile": bool(m.get("hasFile"))} for m in self.have.values()]
        if p == "/api/v3/movie" and method == "POST":
            self.posts.append(body)
            self.have[body["imdbId"]] = body
            return 201, {**body, "id": 7}


class FakeSonarr(FakeArr):
    VERSION, ROOT, key = "4.0.9", "/tv", SONARR_KEY

    def more(self, method, p, qs, body):
        if p == "/api/v3/series/lookup":
            term = qs.get("term", "")
            imdb = term[5:] if term.startswith("imdb:") else None
            if imdb not in SHOWS:
                return 200, []
            s = {**SHOWS[imdb], "imdbId": imdb, "images": []}
            if imdb in self.have:
                s["id"] = 3
            return 200, [s]
        if p == "/api/v3/languageprofile":
            return 200, []
        if p == "/api/v3/series" and method == "GET":
            return 200, [{**s, "id": 3, "statistics": {"percentOfEpisodes": 0}} for s in self.have.values()]
        if p == "/api/v3/series" and method == "POST":
            self.posts.append(body)
            self.have[body["imdbId"]] = body
            return 201, {**body, "id": 3}


class FakeSeerr(Fake):
    """Knows the films and the show above by TMDB ID; `status` holds each one's media status."""
    key = SEERR_KEY
    TMDB = {"tt0084787": ("movie", 1091), "tt0080749": ("movie", 790), "tt0108778": ("tv", 1668)}

    def __init__(self):
        super().__init__()
        self.status = {}     # imdb -> Seerr media status (2 pending ... 5 available)
        self.csrf = False    # Seerr > Settings > Network > CSRF Protection
        self.refuse = None   # a reason Seerr turns a request down with 403

    def check(self, h, method):
        """CSRF Protection: changes need the token cookies handed out with every reply, sent back with
        the token in a header too; an API key alone isn't enough."""
        if self.csrf and method != "GET":
            cookie = h.headers.get("Cookie") or ""
            if "_csrf=secret" not in cookie or "XSRF-TOKEN=tok%2Ben" not in cookie or h.headers.get("X-XSRF-TOKEN") != "tok+en":
                return 403, {"message": "invalid csrf token"}
        if self.refuse and method == "POST":
            return 403, {"message": self.refuse}

    def serve(self, h, method):
        if self.csrf and method == "GET" and urlsplit(h.path).path == "/api/v1/status":
            return self.reply(h, 200, {"version": "2.7.3"}, cookies=(
                "_csrf=secret; Path=/; HttpOnly; Secure; SameSite=Strict", "XSRF-TOKEN=tok%2Ben; Path=/; Secure; SameSite=Strict"))
        super().serve(h, method)

    def handle(self, method, p, qs, body):
        if p == "/api/v1/status":
            return 200, {"version": "2.7.3"}
        if p == "/api/v1/auth/me":
            return 200, {"id": 1, "displayName": "Admin"}
        if p == "/api/v1/search":
            q = qs.get("query", "")
            imdb = q[5:] if q.startswith("imdb:") else None
            if imdb not in self.TMDB:
                return 200, {"page": 1, "results": []}
            kind, tmdb = self.TMDB[imdb]
            info = KNOWN.get(imdb) or SHOWS[imdb]
            r = {"id": tmdb, "mediaType": kind}
            r.update({"title": info["title"], "releaseDate": f"{info['year']}-01-01"} if kind == "movie"
                     else {"name": info["title"], "firstAirDate": f"{info['year']}-09-22"})
            if imdb in self.status:
                r["mediaInfo"] = {"status": self.status[imdb], "status4k": 1}
            return 200, {"page": 1, "results": [r]}
        if p == "/api/v1/request" and method == "POST":
            self.posts.append(body)
            imdb = next(i for i, (k, t) in self.TMDB.items() if t == body["mediaId"] and k == body["mediaType"])
            self.status[imdb] = 2
            return 201, {"id": len(self.posts), "status": 2}
