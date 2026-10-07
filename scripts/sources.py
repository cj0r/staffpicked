"""Where list items come from: MDBList, Trakt, and your own list files.

A source is written as a string in collections.toml or playlists.toml:
  https://mdblist.com/lists/<user>/<list>   or  mdblist:<user>/<list>  or  mdblist:<list id>
  https://trakt.tv/users/<user>/lists/<list> or  trakt:<user>/<list>   or  trakt:<user>/watchlist
  playlists/my-list.md, collections/my-list.md   a local file with one IMDb ID (tt0081505) per line
Items keep the list's own order, which is what playlists play in.
"""
import os, re, urllib.parse
from .util import ConfigError, request

MDBLIST_URL = re.compile(r"mdblist\.com/lists/([^/?#\s]+)/([^/?#\s]+)")
TRAKT_URL = re.compile(r"trakt\.tv/users/([^/?#\s]+)/(?:lists/([^/?#\s]+)|(watchlist))")
IMDB_ID = re.compile(r"\btt\d{7,}\b")
# a list item or table row that starts with a "Title (Year)" (notes with sentences or bold don't count)
FILM_LINE = re.compile(r"^\s*(?:[-*+]|\d+[.)]|\|(?:\s*\d+\s*\|)?)\s*[^\s(|.*][^(|.*]{0,80}\(\d{4}\)")


class Item:
    __slots__ = ("kind", "title", "year", "ids", "score")

    def __init__(self, kind, title, year, ids=None, score=None):
        self.kind, self.title, self.year, self.score = kind, title or "?", year, score
        self.ids = {k: str(v).lower() for k, v in (ids or {}).items() if v}

    def __repr__(self):
        return f"{self.title} ({self.year})" if self.year else self.title


def parse(spec, base_dir):
    """Turn a source string into (kind, details). Raises ConfigError if it isn't one."""
    s = str(spec).strip()
    m = MDBLIST_URL.search(s)
    if m:
        return "mdblist", f"{m[1]}/{m[2]}"
    m = TRAKT_URL.search(s)
    if m:
        return "trakt", f"{m[1]}/{m[2] or 'watchlist'}"
    if s.lower().startswith("mdblist:"):
        rest = s[8:].strip("/ ")
        if rest.isdigit() or re.fullmatch(r"[^/\s]+/[^/\s]+", rest):
            return "mdblist", rest
    elif s.lower().startswith("trakt:"):
        rest = s[6:].strip("/ ")
        if re.fullmatch(r"[^/\s]+/[^/\s]+", rest):
            return "trakt", rest
    elif s.lower().endswith(".md"):
        return "file", s if os.path.isabs(s) else os.path.join(base_dir, s)
    raise ConfigError(f"source {s!r} is not an MDBList or Trakt list or a .md list file")


class Sources:
    def __init__(self, env, base_dir):
        self.env, self.base_dir, self.cache, self.info = env, base_dir, {}, {}

    def items(self, spec):
        kind, where = parse(spec, self.base_dir)
        key = (kind, where)
        if key not in self.cache:
            self.cache[key] = getattr(self, f"_{kind}")(where)
        return self.cache[key]

    def description(self, spec):
        """A list's own description, where the service has one (MDBList and Trakt)."""
        kind, where = parse(spec, self.base_dir)
        try:
            if kind == "mdblist":
                info = request("GET", f"https://api.mdblist.com/lists/{self._path(where)}",
                               {"apikey": self.need("MDBLIST_API_KEY")})
                info = info[0] if isinstance(info, list) and info else info or {}
            elif kind == "trakt" and not where.endswith("/watchlist"):
                user, slug = where.split("/")
                info = request("GET", f"https://api.trakt.tv/users/{user}/lists/{slug}", headers=self._trakt_headers())
            else:
                return ""
        except Exception:
            return ""
        return (info.get("description") or "").strip()

    def need(self, name):
        value = self.env.get(name)
        if not value:
            raise ConfigError(f"{name} is not set in staffpicked.env")
        return value

    # --- MDBList: your own private lists work too, because the API key is yours.
    @staticmethod
    def _path(where):
        if where.isdigit():
            return where
        user, slug = where.split("/")
        return f"{urllib.parse.quote(user)}/{urllib.parse.quote(slug)}"

    def _mdblist(self, where):
        key, out, offset = self.need("MDBLIST_API_KEY"), [], 0
        while True:
            page = request("GET", f"https://api.mdblist.com/lists/{self._path(where)}/items",
                           {"apikey": key, "limit": 1000, "offset": offset, "append_to_response": "ratings"})
            got = 0
            for group, kind in (("movies", "movie"), ("shows", "show")):
                for it in page.get(group) or []:
                    ids = dict(it.get("ids") or {})
                    ids.setdefault("imdb", it.get("imdb_id"))
                    ids.setdefault("tvdb", it.get("tvdb_id"))
                    ids.setdefault("tmdb", it.get("id"))
                    ids.pop("mdblist", None)
                    # a title IMDb doesn't have comes with a stand-in like "tr943706": no IMDb ID at all
                    if not re.fullmatch(r"tt\d+", str(ids.get("imdb") or "")):
                        ids.pop("imdb", None)
                    # the MDBList score rides along with the list, so the list window needs no extra call
                    score = next((r.get("score") for r in it.get("ratings") or [] if r.get("source") == "mdblist"), None)
                    out.append((it.get("rank") or 0, Item(kind, it.get("title"), it.get("release_year"), ids, score)))
                    got += 1
            if not (page.get("pagination") or {}).get("has_more") or not got:
                break
            offset += got
        out.sort(key=lambda r: r[0])     # movies and shows come back separately; rank merges them
        return [it for _, it in out]

    # --- Trakt: public lists need only TRAKT_CLIENT_ID; private lists and
    # watchlists also need TRAKT_ACCESS_TOKEN for the account that owns them.
    def _trakt_headers(self):
        h = {"trakt-api-version": "2", "trakt-api-key": self.need("TRAKT_CLIENT_ID")}
        if self.env.get("TRAKT_ACCESS_TOKEN"):
            h["Authorization"] = f"Bearer {self.env['TRAKT_ACCESS_TOKEN']}"
        return h

    def _trakt(self, where):
        user, slug = where.split("/")
        path = f"/users/{user}/watchlist" if slug == "watchlist" else f"/users/{user}/lists/{slug}/items"
        rows, page = [], 1
        while True:
            batch = request("GET", f"https://api.trakt.tv{path}", {"page": page, "limit": 1000},
                            headers=self._trakt_headers())
            rows += batch or []
            if len(batch or []) < 1000:
                break
            page += 1
        out = []
        for n, r in enumerate(rows):
            kind = r.get("type")
            if kind not in ("movie", "show"):
                continue              # seasons, episodes and people can't go in a collection
            m = r.get(kind) or {}
            ids = {k: v for k, v in (m.get("ids") or {}).items() if k in ("imdb", "tmdb", "tvdb")}
            out.append((r.get("rank") or n, Item(kind, m.get("title"), m.get("year"), ids)))
        out.sort(key=lambda r: r[0])
        return [it for _, it in out]

    # --- Watchlist files: every line with an IMDb ID is one film or show, in file order.
    def _file(self, path):
        if not os.path.isfile(path):
            raise ConfigError(f"list file not found: {path}")
        return [Item("any", label, None, {"imdb": imdb}) for _, imdb, label in read_watchlist(path)]


def _lines(path):
    """(line number, text) of a Markdown file, leaving out HTML comments and fenced code blocks."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    text = re.sub(r"<!--.*?-->", lambda m: "\n" * m[0].count("\n"), text, flags=re.S)
    fenced = False
    for n, line in enumerate(text.split("\n"), 1):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        elif not fenced:
            yield n, line


def _label(line, imdb):
    """The rest of the line, as a name for the output: list marker, ID and table bars removed."""
    rest = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", line.replace(imdb, " "))
    rest = re.sub(r"\s*\|\s*", " ", rest)
    rest = re.sub(r"\s+", " ", rest).strip(" -:,")
    return f"{rest[:60]} ({imdb})" if rest else imdb


def read_watchlist(path):
    """(line number, IMDb ID, label) for each entry, in file order."""
    out = []
    for n, line in _lines(path):
        m = IMDB_ID.search(line)
        if m:
            out.append((n, m[0], _label(line, m[0])))
    return out


def check_file(path):
    """Problems in a list file, for the check command."""
    entries, issues = read_watchlist(path), []
    if not entries:
        issues.append("no lines with an IMDb ID like tt0081505")
    first = {}
    for n, imdb, _ in entries:
        if imdb in first:
            issues.append(f"line {n}: {imdb} is already on line {first[imdb]}")
        first.setdefault(imdb, n)
    has_id = {n for n, _, _ in entries}
    for n, line in _lines(path):
        if n not in has_id and FILM_LINE.match(line):
            issues.append(f"line {n} has no IMDb ID, so it is skipped: {line.strip()[:60]}")
    return len(entries), issues
