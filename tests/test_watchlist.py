"""Reading list files: one film per line with an IMDb ID, in file order."""
import os, tempfile, unittest
from scripts.sources import Sources, check_file, read_watchlist
from tests.helpers import write


class Watchlist(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()

    def file(self, text):
        return write(self.base, "playlists/list.md", text)

    def test_lines_in_order_with_labels(self):
        p = self.file("""
            # 80s Horror

            A description that mentions no ID.

            - tt0084787 | The Thing (1982) John Carpenter's best
            - tt0080749 | The Fog (1980)
            1. tt0087800 A Nightmare on Elm Street (1984)
            | 4 | tt0091064 | The Fly (1986) |
            """)
        rows = read_watchlist(p)
        self.assertEqual([r[1] for r in rows], ["tt0084787", "tt0080749", "tt0087800", "tt0091064"])
        self.assertEqual(rows[0][0], 5)                      # line numbers, for check's messages
        self.assertEqual(rows[1][2], "The Fog (1980) (tt0080749)")
        self.assertIn("The Thing (1982)", rows[0][2])

    def test_comments_and_code_blocks_are_ignored(self):
        p = self.file("""
            - tt0084787 | The Thing (1982)
            <!-- - tt0080749 | The Fog (1980)
            - tt0087800 | still in the comment -->
            ```
            - tt0091064 | The Fly (1986) in a code block
            ```
            - tt0083907 | The Evil Dead (1981)
            """)
        self.assertEqual([r[1] for r in read_watchlist(p)], ["tt0084787", "tt0083907"])

    def test_items_are_any_kind_with_imdb_ids(self):
        self.file("- tt0084787 | The Thing (1982)\n- tt0108778 | Friends (1994)\n")
        items = Sources({}, self.base).items("playlists/list.md")
        self.assertEqual([it.ids["imdb"] for it in items], ["tt0084787", "tt0108778"])
        self.assertTrue(all(it.kind == "any" for it in items))

    def test_check_finds_repeats_and_lines_without_an_id(self):
        p = self.file("""
            - tt0084787 | The Thing (1982)
            - The Fog (1980)
            - tt0084787 | The Thing again (1982)
            """)
        count, issues = check_file(p)
        self.assertEqual(count, 2)
        self.assertTrue(any("already on line 1" in i for i in issues), issues)
        self.assertTrue(any("line 2 has no IMDb ID" in i for i in issues), issues)

    def test_empty_list_is_a_problem(self):
        _, issues = check_file(self.file("# Nothing yet\n"))
        self.assertTrue(issues)

    def test_missing_file(self):
        with self.assertRaises(Exception):
            Sources({}, self.base).items("playlists/nope.md")


if __name__ == "__main__":
    unittest.main()
