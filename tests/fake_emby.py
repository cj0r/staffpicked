"""A small stand-in for an Emby server, enough of its API for a sync to run against.

It holds users, a film library, collections (BoxSets) and playlists in memory, answers the
calls scripts/server.py makes, and records every call so a test can check what was done.
Start it with FakeEmby().start(); its .url goes in SERVER_URL."""
import json, threading, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

API_KEY = "test-key"


class FakeEmby:
    def __init__(self):
        self.users = [{"Id": "u1", "Name": "admin", "Policy": {"IsAdministrator": True}},
                      {"Id": "u2", "Name": "guest", "Policy": {}}]
        self.films = {}          # id -> item
        self.boxsets = {}        # id -> {"Name", "children": [ids]}
        self.playlists = {}      # id -> {"Name", "owner", "items": [ids]}
        self.played = {}         # user id -> {item ids}
        self.hidden = {}         # user id -> {film ids in a library that user can't see}
        self.genres = {}         # id -> name
        self.images = []         # (item id, kind, index)
        self.calls = []          # (method, path)
        self._next = 1000

    def add_film(self, imdb, name, year):
        fid = f"f{len(self.films) + 1}"
        self.films[fid] = {"Id": fid, "Name": name, "Type": "Movie", "ProductionYear": year,
                           "ProviderIds": {"Imdb": imdb}, "DateCreated": "2020-01-01T00:00:00Z",
                           "PremiereDate": f"{year}-06-01T00:00:00Z"}
        return fid

    def new_id(self):
        self._next += 1
        return str(self._next)

    # --- running it
    def start(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                fake.handle(self, "GET")

            def do_POST(self):
                fake.handle(self, "POST")

            def do_DELETE(self):
                fake.handle(self, "DELETE")

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    # --- the API
    def handle(self, h, method):
        url = urllib.parse.urlsplit(h.path)
        path, qs = url.path, {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        n = int(h.headers.get("Content-Length") or 0)
        body = h.rfile.read(n) if n else b""
        self.calls.append((method, path))
        if h.headers.get("X-Emby-Token") != API_KEY and not path.endswith("/AuthenticateByName"):
            return self.reply(h, 401, {"error": "bad key"})
        try:
            out = self.route(method, path.rstrip("/").split("/")[1:], qs, body)
        except KeyError:
            return self.reply(h, 404, {"error": "not found"})
        self.reply(h, 200, out)

    def reply(self, h, code, data):
        raw = b"" if data is None else json.dumps(data).encode()
        h.send_response(code if raw or code != 200 else 204)
        h.send_header("Content-Type", "application/json")
        h.send_header("Content-Length", str(len(raw)))
        h.end_headers()
        h.wfile.write(raw)

    def route(self, method, p, qs, body):
        ids = [i for i in qs.get("Ids", "").split(",") if i]
        if p == ["System", "Info"]:
            return {"ServerName": "Fake", "Version": "4.9"}
        if p == ["Users"]:
            return self.users
        if p == ["Users", "AuthenticateByName"]:
            return {"AccessToken": API_KEY}
        if len(p) == 3 and p[0] == "Users" and p[2] == "Items":
            return {"Items": self.items(p[1], qs)}
        if len(p) == 4 and p[0] == "Users" and p[2] == "Items":
            return self.item(p[3])
        if p == ["Collections"] and method == "POST":
            cid = self.new_id()
            self.boxsets[cid] = {"Name": qs["Name"], "children": ids}
            return {"Id": cid}
        if len(p) == 3 and p[0] == "Collections" and p[2] == "Items":
            kids = self.boxsets[p[1]]["children"]
            if method == "POST":
                kids += [i for i in ids if i not in kids]
            else:
                self.boxsets[p[1]]["children"] = [i for i in kids if i not in ids]
            return None
        if p == ["Playlists"] and method == "POST":
            pid = self.new_id()
            self.playlists[pid] = {"Name": qs["Name"], "owner": qs["UserId"], "items": ids,
                                   "entries": [self.new_id() for _ in ids]}
            return {"Id": pid}
        if len(p) == 3 and p[0] == "Playlists" and p[2] == "Items":
            pl = self.playlists[p[1]]
            if method == "POST":
                pl["items"] += ids
                pl["entries"] += [self.new_id() for _ in ids]
                return None
            if method == "DELETE":
                gone = set(qs.get("EntryIds", "").split(","))
                keep = [(i, e) for i, e in zip(pl["items"], pl["entries"]) if e not in gone]
                pl["items"], pl["entries"] = [i for i, _ in keep], [e for _, e in keep]
                return None
            return {"Items": [{**self.films[i], "PlaylistItemId": e} for i, e in zip(pl["items"], pl["entries"])]}
        if len(p) == 5 and p[0] == "Playlists" and p[2] == "Items" and p[4] == "Move":
            raise KeyError("move needs an index")
        if len(p) == 6 and p[0] == "Playlists" and p[2] == "Items" and p[4] == "Move" and method == "POST":
            pl = self.playlists[p[1]]
            at = pl["entries"].index(p[3])
            item, entry = pl["items"].pop(at), pl["entries"].pop(at)
            pl["items"].insert(int(p[5]), item)
            pl["entries"].insert(int(p[5]), entry)
            return None
        if p == ["Genres"]:
            return {"Items": [{"Id": g, "Name": n} for g, n in self.genres.items()]}
        if len(p) == 2 and p[0] == "Items" and method == "DELETE":
            if not (self.boxsets.pop(p[1], None) or self.playlists.pop(p[1], None)):
                raise KeyError(p[1])
            return None
        if len(p) == 2 and p[0] == "Items" and method == "POST":
            return None       # update_item
        if len(p) >= 4 and p[0] == "Items" and p[2] == "Images":
            self.images.append((p[1], p[3], int(p[4]) if len(p) > 4 else 0))
            return None
        if len(p) == 3 and p[0] == "Items" and p[2] == "Refresh":
            return None
        if p == ["Items", "Access"]:
            return None
        raise KeyError("/".join(p))

    def items(self, uid, qs):
        if "ParentId" in qs:
            box = self.boxsets[qs["ParentId"]]
            return [self.films[i] for i in box["children"]]
        types = qs.get("IncludeItemTypes", "")
        if types == "BoxSet":
            return [{"Id": c, "Name": b["Name"], "Type": "BoxSet"} for c, b in self.boxsets.items()]
        if types == "Playlist":
            return [{"Id": i, "Name": pl["Name"], "Type": "Playlist"} for i, pl in self.playlists.items()
                    if pl["owner"] == uid]
        films = [f for f in self.films.values() if f["Id"] not in self.hidden.get(uid, set())]
        if qs.get("IsPlayed") == "true":
            films = [f for f in films if f["Id"] in self.played.get(uid, set())]
        return films

    def item(self, iid):
        if iid in self.boxsets:
            return {"Id": iid, "Name": self.boxsets[iid]["Name"], "Type": "BoxSet"}
        return self.films[iid]
