"""Collections and playlists renamed in the web UI, waiting for their old copy to come off the servers.

Sync finds collections and playlists by name, so after a rename it would build the new one and
leave the old one behind. The builder writes each rename to cache/renames.json; the next sync
removes the old one from every server the entry goes to (logging it), then forgets the rename.
Only a name StaffPicked itself managed is removed, and never one a current entry still uses.
"""
import json, os

FILE = os.path.join("cache", "renames.json")


def path(base):
    return os.path.join(base, FILE)


def load(base):
    try:
        with open(path(base), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    return [r for r in data if isinstance(r, dict) and r.get("kind") and r.get("old") and r.get("new")] \
        if isinstance(data, list) else []


def save(base, records):
    p = path(base)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=1)
    os.replace(tmp, p)


def add(base, kind, old, new):
    """Remember that an entry of this kind (collection or playlist) went from old to new."""
    old, new = old.strip(), new.strip()
    if not old or not new or old.lower() == new.lower():
        return
    records = []
    for r in load(base):
        if r["kind"] == kind and r["old"].lower() == new.lower():
            continue        # renamed back: the old one is wanted again
        if r["kind"] == kind and r["new"].lower() == old.lower():
            r = {**r, "new": new, "done": []}    # A -> B -> C: A goes too, on every server
        records.append(r)
    if not any(r["kind"] == kind and r["old"].lower() == old.lower() for r in records):
        records.append({"kind": kind, "old": old, "new": new, "done": []})
    save(base, records)


def pending(records, kind, names):
    """{new name, lower-cased: [old names]} for one kind, leaving out an old name that an entry
    (names: every entry of that kind) still uses."""
    taken = {n.lower() for n in names}
    out = {}
    for r in records:
        if r["kind"] == kind and r["old"].lower() not in taken:
            out.setdefault(r["new"].lower(), []).append(r["old"])
    return out


def finish(base, entries, servers, done):
    """Mark the renames handled on the servers in done ({server url: {kind: lower-cased names of
    the entries synced there without an error}}) and forget the ones finished everywhere.
    entries is {kind: every entry of that kind}, for the kinds turned on. Re-reads the file
    first, so a rename saved during the sync is kept."""
    records = load(base)
    keep = []
    for r in records:
        kind_entries = entries.get(r["kind"])
        entry = next((e for e in kind_entries if e.name.lower() == r["new"].lower()), None) \
            if kind_entries is not None else None
        if kind_entries is not None and not entry:
            continue        # the entry was deleted since; nothing left to rename
        marks = set(r.get("done") or [])
        for url, names in done.items():
            if r["kind"] in names and r["new"].lower() in names[r["kind"]]:
                marks.add(url)
        r = {**r, "done": sorted(marks)}
        if entry and all(s["env"].get("SERVER_URL") in marks for s in servers if entry.on(s["name"])):
            continue
        keep.append(r)
    if keep != records:
        save(base, keep)
