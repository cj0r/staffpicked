"""Talking to the media server. Jellyfin shares most of Emby's API and differs only where
the Jellyfin class below says so."""
import base64, re, time, unicodedata
from .util import ConfigError, HTTPError, URLError, request

BATCH = 100      # item ids per request, to keep URLs short
CLIENT = 'Client="staffpicked", Device="staffpicked", DeviceId="staffpicked", Version="0.1"'


def norm(title):
    s = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", "and")
    s = re.sub(r"^(the|a|an)\s+", "", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def batches(ids):
    for i in range(0, len(ids), BATCH):
        yield ids[i:i + BATCH]


class Emby:
    name = "Emby"
    PUBLIC_PLAYLISTS = False    # True where a playlist can be public: seen by every user without a share
    OWNER_MOVES = False         # True where only the playlist's owner, signed in, can reorder it

    def __init__(self, url, key, label="", sid="1"):
        self.label = label or self.name     # the server's name in StaffPicked ("Emby", "Living Room")
        self.sid = str(sid)                 # its number in staffpicked.env
        if not url or not key:
            keys = "SERVER_URL and SERVER_API_KEY" if self.sid == "1" else f"SERVER_{sid}_URL and SERVER_{sid}_API_KEY"
            raise ConfigError(f"{keys} are not set for {self.label}. Fill them in under Settings "
                              "in the web UI, or in staffpicked.env in the config folder.")
        self.url, self.key = url.rstrip("/"), key

    # --- plumbing
    def auth(self, token):
        return {"X-Emby-Token": token}

    def call(self, method, path, token=None, **kw):
        headers = {} if token == "" else self.auth(token or self.key)
        return request(method, self.url + path, headers={**headers, **kw.pop("headers", {})}, **kw)

    def items(self, uid, **params):
        return self.call("GET", f"/Users/{uid}/Items", params=params)["Items"]

    # --- users
    def users(self):
        return self.call("GET", "/Users")

    def user(self, name):
        """A user by name or ID; with no name, the first administrator."""
        users = self.users()
        for u in users:
            if (name.lower() in (u["Name"].lower(), u["Id"].lower())) if name \
                    else (u.get("Policy") or {}).get("IsAdministrator"):
                return u
        raise ConfigError(f"{self.name} user {name!r} not found. Users: {', '.join(u['Name'] for u in users)}")

    def login(self, name, password):
        """Sign in as a user and return a session token (sharing needs one)."""
        r = self.call("POST", "/Users/AuthenticateByName", token="",
                      headers={"X-Emby-Authorization": f"MediaBrowser {CLIENT}"},
                      json_body={"Username": name, "Pw": password or ""})
        return r["AccessToken"]

    def logout(self, token):
        try:
            self.call("POST", "/Sessions/Logout", token=token)
        except URLError:
            pass

    def played(self, uid):
        return {i["Id"] for i in self.items(uid, Recursive="true", IncludeItemTypes="Movie,Series", IsPlayed="true")}

    # --- items
    def library(self, uid):
        return Library(self.items(uid, Recursive="true", IncludeItemTypes="Movie,Series",
                                  Fields="ProviderIds,ProductionYear,DateCreated,PremiereDate"))

    def delete(self, item_id):
        try:
            self.call("DELETE", f"/Items/{item_id}")
        except HTTPError:
            self.call("POST", f"/Items/{item_id}/Delete")  # older Emby builds

    def get_item(self, uid, item_id):
        return self.call("GET", f"/Users/{uid}/Items/{item_id}")

    def update_item(self, item):
        self.call("POST", f"/Items/{item['Id']}", json_body=item)

    def image(self, item_id, kind, index=0):
        """An item's image as (bytes, content type). Raises HTTPError if it has none."""
        path = f"/Items/{item_id}/Images/{kind}" + (f"/{index}" if kind == "Backdrop" else "")
        return request("GET", self.url + path, headers=self.auth(self.key), raw=True)

    def members(self, uid, parent_id, playlist=False):
        """What's in a collection or playlist, with IDs, in its own order."""
        fields = "ProviderIds,ProductionYear"
        if playlist:
            return self.call("GET", f"/Playlists/{parent_id}/Items", params={"UserId": uid, "Fields": fields})["Items"]
        return self.items(uid, ParentId=parent_id, Fields=fields)

    def set_image(self, item_id, kind, index, data, content_type):
        path = f"/Items/{item_id}/Images/{kind}" + (f"/{index}" if kind == "Backdrop" else "")
        self.call("POST", path, data=base64.b64encode(data), content_type=content_type)

    def delete_image(self, item_id, kind, index=0):
        try:
            self.call("DELETE", f"/Items/{item_id}/Images/{kind}/{index}")
        except HTTPError:
            self.call("POST", f"/Items/{item_id}/Images/{kind}/{index}/Delete")  # older Emby builds

    def refresh(self, item_id):
        self.call("POST", f"/Items/{item_id}/Refresh", params={
            "Recursive": "true", "MetadataRefreshMode": "FullRefresh", "ImageRefreshMode": "Default",
            "ReplaceAllMetadata": "false", "ReplaceAllImages": "false"})

    # --- collections
    def collections(self, uid):
        found = {}
        for c in self.items(uid, Recursive="true", IncludeItemTypes="BoxSet"):
            found.setdefault(c["Name"], c["Id"])
        return found

    def children(self, uid, parent_id):
        return {i["Id"] for i in self.items(uid, ParentId=parent_id)}

    def create_collection(self, name, ids):
        first, rest = ids[:BATCH], ids[BATCH:]
        cid = self.call("POST", "/Collections", params={"Name": name, "Ids": ",".join(first)})["Id"]
        self.add_to_collection(cid, rest)
        return cid

    def add_to_collection(self, cid, ids):
        for b in batches(ids):
            self.call("POST", f"/Collections/{cid}/Items", params={"Ids": ",".join(b)})

    def remove_from_collection(self, cid, ids):
        for b in batches(ids):
            self.call("DELETE", f"/Collections/{cid}/Items", params={"Ids": ",".join(b)})

    # --- genres: Emby and Jellyfin both keep one item per genre name, shared by every library
    def genre_items(self, uid):
        """The movie and show genres the user can see, with their image tags."""
        return self.call("GET", "/Genres", params={"UserId": uid, "Recursive": "true", "IncludeItemTypes": "Movie,Series",
                                                   "SortBy": "SortName", "Fields": "ImageTags,BackdropImageTags"})["Items"]

    def genres(self, uid):
        """{genre name: id} for the movie and show genres the user can see."""
        found = {}
        for g in self.genre_items(uid):
            found.setdefault(g["Name"], g["Id"])
        return found

    # --- playlists
    def playlists(self, uid):
        return self.items(uid, Recursive="true", IncludeItemTypes="Playlist")

    def create_playlist(self, uid, name, ids, public=False):
        """public: whether every user can see it (Jellyfin only; Emby shares with share_playlist)."""
        first, rest = ids[:BATCH], ids[BATCH:]
        pid = self.call("POST", "/Playlists", params={
            "Name": name, "Ids": ",".join(first), "UserId": uid, "MediaType": "Video"})["Id"]
        for b in batches(rest):
            self.call("POST", f"/Playlists/{pid}/Items", params={"Ids": ",".join(b), "UserId": uid})
        return pid

    def playlist_entries(self, uid, pid):
        """[(item id, entry id)] in playlist order. The entry id names one spot in the playlist,
        which removing and moving go by."""
        items = self.call("GET", f"/Playlists/{pid}/Items", params={"UserId": uid})["Items"]
        return [(it["Id"], it.get("PlaylistItemId")) for it in items]

    def add_to_playlist(self, uid, pid, ids):
        for b in batches(ids):
            self.call("POST", f"/Playlists/{pid}/Items", params={"Ids": ",".join(b), "UserId": uid})

    def remove_from_playlist(self, pid, entry_ids):
        for b in batches(entry_ids):
            self.call("DELETE", f"/Playlists/{pid}/Items", params={"EntryIds": ",".join(b)})

    def move_in_playlist(self, pid, entry_id, index, token=None):
        """token: the owner signed in, for a server that takes moves only from them (OWNER_MOVES)."""
        self.call("POST", f"/Playlists/{pid}/Items/{entry_id}/Move/{index}", token=token)

    def recent(self, uid, limit=50):
        """The films and shows added to the server most recently, newest first."""
        return self.items(uid, Recursive="true", IncludeItemTypes="Movie,Series", SortBy="DateCreated",
                          SortOrder="Descending", Limit=str(limit), Fields="ProviderIds,DateCreated")

    def share_playlist(self, token, pid, user_ids):
        """View-only access for these users. Emby only accepts this from the owner signed in."""
        self.call("POST", "/Items/Access", token=token, json_body={
            "ItemIds": [pid], "UserIds": user_ids, "ItemAccess": "Read"})

    def unshare_playlist(self, token, pid):
        """Hide a playlist from everyone but its owner, where a server shares new playlists
        on its own (see PUBLIC_PLAYLISTS)."""

    def playlist_public(self, token, pid):
        """Whether every user can see the playlist without being given it (see PUBLIC_PLAYLISTS)."""
        return False

    def settle_new_playlist(self, pid):
        """Wait until a new playlist's own poster is in, where the server makes one, so a poster
        sent after it isn't covered up."""


class Jellyfin(Emby):
    """Run against Jellyfin 10.11 and 12.1. 12.1 takes only its own Authorization header, not X-Emby-Token."""
    name = "Jellyfin"
    # A public playlist is one every user can see and play but only the owner can change: the
    # same as share = "view". Jellyfin only switches it for the owner signed in, not the API key.
    PUBLIC_PLAYLISTS = True
    OWNER_MOVES = True

    def auth(self, token):
        return {"Authorization": f'MediaBrowser {CLIENT}, Token="{token}"'}

    def items(self, uid, **params):
        return self.call("GET", "/Items", params={"userId": uid, **params})["Items"]

    def login(self, name, password):
        r = self.call("POST", "/Users/AuthenticateByName", token="",
                      headers={"Authorization": f"MediaBrowser {CLIENT}"},
                      json_body={"Username": name, "Pw": password or ""})
        return r["AccessToken"]

    def get_item(self, uid, item_id):
        return self.call("GET", f"/Items/{item_id}", params={"userId": uid})

    def delete(self, item_id):
        self.call("DELETE", f"/Items/{item_id}")

    def delete_image(self, item_id, kind, index=0):
        self.call("DELETE", f"/Items/{item_id}/Images/{kind}/{index}")

    def set_image(self, item_id, kind, index, data, content_type):
        if kind != "Backdrop":
            return super().set_image(item_id, kind, index, data, content_type)
        # Jellyfin ignores the index and adds every backdrop at the end, so take off the one
        # being replaced, add the new one, then move it into that spot
        have = sum(1 for i in self.call("GET", f"/Items/{item_id}/Images") if i.get("ImageType") == "Backdrop")
        if index < have:
            self.delete_image(item_id, kind, index)
            have -= 1
        self.call("POST", f"/Items/{item_id}/Images/Backdrop", data=base64.b64encode(data), content_type=content_type)
        if have != index:
            self.call("POST", f"/Items/{item_id}/Images/Backdrop/{have}/Index", params={"newIndex": index})

    def create_playlist(self, uid, name, ids, public=False):
        # Jellyfin makes a playlist public (every user sees it) unless told otherwise
        first, rest = ids[:BATCH], ids[BATCH:]
        pid = self.call("POST", "/Playlists", json_body={
            "Name": name, "Ids": first, "UserId": uid, "MediaType": "Video", "IsPublic": public})["Id"]
        for b in batches(rest):
            self.call("POST", f"/Playlists/{pid}/Items", params={"ids": ",".join(b), "userId": uid})
        return pid

    def playlist_entries(self, uid, pid):
        items = self.call("GET", f"/Playlists/{pid}/Items", params={"userId": uid})["Items"]
        return [(it["Id"], it.get("PlaylistItemId")) for it in items]

    def add_to_playlist(self, uid, pid, ids):
        for b in batches(ids):
            self.call("POST", f"/Playlists/{pid}/Items", params={"ids": ",".join(b), "userId": uid})

    def remove_from_playlist(self, pid, entry_ids):
        for b in batches(entry_ids):
            self.call("DELETE", f"/Playlists/{pid}/Items", params={"entryIds": ",".join(b)})

    def share_playlist(self, token, pid, user_ids):
        self.call("POST", f"/Playlists/{pid}", token=token, json_body={"IsPublic": True})

    def unshare_playlist(self, token, pid):
        self.call("POST", f"/Playlists/{pid}", token=token, json_body={"IsPublic": False})

    def playlist_public(self, token, pid):
        return bool(self.call("GET", f"/Playlists/{pid}", token=token).get("OpenAccess"))

    def settle_new_playlist(self, pid, wait=20, step=1):
        # Jellyfin makes a collage poster a few seconds after a playlist is made, over any
        # poster sent before then
        for _ in range(int(wait / step)):
            if any(i.get("ImageType") == "Primary" for i in self.call("GET", f"/Items/{pid}/Images") or []):
                return
            time.sleep(step)


SERVERS = {"emby": Emby, "jellyfin": Jellyfin}


def connect(env, sid="1"):
    """The server in env's SERVER_* settings; for one of several, pass a server's env and id
    from settings.servers()."""
    kind = (env.get("SERVER_TYPE") or "emby").strip().lower()
    if kind not in SERVERS:
        raise ConfigError(f"{'SERVER_TYPE' if str(sid) == '1' else f'SERVER_{sid}_TYPE'} must be one of: {', '.join(SERVERS)}")
    return SERVERS[kind](env.get("SERVER_URL"), env.get("SERVER_API_KEY"), env.get("SERVER_NAME", ""), sid)


class Library:
    """Movies and shows on the server, findable by IMDb/TMDB/TVDB id or by title and year."""

    def __init__(self, items):
        self.by_id, self.ids, self.titles = {}, {}, {}
        for it in items:
            kind = "show" if it.get("Type") == "Series" else "movie"
            self.by_id[it["Id"]] = it
            for provider, value in (it.get("ProviderIds") or {}).items():
                if value:
                    self.ids.setdefault((kind, provider.lower(), str(value).lower()), it["Id"])
            self.titles.setdefault((kind, norm(it.get("Name", ""))), []).append(it)

    def find(self, item):
        kinds = ("movie", "show") if item.kind == "any" else (item.kind,)   # watchlist IDs can be either
        for provider in ("imdb", "tmdb", "tvdb"):
            value = item.ids.get(provider)
            for kind in kinds:
                hit = value and self.ids.get((kind, provider, value))
                if hit:
                    return hit
        # no id matched: fall back to the title (watchlist entries have IDs only, so this finds nothing)
        cands = self.titles.get((item.kind, norm(item.title)), [])
        if not item.year:
            return cands[0]["Id"] if len(cands) == 1 else None
        # exact year first, then +/-1 (release vs. festival dates differ)
        best = [c for c in cands if c.get("ProductionYear") == item.year] or \
               [c for c in cands if abs((c.get("ProductionYear") or 0) - item.year) <= 1]
        return best[0]["Id"] if best else None

    def match(self, items):
        """(found server ids in list order without repeats, missing items)."""
        found, missing, seen = [], [], set()
        for it in items:
            hit = self.find(it)
            if hit is None:
                missing.append(it)
            elif hit not in seen:
                seen.add(hit)
                found.append(hit)
        return found, missing
