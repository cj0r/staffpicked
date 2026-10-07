"""The web UI's modules, pointed at a throwaway config folder. backend.py reads the folder once,
when it's first imported, so every test that uses it shares this one; reset() empties it."""
import os, shutil, sys, tempfile
from tests.helpers import ROOT

CONFIG = tempfile.mkdtemp(prefix="staffpicked-web-")
os.environ["STAFFPICKED_CONFIG"] = CONFIG
sys.path.insert(0, os.path.join(ROOT, "web"))
import backend, builder  # noqa: E402

assert backend.CONFIG_DIR == CONFIG, "backend was imported before tests.webenv"


def reset():
    for name in os.listdir(CONFIG):
        p = os.path.join(CONFIG, name)
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
