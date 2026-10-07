"""The first-run setup screen, the whole-config download and restore, and the check for films
just added to the server."""
import io, json, os, subprocess, sys, time, unittest, urllib.error, urllib.request, zipfile
from scripts import arrivals, settings
from tests.fake_emby import FakeEmby
from tests.helpers import ROOT, clean_env, config_dir, write
from tests.test_web import free_port


class NewFilms(unittest.TestCase):
    def setUp(self):
        self.emby = FakeEmby().start()
        self.addCleanup(self.emby.stop)
        self.emby.add_film("tt0084787", "The Thing", 1982)
        self.base = config_dir(self.emby.url)
        self.env = settings.load_env(os.path.join(self.base, "staffpicked.env"))

    def test_only_films_added_since_the_last_check_count(self):
        watch = arrivals.Watch()
        self.assertEqual(watch.poll(self.env), {})      # the first check only takes note
        self.emby.add_film("tt0080749", "The Fog", 1980)
        self.assertEqual(watch.poll(self.env), {"tt0080749": "The Fog"})
        self.assertEqual(watch.poll(self.env), {})

    def test_a_film_still_without_ids_is_looked_at_again(self):
        watch = arrivals.Watch()
        watch.poll(self.env)
        fid = self.emby.add_film("tt0080749", "The Fog", 1980)
        film = self.emby.films[fid]
        film["ProviderIds"], film["DateCreated"] = {}, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.assertEqual(watch.poll(self.env), {})
        film["ProviderIds"] = {"Imdb": "tt0080749"}     # its metadata came in
        self.assertEqual(watch.poll(self.env), {"tt0080749": "The Fog"})

    def test_lists_that_were_missing_it(self):
        write(self.base, "cache/results-playlist.json", json.dumps({
            "watch in order": {"Emby": {"name": "Watch In Order", "missing": [{"imdb": "tt0080749"}]}},
            "other": {"Emby": {"name": "Other", "missing": [{"imdb": "tt1111111"}]}}}))
        self.assertEqual(arrivals.wanting(self.base, ["tt0080749"]), {"playlist": ["Watch In Order"]})
        self.assertEqual(arrivals.wanting(self.base, ["tt0000001"]), {})

    def test_how_often(self):
        self.assertEqual(arrivals.minutes({}), 15)
        self.assertEqual(arrivals.minutes({"NEW_FILM_CHECK": "off"}), 0)
        self.assertEqual(arrivals.minutes({"NEW_FILM_CHECK": "1h"}), 60)
        self.assertEqual(arrivals.minutes({"NEW_FILM_CHECK": "5m"}), 5)
        self.assertEqual(arrivals.minutes({"NEW_FILM_CHECK": "1"}), 5)


class WebFirstRun(unittest.TestCase):
    def setUp(self):
        self.emby = FakeEmby().start()
        self.addCleanup(self.emby.stop)
        self.emby.add_film("tt0084787", "The Thing", 1982)
        self.base = config_dir("http://YOUR_SERVER:8096", **{
            "collections.toml": '[[collection]]\nname = "80s Horror"\nsources = ["collections/80s.md"]\n',
            "playlists.toml": "", "genres.toml": "", "collections__80s.md": "- tt0084787 | The Thing (1982)\n"})
        self.cookie = ""
        self.addCleanup(self.stop)
        self.start()

    def start(self):
        self.port = free_port()
        self.proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "web", "server.py")], cwd=ROOT,
                                     env=clean_env(STAFFPICKED_CONFIG=self.base, PORT=str(self.port), TZ="UTC",
                                                   STAFFPICKED_DEFAULTS=os.path.join(ROOT, "config")),
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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

    def call(self, method, path, body=None, raw=None, ctype=None):
        headers = {}
        data = None
        if body is not None:
            headers["Content-Type"], data = "application/json", json.dumps(body).encode()
        if raw is not None:
            headers["Content-Type"], data = ctype, raw
        if self.cookie:
            headers["Cookie"] = self.cookie
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method=method, headers=headers, data=data)
        with urllib.request.urlopen(req, timeout=20) as r:
            c = r.headers.get("Set-Cookie")
            if c and c.startswith("session="):
                self.cookie = c.split(";")[0]
            out = r.read()
            return out if r.headers.get_content_type() == "application/zip" else json.loads(out)

    def env_text(self):
        with open(os.path.join(self.base, "staffpicked.env")) as f:
            return f.read()

    def test_setup_screen(self):
        st = self.call("GET", "/api/status")
        self.assertEqual(st["setup"], {"needed": True, "skipped": False})
        self.assertEqual(self.emby.calls, [])          # no startup sync against the placeholder
        bad = self.call("POST", "/api/setup/test", {"server": {"type": "emby", "url": self.emby.url, "key": "nope"}})
        self.assertFalse(bad["ok"])
        good = self.call("POST", "/api/setup/test", {"server": {"type": "emby", "url": self.emby.url, "key": "test-key"}})
        self.assertTrue(good["ok"], good)
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.call("POST", "/api/setup", {"server": {"url": self.emby.url, "key": "test-key"}, "password": "short"})
        self.assertEqual(e.exception.code, 400)
        out = self.call("POST", "/api/setup", {"server": {"type": "emby", "url": self.emby.url + "/", "key": "test-key"},
                                               "keys": {"MDBLIST_API_KEY": "md-key"}, "password": "a long password"})
        self.assertTrue(out["auth"])
        self.assertIn(f"SERVER_URL={self.emby.url}\n", self.env_text())
        self.assertIn("MDBLIST_API_KEY=md-key\n", self.env_text())
        self.assertEqual(self.call("GET", "/api/status")["setup"]["needed"], False)   # signed in by the cookie
        for _ in range(200):     # the first sync starts on its own
            if any(c[0] == "POST" and c[1] == "/Collections" for c in self.emby.calls):
                break
            time.sleep(0.1)
        else:
            self.fail("the first sync didn't run")

    def test_skip(self):
        self.call("POST", "/api/setup/skip", {})
        self.assertEqual(self.call("GET", "/api/status")["setup"], {"needed": True, "skipped": True})

    def test_screen_effects_setting(self):
        def page(path):
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=20) as r:
                return r.read().decode()
        self.assertTrue(self.call("GET", "/api/status")["effects"])      # on until turned off
        self.assertNotIn("no-effects", page("/"))
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.call("POST", "/api/effects", {"effects": "off"})
        self.assertEqual(e.exception.code, 400)
        self.assertEqual(self.call("POST", "/api/effects", {"effects": False}), {"ok": True, "effects": False})
        self.assertFalse(self.call("GET", "/api/status")["effects"])
        self.assertIn('<html lang="en" class="no-effects">', page("/"))
        self.stop()                                                     # it holds through a restart
        self.start()
        self.assertIn('<html lang="en" class="no-effects">', page("/index.html"))
        self.call("POST", "/api/effects", {"effects": True})
        self.assertNotIn("no-effects", page("/"))

    def test_download_and_restore_the_config(self):
        write(self.base, "web/logs/collections.log", "a log\n")
        write(self.base, "images/poster.jpg", "jpeg")
        data = self.call("GET", "/api/config/download")
        z = zipfile.ZipFile(io.BytesIO(data))
        names = set(z.namelist())
        self.assertTrue({"staffpicked.env", "collections.toml", "collections/80s.md", "images/poster.jpg"} <= names)
        self.assertFalse([n for n in names if n.startswith(("cache/", "web/logs/", "backups/"))])
        # change a file, then put the download back
        write(self.base, "collections/80s.md", "changed\n")
        write(self.base, "collections/new.md", "not in the zip\n")
        out = self.call("POST", "/api/config/restore", raw=data, ctype="application/zip")
        self.assertTrue(out["ok"])
        with open(os.path.join(self.base, "collections", "80s.md")) as f:
            self.assertEqual(f.read(), "- tt0084787 | The Thing (1982)\n")
        self.assertTrue(os.path.isfile(os.path.join(self.base, "collections", "new.md")))   # left alone
        self.assertTrue(os.path.isfile(os.path.join(self.base, out["saved"])))           # the copy from before
        with zipfile.ZipFile(os.path.join(self.base, out["saved"])) as before:
            self.assertEqual(before.read("collections/80s.md"), b"changed\n")

    def test_restore_refuses_a_zip_that_isnt_a_config(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("staffpicked.env", "x")
            z.writestr("../escape.txt", "x")
        for raw in (b"not a zip", buf.getvalue()):
            with self.assertRaises(urllib.error.HTTPError) as e:
                self.call("POST", "/api/config/restore", raw=raw, ctype="application/zip")
            self.assertEqual(e.exception.code, 400)
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(self.base), "escape.txt")))


if __name__ == "__main__":
    unittest.main()
