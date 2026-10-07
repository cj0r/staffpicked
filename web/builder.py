"""Building collections, playlists and genre artwork in the web UI, without hand-editing files.

Two things are edited here:
  - one [[collection]], [[playlist]] or [[genre]] entry at a time in collections.toml,
    playlists.toml or genres.toml.
    Only the entry that changed is rewritten, and inside it only the settings that changed,
    so comments and layout everywhere else in the file stay as they were.
  - the film list of a list file (collections/*.md, playlists/*.md): one "- tt0084787 | notes"
    line per film, in order from the top down as one flat list (playlists have no sections),
    after the file's title and description, which stay as they are.

Every write carries the version (a hash) of the file it was based on, so a change made
meanwhile in the Config Files editor, or another browser, is never overwritten.
"""
import concurrent.futures, hashlib, importlib, json, os, re, tempfile, tomllib, urllib.error

import backend

KINDS = {"collections": "collection", "playlists": "playlist", "genres": "genre"}
# The settings the forms edit, in the order they are written. See the README for each one.
FIELDS = {
    "collection": ("name", "sources", "active", "poster", "backdrops", "description", "sort_name", "display_order",
                   "servers"),
    "playlist": ("name", "sources", "active", "poster", "backdrops", "include_watched", "share", "watched_by",
                 "servers"),
    "genre": ("name", "poster", "thumb", "backdrops", "servers"),
}
LISTS = {"sources", "backdrops", "watched_by", "servers"}
BOOLS = {"include_watched"}
ALIASES = {"source": "sources", "backdrop": "backdrops"}   # older singular spellings

HEADER = re.compile(r"^\s*\[\[?\s*([A-Za-z0-9_.-]+)\s*\]\]?\s*(#.*)?$")
ASSIGN = re.compile(r"^\s*([A-Za-z0-9_-]+)\s*=")
IMDB_ID = re.compile(r"\btt\d{7,}\b")
TITLE_YEAR = re.compile(r"^(.+?)\s*\((\d{4})\)[\s,.:;-]*(.*)$")
LIST_MARKER = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


class Invalid(Exception):
    """The change can't be saved; .problems says why."""
    def __init__(self, problems, warnings=None):
        super().__init__("; ".join(problems))
        self.problems, self.warnings = problems, warnings or []


class Conflict(Exception):
    pass


def version(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def _write(path, text):
    """Write a config or list file, keeping a copy of what it held in backups/ first."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    importlib.import_module(f"{backend.PKG}.backups").keep(backend.CONFIG_DIR, path)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def _settings_module():
    return importlib.import_module(f"{backend.PKG}.settings")


# ---------------------------------------------------------------- collections.toml / playlists.toml

def config_path(job):
    return os.path.join(backend.CONFIG_DIR, backend.JOBS[job]["config"])


def _blocks(lines, kind):
    """(first line, end line) of each [[kind]] table, in file order. Blank and comment lines
    at the end of a table belong to whatever follows it, so they are left alone."""
    heads = [(i, m[1], line.lstrip().startswith("[["))
             for i, line in enumerate(lines) if (m := HEADER.match(line))]
    out = []
    for n, (i, name, is_array) in enumerate(heads):
        if not (is_array and name == kind):
            continue
        end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
        while end > i + 1 and (not lines[end - 1].strip() or lines[end - 1].lstrip().startswith("#")):
            end -= 1
        out.append((i, end))
    return out


def _spans(lines, start, end):
    """{key: [lead, first line, end line]} of each setting in a table, multi-line arrays included.
    lead is where the comment and blank lines just above the setting start, so they stay with it."""
    spans, cur, lead = {}, None, None
    for i in range(start + 1, end):
        stripped = lines[i].strip()
        if cur and _open_array(lines, spans[cur][1], i):      # still inside cur's [ ... ]
            spans[cur][2] = i + 1
        elif m := ASSIGN.match(lines[i]):
            cur = m[1]
            spans[cur] = [i if lead is None else lead, i, i + 1]
            lead = None
        elif cur and stripped and not stripped.startswith("#"):
            spans[cur][2] = i + 1
        elif lead is None:
            lead = i
    return spans


def _open_array(lines, first, i):
    """True while line i is still inside a multi-line array that starts on line first."""
    text = "".join(line.split("#")[0] for line in lines[first:i])
    return text.count("[") > text.count("]")


def _norm(key, value):
    """A setting's value as the form shows it."""
    if key in LISTS:
        vals = value if isinstance(value, list) else [value]
        return [str(v).strip() for v in vals if v is not None and str(v).strip()]
    if key in BOOLS:
        return value if isinstance(value, bool) else str(value).strip().lower() in ("1", "true", "yes", "on")
    return "" if value is None else str(value).strip()


def form_values(kind, raw):
    out = {}
    for k, v in raw.items():
        k = ALIASES.get(k, k)
        if k in FIELDS[kind]:
            out[k] = _norm(k, v)
    return out


def _toml(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ", ".join(_toml(v) for v in value) + "]"
    return json.dumps(str(value), ensure_ascii=False)   # a JSON string is a valid TOML basic string


def _line(key, value):
    text = f"{key} = {_toml(value)}\n"
    if isinstance(value, list) and len(value) > 1 and len(text) > 100:
        text = f"{key} = [\n" + "".join(f"  {_toml(v)},\n" for v in value) + "]\n"
    return text


def clean(kind, entry):
    """The form's values, checked and trimmed. Empty values are left out of the file."""
    if not isinstance(entry, dict):
        raise Invalid(["Expected the entry's settings"])
    out = {}
    for k in FIELDS[kind]:
        v = entry.get(k)
        if k in LISTS:
            v = [str(x).strip() for x in (v if isinstance(v, list) else [v] if v else []) if str(x).strip()]
            texts = v
        elif k in BOOLS:
            v = None if v in (None, "") else _norm(k, v)
            texts = []
        else:
            v = "" if v is None else str(v).strip()
            texts = [v]
        if any("\n" in t or "\r" in t for t in texts):
            raise Invalid([f"{k} can't contain a line break"])
        if v not in ("", [], None):
            out[k] = v
    if kind == "playlist" and out.get("share"):
        out["share"] = out["share"].lower()
    return out


def _render(kind, entry, lines=None, block=None, old_raw=None):
    """The text of one [[kind]] table. Settings that didn't change keep their old lines,
    comments included."""
    if block:
        start, end = block
        spans = _spans(lines, start, end)
        out = [lines[start]]
    else:
        spans, out = {}, [f"[[{kind}]]\n"]
    old_raw = old_raw or {}
    for k in FIELDS[kind]:
        if k not in entry:
            continue
        old_key = next((o for o in (k, *[a for a, b in ALIASES.items() if b == k]) if o in old_raw), None)
        if old_key in spans:
            lead, s, e = spans[old_key]
            out += lines[lead:s]       # its comments stay, changed or not
            out += lines[s:e] if _norm(k, old_raw[old_key]) == entry[k] else [_line(k, entry[k])]
        else:
            out.append(_line(k, entry[k]))
    return "".join(out)


def _parse(text, path):
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise Invalid([f"{os.path.basename(path)} has a syntax error ({e}). Fix it in Config Files first."])


def _check(job, text, name, env):
    """Problems and warnings for one entry, as `python -m scripts check` would report them."""
    kind = KINDS[job]
    _parse(text, config_path(job))
    settings = _settings_module()
    fd, tmp = tempfile.mkstemp(prefix=".builder-", suffix=".toml", dir=backend.CONFIG_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        cfg = settings.Config(kind, tmp)
        problems = cfg.problems().get(name or "(no name)", [])
        entry = next((e for e in cfg.entries if e.name == name), None)
        names = [x["name"] for x in settings.servers(env)]
        warnings = (entry.warnings(cfg.base_dir) + entry.env_problems(env) + entry.server_problems(names)) if entry else []
    finally:
        os.remove(tmp)
    return problems, warnings


def entries(job):
    """Everything the builder shows for a job: its entries, [settings] and its list files."""
    kind, path = KINDS[job], config_path(job)
    text = _read(path)
    data = _parse(text, path)
    raw = data.get(kind, [])
    editable = len(_blocks(text.splitlines(keepends=True), kind)) == len(raw)
    return {
        "version": version(text),
        "editable": editable,
        "settings": data.get("settings", {}),
        "fields": list(FIELDS[kind]),
        "entries": [{"index": i, **form_values(kind, r)} for i, r in enumerate(raw)],
        "watchlists": watchlists(job),
        "images": image_names(),
    }


def save_entry(job, index, entry, base_version, env, new_watchlist=None):
    """Add (index None) or replace one entry. Returns {index, warnings}."""
    kind, path = KINDS[job], config_path(job)
    text = _read(path)
    if base_version != version(text):
        raise Conflict(f"{backend.JOBS[job]['config']} changed since you opened it. Reopen it and try again.")
    data = _parse(text, path)
    raw = data.get(kind, [])
    lines = text.splitlines(keepends=True)
    blocks = _blocks(lines, kind)
    if len(blocks) != len(raw):
        raise Invalid([f"{backend.JOBS[job]['config']} is laid out in a way the builder can't edit safely. Use Config Files."])
    entry = clean(kind, entry)
    wl = None
    if new_watchlist is not None:
        wl = _new_watchlist(job, new_watchlist, entry.get("name", ""))
        entry["sources"] = [wl["name"]] + [s for s in entry.get("sources", []) if s != wl["name"]]
    if index is None:
        body = _render(kind, entry)
        head = text.rstrip("\n")
        new_text = (head + "\n\n" if head else "") + body
        index = len(raw)
    else:
        if not 0 <= index < len(raw):
            raise Conflict("That entry no longer exists. Reopen the list and try again.")
        start, end = blocks[index]
        new_text = "".join(lines[:start]) + _render(kind, entry, lines, blocks[index], raw[index]) + "".join(lines[end:])
    problems, warnings = _check(job, new_text, entry.get("name", ""), env)
    if wl:   # the new file doesn't exist yet, so that warning is expected
        warnings = [w for w in warnings if wl["name"] not in w] + wl["warnings"]
    if problems:
        raise Invalid(problems, warnings)
    if wl:
        _write(wl["path"], wl["text"])
    _write(path, new_text)
    renamed = None
    if index < len(raw) and kind in ("collection", "playlist"):
        old = str(raw[index].get("name", "")).strip()
        if old and old.lower() != entry.get("name", "").strip().lower():
            importlib.import_module(f"{backend.PKG}.renames").add(backend.CONFIG_DIR, kind, old, entry["name"])
            renamed = old
    return {"index": index, "warnings": warnings, "watchlist": wl and wl["name"], "renamed": renamed}


def delete_entry(job, index, base_version):
    kind, path = KINDS[job], config_path(job)
    text = _read(path)
    if base_version != version(text):
        raise Conflict(f"{backend.JOBS[job]['config']} changed since you opened it. Reopen it and try again.")
    raw = _parse(text, path).get(kind, [])
    lines = text.splitlines(keepends=True)
    blocks = _blocks(lines, kind)
    if len(blocks) != len(raw) or not 0 <= index < len(raw):
        raise Conflict("That entry no longer exists. Reopen the list and try again.")
    start, end = blocks[index]
    new_text = "".join(lines[:start]) + "".join(lines[end:])
    new_text = re.sub(r"\n{3,}", "\n\n", new_text).rstrip("\n") + "\n"
    _parse(new_text, path)
    _write(path, new_text)
    return {"name": raw[index].get("name", "")}


# ---------------------------------------------------------------- list files

def watchlists(job):
    """The job's own list files (collections/*.md or playlists/*.md), templates left out."""
    return [f["name"] for f in backend.config_files(job)
            if f["name"].startswith(job + "/") and "template" not in f["name"].lower()]


def watchlist_path(name):
    if not backend.SAFE_NAME.match(name or "") or ".." in name:
        raise Invalid(["That isn't a list file name"])
    return os.path.join(backend.CONFIG_DIR, name)


def slug(title):
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80].strip("-")
    return s or "list"


def _new_watchlist(job, spec, entry_name):
    """A new list file for a new collection or playlist, in that job's folder: {name, path,
    text}. Written only once the entry is valid."""
    if not isinstance(spec, dict):
        spec = {}
    title = str(spec.get("title") or entry_name).strip()
    description = str(spec.get("description") or "").strip()
    if not title:
        raise Invalid([f"Give the {KINDS[job]} a name first"])
    if "\n" in title or "\r" in title:
        raise Invalid(["The name can't contain a line break"])
    base = slug(title).replace("template", "list")
    name = f"{job}/{base}.md"
    path = watchlist_path(name)
    if os.path.exists(path):
        raise Conflict(f"{name} already exists. Pick it under Sources instead, or use another name.")
    pasted = str(spec.get("text") or "")
    if pasted.strip():
        text, warnings = _pasted_list(pasted, title, description)
    else:
        text, warnings = f"# {title}\n" + (f"\n{description}\n" if description else ""), []
    return {"name": name, "path": path, "text": text, "warnings": warnings}


PASTE_LIMIT = 1_000_000


def _pasted_list(pasted, title, description):
    """A whole list pasted into the form, saved as it is: (text, warnings). It needs at least
    one IMDb ID; a "# title" line goes on top if the paste has none."""
    if len(pasted) > PASTE_LIMIT:
        raise Invalid(["The pasted list is over 1 MB"])
    lines = pasted.replace("\r\n", "\n").replace("\r", "\n").strip().split("\n")
    if len(lines) > 1 and lines[0].startswith(("```", "~~~")) and lines[-1].strip() in ("```", "~~~"):
        lines = lines[1:-1]     # pasted with the code fence an AI chat puts around it
    live = _live_lines(lines)
    films, seen, twice, skipped = 0, set(), [], []
    for i, line in enumerate(lines):
        if i not in live:
            continue
        ids = IMDB_ID.findall(line)
        if ids:
            films += 1
            if ids[0] in seen:
                twice.append(ids[0])
            seen.add(ids[0])
        elif LIST_MARKER.match(line) and line.strip():
            skipped.append(LIST_MARKER.sub("", line).strip())
    if not films:
        raise Invalid(["The pasted list has no IMDb IDs. Write each film as \"- tt0084787 | The Thing (1982)\" "
                       "(the tt… part of its imdb.com link), or start an empty list and add films by title."])
    warnings = []
    if skipped:
        shown = "; ".join(skipped[:5]) + (f"; and {len(skipped) - 5} more" if len(skipped) > 5 else "")
        warnings.append(f"{len(skipped)} pasted line(s) have no IMDb ID and are skipped: {shown}. "
                        "Add those films by title under Films.")
    if twice:
        warnings.append(f"On the pasted list twice: {', '.join(dict.fromkeys(twice))}")
    has_title = any(i in live and line.lstrip().startswith("# ") for i, line in enumerate(lines))
    head = "" if has_title else f"# {title}\n\n" + (f"{description}\n\n" if description else "")
    return head + "\n".join(lines) + "\n", warnings


def _live_lines(lines):
    """Indexes of lines StaffPicked reads: not in an HTML comment or a fenced code block."""
    text = "\n".join(lines)
    text = re.sub(r"<!--.*?-->", lambda m: "\n" * m[0].count("\n"), text, flags=re.S)
    live, fenced = set(), False
    for i, line in enumerate(text.split("\n")):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        elif not fenced and (line.strip() or not lines[i].strip()):   # blanked = inside a comment
            live.add(i)
    return live


def _notes(line, imdb):
    """What follows the ID on a film line: everything after the "|" in "- tt0084787 | notes"."""
    before, _, after = line.partition(imdb)
    if after.lstrip().startswith("|"):
        return after.lstrip()[1:].strip()
    rest = LIST_MARKER.sub("", before) + " " + after
    return re.sub(r"\s+", " ", rest.replace("|", " ")).strip(" -:,")


def read_watchlist(name):
    text = _read(watchlist_path(name))
    if not os.path.isfile(watchlist_path(name)):
        raise FileNotFoundError(name)
    lines = text.split("\n")
    live = _live_lines(lines)
    rows, title = [], ""
    for i, line in enumerate(lines):
        m = IMDB_ID.search(line) if i in live else None
        if m:
            rows.append({"kind": "film", "id": m[0], "notes": _notes(line, m[0]), "text": line})
        else:
            if i in live and not title and line.lstrip().startswith("# "):
                title = line.strip()[2:].strip()
            rows.append({"kind": "text", "text": line})
    return {"name": name, "title": title, "rows": rows, "version": version(text),
            "used_by": [e["name"] for e in _entries_using(name)]}


def _entries_using(name):
    job = name.split("/", 1)[0]
    try:
        data = entries(job) if job in KINDS else {"entries": []}
    except Invalid:
        return []
    return [e for e in data["entries"] if name in e.get("sources", [])]


def save_watchlist(name, rows, base_version):
    path = watchlist_path(name)
    if not os.path.isfile(path):
        raise Conflict(f"{name} no longer exists")
    text = _read(path)
    if base_version != version(text):
        raise Conflict(f"{name} changed since you opened it. Reopen it and try again.")
    if not isinstance(rows, list):
        raise Invalid(["Expected the list's rows"])
    out, films, seen, problems = [], [], {}, []
    for r in rows:
        if not isinstance(r, dict):
            raise Invalid(["Bad row"])
        kind = r.get("kind")
        if kind == "film":
            imdb = str(r.get("id", "")).strip().lower()
            if not re.fullmatch(r"tt\d{7,}", imdb):
                problems.append(f"{imdb or 'a film'} isn't an IMDb ID like tt0084787")
                continue
            if imdb in seen:
                problems.append(f"{imdb} ({r.get('notes') or seen[imdb]}) is on the list twice")
            seen[imdb] = r.get("notes") or imdb
            old = str(r.get("text") or "")
            m = IMDB_ID.search(old)
            if old and not r.get("edited") and m and m[0] == imdb:
                line = old
            else:
                notes = re.sub(r"\s+", " ", str(r.get("notes") or "")).strip()
                line = f"- {imdb} | {notes}" if notes else f"- {imdb}"
        elif kind == "text":
            line = str(r.get("text") or "")
        else:
            raise Invalid(["Bad row"])
        if "\n" in line or "\r" in line:
            raise Invalid(["A line can't contain a line break"])
        if kind == "film":
            films.append(len(out))
        out.append(line)
    if problems:
        raise Invalid(problems)
    # One flat list, like the playlist: no section headings anywhere (the "# title" stays)
    # and no blank lines between the first film and the last.
    live = _live_lines(out)
    keep = [not (i in live and re.match(r"^\s*#{2,6}\s", line)) for i, line in enumerate(out)]
    flattened = keep.count(False)
    if films:
        for i in range(films[0], films[-1] + 1):
            keep[i] = keep[i] and bool(out[i].strip())
    kept = []
    for line, k in zip(out, keep):
        if k and not (flattened and not line.strip() and kept and not kept[-1].strip()):
            kept.append(line)   # (where a heading came out, one blank line instead of two)
    out = kept
    new_text = "\n".join(out)
    if not new_text.endswith("\n"):
        new_text += "\n"
    _write(path, new_text)
    return {"films": len(seen), "version": version(new_text), "flattened": flattened}


# ---------------------------------------------------------------- finding IMDb IDs

def _http_error(service, e):
    if isinstance(e, urllib.error.HTTPError):
        return f"{service} answered HTTP {e.code}"
    return f"{service} didn't answer ({type(e).__name__})"   # never the URL: it can hold the key


def search(query, kind, env):
    """Films (kind "movie") or shows ("show") matching a title: [{id, title, year, type}].
    Uses MDBList when there's a key, else TMDB."""
    util = importlib.import_module(f"{backend.PKG}.util")
    query = (query or "").strip()
    kind = "show" if kind == "show" else "movie"
    if not query:
        return []
    m = re.fullmatch(r"(?:.*/title/)?(tt\d{7,})/?\S*", query)
    if m:   # a pasted IMDb ID or link needs no lookup
        return [{"id": m[1], "title": "", "year": None, "type": kind}]
    if env.get("MDBLIST_API_KEY"):
        try:
            data = util.request("GET", f"https://api.mdblist.com/search/{kind}",
                                {"query": query, "limit": 12, "apikey": env["MDBLIST_API_KEY"]}, timeout=20, retries=1)
        except Exception as e:
            raise Invalid([_http_error("MDBList", e)])
        results = data.get("search", []) if isinstance(data, dict) else data or []
        out = []
        for r in results:
            ids = r.get("ids") or {}
            imdb = r.get("imdbid") or ids.get("imdb") or (r.get("id") if str(r.get("id", "")).startswith("tt") else None)
            if imdb:
                out.append({"id": imdb, "title": r.get("title") or "", "year": r.get("year"), "type": r.get("type") or kind})
        return out
    if env.get("TMDB_API_TOKEN"):
        tmdb = "tv" if kind == "show" else "movie"
        headers = {"Authorization": f"Bearer {env['TMDB_API_TOKEN']}"}
        try:
            data = util.request("GET", f"https://api.themoviedb.org/3/search/{tmdb}", {"query": query},
                                headers=headers, timeout=20, retries=1)
        except Exception as e:
            raise Invalid([_http_error("TMDB", e)])
        found = (data or {}).get("results", [])[:8]

        def imdb_id(r):
            try:
                ext = util.request("GET", f"https://api.themoviedb.org/3/{tmdb}/{r['id']}/external_ids",
                                   headers=headers, timeout=20, retries=1)
                return (ext or {}).get("imdb_id")
            except Exception:
                return None
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            ids = list(pool.map(imdb_id, found))
        out = []
        for r, imdb in zip(found, ids):
            date = r.get("release_date") or r.get("first_air_date") or ""
            if imdb:
                out.append({"id": imdb, "title": r.get("title") or r.get("name") or "",
                            "year": int(date[:4]) if date[:4].isdigit() else None, "type": kind})
        return out
    raise Invalid(["Searching needs an MDBList API key or a TMDB token in Settings. "
                   "You can also paste an IMDb ID (the tt… part of an imdb.com link)."])


def delete_entry_named(job, name):
    """Delete the entry called name, wherever it is now (used after removing it from the server)."""
    kind, path = KINDS[job], config_path(job)
    text = _read(path)
    raw = _parse(text, path).get(kind, [])
    index = next((i for i, r in enumerate(raw) if str(r.get("name", "")).strip() == name), None)
    if index is None:
        return None
    return delete_entry(job, index, version(text))


def entry_name(job, index, base_version):
    """The name of entry index, checking the file hasn't changed since the page read it."""
    kind, path = KINDS[job], config_path(job)
    text = _read(path)
    if base_version != version(text):
        raise Conflict(f"{backend.JOBS[job]['config']} changed since you opened it. Reopen it and try again.")
    raw = _parse(text, path).get(kind, [])
    if not 0 <= index < len(raw):
        raise Conflict("That entry no longer exists. Reopen the list and try again.")
    name = str(raw[index].get("name", "")).strip()
    if not name:
        raise Invalid(["This entry has no name, so it can't be removed from the server by name"])
    return name


# ---------------------------------------------------------------- what's on one list

def _is_list_file(spec):
    return bool(re.fullmatch(r"(collections|playlists|watchlists)/[^/]+\.md", spec.strip()))


def list_items(job, index, env, progress=None):
    """The films one collection or playlist gets from its sources, in sync order.
    Reads MDBList and Trakt live, so it runs outside the file lock. progress, if given,
    hears each source as it's read ({"step", "done", "total"})."""
    sources, util = (importlib.import_module(f"{backend.PKG}.{m}") for m in ("sources", "util"))
    try:
        cfg = _settings_module().Config(KINDS[job], config_path(job))
    except Exception as e:
        raise Invalid([f"{backend.JOBS[job]['config']} can't be read: {util.describe(e)}"])
    if not 0 <= index < len(cfg.entries):
        raise Invalid(["That entry isn't in the config any more. Refresh the page."])
    entry = cfg.entries[index]
    src = sources.Sources(env, cfg.base_dir)
    items, problems, seen, feeds, known, shows = [], [], set(), [], {}, set()
    for n, spec in enumerate(entry.sources):
        feeds.append(_feed(sources, spec, cfg.base_dir))
        if progress:
            name = {"mdblist": "MDBList list", "trakt": "Trakt list"}.get(feeds[-1]["kind"], "list file")
            progress({"step": f"Reading the {name} {spec.strip()}", "done": n, "total": len(entry.sources)})
        try:
            if _is_list_file(spec):   # read the whole line, so notes aren't cut short
                got = [(r["id"], r["notes"]) for r in read_watchlist(spec)["rows"] if r["kind"] == "film"]
            else:
                got = [(it.ids.get("imdb", ""), it) for it in src.items(spec)]
        except Exception as e:
            problems.append(f"{spec}: {e if isinstance(e, (Invalid, FileNotFoundError)) else util.describe(e)}")
            continue
        for imdb, it in got:
            if isinstance(it, str):   # "Title (Year) notes"
                m = TITLE_YEAR.match(it)
                title, year, notes = (m[1], int(m[2]), m[3]) if m else (it or imdb, None, "")
            else:
                title, year, notes = it.title, it.year, ""
                if imdb and it.score is not None:
                    known[imdb] = it.score
                if imdb and it.kind == "show":
                    shows.add(imdb)
            key = imdb or f"{title}|{year}"
            items.append({"title": title, "year": year, "notes": notes, "imdb": imdb, "source": spec,
                          "duplicate": key in seen})
            seen.add(key)
            feeds[-1]["count"] += 1
    films = sum(1 for i in items if not i["duplicate"])
    if job != "genres":
        found = importlib.import_module(f"{backend.PKG}.scores").scores(
            backend.CONFIG_DIR, env.get("MDBLIST_API_KEY"), [i["imdb"] for i in items if i["imdb"]], known, shows)
        for it in items:
            it["score"], it["show"] = found.get(it["imdb"]), it["imdb"] in shows
    library = _library(job, entry, env, items)
    return {"name": entry.name, "window": entry.active, "sources": entry.sources, "feeds": feeds,
            "items": items, "problems": problems, "artwork": _artwork_for(entry), "library": library,
            "needs": sorted({m[1] for p in problems for m in NEEDS_KEY.finditer(p)}),
            "details": _details(job, entry, cfg, env, films, len(items) - films, util)}


NEEDS_KEY = re.compile(r"\b([A-Z][A-Z0-9_]+) is not set\b")


def export_items(job, index, env):
    """Read one collection or playlist's films live, for export_list. Runs outside the lock."""
    if KINDS[job] == "genre":
        raise Invalid(["Genres have no films to save"])
    data = list_items(job, index, env)
    films = [i for i in data["items"] if not i["duplicate"] and i["imdb"]]
    if not films:
        raise Invalid(data["problems"] or ["There are no films with an IMDb ID on its lists to save"])
    return data, films


def export_list(job, index, data, films, use_it, env):
    """Freeze what a collection or playlist's sources give today into a list file of its own,
    collections/<name>.md or playlists/<name>.md, to hand-edit. With use_it, the entry then
    follows that file instead of its sources. Returns {name, films, skipped, used}."""
    import datetime
    stem = slug(data["name"]).replace("template", "list")
    name = f"{job}/{stem}.md"
    n = 2
    while os.path.exists(watchlist_path(name)):
        name = f"{job}/{stem}-{n}.md"
        n += 1
    links = ", ".join(s for s in data["sources"] if not _is_list_file(s))
    lines = [f"# {data['name']}", "",
             f"Saved from {links or 'its lists'} on {datetime.date.today().isoformat()}. Edit it freely: "
             "one film per line, in play order.", ""]
    for f in films:
        title = f"{f['title']} ({f['year']})" if f.get("year") else f["title"]
        lines.append(f"- {f['imdb']} | {title}" + (f" {f['notes']}" if f.get("notes") else ""))
    _write(watchlist_path(name), "\n".join(lines) + "\n")
    used = False
    if use_it:
        current = entries(job)
        if not 0 <= index < len(current["entries"]) or current["entries"][index].get("name") != data["name"]:
            raise Conflict(f"{backend.JOBS[job]['config']} changed meanwhile. {name} was saved; pick it under Sources.")
        e = dict(current["entries"][index])
        e.pop("index", None)
        e["sources"] = [name]
        save_entry(job, index, e, current["version"], env)
        used = True
    skipped = sum(1 for i in data["items"] if not i["duplicate"] and not i["imdb"])
    return {"name": name, "films": len(films), "skipped": skipped, "used": used}


def _library(job, entry, env, items):
    """What the last sync found on each server this list goes to: [{server, at, listed,
    in_library, missing, errors, error}]. The first one with a result also marks each film in
    items as on that server (in_library True), missing (False) or not checked yet (None)."""
    if job == "genres":
        return []
    found = importlib.import_module(f"{backend.PKG}.results").load(backend.CONFIG_DIR, KINDS[job])
    mine = found.get(entry.name.lower()) or {}
    out = []
    for s in _settings_module().servers(env):
        row = mine.get(s["name"])
        if not entry.on(s["name"]) or not isinstance(row, dict):
            continue
        out.append({"server": s["name"], "at": row.get("at"), "listed": row.get("listed"),
                    "in_library": row.get("in_library"), "members": row.get("members"),
                    "missing": [m.get("imdb") for m in row.get("missing", []) if m.get("imdb")],
                    "missing_count": row.get("missing_count", len(row.get("missing", []))),
                    "errors": row.get("errors", 0), "error": row.get("error", ""),
                    "have": row.get("have", [])})
    if out:
        have, gone = set(out[0]["have"]), set(out[0]["missing"])
        for it in items:
            it["in_library"] = True if it["imdb"] in have else False if it["imdb"] in gone else None
    for row in out:
        del row["have"]     # only needed to mark the films
    return out


def _details(job, entry, cfg, env, films, repeats, util):
    """[label, value] rows describing an entry, for the top of its list window."""
    import datetime
    found = _settings_module().servers(env)
    names = [x["name"] for x in found]
    where = []
    if len(names) > 1 or entry.servers:
        where = [["Servers", f"Only {', '.join(entry.servers)}" if entry.servers else f"Every server ({', '.join(names)})"]]
    if job == "genres":
        return [["Type", "Genre artwork"], *where,
                ["On the server", f"Set on the genre called {entry.name} (any capitalization). The genre itself "
                                  "comes from your films' metadata and is never created or deleted here."]]
    # who owns and watches playlists differs per server; describe the first one it goes to
    env = next((x["env"] for x in found if entry.on(x["name"])), env)
    try:
        live = util.is_active(entry.active, datetime.date.today())
        season = ("In season now" if live else "Out of season") + f", {entry.active}" if entry.active else "Year round"
    except util.ConfigError as e:
        season = f"Not valid: {e}"
    rows = [["Type", KINDS[job].capitalize()],
            ["Films", f"{films}" + (f" ({repeats} listed in more than one source counted once)" if repeats else "")],
            ["Season", season], *where]
    if job == "collections":
        if entry.description:
            rows.append(["Description", entry.description])
        elif cfg.settings.get("use_list_descriptions"):
            rows.append(["Description", "Copied from the MDBList or Trakt list, if it has one"])
        rows.append(["Sort name", entry.sort_name or f"{entry.name} (same as the title)"])
        rows.append(["Display order", {"release_date": "Release date", "sort_name": "Sort name"}.get(
            entry.display_order, "Not set here (the server's setting is left as it is)")])
    else:
        people = [p.strip() for p in (env.get("PLAYLIST_USERS") or "").split(",") if p.strip()]
        admin = env.get("SERVER_USER", "").strip()
        if not admin or re.fullmatch(r"[0-9a-fA-F-]{20,}", admin):   # blank, or a user ID nobody can read
            admin = "the admin user set in Settings" if admin else "the server's first admin user"
        watchers = entry.watched_by or env.get("WATCHED_BY") or admin
        if people:
            rows.append(["Sharing", f"A private copy for each of {', '.join(people)}, hiding what that person watched"])
        else:
            rows.append(["Sharing", "Every user can see it" if entry.share == "view" else f"Only {admin} can see it"])
            rows.append(["Watched films", "Kept on the list" if entry.include_watched else f"Dropped once played by {watchers}"])
    return rows


def _feed(sources, spec, base_dir):
    """One source as the page shows it: what kind it is, and a link or list file to open."""
    out = {"spec": spec, "kind": "unknown", "url": None, "file": None, "count": 0}
    try:
        kind, where = sources.parse(spec, base_dir)
    except Exception:
        return out
    out["kind"] = kind
    if kind == "mdblist":
        out["url"] = f"https://mdblist.com/lists/{where}" if "/" in where else f"https://mdblist.com/?list={where}"
    elif kind == "trakt":
        user, slug = where.split("/")
        out["url"] = f"https://trakt.tv/users/{user}/" + ("watchlist" if slug == "watchlist" else f"lists/{slug}")
    elif _is_list_file(spec):
        out["file"] = spec.strip()
    return out


def _artwork_for(entry):
    """The poster, thumb and backdrops an entry sets, each with a config-folder image the page can
    show: the file itself, or for a URL or provider image the copy the last sync saved."""
    artwork = importlib.import_module(f"{backend.PKG}.artwork")
    specs = [(what, 0, spec) for what, spec in (("poster", entry.poster), ("thumb", entry.thumb)) if spec] + \
            [("backdrop", i, b) for i, b in enumerate(entry.backdrops)]
    out = []
    for what, i, spec in specs:
        image = None
        if artwork.is_remote(spec):
            stem = artwork.copy_name(entry.what, entry.name, what, i)
            image = next((f"images/{stem}{ext}" for ext in artwork.IMAGE_TYPES
                          if image_path(f"images/{stem}{ext}")), None)
        elif image_path(spec):
            image = spec
        url = spec if not image and re.match(r"https?://", spec) else None
        out.append({"what": what, "spec": spec, "image": image, "url": url, "remote": artwork.is_remote(spec)})
    return out


# ---------------------------------------------------------------- importing from the server

def _server(env, want=None):
    """One media server (by name or number; the first one if not given) as (server, its env)."""
    mods = {m: importlib.import_module(f"{backend.PKG}.{m}") for m in ("server", "util")}
    try:
        s = _settings_module().pick_servers(env, want)[0]
        return mods["server"].connect(s["env"], s["id"]), s["env"]
    except mods["util"].ConfigError as e:
        raise Invalid([str(e)])


def _importer(env, server=None):
    mods = {m: importlib.import_module(f"{backend.PKG}.{m}") for m in ("importer", "util")}
    srv, senv = _server(env, server)
    return mods["importer"].Importer(srv, senv, backend.CONFIG_DIR), mods["util"]


def import_scan(env, progress=None, server=None):
    """One server's collections and playlists, each marked managed, similar, new or duplicate,
    plus {server: its name, servers: every server's name}.
    progress, if given, hears each slow step ({"step", "done", "total"})."""
    imp, util = _importer(env, server)
    try:
        out = imp.scan(progress=progress)
    except util.ConfigError as e:
        raise Invalid([str(e)])
    except Exception as e:
        raise Invalid([f"Couldn't read {imp.server.label}'s collections and playlists: {util.describe(e)}"])
    return {**out, "server": imp.server.label, "servers": [x["name"] for x in _settings_module().servers(env)]}


def import_adopt(picks, env, progress=None, server=None):
    """Import or link the picked ones from one server. Returns {results: [one line per pick]}.
    progress, if given, hears each pick before and after ({"step", "done", "total", "line"?})."""
    if not isinstance(picks, list) or not picks or not all(isinstance(p, dict) for p in picks):
        raise Invalid(["Pick at least one collection or playlist"])
    imp, util = _importer(env, server)
    try:
        return {"results": imp.adopt(picks, progress=progress)}
    except util.ConfigError as e:
        raise Invalid([str(e)])


def server_genres(env):
    """The movie and show genres on every media server, for picking one by its exact name:
    {genres: [name], server: "Emby" or "Emby and Jellyfin", problems: [a server that couldn't be read]}."""
    util = importlib.import_module(f"{backend.PKG}.util")
    names, read, problems = {}, [], []
    for s in _settings_module().servers(env):
        try:
            srv, senv = _server(env, s["id"])
            uid = srv.user(senv.get("SERVER_USER"))["Id"]
            for g in srv.genres(uid):
                names.setdefault(g.lower(), g)
            read.append(s["name"])
        except Invalid as e:
            problems.append(f"{s['name']}: {e}")
        except Exception as e:
            problems.append(f"Couldn't read {s['name']}'s genres: {util.describe(e)}")
    if not read:
        raise Invalid(problems or ["No media server is set up"])
    return {"genres": sorted(names.values(), key=str.lower), "server": " and ".join(read), "problems": problems}


def server_users(env):
    """Every media server's users, for picking who a playlist's "watched by" counts:
    {servers: [{name, users: [user name]}], problems: [a server that couldn't be read]}."""
    util = importlib.import_module(f"{backend.PKG}.util")
    out, problems = [], []
    for s in _settings_module().servers(env):
        try:
            srv, _ = _server(env, s["id"])
            users = [u["Name"] for u in srv.users() if not (u.get("Policy") or {}).get("IsDisabled")]
            out.append({"name": s["name"], "users": sorted(users, key=str.lower)})
        except Invalid as e:
            problems.append(f"{s['name']}: {e}")
        except Exception as e:
            problems.append(f"Couldn't read {s['name']}'s users: {util.describe(e)}")
    if not out:
        raise Invalid(problems or ["No media server is set up"])
    return {"servers": out, "problems": problems}


# ---------------------------------------------------------------- image files

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
IMAGE_DIRS = ("images", "collections", "playlists")


def _image_uses():
    """{absolute path: [what uses it]} for every local image the configs point at, and the
    copies StaffPicked saves of URL and provider images (images/<kind>-<name>-poster.jpg etc.,
    genres included).
    Refuses if a config can't be read, because then nothing can be called unused."""
    uses, copies = {}, {}
    for job, kind in KINDS.items():
        path = config_path(job)
        data = _parse(_read(path), path)
        for raw in data.get(kind, []):
            v = form_values(kind, raw)
            label = f"{kind} {v.get('name') or '(no name)'}"
            images = [(what, 0, v[what]) for what in ("poster", "thumb") if v.get(what)] + \
                     [("backdrop", i, b) for i, b in enumerate(v.get("backdrops", []))]
            for what, i, spec in images:
                if ":" in spec.split("/")[0] and not os.path.isabs(spec):   # URL or provider image
                    s = re.sub(r"[^a-z0-9]+", "-", (v.get("name") or "").lower()).strip("-") or "unnamed"
                    copies[f"{kind}-{s}-{what}" + (f"-{i + 1}" if i else "")] = label
                else:
                    p = os.path.realpath(spec if os.path.isabs(spec) else os.path.join(backend.CONFIG_DIR, spec))
                    uses.setdefault(p, []).append(label)
    return uses, copies


def images():
    """Image files in images/ (archive/ included) and next to the list files, each with what uses it."""
    uses, copies = _image_uses()
    out = []
    for d in IMAGE_DIRS:
        root = os.path.join(backend.CONFIG_DIR, d)
        for folder, subdirs, files in os.walk(root):
            if d != "images":
                subdirs[:] = []
            for f in sorted(files):
                if not f.lower().endswith(IMAGE_EXTS):
                    continue
                p = os.path.join(folder, f)
                rel = os.path.relpath(p, backend.CONFIG_DIR).replace(os.sep, "/")
                used = list(uses.get(os.path.realpath(p), []))
                archived = rel.startswith("images/archive/")
                if not archived and folder == os.path.join(backend.CONFIG_DIR, "images"):
                    stem = os.path.splitext(f)[0]
                    if stem in copies:
                        used.append(f"saved copy for {copies[stem]}")
                st = os.stat(p)
                out.append({"name": rel, "size": st.st_size, "modified": int(st.st_mtime),
                            "used_by": used, "state": "used" if used else "archived" if archived else "unused"})
    return out


def image_path(name):
    """The file for an image name from the page, only inside images/ or the list folders."""
    name = str(name or "")
    if not name.lower().endswith(IMAGE_EXTS) or not name.split("/")[0] in IMAGE_DIRS or "\\" in name:
        return None
    p = os.path.realpath(os.path.join(backend.CONFIG_DIR, name))
    roots = [os.path.realpath(os.path.join(backend.CONFIG_DIR, d)) + os.sep for d in IMAGE_DIRS]
    return p if any(p.startswith(r) for r in roots) and os.path.isfile(p) else None


def delete_images(names):
    """Delete the named image files. Nothing is deleted if any of them is missing or in use."""
    if not isinstance(names, list) or not names:
        raise Invalid(["Pick at least one image"])
    listing = {i["name"]: i for i in images()}
    problems = []
    for n in names:
        if n not in listing or not image_path(n):
            problems.append(f"{n} isn't there any more")
        elif listing[n]["used_by"]:
            problems.append(f"{n} is in use ({', '.join(listing[n]['used_by'])})")
    if problems:
        raise Invalid(problems)
    deleted = []
    for n in dict.fromkeys(names):
        os.remove(image_path(n))
        deleted.append(n)
    return {"deleted": deleted}


UPLOAD_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
UPLOAD_LIMIT = 30_000_000


def _image_type(data):
    """The real type of uploaded bytes, from their first bytes (not what the browser claims)."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def save_upload(filename, data):
    """Save an image uploaded from the browser to images/, under its own name made safe and
    never over an existing file. Returns {name}: the path to put in a poster or backdrop."""
    ctype = _image_type(data)
    if not ctype:
        raise Invalid(["That file isn't a JPEG, PNG or WebP image"])
    stem = re.sub(r"[^a-z0-9]+", "-", os.path.splitext(os.path.basename(str(filename or "")))[0].lower()).strip("-")[:80]
    stem, ext = stem or "upload", UPLOAD_TYPES[ctype]
    folder = os.path.join(backend.CONFIG_DIR, "images")
    os.makedirs(folder, exist_ok=True)
    name, n = f"{stem}{ext}", 1
    while os.path.exists(os.path.join(folder, name)):
        n += 1
        name = f"{stem}-{n}{ext}"
    path = os.path.join(folder, name)
    with open(path + ".part", "wb") as f:
        f.write(data)
    os.replace(path + ".part", path)
    return {"name": f"images/{name}", "size": len(data)}


def image_names():
    """Image files in the config folder, for picking one in a form (archived copies left out)."""
    out = []
    for d in IMAGE_DIRS:
        root = os.path.join(backend.CONFIG_DIR, d)
        for folder, subdirs, files in os.walk(root):
            subdirs[:] = [s for s in subdirs if d == "images" and s != "archive"]
            for f in sorted(files):
                if f.lower().endswith(IMAGE_EXTS):
                    out.append(os.path.relpath(os.path.join(folder, f), backend.CONFIG_DIR).replace(os.sep, "/"))
    return out
