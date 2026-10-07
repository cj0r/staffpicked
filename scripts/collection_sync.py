"""Collections: one per [[collection]] in collections.toml, kept in step with its lists.

Each run adds what the lists gained and removes what they lost. Outside its active
window a collection is deleted (the media is untouched) and it returns when the
window opens. An existing collection with the same name (any capitalization) is updated
in place, never duplicated. Collections with names not in the config are never touched."""
import datetime
from . import settings
from .results import Results
from .state import apply_artwork
from .util import Brake, describe, is_active, title


class CollectionSync:
    def __init__(self, server, uid, cfg, src, art, state, log, results=None):
        self.server, self.uid, self.cfg, self.src, self.art, self.state, self.log = \
            server, uid, cfg, src, art, state, log
        self.results = results or Results("", dry_run=True)
        self.existing = {}    # lower-cased name -> id, so "Halloween" and "halloween" are one collection
        for name, cid in server.collections(uid).items():
            self.existing.setdefault(name.lower(), cid)
        self.library = None
        self.members = []
        self.rename_failed = set()   # entries whose old name, from before a rename, is still there
        self.brake = Brake()         # sync_server sets the real one from the settings

    def run(self, today, only=None, remove_all=False, renamed=None):
        """renamed: {new name, lower-cased: [old names]}; the old ones are removed."""
        self.rename_failed = set()
        for entry in self.cfg.entries:
            if only and entry.name.lower() != only.lower():
                continue
            self.log(f"\n[collection] {entry.name}")
            self.log.begin("collection", entry.name, self.server.label)
            try:
                for old in (renamed or {}).get(entry.name.lower(), []):
                    if old.lower() in self.existing:
                        self.log(f"  renamed from '{old}'")
                        self.rename_failed.add(entry.name.lower())
                        self.remove(old)
                        self.rename_failed.discard(entry.name.lower())
                if remove_all or not is_active(entry.active, today):
                    if not remove_all:
                        self.log("  inactive today")
                        self.results.record("collection", entry.name, self.server.label, off_season=True,
                                            errors=0, error="")
                    self.remove(entry.name)
                else:
                    self.sync(entry)
            except Exception as e:
                self.log.error(describe(e))
                self.results.error("collection", entry.name, self.server.label, describe(e))
            self.log.end()
        if not remove_all and self.members and self.cfg.get("refresh_new_releases", False):
            self.refresh(today)

    def remove(self, name):
        cid = self.existing.get(name.lower())
        if cid:
            self.log.change(f"removing collection '{name}'")
            if not self.log.dry_run:
                self.server.delete(cid)
                self.existing.pop(name.lower())
                images = self.state.images(self.server)
                for key in [k for k in images if k.startswith(f"{cid}/")]:
                    del images[key]

    def sync(self, entry):
        if self.library is None:
            self.library = self.server.library(self.uid)
        items = [it for s in entry.sources for it in self.src.items(s)]
        wanted, missing = self.library.match(items)
        self.members += wanted
        self.log(f"  {len(wanted)} in library, {len(missing)} of {len(items)} listed items not in library")
        cid = self.existing.get(entry.name.lower())
        have = self.server.children(self.uid, cid) if cid else set()
        drop = sorted(have - set(wanted))
        held = self.brake.check(len(drop), len(have))
        if held:
            self.log.error(held)
            self.log(f"  {Brake.HINT}")
            self.results.matched("collection", entry.name, self.server.label, items, missing, added=0, removed=0,
                                 held=True, errors=1, error=held, members=len(have))
            return
        if not wanted:
            self.log("  nothing from the lists is in the library")
            self.remove(entry.name)
            self.results.matched("collection", entry.name, self.server.label, items, missing, added=0, removed=0)
            return
        add = []
        if not cid:
            add = wanted
            self.log.change(f"creating collection with {len(wanted)} items")
            self.log.added += len(add)
            self.log.films(self.titles(add), [])
            if self.log.dry_run:
                return
            cid = self.existing[entry.name.lower()] = self.server.create_collection(entry.name, wanted)
        else:
            add = [i for i in wanted if i not in have]
            self.log.added += len(add)
            self.log.removed += len(drop)
            self.log.films(self.titles(add), self.titles(drop))
            if add:
                self.log.change(f"adding {len(add)}")
                if not self.log.dry_run:
                    self.server.add_to_collection(cid, add)
            if drop:
                self.log.change(f"removing {len(drop)} no longer on the lists")
                if not self.log.dry_run:
                    self.server.remove_from_collection(cid, drop)
        self.results.matched("collection", entry.name, self.server.label, items, missing,
                             added=len(add), removed=len(drop), members=len(wanted))
        self.details(entry, cid)
        apply_artwork(self.server, self.art, self.state, entry, cid, self.log)

    def titles(self, ids):
        return [title(self.library.by_id.get(i)) for i in ids]

    def details(self, entry, cid):
        description = entry.description
        if not description and self.cfg.get("use_list_descriptions", False):
            description = next((d for d in map(self.src.description, entry.sources) if d), "")
        order = settings.DISPLAY_ORDERS.get(entry.display_order)
        if not (description or entry.sort_name or order):
            return
        item = self.server.get_item(self.uid, cid)
        changes = {}
        if description and item.get("Overview") != description:
            changes["Overview"] = description
        if entry.sort_name and item.get("ForcedSortName") != entry.sort_name:
            changes["ForcedSortName"] = entry.sort_name
        if order and item.get("DisplayOrder") != order:
            changes["DisplayOrder"] = order
        if changes:
            what = {"Overview": "description", "ForcedSortName": "sort name", "DisplayOrder": "display order"}
            self.log.change("updating " + " and ".join(what[k] for k in changes))
            if not self.log.dry_run:
                item.update(changes)
                self.server.update_item(item)

    def refresh(self, today):
        """Refresh metadata of items both added and released recently, so new releases' ratings settle."""
        added_days = int(self.cfg.get("new_release_added_days", 10))
        released_days = int(self.cfg.get("new_release_released_days", 30))

        def age(value):
            try:
                return (today - datetime.date.fromisoformat(value[:10])).days
            except (TypeError, ValueError):
                return None
        due = []
        for i in dict.fromkeys(self.members):
            it = self.library.by_id.get(i, {})
            added, released = age(it.get("DateCreated")), age(it.get("PremiereDate"))
            if added is not None and released is not None and added <= added_days and released <= released_days:
                due.append(it)
        if not due:
            return
        self.log(f"\nRefreshing metadata of {len(due)} new release(s): " + ", ".join(it.get("Name", "?") for it in due)
                 + (" (dry run)" if self.log.dry_run else ""))
        if not self.log.dry_run:
            for it in due:
                try:
                    self.server.refresh(it["Id"])
                except Exception as e:
                    self.log.warn(f"refresh of {it.get('Name')} failed ({describe(e)})")
