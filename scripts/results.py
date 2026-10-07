"""What the last sync found for each collection, playlist and genre, kept for the web UI.

One file per kind in cache/ (results-collection.json and so on), so a collections run and a
playlists run never write the same file. Each holds, per entry and per media server:

  at          when it was synced
  errors      problems the sync hit for this entry (0 when it went fine), and the last one
  listed      films and shows on its lists, repeats counted once
  in_library  how many of those the server has
  have        IMDb IDs of the ones it has
  missing     the ones it doesn't: [{imdb, title, year}]
  added, removed   what changed on the server this time

Dry runs change nothing, so they don't write here either."""
import datetime, json, os

MAX_MISSING = 1000     # plenty for any list, and keeps the file small for a huge one


def _now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def path(base_dir, kind):
    return os.path.join(base_dir, "cache", f"results-{kind}.json")


def load(base_dir, kind):
    """{lower-cased entry name: {server name: result}} from the last syncs, or {}."""
    try:
        with open(path(base_dir, kind), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def item_key(item):
    return item.ids.get("imdb") or f"{item.title}|{item.year}"


class Results:
    def __init__(self, base_dir, dry_run=False):
        self.base_dir, self.dry_run = base_dir, dry_run
        self.data, self.changed = {}, set()
        self.matched_now = set()     # (kind, name, server) already read against a library this run

    def _kind(self, kind):
        if kind not in self.data:
            self.data[kind] = load(self.base_dir, kind)
        return self.data[kind]

    def record(self, kind, name, server, **fields):
        """Store (or add to) what this run found for one entry on one server."""
        if self.dry_run or not name:
            return
        entry = self._kind(kind).setdefault(name.lower(), {})
        row = entry.get(server) if isinstance(entry.get(server), dict) else {}
        if fields.pop("fresh", False):
            row = {}
        row.update(name=name, at=_now(), **fields)
        row.setdefault("errors", 0)
        entry[server] = row
        self.changed.add(kind)

    def matched(self, kind, name, server, items, missing, **fields):
        """Record a list read against the library: items as read from its sources, and the
        ones the server doesn't have."""
        gone = {id(m) for m in missing}
        seen, have, lost = set(), [], []
        for it in items:
            key = item_key(it)
            if key in seen:
                continue
            seen.add(key)
            if id(it) in gone:
                lost.append({"imdb": it.ids.get("imdb", ""), "title": it.title, "year": it.year})
            elif it.ids.get("imdb"):
                have.append(it.ids["imdb"])
        key = (kind, name.lower(), server)
        prev = self._kind(kind).get(name.lower(), {}).get(server) if key in self.matched_now else None
        if isinstance(prev, dict):
            # the same entry again on this server, for another person (a private playlist copy
            # each): each person sees their own libraries, so a film is only missing when nobody's
            # library has it, and the counts add up across their copies
            have = list(dict.fromkeys(prev.get("have", []) + have))
            got = set(have)
            lost = [m for m in prev.get("missing", []) + lost if m.get("imdb") not in got]
            lost = list({(m.get("imdb") or f"{m.get('title')}|{m.get('year')}"): m for m in lost}.values())
            for k in ("added", "removed"):
                if k in fields:
                    fields[k] += prev.get(k) or 0
            for k in ("members", "watched"):
                if k in fields:
                    fields[k] = max(fields[k], prev.get(k) or 0)
        self.matched_now.add(key)
        self.record(kind, name, server, fresh=True, listed=len(seen), in_library=len(seen) - len(lost),
                    have=have, missing=lost[:MAX_MISSING], missing_count=len(lost), **fields)

    def error(self, kind, name, server, message):
        """An entry that failed: keep what the last good sync found, and note the problem."""
        self.record(kind, name, server, errors=1, error=message)

    def save(self):
        if self.dry_run:
            return
        for kind in self.changed:
            p = path(self.base_dir, kind)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data[kind], f, indent=1, sort_keys=True)
            os.replace(tmp, p)
        self.changed.clear()
