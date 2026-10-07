"""A whole sync, run the way the container runs it, against a fake Emby server."""
import json, os, unittest
from scripts import results
from tests.fake_emby import FakeEmby
from tests.helpers import cli, config_dir

COLLECTIONS = """
[[collection]]
name = "80s Horror"
sources = ["collections/80s.md"]

[[collection]]
name = "Never In Season"
sources = ["collections/80s.md"]
active = "2001-01-01 to 2001-01-02"
"""

PLAYLISTS = """
[settings]
include_watched = false
share = "private"

[[playlist]]
name = "Watch In Order"
sources = ["playlists/order.md"]
"""


class Sync(unittest.TestCase):
    def setUp(self):
        self.emby = FakeEmby().start()
        self.addCleanup(self.emby.stop)
        self.thing = self.emby.add_film("tt0084787", "The Thing", 1982)
        self.fog = self.emby.add_film("tt0080749", "The Fog", 1980)
        self.fly = self.emby.add_film("tt0091064", "The Fly", 1986)
        self.base = config_dir(
            self.emby.url,
            **{"collections.toml": COLLECTIONS, "playlists.toml": PLAYLISTS,
               "collections__80s.md": """
                   - tt0084787 | The Thing (1982)
                   - tt0080749 | The Fog (1980)
                   - tt9999999 | Not On The Server (1985)
                   """,
               "playlists__order.md": """
                   - tt0091064 | The Fly (1986)
                   - tt0084787 | The Thing (1982)
                   - tt0080749 | The Fog (1980)
                   """})

    def sync(self, *extra):
        code, out = cli(self.base, "sync", *extra)
        self.assertEqual(code, 0, out)
        return out

    def collection(self, name):
        return next((b for b in self.emby.boxsets.values() if b["Name"] == name), None)

    def summary(self, out):
        line = next(line for line in out.splitlines() if line.startswith("[summary] "))
        return json.loads(line[len("[summary] "):])

    def test_builds_collections_and_playlists(self):
        out = self.sync()
        self.assertEqual(sorted(self.collection("80s Horror")["children"]), sorted([self.thing, self.fog]))
        self.assertIsNone(self.collection("Never In Season"))
        pl = next(p for p in self.emby.playlists.values() if p["Name"] == "Watch In Order")
        self.assertEqual(pl["items"], [self.fly, self.thing, self.fog])     # the list's order
        self.assertEqual(pl["owner"], "u1")
        self.assertIn("[server] Emby: ok", out)
        self.assertEqual(self.summary(out), {"added": 5, "removed": 0, "errors": 0, "dry_run": False})

    def test_second_run_changes_only_what_the_list_did(self):
        self.sync()
        with open(os.path.join(self.base, "collections", "80s.md"), "w") as f:
            f.write("- tt0084787 | The Thing (1982)\n- tt0091064 | The Fly (1986)\n")
        out = self.sync("--only", "80s Horror")
        self.assertEqual(sorted(self.collection("80s Horror")["children"]), sorted([self.thing, self.fly]))
        self.assertEqual(self.summary(out)["added"], 1)
        self.assertEqual(self.summary(out)["removed"], 1)

    def test_watched_films_drop_off_the_playlist(self):
        self.emby.played["u1"] = {self.fly}
        self.sync()
        pl = next(p for p in self.emby.playlists.values() if p["Name"] == "Watch In Order")
        self.assertEqual(pl["items"], [self.thing, self.fog])

    def test_each_person_gets_films_from_the_libraries_they_can_see(self):
        # admin can't see the 4K library holding The Fly, guest can't see the HD one with The Thing
        self.emby.hidden = {"u1": {self.fly}, "u2": {self.thing}}
        with open(os.path.join(self.base, "staffpicked.env"), "a") as f:
            f.write("PLAYLIST_USERS=admin,guest\n")
        self.sync()
        mine = {p["owner"]: p["items"] for p in self.emby.playlists.values() if p["Name"] == "Watch In Order"}
        self.assertEqual(mine, {"u1": [self.thing, self.fog], "u2": [self.fly, self.fog]})
        r = results.load(self.base, "playlist")["watch in order"]["Emby"]
        self.assertEqual((r["listed"], r["in_library"], r["missing_count"]), (3, 3, 0))
        self.assertEqual(sorted(r["have"]), ["tt0080749", "tt0084787", "tt0091064"])

    def diffs(self, out):
        return [json.loads(line[len("[diff] "):]) for line in out.splitlines() if line.startswith("[diff] ")]

    def test_each_list_says_what_it_changes_by_title(self):
        d = {x["name"]: x for x in self.diffs(self.sync("--dry-run"))}
        self.assertEqual(d["80s Horror"]["added"], ["The Thing (1982)", "The Fog (1980)"])
        self.assertTrue(d["80s Horror"]["dry_run"])
        self.assertEqual(d["Watch In Order"]["added"], ["The Fly (1986)", "The Thing (1982)", "The Fog (1980)"])
        self.assertEqual(d["Watch In Order"]["changes"], ["building playlist with 3 items, sharing: private"])
        self.sync()
        # nothing changed since: no list has anything to say
        self.assertEqual(self.diffs(self.sync()), [])
        with open(os.path.join(self.base, "collections", "80s.md"), "w") as f:
            f.write("- tt0084787 | The Thing (1982)\n")
        d = {x["name"]: x for x in self.diffs(self.sync())}
        self.assertEqual((d["80s Horror"]["added"], d["80s Horror"]["removed"]), ([], ["The Fog (1980)"]))

    def test_dry_run_changes_nothing(self):
        out = self.sync("--dry-run")
        self.assertEqual(self.emby.boxsets, {})
        self.assertEqual(self.emby.playlists, {})
        self.assertTrue(self.summary(out)["dry_run"])
        self.assertEqual(results.load(self.base, "collection"), {})     # nor the results file

    def test_results_record_what_is_missing(self):
        self.sync()
        r = results.load(self.base, "collection")["80s horror"]["Emby"]
        self.assertEqual((r["listed"], r["in_library"], r["missing_count"], r["errors"]), (3, 2, 1, 0))
        self.assertEqual(r["missing"][0]["imdb"], "tt9999999")
        self.assertEqual(sorted(r["have"]), ["tt0080749", "tt0084787"])
        self.assertEqual(r["added"], 2)
        self.assertTrue(results.load(self.base, "collection")["never in season"]["Emby"]["off_season"])
        p = results.load(self.base, "playlist")["watch in order"]["Emby"]
        self.assertEqual((p["listed"], p["in_library"], p["members"]), (3, 3, 3))

    def test_a_broken_list_is_recorded_and_the_rest_still_syncs(self):
        os.remove(os.path.join(self.base, "playlists", "order.md"))
        code, out = cli(self.base, "sync")
        self.assertEqual(code, 1)
        self.assertIsNotNone(self.collection("80s Horror"))
        r = results.load(self.base, "playlist")["watch in order"]["Emby"]
        self.assertEqual(r["errors"], 1)
        self.assertIn("not found", r["error"])

    def test_server_down_is_recorded_for_each_list(self):
        self.emby.stop()
        code, out = cli(self.base, "sync")
        self.assertEqual(code, 1)
        self.assertIn("[server] Emby: 1 error(s)", out)
        r = results.load(self.base, "collection")["80s horror"]["Emby"]
        self.assertEqual(r["errors"], 1)

    def test_remove_takes_them_off(self):
        self.sync()
        out = cli(self.base, "remove")[1]
        self.assertEqual(self.emby.boxsets, {}, out)
        self.assertEqual(self.emby.playlists, {}, out)

    def playlist(self):
        return [(pid, p) for pid, p in self.emby.playlists.items() if p["Name"] == "Watch In Order"]

    def write_list(self, rel, *imdbs):
        with open(os.path.join(self.base, rel), "w") as f:
            f.write("".join(f"- {i}\n" for i in imdbs))

    def test_playlists_are_updated_in_place(self):
        self.sync()
        [(pid, _)] = self.playlist()
        art = len(self.emby.images)
        # reorder, drop The Fog, and add a new film in the middle
        cell = self.emby.add_film("tt0087800", "A Nightmare on Elm Street", 1984)
        self.write_list("playlists/order.md", "tt0084787", "tt0087800", "tt0091064")
        out = self.sync("--only", "Watch In Order")
        [(same, pl)] = self.playlist()
        self.assertEqual(same, pid, out)        # still the same playlist
        self.assertEqual(pl["items"], [self.thing, cell, self.fly])
        self.assertFalse(any(m == "DELETE" and p == f"/Items/{pid}" for m, p in self.emby.calls))
        self.assertEqual(len(self.emby.images), art)     # no artwork is sent again
        self.assertEqual((self.summary(out)["added"], self.summary(out)["removed"]), (1, 1))

    def test_an_unchanged_playlist_is_left_alone(self):
        self.sync()
        self.emby.calls.clear()
        self.sync("--only", "Watch In Order")
        self.assertFalse([c for c in self.emby.calls if c[0] in ("POST", "DELETE") and "/Playlists" in c[1]])

    def test_a_list_that_empties_is_held_back(self):
        self.emby.add_film("tt0087800", "A Nightmare on Elm Street", 1984)
        self.write_list("collections/80s.md", "tt0084787", "tt0080749", "tt0091064", "tt0087800")
        self.write_list("playlists/order.md", "tt0091064", "tt0084787", "tt0080749", "tt0087800")
        self.sync()
        coll, order = sorted(self.collection("80s Horror")["children"]), self.playlist()[0][1]["items"][:]
        self.write_list("collections/80s.md", "tt9999999")
        self.write_list("playlists/order.md", "tt0091064")
        code, out = cli(self.base, "sync")
        self.assertEqual(code, 1, out)
        self.assertIn("Held back", out)
        self.assertEqual(sorted(self.collection("80s Horror")["children"]), coll)
        self.assertEqual(self.playlist()[0][1]["items"], order)
        r = results.load(self.base, "collection")["80s horror"]["Emby"]
        self.assertTrue(r["held"])
        self.assertEqual(r["errors"], 1)
        # let it through on purpose
        out = self.sync("--allow-removals")
        self.assertIsNone(self.collection("80s Horror"))
        self.assertEqual(self.playlist()[0][1]["items"], [self.fly])
        self.assertNotIn("held", results.load(self.base, "collection")["80s horror"]["Emby"])

    def test_the_limit_can_be_turned_off(self):
        self.emby.add_film("tt0087800", "A Nightmare on Elm Street", 1984)
        self.write_list("playlists/order.md", "tt0091064", "tt0084787", "tt0080749", "tt0087800")
        self.sync()
        self.write_list("playlists/order.md", "tt0091064")
        self.assertIn("Held back", cli(self.base, "sync")[1])
        with open(os.path.join(self.base, "staffpicked.env"), "a") as f:
            f.write("REMOVAL_LIMIT=0\n")
        self.sync()
        self.assertEqual(self.playlist()[0][1]["items"], [self.fly])

    def test_watching_doesnt_trip_the_brake(self):
        self.sync()
        self.emby.played["u1"] = {self.fly, self.thing, self.fog}
        out = self.sync()
        self.assertNotIn("Held back", out)
        self.assertEqual(self.playlist(), [])     # all watched: nothing left to play

    def test_check_needs_no_server(self):
        self.emby.stop()
        code, out = cli(self.base, "check")
        self.assertEqual(code, 0, out)
        self.assertIn("OK", out)


if __name__ == "__main__":
    unittest.main()
