"""The web UI's server, started the way the container starts it, against a fake Emby."""
import json, os, socket, subprocess, sys, time, unittest, urllib.error, urllib.request
from tests.fake_emby import FakeEmby
from tests.helpers import ROOT, clean_env, config_dir

COLLECTIONS = """
[[collection]]
name = "80s Horror"
sources = ["collections/80s.md"]
poster = "images/80s.jpg"
"""


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Web(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.emby = FakeEmby().start()
        cls.emby.add_film("tt0084787", "The Thing", 1982)
        cls.base = config_dir(cls.emby.url, **{
            "collections.toml": COLLECTIONS, "playlists.toml": "", "genres.toml": "",
            "collections__80s.md": "- tt0084787 | The Thing (1982)\n- tt9999999 | Not Here (1985)\n"})
        os.makedirs(os.path.join(cls.base, "images"))
        with open(os.path.join(cls.base, "images", "80s.jpg"), "wb") as f:
            f.write(b"\xff\xd8\xff\xe0 fake jpeg")
        cls.port = free_port()
        cls.proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "web", "server.py")], cwd=ROOT,
                                    env=clean_env(STAFFPICKED_CONFIG=cls.base, PORT=str(cls.port),
                                                  STAFFPICKED_DEFAULTS=os.path.join(ROOT, "config")),
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for _ in range(100):
            try:
                cls.get("/api/health")
                break
            except OSError:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=10)
        cls.proc.stdout.close()
        cls.emby.stop()

    @classmethod
    def call(cls, method, path, body=None):
        req = urllib.request.Request(f"http://127.0.0.1:{cls.port}{path}", method=method,
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"} if body is not None else {})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())

    @classmethod
    def get(cls, path):
        return cls.call("GET", path)

    def wait_for(self, job):
        for _ in range(300):
            st = next(j for j in self.get("/api/status")["jobs"] if j["name"] == job)
            if not st["running"]:
                return st
            time.sleep(0.1)
        self.fail(f"{job} still running")

    def test_health(self):
        h = self.get("/api/health")
        self.assertTrue(h["ok"])

    def test_sync_from_the_page(self):
        self.call("POST", "/api/jobs/collections/run", {"action": "sync"})
        st = self.wait_for("collections")
        self.assertEqual(st["run"]["status"], "ok")
        self.assertEqual(st["run"]["summary"]["added"], 1)
        self.assertEqual(st["run"]["progress"]["done"], 1)
        row = st["items"][0]
        self.assertEqual(row["poster"], "images/80s.jpg")
        self.assertEqual((row["last"]["listed"], row["last"]["in_library"], row["last"]["errors"]), (2, 1, 0))
        # Recent Runs: the run, its outcome, and its own log
        run = self.get("/api/history")[0]
        self.assertTrue(run["has_log"])
        self.assertEqual(run["summary"]["added"], 1)
        log = self.get(f"/api/runs/{run['id']}/log")
        self.assertTrue(any("[collection] 80s Horror" in line for line in log["lines"]))
        self.assertFalse(any(line.startswith(("[summary]", "[diff]")) for line in log["lines"]))
        # and what it changed on each list, by title
        self.assertEqual([(c["name"], c["added"]) for c in log["changes"]], [("80s Horror", ["The Thing (1982)"])])
        self.assertEqual(run["changed"], 1)
        # the list window marks what's on the server and what isn't
        items = self.get("/api/builder/collections/0/items")
        marks = {i["imdb"]: i["in_library"] for i in items["items"]}
        self.assertEqual(marks, {"tt0084787": True, "tt9999999": False})
        self.assertEqual(items["library"][0]["missing"], ["tt9999999"])
        self.assertTrue(all("score" in i for i in items["items"]))   # none here: no MDBList key

    def test_saving_a_file_keeps_the_old_one(self):
        name = "collections/80s.md"
        old = self.get(f"/api/files/collections/{name}")["text"]
        self.call("PUT", f"/api/files/collections/{name}", {"text": old + "- tt0080749 | The Fog (1980)\n"})
        v = self.get(f"/api/backups?job=collections&name={name}")["versions"]
        self.assertGreaterEqual(len(v), 1)
        self.assertEqual(self.get(f"/api/backups?job=collections&name={name}&id={v[0]['id']}")["text"], old)
        self.call("PUT", f"/api/files/collections/{name}", {"text": old})

    def test_run_logs_need_a_real_id(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.get("/api/runs/..%2F..%2Fweb/log")
        self.assertEqual(e.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
