"""Earlier versions of config files are kept in backups/ so a save can be undone."""
import os, tempfile, time, unittest
from scripts import backups
from tests.helpers import write


class Backups(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()

    def test_new_files_have_nothing_to_keep(self):
        self.assertIsNone(backups.keep(self.base, os.path.join(self.base, "playlists.toml")))
        self.assertEqual(backups.versions(self.base, "playlists.toml"), [])

    def test_keeps_text_newest_first(self):
        p = write(self.base, "playlists/my list.md", "one\n")
        backups.keep(self.base, p)
        write(self.base, "playlists/my list.md", "two\n")
        backups.keep(self.base, p)
        v = backups.versions(self.base, "playlists/my list.md")
        self.assertEqual([backups.read(self.base, "playlists/my list.md", x["id"]) for x in v], ["two\n", "one\n"])

    def test_same_text_twice_keeps_one(self):
        p = write(self.base, "genres.toml", "same\n")
        backups.keep(self.base, p)
        self.assertIsNone(backups.keep(self.base, p))
        self.assertEqual(len(backups.versions(self.base, "genres.toml")), 1)

    def test_only_the_newest_are_kept(self):
        p = os.path.join(self.base, "collections.toml")
        for n in range(backups.KEEP + 3):
            write(self.base, "collections.toml", f"v{n}\n")
            backups.keep(self.base, p)
            time.sleep(0.001)
        v = backups.versions(self.base, "collections.toml")
        self.assertEqual(len(v), backups.KEEP)
        self.assertEqual(backups.read(self.base, "collections.toml", v[0]["id"]), f"v{backups.KEEP + 2}\n")

    def test_files_outside_the_config_folder_are_left_alone(self):
        other = tempfile.NamedTemporaryFile(delete=False)
        other.write(b"x")
        other.close()
        self.assertIsNone(backups.keep(self.base, other.name))
        self.assertFalse(os.path.exists(os.path.join(self.base, "backups")))

    def test_bad_ids_are_refused(self):
        write(self.base, "genres.toml", "x\n")
        for bad in ("../../etc/passwd", "", "2026"):
            with self.subTest(bad=bad), self.assertRaises(FileNotFoundError):
                backups.read(self.base, "genres.toml", bad)


if __name__ == "__main__":
    unittest.main()
