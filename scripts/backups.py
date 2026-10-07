"""Earlier versions of the config files, so a save can be undone.

Before collections.toml, playlists.toml, genres.toml or a list file is overwritten or deleted,
its current text is copied to backups/ in the config folder, named after the file and the time:
backups/playlists.toml/20261003-061500-123456. The newest KEEP copies of each file are kept.
Restoring is a save like any other, so it backs up what it replaces too."""
import datetime, os, re

KEEP = 10
DIR = "backups"
STAMP = re.compile(r"^\d{8}-\d{6}-\d{6}$")


def _folder(config_dir, rel):
    return os.path.join(config_dir, DIR, *rel.replace("\\", "/").split("/"))


def _rel(config_dir, path):
    rel = os.path.relpath(os.path.abspath(path), os.path.abspath(config_dir)).replace(os.sep, "/")
    if rel.startswith("../") or rel == ".." or rel.startswith(DIR + "/"):
        return None      # only files inside the config folder, and never the backups themselves
    return rel


def keep(config_dir, path):
    """Copy the file at path into backups/ before it changes. Returns the copy's path, or None
    when there's nothing to keep (a new file, or one outside the config folder)."""
    rel = _rel(config_dir, path)
    if not rel or not os.path.isfile(path):
        return None
    folder = _folder(config_dir, rel)
    os.makedirs(folder, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = os.path.join(folder, stamp)
    with open(path, "rb") as f:
        data = f.read()
    newest = versions(config_dir, rel)[:1]
    if newest and _read(config_dir, rel, newest[0]["id"]) == data:
        return None      # the same text as the last copy; saving twice keeps one
    with open(target, "wb") as f:
        f.write(data)
    for old in versions(config_dir, rel)[KEEP:]:
        os.remove(os.path.join(folder, old["id"]))
    return target


def versions(config_dir, rel):
    """The saved copies of one file, newest first: [{id, at, size}]."""
    folder = _folder(config_dir, rel)
    try:
        names = [n for n in os.listdir(folder) if STAMP.match(n)]
    except OSError:
        return []
    out = []
    for n in sorted(names, reverse=True):
        at = datetime.datetime.strptime(n, "%Y%m%d-%H%M%S-%f").astimezone()
        out.append({"id": n, "at": at.isoformat(timespec="seconds"), "size": os.path.getsize(os.path.join(folder, n))})
    return out


def _read(config_dir, rel, version_id):
    with open(os.path.join(_folder(config_dir, rel), version_id), "rb") as f:
        return f.read()


def read(config_dir, rel, version_id):
    """The text of one saved copy. Raises FileNotFoundError for an unknown one."""
    if not STAMP.match(version_id or "") or not _rel(config_dir, os.path.join(config_dir, rel)):
        raise FileNotFoundError(version_id)
    return _read(config_dir, rel, version_id).decode("utf-8")

