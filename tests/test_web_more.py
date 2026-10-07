"""More of the web UI's server: staying signed in across restarts, the time zone, list export,
requests and the notification test, each against a server started like the container starts it."""
import json, os, subprocess, sys, threading, time, unittest, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from tests.fake_emby import FakeEmby
from tests.fake_arr import API_KEY as RADARR_KEY, SEERR_KEY, FakeRadarr, FakeSeerr
from tests.helpers import ROOT, clean_env, config_dir
from tests.test_web import free_port

COLLECTIONS = """
[[collection]]
name = "80s Horror"
sources = ["collections/80s.md"]
"""


class Hook:
    """A webhook receiver that keeps what it's sent."""
    def __init__(self):
        got = self.got = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                got.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(204)
                self.end_headers()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/hook"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class WebMore(unittest.TestCase):
    def setUp(self):
        self.emby = FakeEmby().start()
        self.addCleanup(self.emby.stop)
        self.emby.add_film("tt0084787", "The Thing", 1982)
        self.base = config_dir(self.emby.url, **{
            "collections.toml": COLLECTIONS, "playlists.toml": "", "genres.toml": "",
            "collections__80s.md": "- tt0084787 | The Thing (1982)\n- tt0080749 | The Fog (1980)\n"})
        self.port = free_port()
        self.cookie = ""
        self.start()

    def start(self):
        self.proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "web", "server.py")], cwd=ROOT,
                                     env=clean_env(STAFFPICKED_CONFIG=self.base, PORT=str(self.port), TZ="UTC",
                                                   STAFFPICKED_DEFAULTS=os.path.join(ROOT, "config")),
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.stop)
        for _ in range(100):
            try:
                self.call("GET", "/api/health")
                return
            except OSError:
                time.sleep(0.1)

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait(timeout=10)

    def call(self, method, path, body=None, cookie=None):
        headers = {"Content-Type": "application/json"} if body is not None else {}
        if cookie if cookie is not None else self.cookie:
            headers["Cookie"] = cookie if cookie is not None else self.cookie
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method=method, headers=headers,
                                     data=None if body is None else json.dumps(body).encode())
        with urllib.request.urlopen(req, timeout=20) as r:
            set_cookie = r.headers.get("Set-Cookie")
            if set_cookie and set_cookie.startswith("session=") and "Max-Age=0" not in set_cookie:
                self.cookie = set_cookie.split(";")[0]
            return json.loads(r.read())

    def error(self, method, path, body=None, cookie=None):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.call(method, path, body, cookie)
        return e.exception.code, json.loads(e.exception.read() or b"{}")

    def test_staying_signed_in_across_a_restart(self):
        self.call("PUT", "/api/password", {"new": "correct horse"})
        self.assertTrue(self.cookie)
        self.call("GET", "/api/status")
        web = json.load(open(os.path.join(self.base, "web", "web.json")))
        token = self.cookie.split("=", 1)[1]
        self.assertNotIn(token, json.dumps(web))          # only a hash is kept
        self.stop()
        self.start()
        self.assertEqual(self.call("GET", "/api/auth")["signed_in"], True)
        self.call("GET", "/api/status")
        self.assertEqual(self.error("GET", "/api/status", cookie="session=forged")[0], 401)
        self.call("POST", "/api/logout", {})
        self.assertEqual(self.error("GET", "/api/status", cookie=f"session={token}")[0], 401)

    def test_time_zone_from_settings(self):
        self.assertEqual(self.call("GET", "/api/status")["time_zone"], "UTC")
        self.call("PUT", "/api/settings", {"env": {"TIME_ZONE": "America/Chicago"}})
        st = self.call("GET", "/api/status")
        self.assertEqual(st["time_zone"], "America/Chicago")
        self.assertRegex(st["next_run"], r"-0[56]:00$")
        code, body = self.error("PUT", "/api/settings", {"env": {"TIME_ZONE": "Mars/Base"}})
        self.assertEqual(code, 400)
        field = next(f for f in self.call("GET", "/api/settings")["fields"] if f["key"] == "TIME_ZONE")
        self.assertIn("Europe/Paris", field["suggest"])

    def test_schedule_settings(self):
        self.call("PUT", "/api/settings", {"env": {"SYNC_TIME": "18:00, 6:00", "SYNC_EVERY": ""}})
        st = self.call("GET", "/api/status")
        self.assertEqual(st["schedule"], "Daily at 06:00 and 18:00")
        with open(os.path.join(self.base, "staffpicked.env")) as f:
            text = f.read()
        self.assertIn("SYNC_TIME=06:00, 18:00\n", text)
        self.assertNotIn("SYNC_EVERY", text)     # blank and not in the file: left out
        self.call("PUT", "/api/settings", {"env": {"SYNC_EVERY": "3h"}})
        self.assertEqual(self.call("GET", "/api/status")["schedule"], "Every 3 hours")
        for bad in ({"SYNC_TIME": "06:00, 7pm"}, {"SYNC_EVERY": "5m"}):
            with self.subTest(bad=bad):
                self.assertEqual(self.error("PUT", "/api/settings", {"env": bad})[0], 400)

    def test_save_as_a_list_file(self):
        out = self.call("POST", "/api/builder/collections/0/export", {"use_it": True})
        self.assertEqual((out["name"], out["films"], out["used"]), ("collections/80s-horror.md", 2, True))
        with open(os.path.join(self.base, out["name"])) as f:
            text = f.read()
        self.assertTrue(text.startswith("# 80s Horror\n"))
        self.assertIn("- tt0080749 | The Fog (1980)\n", text)
        entry = self.call("GET", "/api/builder/collections")["entries"][0]
        self.assertEqual(entry["sources"], ["collections/80s-horror.md"])
        again = self.call("POST", "/api/builder/collections/0/export", {})
        self.assertEqual((again["name"], again["used"]), ("collections/80s-horror-2.md", False))

    def test_startup_sync_sends_its_summary(self):
        hook = Hook()
        self.addCleanup(hook.stop)
        self.stop()
        with open(os.path.join(self.base, "staffpicked.env"), "a") as f:
            f.write(f"SYNC_ON_START=true\nNOTIFY_URL={hook.url}\nNOTIFY_ON=always\nENABLE_PLAYLISTS=false\n")
        self.start()
        for _ in range(200):
            if hook.got:
                break
            time.sleep(0.1)
        self.assertEqual(hook.got[0]["title"], "StaffPicked: Startup sync done")
        self.assertEqual(hook.got[0]["message"], "Collections +1")

    def test_requests_and_notification_tests(self):
        fake, seer, hook = FakeRadarr().start(), FakeSeerr().start(), Hook()
        self.addCleanup(fake.stop)
        self.addCleanup(seer.stop)
        self.addCleanup(hook.stop)
        self.assertEqual(self.call("GET", "/api/status")["requests"], {"service": "seerr", "movies": False, "shows": False})
        self.assertEqual(self.call("POST", "/api/requests/test", {"service": "seerr", "env": {
            "SEERR_URL": seer.url, "SEERR_API_KEY": SEERR_KEY}})["user"], "Admin")
        self.call("PUT", "/api/settings", {"env": {"SEERR_URL": seer.url, "SEERR_API_KEY": SEERR_KEY}})
        self.assertTrue(self.call("GET", "/api/status")["requests"]["shows"])
        items = [{"imdb": "tt0080749", "show": False}, {"imdb": "tt0108778", "show": True}]
        self.assertEqual(self.call("POST", "/api/requests/status", {"items": items})["states"],
                         {"tt0080749": "missing", "tt0108778": "missing"})
        # a stand-in ID (MDBList's "tr..." for a title IMDb doesn't have) is skipped, not the whole check
        self.assertEqual(self.call("POST", "/api/requests/status", {"items": items + [{"imdb": "tr943706"}]})["states"],
                         {"tt0080749": "missing", "tt0108778": "missing"})
        self.assertEqual(self.call("POST", "/api/requests/add", {"imdb": "tt0080749"})["result"], "added")
        self.assertEqual(self.call("POST", "/api/requests/status", {"items": items})["states"]["tt0080749"], "requested")
        # Radarr instead
        r = self.call("POST", "/api/requests/test", {"service": "radarr", "env": {"RADARR_URL": fake.url, "RADARR_API_KEY": RADARR_KEY}})
        self.assertEqual(r["folder"], "/movies")
        self.call("PUT", "/api/settings", {"env": {"REQUEST_SERVICE": "arr", "RADARR_URL": fake.url, "RADARR_API_KEY": RADARR_KEY}})
        self.assertEqual(self.call("GET", "/api/status")["requests"], {"service": "arr", "movies": True, "shows": False})
        self.assertEqual(self.call("POST", "/api/requests/test", {"service": "radarr"})["profiles"], ["Any", "HD-1080p"])
        out = self.call("POST", "/api/requests/add", {"imdb": "tt0080749"})
        self.assertEqual((out["result"], out["name"], out["service"]), ("added", "The Fog (1980)", "Radarr"))
        out = self.call("POST", "/api/requests/status", {"items": items})
        self.assertEqual((out["states"], list(out["errors"])), ({"tt0080749": "requested"}, ["sonarr"]))
        # one title at a time: a list, even of one, is turned down
        self.assertEqual(self.error("POST", "/api/requests/add", {"imdb": ["tt0084787"]})[0], 400)
        self.assertEqual(self.error("POST", "/api/requests/add", {"imdb": "../x"})[0], 400)
        self.assertEqual(self.error("POST", "/api/requests/test", {"service": "plex"})[0], 400)
        self.call("POST", "/api/notify/test", {"url": hook.url})
        self.assertEqual(hook.got[0]["title"], "StaffPicked: test")


if __name__ == "__main__":
    unittest.main()
