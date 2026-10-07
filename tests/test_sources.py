import unittest
from unittest import mock

from scripts import sources


class MdblistIds(unittest.TestCase):
    def test_a_stand_in_imdb_id_counts_as_none(self):
        # MDBList gives a title IMDb doesn't have an id like "tr943706" in place of a tt number
        page = {"movies": [
            {"title": "Autumn", "release_year": 2023, "rank": 1, "id": 5, "imdb_id": None, "ids": {"imdb": "tr943706", "tmdb": 5}},
            {"title": "The Fog", "release_year": 1980, "rank": 2, "id": 790, "imdb_id": "tt0080749", "ids": {"imdb": "tt0080749"}},
        ], "pagination": {"has_more": False}}
        with mock.patch.object(sources, "request", return_value=page):
            items = sources.Sources({"MDBLIST_API_KEY": "k"}, ".").items("mdblist:me/fall")
        self.assertEqual([it.ids.get("imdb") for it in items], [None, "tt0080749"])
        self.assertEqual(str(items[0].ids["tmdb"]), "5")


if __name__ == "__main__":
    unittest.main()
