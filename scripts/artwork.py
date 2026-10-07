"""Posters, thumbs and backdrops, from a local file, a URL, TMDB, fanart.tv or MediUX.

An image is written as a string in collections.toml, playlists.toml or genres.toml:
  images/80s-horror.jpg        a file, relative to the config folder (or absolute)
  https://example.com/a.jpg    any image URL
  tmdb:movie/586577            TMDB's best image for a movie (also tmdb:tv/<id>, tmdb:collection/<id>);
                               backdrops prefer textless ones, posters and thumbs prefer English
  tmdb:/gE6lGe7f7QtX1R2pRpXu1AgH1hU.jpg   one exact TMDB image file
  fanart:movie/586577          fanart.tv's most liked image (movie by TMDB or IMDb id; tv by TVDB id)
                               (a thumb is fanart.tv's wide moviethumb or tvthumb)
  mediux:movie/1091            MediUX's best set for a movie (also mediux:collection/<TMDB id>),
                               English or textless first, then its most popular
  mediux:set/10389             one MediUX set, the number in its mediux.pro/sets/ address
                               (a pasted https://mediux.pro/sets/10389 link works too)
  mediux:<asset id>            one exact MediUX image

ThePosterDB has no API for apps, so its posters are added by hand: download one from
theposterdb.com and upload it, or save it in images/.

Images that aren't local files are also saved to images/ (see save_copy), so the config
folder keeps a copy of every poster and backdrop in use.
"""
import os, re, time
from .util import ConfigError, HTTPError, request

IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
TMDB_KINDS = ("movie", "tv", "collection")
MEDIUX = re.compile(r"(movie/\d+|collection/\d+|set/\d+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.I)
MEDIUX_SET_LINK = re.compile(r"https?://(?:www\.)?mediux\.pro/sets/(\d+)", re.I)
TPDB_BY_HAND = ("ThePosterDB images are added by hand: download the poster from theposterdb.com, "
                "then upload it or save it in images/ and use that file")


def mediux_spec(spec):
    """What follows "mediux:" for a MediUX image (a pasted mediux.pro set link counts), or None."""
    s = str(spec).strip()
    link = MEDIUX_SET_LINK.match(s)
    if link:
        return f"set/{link[1]}"
    return s[7:] if s.lower().startswith("mediux:") else None


def needs_mediux_token(spec):
    """MediUX lookups need MEDIUX_API_TOKEN; one exact image doesn't."""
    rest = mediux_spec(spec)
    return rest is not None and "/" in rest


def check(spec, base_dir):
    """Problems with an image setting that can be found without downloading anything."""
    s = str(spec).strip()
    low = s.lower()
    if low.startswith(("http://", "https://")):
        return []
    if low.startswith("mediux:"):
        return [] if MEDIUX.fullmatch(s[7:]) else \
            [f"{s!r}: use mediux:movie/<TMDB id>, mediux:collection/<TMDB id>, mediux:set/<set id> or mediux:<asset id>"]
    if low.startswith("tmdb:"):
        rest = s[5:]
        ok = rest.startswith("/") or re.fullmatch(rf"({'|'.join(TMDB_KINDS)})/\d+", rest)
        return [] if ok else [f"{s!r}: use tmdb:movie/<id>, tmdb:tv/<id>, tmdb:collection/<id> or tmdb:/<file>.jpg"]
    if low.startswith("fanart:"):
        ok = re.fullmatch(r"(movie/(\d+|tt\d+)|tv/\d+)", s[7:])
        return [] if ok else [f"{s!r}: use fanart:movie/<TMDB or IMDb id> or fanart:tv/<TVDB id>"]
    if low.startswith("tpdb:"):
        return [f"{s!r}: {TPDB_BY_HAND}"]
    path = s if os.path.isabs(s) else os.path.join(base_dir, s)
    if os.path.splitext(path)[1].lower() not in IMAGE_TYPES:
        return [f"image {s!r} must be .jpg, .jpeg, .png or .webp"]
    return []


def is_remote(spec):
    """True for a URL or provider image, False for a local file."""
    s = str(spec).strip()
    return ":" in s.split("/")[0] and not os.path.isabs(s)


def missing_file(spec, base_dir):
    """True for a local image file that isn't there (a warning: the rest still syncs)."""
    s = str(spec).strip()
    if is_remote(s):
        return False
    return not os.path.isfile(s if os.path.isabs(s) else os.path.join(base_dir, s))


def copy_name(what, name, label, index):
    """File name (without extension) for a downloaded image, e.g. collection-80s-horror-backdrop-2."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "unnamed"
    return f"{what}-{slug}-{label}" + (f"-{index + 1}" if index else "")


def _saved(folder, stem):
    return [os.path.join(folder, stem + e) for e in IMAGE_TYPES if os.path.isfile(os.path.join(folder, stem + e))]


def archive(base_dir, stem, dry_run=False):
    """Move images/<stem>.* to images/archive/<stem>-<date and time>.<ext>; never deletes.
    Returns the archive paths."""
    folder = os.path.join(base_dir, "images")
    stamp, moved = time.strftime("%Y-%m-%d-%H%M%S"), []
    for path in _saved(folder, stem):
        ext, n = os.path.splitext(path)[1], 1
        dest = os.path.join(folder, "archive", f"{stem}-{stamp}{ext}")
        while os.path.exists(dest):
            n += 1
            dest = os.path.join(folder, "archive", f"{stem}-{stamp}-{n}{ext}")
        if not dry_run:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            os.replace(path, dest)
        moved.append(dest)
    return moved


def save_copy(base_dir, stem, data, ctype, dry_run=False):
    """Save a downloaded image as images/<stem>.<ext>. A different image already saved under that
    name is archived first (see archive). Returns (saved path or None if unchanged, archive paths)."""
    folder = os.path.join(base_dir, "images")
    ext = {v: k for k, v in reversed(IMAGE_TYPES.items())}.get(ctype, ".jpg")
    target = os.path.join(folder, stem + ext)
    if os.path.isfile(target):
        with open(target, "rb") as f:
            if f.read() == data:
                return None, []                # this image is already saved
    archived = archive(base_dir, stem, dry_run=dry_run)
    if not dry_run:
        os.makedirs(folder, exist_ok=True)
        with open(target + ".part", "wb") as f:
            f.write(data)
        os.replace(target + ".part", target)
    return target, archived


class Artwork:
    def __init__(self, env, base_dir):
        self.env, self.base_dir = env, base_dir

    def need(self, name):
        value = self.env.get(name)
        if not value:
            raise ConfigError(f"{name} is not set in staffpicked.env")
        return value

    def fetch(self, spec, kind):
        """Return (bytes, content type) for an image setting. kind is "poster", "thumb" or "backdrop"."""
        s = str(spec).strip()
        low = s.lower()
        if mediux_spec(s) is not None:
            return self.mediux(mediux_spec(s), kind)
        if low.startswith(("http://", "https://")):
            return self.download(s)
        if low.startswith("tmdb:"):
            return self.tmdb(s[5:], kind)
        if low.startswith("fanart:"):
            return self.fanart(s[7:], kind)
        if low.startswith("tpdb:"):
            raise ValueError(TPDB_BY_HAND)
        path = s if os.path.isabs(s) else os.path.join(self.base_dir, s)
        with open(path, "rb") as f:
            return f.read(), IMAGE_TYPES.get(os.path.splitext(path)[1].lower(), "image/jpeg")

    @staticmethod
    def download(url):
        data, ctype = request("GET", url, raw=True)
        if not ctype.startswith("image/"):
            ext = os.path.splitext(url.split("?")[0])[1].lower()
            if ext not in IMAGE_TYPES:
                raise ValueError(f"{url} did not return an image ({ctype})")
            ctype = IMAGE_TYPES[ext]
        return data, ctype

    # --- TMDB: v4 read access token (TMDB_API_TOKEN), sent as a bearer token.
    def tmdb(self, rest, kind):
        if rest.startswith("/"):
            return self.download(f"https://image.tmdb.org/t/p/original{rest}")
        what, tmdb_id = rest.split("/")
        r = request("GET", f"https://api.themoviedb.org/3/{what}/{tmdb_id}/images",
                    headers={"Authorization": f"Bearer {self.need('TMDB_API_TOKEN')}"})
        images = r.get("posters" if kind == "poster" else "backdrops") or []
        # posters and thumbs (a wide backdrop with its title on): English, then textless;
        # backdrops: textless, then English
        langs = (None, "en") if kind == "backdrop" else ("en", None)
        rank = lambda i: (langs.index(i.get("iso_639_1")) if i.get("iso_639_1") in langs else 2,
                          -(i.get("width") or 0), -(i.get("vote_average") or 0))
        if not images:
            raise ValueError(f"TMDB has no {kind} for {what}/{tmdb_id}")
        return self.download(f"https://image.tmdb.org/t/p/original{min(images, key=rank)['file_path']}")

    # --- fanart.tv: personal API key (FANARTTV_API_KEY).
    def fanart(self, rest, kind):
        what, the_id = rest.split("/")
        r = request("GET", f"https://webservice.fanart.tv/v3/{'movies' if what == 'movie' else 'tv'}/{the_id}",
                    {"api_key": self.need("FANARTTV_API_KEY")})
        field = {("movie", "poster"): "movieposter", ("movie", "backdrop"): "moviebackground",
                 ("movie", "thumb"): "moviethumb", ("tv", "poster"): "tvposter",
                 ("tv", "backdrop"): "showbackground", ("tv", "thumb"): "tvthumb"}[(what, kind)]
        images = r.get(field) or []
        if not images:
            raise ValueError(f"fanart.tv has no {field} for {what}/{the_id}")
        prefer = "" if kind == "backdrop" else "en"
        best = max(images, key=lambda i: (i.get("lang") in (prefer, "00"), int(i.get("likes") or 0)))
        return self.download(best["url"])

    # --- MediUX: an API for poster sets (MEDIUX_API_TOKEN, sent as a bearer token), looked up by
    # TMDB id or set id. Images are public at /assets/<id>; each is downloaded once and kept in
    # cache/mediux/, so a sync only asks MediUX which image to use.
    MEDIUX_API = "https://images.mediux.io"

    def mediux(self, rest, kind):
        if "/" not in rest:
            return self._mediux_asset(rest.lower())
        if kind == "thumb":
            raise ValueError("MediUX has no thumbs; use it for posters and backdrops")
        what, the_id = rest.split("/")
        side = "poster" if kind == "poster" else "backdrop"
        image = "{ id modified_on language { display_name } }"
        if what == "set":         # a set page's number: a movie set or a collection set
            data = self._mediux_query(f"{{ movie: movie_sets_by_id(id: {the_id}) {{ popularity movie_{side} {image} }} "
                                      f"collection: collection_sets_by_id(id: {the_id}) {{ popularity collection_{side} {image} }} }}")
            sets = [(data[t], f"{t}_{side}") for t in ("movie", "collection") if data.get(t)]
        else:
            data = self._mediux_query(f"{{ item: {what}s_by_id(id: {the_id}) {{ sets: {what}_sets {{ popularity "
                                      f"{what}_{side} {image} }} }} }}")
            sets = [(one, f"{what}_{side}") for one in (data.get("item") or {}).get("sets") or []]
        images = [(one.get("popularity"), i) for one, field in sets for i in one.get(field) or []]
        if not images:
            raise ValueError(f"MediUX has no {kind} for {rest}")
        # English or no text first, then the most popular set (1 is the top); newest wins a tie
        images.sort(key=lambda pi: pi[1].get("modified_on") or "", reverse=True)
        pick = min(images, key=lambda pi: (((pi[1].get("language") or {}).get("display_name") or "English") != "English",
                                           pi[0] or 10 ** 9))
        return self._mediux_asset(pick[1]["id"])

    def _mediux_query(self, query):
        try:
            r = request("POST", f"{self.MEDIUX_API}/graphql", json_body={"query": query},
                        headers={"Authorization": f"Bearer {self.need('MEDIUX_API_TOKEN')}"})
        except HTTPError as e:
            if e.code == 401:
                raise ConfigError("MediUX refused MEDIUX_API_TOKEN; check it in Settings") from None
            raise
        return (r or {}).get("data") or {}     # an id MediUX doesn't have comes back as null

    def _mediux_asset(self, asset_id):
        folder = os.path.join(self.base_dir, "cache", "mediux")
        for ext, ctype in IMAGE_TYPES.items():
            path = os.path.join(folder, asset_id + ext)
            if os.path.isfile(path):
                with open(path, "rb") as f:
                    return f.read(), ctype
        data, ctype = self.download(f"{self.MEDIUX_API}/assets/{asset_id}")
        ext = next((e for e, t in IMAGE_TYPES.items() if t == ctype), ".jpg")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, asset_id + ext), "wb") as f:
            f.write(data)
        return data, ctype
