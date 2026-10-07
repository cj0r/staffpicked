"""Shared bits for the tests: a throwaway config folder and running the CLI on it."""
import os, subprocess, sys, tempfile, textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def write(base, rel, text):
    path = os.path.join(base, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(text).lstrip("\n"))
    return path


def config_dir(server_url="", **files):
    """A temp config folder with a staffpicked.env pointing at server_url and the given files
    ({"collections.toml": "...", "collections/x.md": "..."}; use __ for / in keyword names)."""
    base = tempfile.mkdtemp(prefix="staffpicked-test-")
    write(base, "staffpicked.env", f"""
        SERVER_TYPE=emby
        SERVER_URL={server_url}
        SERVER_API_KEY=test-key
        SERVER_USER=admin
        ENABLE_COLLECTIONS=true
        ENABLE_PLAYLISTS=true
        ENABLE_GENRES=false
        SYNC_ON_START=false
        """)
    for name, text in files.items():
        write(base, name.replace("__", "/"), text)
    return base


def clean_env(**extra):
    """The process environment without any StaffPicked settings, so the env file decides."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("SERVER_", "ENABLE_", "MDBLIST", "TRAKT", "TMDB", "FANARTTV", "TPDB", "DRY_RUN",
                                "STAFFPICKED", "SYNC_", "REMOVAL_", "NEW_FILM", "WATCHED_BY", "PLAYLIST_USERS", "LINKED_USERS",
                                "TRUSTED_PROXIES", "URL_BASE"))}
    env.update(PYTHONPATH=ROOT, **extra)
    return env


def cli(base, *args):
    """Run python -m scripts on a config folder. Returns (exit code, output)."""
    p = subprocess.run([sys.executable, "-m", "scripts", *args, "--config", base,
                        "--env", os.path.join(base, "staffpicked.env")],
                       cwd=ROOT, env=clean_env(), capture_output=True, text=True, timeout=120)
    return p.returncode, p.stdout + p.stderr
