"""Genres: artwork for the genres already on the server, one per [[genre]] in genres.toml.

Genres come from the server's own metadata, so StaffPicked never creates, renames or deletes
one. It finds each genre by name (any capitalization) and sets the poster, thumb and backdrops
the entry gives it. Removing takes off only the artwork StaffPicked set; the genre stays.
Genres with names not in the config are never touched."""
from .results import Results
from .state import LABELS, apply_artwork
from .util import HTTPError, describe


class GenreSync:
    def __init__(self, server, uid, cfg, art, state, log, results=None):
        self.server, self.cfg, self.art, self.state, self.log = server, cfg, art, state, log
        self.results = results or Results("", dry_run=True)
        self.existing = {}    # lower-cased name -> id
        for name, gid in server.genres(uid).items():
            self.existing.setdefault(name.lower(), gid)

    def run(self, only=None, remove_all=False):
        for entry in self.cfg.entries:
            if only and entry.name.lower() != only.lower():
                continue
            self.log(f"\n[genre] {entry.name}")
            self.log.begin("genre", entry.name, self.server.label)
            try:
                gid = self.existing.get(entry.name.lower())
                if not gid:
                    self.log.warn(f"no genre called '{entry.name}' on the server; check the spelling "
                                  "against a film's genres")
                    if not remove_all:
                        self.results.record("genre", entry.name, self.server.label, fresh=True, errors=0,
                                            warning=f"No genre called '{entry.name}' on {self.server.label}")
                elif remove_all:
                    self.remove(gid)
                else:
                    apply_artwork(self.server, self.art, self.state, entry, gid, self.log)
                    self.results.record("genre", entry.name, self.server.label, fresh=True, errors=0)
            except Exception as e:
                self.log.error(describe(e))
                self.results.error("genre", entry.name, self.server.label, describe(e))
            self.log.end()

    def remove(self, gid):
        """Take off the images StaffPicked set on this genre (backdrops last first, so the
        numbering of the rest holds). Images set some other way are left alone."""
        images = self.state.images(self.server)
        mine = sorted((k.split("/") for k in images if k.startswith(f"{gid}/")),
                      key=lambda k: (k[1] == "Backdrop", -int(k[2])))
        if not mine:
            self.log("  no artwork from StaffPicked on it")
            return
        for _, kind, index in mine:
            self.log.change(f"removing its {LABELS.get(kind, kind.lower())}" + (f" {int(index) + 1}" if kind == "Backdrop" else ""))
            if self.log.dry_run:
                continue
            try:
                self.server.delete_image(gid, kind, int(index))
            except HTTPError as e:
                if e.code != 404:      # 404: already gone
                    self.log.warn(f"could not remove the {LABELS.get(kind, kind)} ({describe(e)})")
                    continue
            except Exception as e:
                self.log.warn(f"could not remove the {LABELS.get(kind, kind)} ({describe(e)})")
                continue
            del images[f"{gid}/{kind}/{index}"]
