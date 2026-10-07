"""MDBList scores for the list window are cached, so each film is looked up once a week at most."""
import json, os, shutil, tempfile, time, unittest
from unittest import mock
from scripts import scores


class ScoreCache(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="staffpicked-test-")
        self.addCleanup(shutil.rmtree, self.base, True)
        self.calls = []

    def fake(self, method, url, params=None, json_body=None, **kw):
        self.calls.append(list(json_body["ids"]))
        return [{"ids": {"imdb": i}, "score": 70} for i in json_body["ids"] if i != "tt0000404"]

    def look(self, imdbs, known=None, key="k"):
        with mock.patch.object(scores, "request", self.fake):
            return scores.scores(self.base, key, imdbs, known)

    def test_new_films_are_looked_up_in_batches_once(self):
        ids = [f"tt{n:07d}" for n in range(1, 251)]
        got = self.look(ids)
        self.assertEqual([len(c) for c in self.calls], [200, 50])
        self.assertEqual(len(got), 250)
        self.look(ids)                  # all cached now
        self.assertEqual(len(self.calls), 2)

    def test_scores_from_a_list_and_unknown_films_need_no_lookup(self):
        got = self.look(["tt0084787", "tt0000404"], known={"tt0084787": 82})
        self.assertEqual(got, {"tt0084787": 82})
        self.assertEqual(self.calls, [["tt0000404"]])
        self.look(["tt0084787", "tt0000404"])      # MDBList didn't know it; not asked again
        self.assertEqual(len(self.calls), 1)

    def test_old_scores_are_refreshed(self):
        self.look(["tt0084787"])
        path = os.path.join(self.base, scores.FILE)
        data = json.load(open(path))
        data["tt0084787"][1] = time.time() - scores.MAX_AGE - 1
        json.dump(data, open(path, "w"))
        self.look(["tt0084787"])
        self.assertEqual(len(self.calls), 2)

    def test_without_a_key_only_the_cache_answers(self):
        self.assertEqual(self.look(["tt0084787"], key=""), {})
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
