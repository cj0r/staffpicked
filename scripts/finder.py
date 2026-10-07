"""Finding the list a collection on the server was built from, so it can come back as a
list-based collection instead of a fixed copy of what it holds today.

Two ways, in this order:
  1. a link in the collection itself: an MDBList or Trakt list URL in its overview or tags
  2. matching its films against MDBList lists: your own lists, plus the public lists whose
     names come closest to the collection's. A list matches when the films it has in your
     library are (nearly) the films in the collection. Up to three lists can be combined,
     for collections built from several.
Matching needs MDBLIST_API_KEY. Nothing here changes anything; it only reads.
"""
import difflib, re
from .sources import MDBLIST_URL, TRAKT_URL, Sources
from .util import request

API = "https://api.mdblist.com"
GOOD = 0.6         # how close (0-1, Jaccard) a list's films must be to the collection's
MAX_LISTS = 3      # most lists combined for one collection
SEARCHED = 6       # public lists checked per collection, closest names first


def _key(name):
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def _jaccard(a, b):
    return len(a & b) / len(a | b) if a or b else 0.0


class SourceFinder:
    def __init__(self, env, base_dir, library_imdb):
        self.env, self.library = env, library_imdb      # IMDb IDs of every film and show on the server
        self.src = Sources(env, base_dir)
        self.key = env.get("MDBLIST_API_KEY")
        self._own, self._searches, self._films = None, {}, {}

    def find(self, name, members, hint_text=""):
        """{"sources": [spec], "how": text} for a collection with these IMDb IDs, or None."""
        links = [f"https://mdblist.com/lists/{m[1]}/{m[2]}" for m in MDBLIST_URL.finditer(hint_text or "")]
        links += [f"https://trakt.tv/users/{m[1]}/{'lists/' + m[2] if m[2] else 'watchlist'}"
                  for m in TRAKT_URL.finditer(hint_text or "")]
        if links:
            how = "linked in its overview or tags"
            if any("trakt.tv" in l for l in links) and not self.env.get("TRAKT_CLIENT_ID"):
                how += "; syncing it needs a Trakt client ID in Settings"
            return {"sources": list(dict.fromkeys(links)), "how": how}
        if not self.key or not members:
            return None
        members = set(members)
        candidates = self.candidates(name)
        scored = []
        for lst in candidates:
            films = self.films(lst)
            if films is None:
                continue
            here = films & self.library
            # small collections match too easily, so they also need a list with a similar name
            if len(members) < 3 and difflib.SequenceMatcher(None, _key(lst["name"]), _key(name)).ratio() < 0.8:
                continue
            if here and len(here & members) / len(here) >= 0.5:     # mostly inside the collection
                scored.append((_jaccard(here, members), lst, here))
        scored.sort(key=lambda s: -s[0])
        picked, have, best = [], set(), 0.0
        for score, lst, here in scored:
            if len(picked) == MAX_LISTS:
                break
            gain = _jaccard(have | here, members)
            if gain >= best + 0.05:
                picked.append(lst)
                have, best = have | here, gain
        if not picked or best < GOOD:
            return None
        both = "together they have" if len(picked) > 1 else "it has"
        return {"sources": [f"https://mdblist.com/lists/{lst['user_name']}/{lst['slug']}" for lst in picked],
                "how": f"found on MDBList: {both} {round(best * 100)}% the same films"}

    def candidates(self, name):
        """Your own MDBList lists plus the public ones with the closest names."""
        if self._own is None:
            try:
                self._own = request("GET", f"{API}/lists/user", {"apikey": self.key}) or []
            except Exception:
                self._own = []
        if name not in self._searches:
            try:
                found = request("GET", f"{API}/lists/search", {"query": name, "apikey": self.key}) or []
            except Exception:
                found = []
            found.sort(key=lambda lst: -difflib.SequenceMatcher(None, _key(lst.get("name")), _key(name)).ratio())
            self._searches[name] = found[:SEARCHED]
        seen, out = set(), []
        for lst in self._own + self._searches[name]:
            if lst.get("id") not in seen and lst.get("user_name") and lst.get("slug"):
                seen.add(lst["id"])
                out.append(lst)
        return out

    def films(self, lst):
        """IMDb IDs on a list (None if it can't be read)."""
        if lst["id"] not in self._films:
            try:
                items = self.src.items(f"mdblist:{lst['id']}")
                self._films[lst["id"]] = {it.ids["imdb"] for it in items if it.ids.get("imdb")}
            except Exception:
                self._films[lst["id"]] = None
        return self._films[lst["id"]]
