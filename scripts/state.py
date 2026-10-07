"""A small JSON file remembering which images were uploaded, so unchanged ones aren't sent again."""
import hashlib, json, os
from . import artwork


class State:
    def __init__(self, path, dry_run=False):
        self.path, self.dry_run = path, dry_run
        try:
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)
        except (OSError, ValueError):
            self.data = {}

    def images(self, server):
        """{item id/kind/index: digest} of the images uploaded to one server. Server 1 keeps the
        top-level table it always had; other servers each get their own, by URL, since item ids
        from two servers can be the same."""
        if getattr(server, "sid", "1") == "1":
            return self.data.setdefault("images", {})
        return self.data.setdefault("servers", {}).setdefault(server.url, {}).setdefault("images", {})

    def save(self):
        if self.dry_run:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=1, sort_keys=True)


LABELS = {"Primary": "poster", "Thumb": "thumb", "Backdrop": "backdrop"}   # server image type -> setting


def apply_artwork(server, art, state, entry, item_id, log, remember=True):
    """Upload an entry's poster, thumb and backdrops to a server item, skipping images already there.
    remember=False uploads them all whatever the last run sent."""
    images = [(kind, 0, spec) for kind, spec in (("Primary", entry.poster), ("Thumb", entry.thumb)) if spec] + \
             [("Backdrop", i, b) for i, b in enumerate(entry.backdrops)]
    seen = state.images(server)
    for kind, index, spec in images:
        label = LABELS[kind]
        try:
            data, ctype = art.fetch(spec, label)
        except Exception as e:
            log.warn(f"could not get {label} {spec} ({e})")
            continue
        keep_copy(art.base_dir, entry, label, index, spec, data, ctype, log)
        key = f"{item_id}/{kind}/{index}"
        digest = hashlib.sha256(data).hexdigest()
        if remember and seen.get(key) == digest:
            continue
        log.change(f"setting {label} from {spec}")
        if log.dry_run:
            continue
        try:
            server.set_image(item_id, kind, index, data, ctype)
            if remember:
                seen[key] = digest
        except Exception as e:
            log.warn(f"could not set {label} ({e})")


def keep_copy(base_dir, entry, label, index, spec, data, ctype, log):
    """Keep a copy of a downloaded image in images/, next to the local ones. When the image
    changes, the old copy is archived, never deleted. A local file is already in the config
    folder, so it needs no copy, and images/ is left alone: a file there is the user's to keep."""
    if not artwork.is_remote(spec):
        return
    stem = artwork.copy_name(entry.what, entry.name, label, index)
    try:
        saved, archived = artwork.save_copy(base_dir, stem, data, ctype, log.dry_run)
    except OSError as e:
        log.warn(f"could not save a copy of the {label} in images/ ({e})")
        return
    dry = " (dry run)" if log.dry_run else ""
    for path in archived:
        log(f"  archived the old {label} as {os.path.relpath(path, base_dir)}{dry}")
    if saved:
        log(f"  saved the {label} as {os.path.relpath(saved, base_dir)}{dry}")
