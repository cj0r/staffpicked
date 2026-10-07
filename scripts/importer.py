"""Bringing collections, playlists and genre artwork that already exist on the server under StaffPicked.

  scan()   lists the server's collections, the playlists SERVER_USER owns and the genres that
           have artwork on the server, each marked:
             managed    a StaffPicked entry has the same name, so sync already updates that
                        one in place and never makes a second copy
             similar    a StaffPicked entry has nearly the same name ("Indepedence Day" vs
                        "Independence Day"); linking renames the entry to the server's name,
                        so sync updates the existing one instead of building a duplicate
             new        nothing in StaffPicked matches; importing adds an entry for it
             duplicate  the server already has another one with this name; StaffPicked only
                        ever updates the first, and this one is left alone
  adopt()  does the chosen imports and links. An import saves the item's poster and backdrop
           to images/ and adds a [[collection]] or [[playlist]] entry. A collection whose list
           can be found (see finder.py) gets that list as its source, so it keeps following
           the list; anything else gets a new list file of its films, in the server's
           order, as a fixed copy. A managed collection that an earlier import left as a fixed
           copy can be switched to its list the same way ("use list"). A genre import saves
           its poster, thumb and backdrops to images/ and adds a [[genre]] entry pointing at them.

Nothing on the server changes here, and nothing is deleted: only the config folder is written.
The next sync then manages what was adopted like any other entry.
"""
import datetime, difflib, json, os, re, time, tomllib
from . import artwork, backups, settings, sources
from .finder import SourceFinder
from .util import ConfigError, describe

KINDS = {"collection": "collections.toml", "playlist": "playlists.toml", "genre": "genres.toml"}
SIMILAR = 0.85     # how alike two names must be (0-1) to count as the same thing
FOUND = {}         # (collection id, its films) -> (time, list found), so the import after a scan is quick
FOUND_FOR = 600    # seconds a lookup is reused
HEADER = re.compile(r"^\s*\[\[?\s*([A-Za-z0-9_.-]+)\s*\]\]?")
NAME_LINE = re.compile(r"""^(\s*name\s*=\s*)("(?:[^"\\]|\\.)*"|'[^']*')(.*)$""", re.S)


def key(name):
    """A name with case, punctuation and leading articles ignored, for spotting near-matches."""
    s = name.lower().replace("&", "and")
    s = re.sub(r"^(the|a|an)\s+", "", s.strip())
    return re.sub(r"[^a-z0-9]+", "", s)


def similar(a, b):
    """Two keys that are likely the same list: equal, or one typo apart, but never with
    different numbers in them ("Halloween" and "Halloween 2" are different lists)."""
    if re.sub(r"\D", "", a) != re.sub(r"\D", "", b):
        return False
    return a == b or difflib.SequenceMatcher(None, a, b).ratio() >= SIMILAR


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:80].strip("-") or "imported"


def _toml(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ", ".join(_toml(v) for v in value) + "]"
    return json.dumps(str(value), ensure_ascii=False)     # a JSON string is a valid TOML string


class Importer:
    def __init__(self, server, env, base_dir, log=print):
        self.server, self.env, self.base_dir, self.log = server, env, base_dir, log
        self._owner, self._finder = None, None

    # --- what StaffPicked has
    def path(self, kind):
        return os.path.join(self.base_dir, KINDS[kind])

    def entries(self, kind):
        """The entries in a config file ([] if the file doesn't exist yet)."""
        if not os.path.isfile(self.path(kind)):
            return []
        return [e for e in settings.Config(kind, self.path(kind)).entries if e.name]

    # --- what the server has
    def owner(self):
        if self._owner is None:
            self._owner = self.server.user(self.env.get("SERVER_USER"))
        return self._owner

    def public(self, pid):
        """Whether a playlist is public now (Jellyfin), so importing it keeps it that way. Reading
        that takes the owner signed in; without SERVER_PASSWORD it counts as private."""
        if not self.server.PUBLIC_PLAYLISTS:
            return False
        try:
            token = self.server.login(self.owner()["Name"], self.env.get("SERVER_PASSWORD") or "")
        except Exception:
            return False
        try:
            return self.server.playlist_public(token, pid)
        except Exception:
            return False
        finally:
            self.server.logout(token)

    def on_server(self, kind):
        uid = self.owner()["Id"]
        if kind == "collection":
            return self.server.items(uid, Recursive="true", IncludeItemTypes="BoxSet",
                                     Fields="ChildCount,Overview,Tags", SortBy="SortName")
        if kind == "genre":     # only genres with artwork have anything to bring in
            return [g for g in self.server.genre_items(uid) if self.genre_art(g)]
        return self.server.playlists(uid)

    @staticmethod
    def genre_art(item):
        """[(setting, server image type, index)] for the images a genre has on the server."""
        tags = item.get("ImageTags") or {}
        return ([("poster", "Primary", 0)] if tags.get("Primary") else []) + \
               ([("thumb", "Thumb", 0)] if tags.get("Thumb") else []) + \
               [("backdrop", "Backdrop", i) for i in range(len(item.get("BackdropImageTags") or []))]

    def scan(self, find_sources=True, progress=None):
        """{"collection": [row], "playlist": [row]}; see the module docstring for the statuses.
        progress, if given, is called with {"step", "done", "total"} as slow lookups go.
        Each row's action is what adopting it does: import, link, source (use list) or None.
        With find_sources, collections to import, and managed ones left as fixed copies, also
        get the list they were built from as row["source"] (None if none was found)."""
        out = {}
        for kind in KINDS:
            if progress:
                progress({"step": f"Reading the server's {kind}s", "done": None, "total": None})
            entries = self.entries(kind)
            names = [e.name for e in entries]
            exact = {n.lower(): n for n in names}
            keys = {n: key(n) for n in names}
            taken, rows, hints = {}, [], {}
            for it in self.on_server(kind):
                name = it.get("Name") or ""
                hints[it["Id"]] = " ".join([it.get("Overview") or ""] + list(it.get("Tags") or []))
                row = {"kind": kind, "id": it["Id"], "name": name, "count": it.get("ChildCount"),
                       "status": "new", "entry": None}
                if kind == "genre":
                    art = [w for w, _, _ in self.genre_art(it)]
                    n = art.count("backdrop")
                    row["art"] = [w for w in art if w != "backdrop"] + ([f"{n} backdrop{'s' if n > 1 else ''}"] if n else [])
                first = taken.get(name.lower())
                if first:
                    row.update(status="duplicate", entry=first)
                elif name.lower() in exact:
                    row.update(status="managed", entry=exact[name.lower()])
                else:
                    best = max(names, key=lambda n: difflib.SequenceMatcher(None, keys[n], key(name)).ratio(), default=None)
                    if best and similar(keys[best], key(name)):
                        row.update(status="similar", entry=best)
                taken.setdefault(name.lower(), name)
                rows.append(row)
            # a near-match only counts once the entry isn't already the exact match of something else
            exact_hit = {r["entry"].lower() for r in rows if r["status"] == "managed"}
            for r in rows:
                if r["status"] == "similar" and r["entry"].lower() in exact_hit:
                    r.update(status="new", entry=None)
            fixed = {e.name.lower() for e in entries if e.sources and all(s.lower().endswith(".md") for s in e.sources)}
            lookups = [r for r in rows if find_sources and kind == "collection"
                       and (r["status"] == "new" or (r["status"] == "managed" and r["entry"].lower() in fixed))]
            for r in rows:
                r["source"], r["fixed"] = None, r["status"] == "managed" and r["entry"].lower() in fixed
                r["action"] = {"new": "import", "similar": "link"}.get(r["status"])
                if kind == "collection" and r["fixed"]:
                    r["action"] = "source"      # with the list found, or one the person gives
                if find_sources and kind == "collection" and (r["status"] == "new" or r["fixed"]):
                    if progress:
                        progress({"step": f"Looking for the list behind '{r['name']}'",
                                  "done": lookups.index(r), "total": len(lookups)})
                    r["source"] = self.source_of(r, hints.get(r["id"], ""))
                    if not r["source"] and not self.env.get("MDBLIST_API_KEY"):
                        r["no_key"] = True      # matching against MDBList lists needs the key
            out[kind] = rows
        return out

    def source_of(self, row, hint_text):
        """The list a collection was built from, as finder.py finds it, or None."""
        uid = self.owner()["Id"]
        members = self.server.members(uid, row["id"])
        ids = {v.lower() for it in members for k, v in (it.get("ProviderIds") or {}).items() if k.lower() == "imdb" and v}
        cache_key = (self.env.get("SERVER_URL"), row["id"], hint_text, frozenset(ids))
        hit = FOUND.get(cache_key)
        if hit and time.time() - hit[0] < FOUND_FOR:
            return hit[1]
        if self._finder is None:
            lib = self.server.library(uid)
            imdb = {value for (_, provider, value) in lib.ids if provider == "imdb"}
            self._finder = SourceFinder(self.env, self.base_dir, imdb)
        try:
            found = self._finder.find(row["name"], ids, hint_text)
        except Exception:
            return None
        FOUND[cache_key] = (time.time(), found)
        return found

    # --- adopting
    def given(self, url):
        """A list link the person typed in for a collection: checked, and read once to be sure
        it works. Returns it as a found source, or raises ValueError saying what's wrong."""
        url = str(url or "").strip()
        try:
            kind, where = sources.parse(url, self.base_dir)
        except ConfigError:
            kind = None
        if kind not in ("mdblist", "trakt"):
            raise ValueError(f"{url!r} isn't an MDBList or Trakt list link, like https://mdblist.com/lists/<user>/<list>")
        user, _, slug_ = where.partition("/")
        if kind == "mdblist":
            spec = f"https://mdblist.com/lists/{where}" if slug_ else f"mdblist:{where}"
        else:
            spec = f"https://trakt.tv/users/{user}/" + ("watchlist" if slug_ == "watchlist" else f"lists/{slug_}")
        try:
            films = sources.Sources(self.env, self.base_dir).items(spec)
        except ConfigError as e:
            raise ValueError(f"can't read {spec}: {e}")
        except Exception as e:
            raise ValueError(f"can't read {spec} ({describe(e)}); check the link and that the list is public")
        return {"sources": [spec], "how": f"the link you gave; {len(films)} titles on it"}

    def adopt(self, picks, dry_run=False, progress=None):
        """picks: [{"kind", "id", "action": "import" | "link" | "source", "url"?}]. A collection's url
        is a list link the person gave because none was found; it's used instead of a fixed list
        file. Returns one line per pick saying what was done (or why not). Every pick is checked
        against a fresh scan first. progress, if given, is called with {"step", "done", "total"}
        before each pick and with the pick's result line ("line") after it."""
        tell = progress or (lambda d: None)
        tell({"step": "Checking what's on the server", "done": 0, "total": len(picks)})
        scan = self.scan(progress=lambda d: tell({**d, "done": 0, "total": len(picks)}))
        found = {r["id"]: r["source"] for rows in scan.values() for r in rows}   # lists are looked up once
        done = []
        for n, p in enumerate(picks):
            had = len(done)
            self._adopt_one(p, scan, done, dry_run, n, len(picks), tell)
            tell({"step": None, "done": n + 1, "total": len(picks), "line": done[-1] if len(done) > had else None})
            if not dry_run and n + 1 < len(picks):     # later picks see this one's changes
                scan = self.scan(find_sources=False)
                for rows in scan.values():
                    for r in rows:
                        r["source"] = found.get(r["id"])
        return done

    def _adopt_one(self, p, scan, done, dry_run, n, total, tell):
        kind, action = p.get("kind"), p.get("action")
        row = next((r for r in scan.get(kind, []) if r["id"] == p.get("id")), None)
        if not row:
            done.append(f"Skipped: no {kind} with id {p.get('id')} on the server")
            return
        verb = {"import": "Importing", "link": "Linking", "source": "Switching"}.get(action, "Checking")
        tell({"step": f"{verb} {kind} '{row['name']}'", "done": n, "total": total})
        label = f"{kind} '{row['name']}'"
        try:
            if p.get("url") and kind == "collection" and action in ("import", "source"):
                row["source"] = self.given(p["url"])
            if action == "source" and not row["source"]:
                done.append(f"Skipped {label}: no list was found for it and no link was given")
                return
            if action != row["action"]:
                why = "no list was found for it" if action == "source" else f"it's {row['status']}"
                if row["status"] in ("managed", "duplicate") and action != "source":
                    why = f"StaffPicked already manages '{row['entry']}'"
                done.append(f"Skipped {label}: can't {action} it, because {why}")
                return
            if action == "link":
                self.rename(kind, row["entry"], row["name"], dry_run)
                done.append(f"Linked {label}: renamed the StaffPicked entry '{row['entry']}' to match it")
            elif action == "import":
                done.append(f"Imported {label}: " + self.import_one(row, dry_run))
            else:
                self.set_sources(kind, row["entry"], row["source"]["sources"], dry_run)
                done.append(f"Switched {label} to {' + '.join(row['source']['sources'])} "
                            f"({row['source']['how']}); its old list file is still in {settings.LIST_DIRS[kind]}/"
                            + (" (dry run)" if dry_run else ""))
        except (ConfigError, OSError, ValueError) as e:
            done.append(f"Failed {label}: {e}")
        except Exception as e:
            done.append(f"Failed {label}: {describe(e)}")

    def import_one(self, row, dry_run):
        if row["kind"] == "genre":
            return self.import_genre(row, dry_run)
        if row.get("source"):
            return self.import_from_list(row, dry_run)
        kind, name, uid = row["kind"], row["name"], self.owner()["Id"]
        members = self.server.members(uid, row["id"], playlist=kind == "playlist")
        films, skipped = [], []
        for it in members:
            imdb = next((v for k, v in (it.get("ProviderIds") or {}).items() if k.lower() == "imdb" and v), None)
            year = f" ({it['ProductionYear']})" if it.get("ProductionYear") else ""
            title = f"{it.get('Name', '?')}{year}".replace("|", "/")
            if imdb and it.get("Type") in ("Movie", "Series"):
                films.append(f"- {imdb.lower()} | {title}")
            else:
                why = "no IMDb ID" if it.get("Type") in ("Movie", "Series") else f"{it.get('Type', 'item').lower()}, not a film or show"
                skipped.append(f"{title}, {why}")
        if not films:
            raise ValueError("nothing in it has an IMDb ID, so there's nothing to put in a list file")

        listfile = self.free_name(name, kind)
        today = datetime.date.today().isoformat()
        text = (f"# {name}\n\nImported from the {self.server.name} {kind} \"{name}\" on {today}, "
                f"one film per line in the {self.server.name} order.\n\n" + "\n".join(films) + "\n")
        if skipped:
            text += ("\n<!--\nLeft out, because a list line needs an IMDb ID:\n"
                     + "\n".join(f"  {s.replace('--', '-')}" for s in skipped) + "\n-->\n")

        entry = {"name": name, "sources": [listfile]}
        entry.update(self.artwork(row, dry_run))
        if kind == "playlist":
            # keep it as it is now: every film stays, and it isn't shared with anyone new
            entry.update(include_watched=True, share="view" if self.public(row["id"]) else "private")

        if not dry_run:
            os.makedirs(os.path.join(self.base_dir, settings.LIST_DIRS[kind]), exist_ok=True)
            with open(os.path.join(self.base_dir, listfile), "x", encoding="utf-8") as f:
                f.write(text)
            try:
                self.append(kind, entry)
            except Exception:
                os.remove(os.path.join(self.base_dir, listfile))
                raise
        art = ([entry["poster"]] if "poster" in entry else []) + entry.get("backdrops", [])
        left = ""
        if skipped:
            left = f", {len(skipped)} left out (listed at the end of the file)"
            if kind == "collection":
                left += "; sync will take them out of the collection"
        return (f"{len(films)} film(s) to {listfile}" + left
                + (f", artwork saved to {', '.join(art)}" if art else "") + (" (dry run)" if dry_run else ""))

    def import_genre(self, row, dry_run):
        """A genre with artwork on the server: its images saved to images/, and a [[genre]] entry
        that sets the same ones, so sync keeps them (and you can swap any of them later)."""
        uid = self.owner()["Id"]
        item = next((g for g in self.server.genre_items(uid) if g["Id"] == row["id"]), None)
        entry, backdrops = {"name": row["name"]}, []
        for label, kind_img, index in self.genre_art(item or {}):
            saved = self.save_image(row, label, kind_img, dry_run, index)
            if saved and label == "backdrop":
                backdrops.append(saved)
            elif saved:
                entry[label] = saved
        if backdrops:
            entry["backdrops"] = backdrops
        if len(entry) == 1:
            raise ValueError(f"{self.server.name} didn't send any of its images")
        if not dry_run:
            self.append("genre", entry)
        art = [v for k, v in entry.items() if k in ("poster", "thumb")] + backdrops
        return f"artwork saved to {', '.join(art)}" + (" (dry run)" if dry_run else "")

    def import_from_list(self, row, dry_run):
        """A collection whose list was found: an entry that follows that list, no list file."""
        entry = {"name": row["name"], "sources": row["source"]["sources"]}
        entry.update(self.artwork(row, dry_run))
        if not dry_run:
            self.append(row["kind"], entry)
        art = ([entry["poster"]] if "poster" in entry else []) + entry.get("backdrops", [])
        return (f"follows {' + '.join(entry['sources'])} ({row['source']['how']})"
                + (f", artwork saved to {', '.join(art)}" if art else "") + (" (dry run)" if dry_run else ""))

    def artwork(self, row, dry_run):
        """The item's current poster and backdrop, saved to images/, as entry settings."""
        out = {}
        poster = self.save_image(row, "poster", "Primary", dry_run)
        backdrop = self.save_image(row, "backdrop", "Backdrop", dry_run)
        if poster:
            out["poster"] = poster
        if backdrop:
            out["backdrops"] = [backdrop]
        return out

    def free_name(self, name, kind):
        """An unused collections/ or playlists/<name>.md (or <name>-2.md, <name>-3.md, ...)."""
        base = slug(name).replace("template", "list")
        sub = settings.LIST_DIRS[kind]
        folder = os.path.join(self.base_dir, sub)
        for c in [base] + [f"{base}-{n}" for n in range(2, 100)]:
            if not os.path.exists(os.path.join(folder, c + ".md")):
                return f"{sub}/{c}.md"
        raise ValueError(f"too many list files named {base} in {sub}/")

    def save_image(self, row, label, kind_img, dry_run, index=0):
        try:
            data, ctype = self.server.image(row["id"], kind_img, index)
        except Exception:
            return None          # it has no image of this kind
        if not data:
            return None
        stem = artwork.copy_name(row["kind"], row["name"], label, index)
        saved, _ = artwork.save_copy(self.base_dir, stem, data, ctype, dry_run)
        if not saved:            # that exact image is already saved
            saved = next(p for p in artwork._saved(os.path.join(self.base_dir, "images"), stem))
        return os.path.relpath(saved, self.base_dir).replace(os.sep, "/")

    # --- writing the TOML files, leaving everything else in them as it was
    def append(self, kind, entry):
        path = self.path(kind)
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            text = ""
        block = f"[[{kind}]]\n" + "".join(f"{k} = {_toml(v)}\n" for k, v in entry.items())
        head = text.rstrip("\n")
        self.write(path, (head + "\n\n" if head else "") + block)

    def find_entry(self, kind, name):
        """(lines of the config file, the entry's name line, the line after its table)."""
        with open(self.path(kind), encoding="utf-8") as f:
            lines = f.read().splitlines(keepends=True)
        in_kind, hit = False, None
        for i, line in enumerate(lines):
            head = HEADER.match(line)
            if head:
                if hit is not None:
                    return lines, hit, i
                in_kind = line.lstrip().startswith("[[") and head[1] == kind
                continue
            m = in_kind and hit is None and NAME_LINE.match(line)
            if m and tomllib.loads(f"name = {m[2]}")["name"] == name:
                hit = i
        if hit is None:
            raise ValueError(f"couldn't find the entry named '{name}' in {KINDS[kind]}")
        return lines, hit, len(lines)

    def rename(self, kind, old, new, dry_run):
        lines, i, _ = self.find_entry(kind, old)
        m = NAME_LINE.match(lines[i])
        lines[i] = f"{m[1]}{_toml(new)}{m[3]}"
        if not dry_run:
            self.write(self.path(kind), "".join(lines))

    def set_sources(self, kind, name, sources, dry_run):
        """Replace an entry's sources (a one-line or multi-line array) with these."""
        lines, i, end = self.find_entry(kind, name)
        top = next(n for n in range(i, -1, -1) if HEADER.match(lines[n]))
        start = next((n for n in range(top + 1, end) if re.match(r"^\s*sources?\s*=", lines[n])), None)
        if start is None:
            raise ValueError(f"'{name}' has no sources line to replace")
        stop = start + 1
        if lines[start].count("[") > lines[start].count("]"):     # a multi-line array
            while stop < end and "]" not in lines[stop - 1].split("#")[0]:
                stop += 1
        text = f"sources = {_toml(sources)}\n"
        if len(sources) > 1 and len(text) > 100:
            text = "sources = [\n" + "".join(f"  {_toml(v)},\n" for v in sources) + "]\n"
        lines[start:stop] = [text]
        if not dry_run:
            self.write(self.path(kind), "".join(lines))

    def write(self, path, text):
        tomllib.loads(text)          # never write a file StaffPicked can't read
        backups.keep(self.base_dir, path)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
