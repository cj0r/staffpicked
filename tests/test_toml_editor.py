"""The web UI's entry editor rewrites one [[collection]] or [[playlist]] at a time and leaves
every comment and every other entry exactly as it was."""
import os, tomllib, unittest
from tests import webenv
from tests.helpers import write

backend, builder = webenv.backend, webenv.builder

ORIGINAL = """\
# My collections. This comment stays.

[settings]
use_list_descriptions = false   # trailing comments stay too

# --- Halloween ---
[[collection]]
name = "80s Horror"
# where the films come from
sources = [
  "collections/80s.md",      # my own list
]
active = "09-30 to 11-02"
description = "Rubber suits."

[[collection]]
name = "Christmas"
sources = ["collections/xmas.md"]
active = "12-01 to 12-31"
"""


class TomlEditor(unittest.TestCase):
    def setUp(self):
        webenv.reset()
        self.path = write(webenv.CONFIG, "collections.toml", ORIGINAL)
        write(webenv.CONFIG, "collections/80s.md", "- tt0084787 | The Thing (1982)\n")
        write(webenv.CONFIG, "collections/xmas.md", "- tt0087363 | Gremlins (1984)\n")
        write(webenv.CONFIG, "staffpicked.env", "SERVER_URL=http://x\nSERVER_API_KEY=k\n")

    def text(self):
        with open(self.path, encoding="utf-8") as f:
            return f.read()

    def entries(self):
        return builder.entries("collections")

    def save(self, index, **changes):
        e = self.entries()
        entry = {**(e["entries"][index] if index is not None else {}), **changes}
        entry.pop("index", None)
        return builder.save_entry("collections", index, entry, e["version"], {})

    def test_unchanged_save_changes_nothing(self):
        self.save(0)
        self.assertEqual(self.text(), ORIGINAL)

    def test_one_setting_changes_and_the_rest_keeps_its_comments(self):
        self.save(0, active="10-01 to 11-02")
        text = self.text()
        self.assertIn('active = "10-01 to 11-02"\n', text)
        self.assertEqual(text.replace('active = "10-01 to 11-02"', 'active = "09-30 to 11-02"', 1), ORIGINAL)

    def test_other_entries_are_untouched(self):
        self.save(1, description="Snow and gremlins.")
        text = self.text()
        self.assertTrue(text.startswith(ORIGINAL.rstrip("\n")))
        self.assertTrue(text.endswith('description = "Snow and gremlins."\n'))
        data = tomllib.loads(text)
        self.assertEqual(data["collection"][1]["description"], "Snow and gremlins.")
        self.assertEqual(data["collection"][0], tomllib.loads(ORIGINAL)["collection"][0])

    def test_quotes_and_unicode_survive(self):
        self.save(0, description='She said "boo" — twice')
        self.assertEqual(tomllib.loads(self.text())["collection"][0]["description"], 'She said "boo" — twice')

    def test_new_entry_goes_at_the_end(self):
        out = self.save(None, name="Summer", sources=["collections/80s.md"], active="06-01 to 08-31")
        self.assertEqual(out["index"], 2)
        text = self.text()
        self.assertTrue(text.startswith(ORIGINAL))
        self.assertEqual(tomllib.loads(text)["collection"][2]["name"], "Summer")

    def test_delete_takes_out_only_that_entry(self):
        builder.delete_entry("collections", 0, self.entries()["version"])
        text = self.text()
        self.assertIn("# My collections. This comment stays.", text)
        self.assertNotIn("80s Horror", text)
        self.assertEqual([c["name"] for c in tomllib.loads(text)["collection"]], ["Christmas"])

    def test_a_stale_version_is_refused(self):
        e = self.entries()
        write(webenv.CONFIG, "collections.toml", ORIGINAL + "\n# edited elsewhere\n")
        with self.assertRaises(builder.Conflict):
            builder.save_entry("collections", 0, {**e["entries"][0], "active": ""}, e["version"], {})

    def test_line_breaks_are_refused(self):
        with self.assertRaises(builder.Invalid):
            self.save(0, description="two\nlines")
        self.assertEqual(self.text(), ORIGINAL)

    def test_each_save_keeps_a_backup(self):
        self.save(0, active="10-01 to 11-02")
        self.save(0, active="10-05 to 11-02")
        mod = backend.backups_module()
        versions = mod.versions(webenv.CONFIG, "collections.toml")
        self.assertEqual(len(versions), 2)
        self.assertEqual(mod.read(webenv.CONFIG, "collections.toml", versions[-1]["id"]), ORIGINAL)
        self.assertIn('"10-01 to 11-02"', mod.read(webenv.CONFIG, "collections.toml", versions[0]["id"]))


if __name__ == "__main__":
    unittest.main()
