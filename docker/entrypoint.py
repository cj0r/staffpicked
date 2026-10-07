"""Container start: run StaffPicked as the user that owns your config folder.

The container starts as root only long enough to make /config writable for one user, then
drops to that user and runs the command. The user is PUID:PGID when set; otherwise whoever
owns the config folder on the host, or 1000:1000 when that's root (a folder Docker created).
Under rootless Docker or Podman, root in the container is already the host user, so it
stays root. Started with a fixed user instead (docker run --user, compose "user:"), it runs
the command as is.
"""
import os, sys

CONFIG = os.environ.get("STAFFPICKED_CONFIG", "/config")


def rootless():
    """True when container root is mapped to an ordinary host user (rootless Docker, Podman)."""
    try:
        with open("/proc/self/uid_map") as f:
            inside, outside, _ = f.readline().split()
        return inside == "0" and outside != "0"
    except (OSError, ValueError):
        return False


def ids():
    """PUID:PGID if set, else the config folder's owner, else 1000:1000 (or 0:0 when rootless)."""
    puid, pgid = os.environ.get("PUID", "").strip(), os.environ.get("PGID", "").strip()
    try:
        if puid or pgid:
            return int(puid or 1000), int(pgid or puid or 1000)
    except ValueError:
        sys.exit("ERROR: PUID and PGID must be numbers, e.g. PUID=1000 PGID=1000")
    if rootless():
        return 0, 0
    try:
        st = os.stat(CONFIG)
        if st.st_uid != 0:
            return st.st_uid, st.st_gid
    except OSError:
        pass
    return 1000, 1000


def own(uid, gid):
    """Give /config and everything in it to uid:gid, touching only what isn't theirs already."""
    os.makedirs(CONFIG, exist_ok=True)
    for root, dirs, files in os.walk(CONFIG):
        for path in [root] + [os.path.join(root, f) for f in files]:
            try:
                st = os.lstat(path)
                if (st.st_uid, st.st_gid) != (uid, gid):
                    os.lchown(path, uid, gid)
            except OSError as e:
                print(f"WARNING: could not change the owner of {path} ({e})", file=sys.stderr)


def main():
    cmd = sys.argv[1:] or ["python", "/app/web/server.py"]
    if os.getuid() == 0:
        uid, gid = ids()
        print(f"StaffPicked runs as user {uid}, group {gid}", flush=True)
        if uid != 0:
            own(uid, gid)
            os.setgroups([gid])
            os.setgid(gid)
            os.setuid(uid)
            os.environ["HOME"] = CONFIG
    os.execvp(cmd[0], cmd)


if __name__ == "__main__":
    main()
