"""Playlists: one per [[playlist]] in playlists.toml, in the order of its lists.

Collections can only sort by name or date, so playlists are what keep a custom
order. Each run updates every active playlist in place (adds, removes and reorders, so
it stays the same playlist on the server), drops films already watched (unless
include_watched), and removes playlists whose window has ended. A run that would take
most of a playlist off is held back (see util.Brake).
Only playlists are touched: a collection with the same name is left alone.

Two ways to run, chosen in staffpicked.env:
  shared (default)   SERVER_USER owns one playlist per entry. share = "view" lets every
                     other user see it, which needs SERVER_PASSWORD (Emby only accepts
                     sharing from the owner signed in). WATCHED_BY names the users whose
                     viewing drops a film.
  per person         PLAYLIST_USERS gives each of those users a private copy that hides
                     only what THEY watched (plus anyone linked to them in LINKED_USERS).
"""
from .results import Results
from .state import apply_artwork
from .util import Brake, describe, is_active, title


class Watchers:
    """Which users count for a playlist, and what each has played (cached per run)."""

    def __init__(self, server, owner_id, default, log):
        self.server, self.owner_id, self.default, self.log = server, owner_id, default, log
        self.played, self.users = {}, None

    def resolve(self, setting):
        setting = setting or self.default
        if not setting:
            return [(self.owner_id, "playlist owner")]
        if self.users is None:
            self.users = self.server.users()
        found = []
        for want in (w.strip() for w in setting.split(",") if w.strip()):
            u = next((u for u in self.users if want.lower() in (u["Name"].lower(), u["Id"].lower())), None)
            if u:
                found.append((u["Id"], u["Name"]))
            else:
                self.log.warn(f"watched-by user {want!r} not found; ignoring it")
        return found

    def played_by(self, uid):
        if uid not in self.played:
            self.played[uid] = self.server.played(uid)
        return self.played[uid]


class Owner:
    """The playlist owner. Sharing (and on Jellyfin, reordering) needs the owner signed in, not
    the API key. password None: never try to sign in (a PLAYLIST_USERS person, whose password
    StaffPicked doesn't have; wrong guesses could lock them out)."""

    def __init__(self, server, user, password):
        self.server, self.id, self.name, self.password = server, user["Id"], user["Name"], password
        self.token, self.login_error = None, None
        if password is None:
            self.login_error = f"StaffPicked can't sign in as '{self.name}'"

    def session(self):
        if not self.token and not self.login_error:
            try:
                self.token = self.server.login(self.name, self.password)
            except Exception as e:
                key = "SERVER_PASSWORD" if self.server.sid == "1" else f"SERVER_{self.server.sid}_PASSWORD"
                self.login_error = (f"could not sign in as '{self.name}' ({describe(e)}). "
                                    f"Set {key} in staffpicked.env (or the password in Settings) to that user's password.")
        return self.token

    def close(self):
        if self.token:
            self.server.logout(self.token)


class PlaylistSync:
    def __init__(self, server, env, cfg, src, art, state, log, results=None):
        self.server, self.env, self.cfg, self.src, self.art, self.state, self.log = \
            server, env, cfg, src, art, state, log
        self.results = results or Results("", dry_run=True)
        self.library, self.library_of = None, None
        self.renamed, self.rename_failed = {}, set()
        self.brake = Brake(env)

    def run(self, today, only=None, remove_all=False, renamed=None):
        """renamed: {new name, lower-cased: [old names]}; the old ones are removed."""
        self.renamed, self.rename_failed = renamed or {}, set()
        entries = [e for e in self.cfg.entries if not only or e.name.lower() == only.lower()]
        people = [p.strip() for p in (self.env.get("PLAYLIST_USERS") or "").split(",") if p.strip()]
        if people:
            users = [self.server.user(p) for p in people]
            for person in users:
                self.log(f"\n=== playlists for {person['Name']} ===")
                owner = Owner(self.server, person, None)
                watchers = Watchers(self.server, person["Id"], self.linked_to(person), self.log)
                self.run_for(owner, watchers, entries, today, remove_all, per_person=True)
            # a shared copy from before, owned by SERVER_USER, is no longer wanted
            main = self.env.get("SERVER_USER")
            if main and main.lower() not in {x.lower() for u in users for x in (u["Name"], u["Id"])}:
                old = self.server.user(main)
                playlists = self.server.playlists(old["Id"])
                for e in entries:
                    for name in [e.name, *self.renamed.get(e.name.lower(), [])]:
                        self.remove(playlists, name)
        else:
            owner = Owner(self.server, self.server.user(self.env.get("SERVER_USER")), self.env.get("SERVER_PASSWORD") or "")
            watchers = Watchers(self.server, owner.id, self.env.get("WATCHED_BY", ""), self.log)
            try:
                self.run_for(owner, watchers, entries, today, remove_all)
            finally:
                owner.close()

    def linked_to(self, person):
        """The person plus everyone linked with them in LINKED_USERS, as a watched-by value."""
        me = {person["Name"].lower(), person["Id"].lower()}
        names = [person["Id"]]
        for group in (self.env.get("LINKED_USERS") or "").split(";"):
            members = [m.strip() for m in group.split(",") if m.strip()]
            if me & {m.lower() for m in members}:
                names += [m for m in members if m.lower() not in me]
        return ", ".join(names)

    def remove(self, playlists, name):
        for old in [p for p in playlists if p["Name"].lower() == name.lower()]:
            self.log.change(f"removing playlist '{name}'")
            if not self.log.dry_run:
                self.server.delete(old["Id"])
                # Jellyfin gives a playlist made again under the same name the same ID, so the
                # images sent to the old one have to go out again
                images = self.state.images(self.server)
                for key in [k for k in images if k.startswith(f"{old['Id']}/")]:
                    del images[key]

    def run_for(self, owner, watchers, entries, today, remove_all, per_person=False):
        playlists = self.server.playlists(owner.id)
        for entry in entries:
            self.log(f"\n[playlist] {entry.name}")
            self.log.begin("playlist", entry.name, self.server.label, owner.name if per_person else "")
            try:
                for old in self.renamed.get(entry.name.lower(), []):
                    if any(p["Name"].lower() == old.lower() for p in playlists):
                        self.log(f"  renamed from '{old}'")
                        self.rename_failed.add(entry.name.lower())
                        self.remove(playlists, old)
                        self.rename_failed.discard(entry.name.lower())
                if remove_all or not is_active(entry.active, today):
                    if not remove_all:
                        self.log("  inactive today")
                        self.results.record("playlist", entry.name, self.server.label, off_season=True,
                                            errors=0, error="")
                    self.remove(playlists, entry.name)
                else:
                    self.build(owner, watchers, playlists, entry, per_person)
            except Exception as e:
                self.log.error(describe(e))
                self.results.error("playlist", entry.name, self.server.label, describe(e))
            self.log.end()

    def build(self, owner, watchers, playlists, entry, per_person):
        if self.library is None or self.library_of != owner.id:
            # each person's own view: they may see different libraries (an HD and a 4K one)
            self.library, self.library_of = self.server.library(owner.id), owner.id
        items = [it for s in entry.sources for it in self.src.items(s)]
        found, missing = self.library.match(items)
        self.log(f"  {len(found)} of {len(items)} in library")
        watched = []
        if not entry.include_watched:
            who = watchers.resolve("" if per_person else entry.watched_by)
            played = set().union(*(watchers.played_by(i) for i, _ in who)) if who else set()
            watched = [i for i in found if i in played]
            found = [i for i in found if i not in played]
            self.log(f"  dropping what these users watched: {', '.join(n for _, n in who) or 'nobody (no users matched)'}")
            if watched:
                names = [self.library.by_id[i].get("Name", "?") for i in watched]
                self.log(f"  skipping {len(watched)} already watched: " + "; ".join(names))
        share = "private" if per_person else entry.share
        # the playlist as it is now: the first one by this name is kept and updated in place, so
        # it stays the same playlist (pins, shortcuts and resume spots survive); extra copies go
        mine = [p for p in playlists if p["Name"].lower() == entry.name.lower()]
        keep, extra = (mine[0], mine[1:]) if mine else (None, [])
        entries = []
        if keep:
            try:
                entries = self.server.playlist_entries(owner.id, keep["Id"])
            except Exception as e:
                self.log.warn(f"couldn't read the playlist ({describe(e)}); building it again")
                extra, keep = [keep, *extra], None
        before = {i for i, _ in entries}
        for old in extra:
            try:
                before |= {m["Id"] for m in self.server.members(owner.id, old["Id"], playlist=True)}
            except Exception:
                pass
        gone = before - set(found)
        # films leaving because someone watched them are expected; anything else past the limit
        # is held back
        held = self.brake.check(len(gone - set(watched)), len(before))
        if held:
            self.log.error(held)
            self.log(f"  {Brake.HINT}")
            self.results.matched("playlist", entry.name, self.server.label, items, missing, added=0, removed=0,
                                 held=True, errors=1, error=held, members=len(before))
            return
        added, removed = len(set(found) - before), len(gone)
        self.log.films([title(self.library.by_id.get(i)) for i in found if i not in before],
                       [title(self.library.by_id.get(i)) for i in sorted(gone)])
        self.log.added += added
        self.log.removed += removed
        self.results.matched("playlist", entry.name, self.server.label, items, missing, added=added,
                             removed=removed, members=len(found), watched=len(watched))
        if not found:
            self.remove(playlists, entry.name)
            self.log("  nothing left to play")
            return
        for old in extra:
            self.log.change(f"removing an extra copy of playlist '{entry.name}'")
            if not self.log.dry_run:
                self.server.delete(old["Id"])
        pid = keep and keep["Id"]
        made = False
        if pid:
            try:
                self.update(owner, pid, entries, found)
            except Exception as e:
                # a server that won't edit playlists in place still gets the right playlist
                self.log.warn(f"couldn't update the playlist in place ({describe(e)}); building it again")
                self.log.noting = False
                self.remove(playlists, entry.name)
                self.log.noting = True
                pid = None
        if not pid:
            if self.log.dry_run:
                self.log.change(f"building playlist with {len(found)} items, sharing: {share}")
                for n, i in enumerate(found[:10], 1):
                    self.log(f"    {n:2}. {self.library.by_id[i].get('Name')} ({self.library.by_id[i].get('ProductionYear')})")
                if len(found) > 10:
                    self.log(f"    ... and {len(found) - 10} more")
            else:
                pid = self.server.create_playlist(owner.id, entry.name, found, public=share == "view")
                made = True
                self.log.change(f"built playlist with {len(found)} items")
        if pid and not self.log.dry_run:
            # a server whose playlists can be public made a new one public or private already;
            # one kept from before may have been made the other way
            if share == "view" and not (made and self.server.PUBLIC_PLAYLISTS):
                self.share(owner, pid)
            elif share == "private" and not made and not per_person and self.server.PUBLIC_PLAYLISTS:
                self.unshare(owner, pid)
            if made and entry.poster:
                self.server.settle_new_playlist(pid)
            apply_artwork(self.server, self.art, self.state, entry, pid, self.log)
        if missing:
            shown = "; ".join(map(repr, missing[:15])) + (f"; and {len(missing) - 15} more" if len(missing) > 15 else "")
            self.log(f"  not in library ({len(missing)}): {shown}")

    def update(self, owner, pid, entries, found):
        """Make an existing playlist hold found, in that order: take off what's no longer wanted
        (and repeats), add what's new, then move what's out of place."""
        if any(not e for _, e in entries):
            raise RuntimeError("the server didn't say where each film sits in the playlist")
        wanted, seen, drop = set(found), set(), []
        for item, entry_id in entries:
            if item in wanted and item not in seen:
                seen.add(item)
            else:
                drop.append(entry_id)
        add = [i for i in found if i not in seen]
        dry = self.log.dry_run
        if drop:
            self.log.change(f"taking {len(drop)} off the playlist")
            if not dry:
                self.server.remove_from_playlist(pid, drop)
        if add:
            self.log.change(f"adding {len(add)} to the playlist")
            if not dry:
                self.server.add_to_playlist(owner.id, pid, add)
        if dry:
            order = [i for i, e in entries if e not in set(drop)] + add
            moves = sum(1 for a, b in zip(order, found) if a != b)
            if moves:
                self.log.change("putting the playlist back in the list's order")
            return
        current = self.server.playlist_entries(owner.id, pid) if (drop or add) else entries
        spot = {i: e for i, e in current}
        order = [i for i, _ in current]
        moved, token = 0, None
        for n, item in enumerate(found):
            if n < len(order) and order[n] == item:
                continue
            if not spot.get(item):
                raise RuntimeError("the server didn't say where each film sits in the playlist")
            if self.server.OWNER_MOVES and not token:
                token = owner.session()
                if not token:
                    raise RuntimeError(f"{self.server.name} only lets the owner reorder a playlist: {owner.login_error}")
            self.server.move_in_playlist(pid, spot[item], n, token=token)
            order.remove(item)
            order.insert(n, item)
            moved += 1
        if moved:
            self.log.change(f"moved {moved} to keep the list's order")

    def share(self, owner, pid):
        token = owner.session()
        if not token:
            self.log.warn(f"not shared: {owner.login_error}")
            return
        try:
            others = [u["Id"] for u in self.server.users()
                      if u["Id"] != owner.id and not (u.get("Policy") or {}).get("IsDisabled")]
            if others:
                self.server.share_playlist(token, pid, others)
            self.log(f"  shared view-only with {len(others)} other user(s)")
        except Exception as e:
            self.log.warn(f"could not share ({describe(e)}). Check that '{owner.name}' has "
                          "'Allow sharing personal content' on (Dashboard > Users > Profile).")

    def unshare(self, owner, pid):
        """Make sure a private playlist is the owner's alone. (Per-person owners have no password
        here to sign in with; their playlists are made private.)"""
        token = owner.session()
        if not token:
            self.log.warn(f"couldn't make sure it's private: {owner.login_error}")
            return
        try:
            self.server.unshare_playlist(token, pid)
        except Exception as e:
            self.log.warn(f"couldn't make sure it's private ({describe(e)})")
