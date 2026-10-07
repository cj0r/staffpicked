import os, tempfile, unittest
from unittest import mock

from scripts import artwork


class ThePosterDBTest(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.art = artwork.Artwork({}, self.base)

    def test_tpdb_images_are_never_downloaded(self):
        with mock.patch.object(artwork.Artwork, "download", side_effect=AssertionError("asked TPDb")):
            with self.assertRaisesRegex(ValueError, "added by hand"):
                self.art.fetch("tpdb:215103", "poster")

    def test_check_says_to_add_a_tpdb_poster_by_hand(self):
        problems = artwork.check("tpdb:215103", self.base)
        self.assertEqual(len(problems), 1)
        self.assertIn("theposterdb.com", problems[0])

    def test_no_sign_in_settings_remain(self):
        from scripts import settings
        self.assertFalse([k for k in settings.ENV_KEYS if k.startswith("TPDB")])


def poster(asset, lang=None, modified="2025-01-01T00:00:00.000Z"):
    return {"id": asset, "modified_on": modified, "language": {"display_name": lang} if lang else None}


class MediuxTest(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.art = artwork.Artwork({"MEDIUX_API_TOKEN": "tok"}, self.base)
        self.sent = []

    def answer(self, data):
        def fake(method, url, params=None, headers=None, json_body=None, raw=False, **kw):
            if raw:
                return f"image {url.rsplit('/', 1)[1]}".encode(), "image/png"
            self.sent.append((url, headers, json_body["query"]))
            return {"data": data}
        return mock.patch.object(artwork, "request", side_effect=fake)

    def test_a_movie_picks_english_or_textless_then_the_most_popular_set(self):
        sets = [{"popularity": 1, "movie_poster": [poster("aaaaaaaa-0000-0000-0000-000000000001", "German")]},
                {"popularity": 3, "movie_poster": [poster("aaaaaaaa-0000-0000-0000-000000000003", "English")]},
                {"popularity": 2, "movie_poster": [poster("aaaaaaaa-0000-0000-0000-000000000002")]}]
        with self.answer({"item": {"sets": sets}}):
            data, ctype = self.art.fetch("mediux:movie/1091", "poster")
        self.assertEqual((data, ctype), (b"image aaaaaaaa-0000-0000-0000-000000000002", "image/png"))
        url, headers, query = self.sent[0]
        self.assertEqual(url, "https://images.mediux.io/graphql")
        self.assertEqual(headers["Authorization"], "Bearer tok")
        self.assertIn("movies_by_id(id: 1091)", query)
        self.assertIn("movie_poster", query)

    def test_a_set_link_and_an_exact_image(self):
        with self.answer({"movie": None, "collection": {"popularity": None, "collection_backdrop": [
                poster("bbbbbbbb-0000-0000-0000-000000000001")]}}):
            data, _ = self.art.fetch("https://mediux.pro/sets/44610", "backdrop")
        self.assertEqual(data, b"image bbbbbbbb-0000-0000-0000-000000000001")
        self.assertIn("collection_sets_by_id(id: 44610)", self.sent[0][2])
        with self.answer({}):
            data, _ = self.art.fetch("mediux:CCCCCCCC-0000-0000-0000-000000000001", "poster")
        self.assertEqual(data, b"image cccccccc-0000-0000-0000-000000000001")

    def test_images_are_downloaded_once(self):
        asset = "dddddddd-0000-0000-0000-000000000001"
        with self.answer({}):
            self.art.fetch(f"mediux:{asset}", "poster")
        self.assertTrue(os.path.isfile(os.path.join(self.base, "cache", "mediux", asset + ".png")))
        with mock.patch.object(artwork, "request", side_effect=AssertionError("downloaded again")):
            self.assertEqual(self.art.fetch(f"mediux:{asset}", "poster")[0], f"image {asset}".encode())

    def test_nothing_found_and_no_thumbs(self):
        with self.answer({"item": None}), self.assertRaisesRegex(ValueError, "no poster"):
            self.art.fetch("mediux:movie/1", "poster")
        with self.assertRaisesRegex(ValueError, "no thumbs"):
            self.art.fetch("mediux:movie/1", "thumb")

    def test_checks_and_the_token(self):
        self.assertEqual(artwork.check("mediux:movie/1091", self.base), [])
        self.assertEqual(artwork.check("mediux:set/10389", self.base), [])
        self.assertTrue(artwork.check("mediux:film/1091", self.base))
        self.assertTrue(artwork.needs_mediux_token("https://mediux.pro/sets/10389"))
        self.assertFalse(artwork.needs_mediux_token("mediux:dddddddd-0000-0000-0000-000000000001"))
        no_token = artwork.Artwork({}, self.base)
        with self.assertRaisesRegex(Exception, "MEDIUX_API_TOKEN"):
            no_token.fetch("mediux:movie/1091", "poster")


if __name__ == "__main__":
    unittest.main()
