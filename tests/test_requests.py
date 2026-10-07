"""Requesting missing films and shows through Seerr, or Radarr and Sonarr, against fakes of each."""
import unittest
from scripts import arr, requests_to, seerr, util
from tests.fake_arr import API_KEY, SEERR_KEY, SONARR_KEY, FakeRadarr, FakeSeerr, FakeSonarr


class Base(unittest.TestCase):
    def setUp(self):
        util.sleep = lambda s: None
        self.addCleanup(setattr, util, "sleep", __import__("time").sleep)

    def fake(self, cls):
        f = cls().start()
        self.addCleanup(f.stop)
        return f


class Radarr(Base):
    def setUp(self):
        super().setUp()
        self.fake = self.fake(FakeRadarr)
        self.env = {"RADARR_URL": self.fake.url + "/", "RADARR_API_KEY": API_KEY}

    def test_status_names_where_films_go(self):
        s = arr.Radarr({**self.env, "RADARR_QUALITY_PROFILE": "hd-1080p"}).status()
        self.assertEqual((s["version"], s["profile"], s["folder"]), ("5.9.1", "HD-1080p", "/movies"))

    def test_status_lists_choices_even_when_the_saved_one_is_gone(self):
        s = arr.Radarr({**self.env, "RADARR_QUALITY_PROFILE": "Ultra"}).status()
        self.assertEqual((s["profiles"], s["folders"]), (["Any", "HD-1080p"], ["/movies", "/movies-4k"]))
        self.assertIn("no quality profile called 'Ultra'", s["problem"])

    def test_adds_new_films_and_skips_the_rest(self):
        r = arr.Radarr({**self.env, "RADARR_ROOT_FOLDER": "/movies-4k/", "RADARR_SEARCH": "false"})
        self.assertEqual(r.add("tt0084787"), {"result": "added", "name": "The Thing (1982)", "state": "requested"})
        self.assertEqual(r.add("tt9999999")["result"], "failed")
        post = self.fake.posts[0]
        self.assertEqual((post["tmdbId"], post["qualityProfileId"], post["rootFolderPath"], post["monitored"]),
                         (1091, 1, "/movies-4k", True))
        self.assertEqual(post["addOptions"], {"searchForMovie": False})
        self.assertEqual(r.add("tt0084787")["result"], "already")

    def test_states_say_requested_available_or_missing(self):
        self.fake.have["tt0084787"] = {"imdbId": "tt0084787", "hasFile": False}
        self.fake.have["tt0080749"] = {"imdbId": "tt0080749", "hasFile": True}
        self.assertEqual(arr.Radarr(self.env).states(["tt0084787", "tt0080749", "tt1234567"]),
                         {"tt0084787": "requested", "tt0080749": "available", "tt1234567": "missing"})

    def test_settings_mistakes_say_what_is_wrong(self):
        with self.assertRaisesRegex(util.ServiceError, "API key"):
            arr.Radarr({**self.env, "RADARR_API_KEY": "nope"}).status()
        with self.assertRaisesRegex(util.ServiceError, "no quality profile called 'Ultra'.*Any, HD-1080p"):
            arr.Radarr({**self.env, "RADARR_QUALITY_PROFILE": "Ultra"}).add("tt0084787")
        with self.assertRaisesRegex(util.ServiceError, "Set the Radarr URL"):
            arr.Radarr({})


class Sonarr(Base):
    def test_adds_a_show_by_imdb_id(self):
        fake = self.fake(FakeSonarr)
        s = arr.Sonarr({"SONARR_URL": fake.url, "SONARR_API_KEY": SONARR_KEY})
        self.assertEqual(s.status()["folder"], "/tv")
        self.assertEqual(s.states(["tt0108778"]), {"tt0108778": "missing"})
        self.assertEqual(s.add("tt0108778")["name"], "Friends (1994)")
        post = fake.posts[0]
        self.assertEqual((post["tvdbId"], post["rootFolderPath"], post["seasonFolder"]), (79168, "/tv", True))
        self.assertEqual(post["addOptions"]["monitor"], "all")
        self.assertEqual(s.states(["tt0108778"]), {"tt0108778": "requested"})
        self.assertEqual(s.add("tt0108778")["result"], "already")
        self.assertEqual(s.add("tt0000001")["result"], "failed")


class Seerr(Base):
    def setUp(self):
        super().setUp()
        self.fake = self.fake(FakeSeerr)
        self.env = {"SEERR_URL": self.fake.url + "/", "SEERR_API_KEY": SEERR_KEY}

    def test_status_and_key(self):
        self.assertEqual(seerr.Seerr(self.env).status(), {"version": "2.7.3", "user": "Admin"})
        with self.assertRaisesRegex(util.ServiceError, "turned down the API key"):
            seerr.Seerr({**self.env, "SEERR_API_KEY": "nope"}).status()

    def test_requests_films_and_shows(self):
        s = seerr.Seerr(self.env)
        self.assertEqual(s.add("tt0084787"), {"result": "added", "name": "The Thing (1982)", "state": "requested"})
        self.assertEqual(s.add("tt0108778", True)["name"], "Friends (1994)")
        self.assertEqual(self.fake.posts, [{"mediaType": "movie", "mediaId": 1091},
                                           {"mediaType": "tv", "mediaId": 1668, "seasons": "all"}])
        self.assertEqual(s.add("tt0084787")["result"], "already")
        self.assertEqual(s.add("tt9999999")["result"], "failed")

    def test_csrf_protection_and_refusals(self):
        # Test passes (only reads), so a request turned down must say why, not blame the key
        self.fake.csrf = True
        s = seerr.Seerr(self.env)
        self.assertEqual(s.status()["user"], "Admin")
        self.assertEqual(s.add("tt0084787")["result"], "added")
        self.fake.csrf, self.fake.refuse = False, "This title is blocklisted."
        with self.assertRaisesRegex(util.ServiceError, "Seerr said no: This title is blocklisted."):
            s.add("tt0080749")

    def test_states(self):
        self.fake.status.update({"tt0084787": 3, "tt0080749": 5})
        self.assertEqual(seerr.Seerr(self.env).states([("tt0084787", False), ("tt0080749", False), ("tt0108778", True)]),
                         {"tt0084787": "requested", "tt0080749": "available", "tt0108778": "missing"})


class Choosing(Base):
    def test_seerr_is_the_default_and_arr_splits_films_and_shows(self):
        radarr, sonarr, seer = self.fake(FakeRadarr), self.fake(FakeSonarr), self.fake(FakeSeerr)
        env = {"SEERR_URL": seer.url, "SEERR_API_KEY": SEERR_KEY}
        self.assertEqual(requests_to.setup(env), {"service": "seerr", "movies": True, "shows": True})
        self.assertEqual(requests_to.add(env, "tt0080749", False)["service"], "Seerr")
        env = {"REQUEST_SERVICE": "arr", "RADARR_URL": radarr.url, "RADARR_API_KEY": API_KEY,
               "SONARR_URL": sonarr.url, "SONARR_API_KEY": SONARR_KEY}
        self.assertEqual(requests_to.setup({**env, "SONARR_URL": ""}), {"service": "arr", "movies": True, "shows": False})
        self.assertEqual(requests_to.add(env, "tt0080749", False)["service"], "Radarr")
        self.assertEqual(requests_to.add(env, "tt0108778", True)["service"], "Sonarr")
        states, errors = requests_to.states(env, [("tt0080749", False), ("tt0108778", True), ("tt0084787", False)])
        self.assertEqual(states, {"tt0080749": "requested", "tt0108778": "requested", "tt0084787": "missing"})
        self.assertEqual(errors, {})
        states, errors = requests_to.states({**env, "SONARR_API_KEY": ""}, [("tt0108778", True)])
        self.assertEqual((states, list(errors)), ({}, ["sonarr"]))


if __name__ == "__main__":
    unittest.main()
