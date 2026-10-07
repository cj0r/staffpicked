"""Every config file opens with a commented KEY block listing each setting it takes. These
tests keep the blocks in step with what StaffPicked actually reads."""
import os, re, unittest
from scripts import settings
from tests.helpers import ROOT


def key_block(name):
    with open(os.path.join(ROOT, "config", name), encoding="utf-8") as f:
        text = f.read()
    start = text.index("KEY:")
    end = text.index("# ====", text.index("# ====", start) + 1)   # the block closes with a rule
    return text[start:end]


class KeyBlocks(unittest.TestCase):
    def test_env_key_lists_every_setting(self):
        block = key_block("staffpicked.env.example")
        skip = {"STAFFPICKED_CONFIG", "TZ"}      # set by Docker, not in the file
        for key in sorted(set(settings.ENV_KEYS) - skip):
            with self.subTest(key=key):
                self.assertRegex(block, rf"#\s+{key}\b")

    def test_env_key_names_the_numbered_server_settings(self):
        block = key_block("staffpicked.env.example")
        for field in settings.SERVER_FIELDS:
            with self.subTest(field=field):
                self.assertIn(f"SERVER_2_{field}", block)

    def test_env_example_sets_only_known_keys(self):
        with open(os.path.join(ROOT, "config", "staffpicked.env.example"), encoding="utf-8") as f:
            keys = [m[1] for line in f if (m := re.match(r"^([A-Z_0-9]+)=", line))]
        for key in keys:
            with self.subTest(key=key):
                self.assertTrue(key in settings.ENV_KEYS or settings.NUMBERED.match(key), key)

    def test_toml_keys_list_every_setting(self):
        for kind, name in (("collection", "collections.toml.example"), ("playlist", "playlists.toml.example"),
                           ("genre", "genres.toml.example")):
            block = key_block(name)
            entry_keys, setting_keys = settings.SHAPES[kind]
            old = {"source", "backdrop"}       # older singular spellings, still read but not shown
            for key in sorted((entry_keys | setting_keys) - old):
                with self.subTest(file=name, key=key):
                    self.assertRegex(block, rf"#\s+{key} = ")

    def test_examples_load_cleanly(self):
        for kind, name in (("collection", "collections.toml"), ("playlist", "playlists.toml"),
                           ("genre", "genres.toml")):
            with self.subTest(file=name):
                cfg = settings.Config(kind, os.path.join(ROOT, "config", name + ".example"))
                self.assertFalse({n: p for n, p in cfg.problems().items() if p})


if __name__ == "__main__":
    unittest.main()
