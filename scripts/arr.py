"""Requesting a film from Radarr or a show from Sonarr (both v3 API), one at a time.

Settings in staffpicked.env (REQUEST_SERVICE=arr picks these over Seerr):
  RADARR_URL / SONARR_URL                         as you open it in a browser, e.g. http://192.168.1.10:7878
  RADARR_API_KEY / SONARR_API_KEY                 Settings > General > API Key
  RADARR_QUALITY_PROFILE / SONARR_QUALITY_PROFILE a quality profile's name (blank = the first one)
  RADARR_ROOT_FOLDER / SONARR_ROOT_FOLDER         where they go, e.g. /movies (blank = the first root folder)
  RADARR_SEARCH / SONARR_SEARCH                   true (default) to start searching as each is added

Neither cares which media server you use, so this works the same for Emby and Jellyfin."""
from urllib.error import HTTPError
from .util import ServiceError, describe, http_error, request, truthy

# What a title's state is called everywhere: in the service but not downloaded yet, or downloaded.
REQUESTED, AVAILABLE, MISSING = "requested", "available", "missing"


def tvdb_for(env, imdb):
    """A show's TheTVDB ID from its IMDb ID through TMDB, for a Sonarr that can't look IMDb IDs up.
    None without a TMDB token or a match."""
    token = (env.get("TMDB_API_TOKEN") or "").strip()
    if not token:
        return None
    headers = {"Authorization": f"Bearer {token}"}
    try:
        found = request("GET", f"https://api.themoviedb.org/3/find/{imdb}", {"external_source": "imdb_id"},
                        headers=headers, timeout=30)
        shows = (found or {}).get("tv_results") or []
        if not shows:
            return None
        ext = request("GET", f"https://api.themoviedb.org/3/tv/{shows[0]['id']}/external_ids", headers=headers, timeout=30)
        return (ext or {}).get("tvdb_id")
    except Exception:
        return None


class Arr:
    NAME, PREFIX, WHAT = "", "", ""

    def __init__(self, env):
        p = self.PREFIX
        self.env = env
        self.url = (env.get(f"{p}_URL") or "").strip().rstrip("/")
        self.key = (env.get(f"{p}_API_KEY") or "").strip()
        self.profile = (env.get(f"{p}_QUALITY_PROFILE") or "").strip()
        self.folder = (env.get(f"{p}_ROOT_FOLDER") or "").strip()
        self.search = truthy(env.get(f"{p}_SEARCH") or "true")
        if not self.url or not self.key:
            raise ServiceError(f"Set the {self.NAME} URL and API key in Settings")

    def call(self, method, path, **kw):
        try:
            return request(method, f"{self.url}/api/v3{path}", headers={"X-Api-Key": self.key}, timeout=30, **kw)
        except HTTPError as e:
            if e.code == 401:
                raise ServiceError(f"{self.NAME} turned down the API key") from e
            raise

    def status(self):
        """{version, profiles: [names], folders: [paths], profile, folder, problem} for Settings, which
        offers the profiles and folders as choices. A saved choice the service doesn't have is the problem."""
        info = self.call("GET", "/system/status")
        out = {"version": info.get("version", ""), "profiles": [p["name"] for p in self.profiles()],
               "folders": [f["path"] for f in self.folders()], "profile": "", "folder": "", "problem": ""}
        try:
            profile, out["folder"] = self.target()
            out["profile"] = profile["name"]
        except ServiceError as e:
            out["problem"] = str(e)
        return out

    def profiles(self):
        return self.call("GET", "/qualityprofile") or []

    def folders(self):
        return self.call("GET", "/rootfolder") or []

    def target(self):
        """(quality profile, root folder path) new titles go to."""
        profiles, folders = self.profiles(), self.folders()
        if not profiles:
            raise ServiceError(f"{self.NAME} has no quality profiles")
        if not folders:
            raise ServiceError(f"{self.NAME} has no root folders; add one under Settings > Media Management")
        profile = profiles[0]
        if self.profile:
            profile = next((p for p in profiles if p["name"].lower() == self.profile.lower()
                            or str(p.get("id")) == self.profile), None)
            if not profile:
                raise ServiceError(f"{self.NAME} has no quality profile called {self.profile!r}; it has "
                                   + ", ".join(p["name"] for p in profiles))
        folder = folders[0]["path"]
        if self.folder:
            match = next((f["path"] for f in folders if f["path"].rstrip("/") == self.folder.rstrip("/")), None)
            if not match:
                raise ServiceError(f"{self.NAME} has no root folder {self.folder!r}; it has "
                                   + ", ".join(f["path"] for f in folders))
            folder = match
        return profile, folder

    def states(self, imdb_ids):
        """{imdb: requested | available | missing} for each ID, from one look at everything it has."""
        have = {}
        for it in self.call("GET", self.LIBRARY) or []:
            if it.get("imdbId"):
                have[it["imdbId"]] = AVAILABLE if self.downloaded(it) else REQUESTED
        return {i: have.get(i, MISSING) for i in imdb_ids}

    def add(self, imdb):
        """Add one title it doesn't have yet: {result: added | already | failed, name, error}."""
        try:
            found = self.lookup(imdb)
            if not found:
                return {"result": "failed", "name": imdb, "error": f"{self.NAME} couldn't find it"}
            name = f"{found.get('title', imdb)} ({found.get('year')})" if found.get("year") else found.get("title", imdb)
            if found.get("id"):
                return {"result": "already", "name": name, "state": AVAILABLE if self.downloaded(found) else REQUESTED}
            self.call("POST", self.LIBRARY, json_body=self.body(found))
            return {"result": "added", "name": name, "state": REQUESTED}
        except ServiceError:
            raise
        except HTTPError as e:
            if e.code == 404:
                return {"result": "failed", "name": imdb, "error": f"{self.NAME} couldn't find it"}
            text = http_error(e)
        except Exception as e:
            text = describe(e)
        if "ExistsValidator" in text or "already been added" in text.lower():
            return {"result": "already", "name": imdb, "state": REQUESTED}
        return {"result": "failed", "name": imdb, "error": text}


class Radarr(Arr):
    NAME, PREFIX, WHAT, LIBRARY = "Radarr", "RADARR", "film", "/movie"

    def downloaded(self, movie):
        return bool(movie.get("hasFile"))

    def lookup(self, imdb):
        found = self.call("GET", "/movie/lookup/imdb", params={"imdbId": imdb})
        movie = found[0] if isinstance(found, list) and found else found
        return movie if movie and movie.get("tmdbId") else None

    def body(self, movie):
        profile, folder = self.target()
        body = {k: movie[k] for k in ("title", "tmdbId", "year", "titleSlug", "images", "imdbId") if k in movie}
        body.update(qualityProfileId=profile["id"], rootFolderPath=folder, monitored=True,
                    minimumAvailability="released", addOptions={"searchForMovie": self.search})
        return body


class Sonarr(Arr):
    NAME, PREFIX, WHAT, LIBRARY = "Sonarr", "SONARR", "show", "/series"

    def downloaded(self, series):
        return (series.get("statistics") or {}).get("percentOfEpisodes", 0) >= 100

    def lookup(self, imdb):
        """Sonarr v4 looks shows up by IMDb ID; older ones only by TheTVDB ID, which TMDB can supply."""
        terms = [f"imdb:{imdb}"]
        tvdb = None
        for n, term in enumerate(terms):
            try:
                found = self.call("GET", "/series/lookup", params={"term": term}) or []
            except HTTPError as e:
                if e.code not in (400, 404):
                    raise
                found = []
            hit = next((s for s in found if s.get("tvdbId") and (n or s.get("imdbId") in (None, "", imdb))), None)
            if hit:
                return hit
            if not n and (tvdb := tvdb_for(self.env, imdb)):
                terms.append(f"tvdb:{tvdb}")
        return None

    def body(self, series):
        profile, folder = self.target()
        body = {k: series[k] for k in ("title", "tvdbId", "year", "titleSlug", "images", "seasons", "imdbId", "tvMazeId")
                if k in series}
        body.update(qualityProfileId=profile["id"], rootFolderPath=folder, monitored=True, seasonFolder=True,
                    seriesType=series.get("seriesType") or "standard",
                    addOptions={"monitor": "all", "searchForMissingEpisodes": self.search,
                                "searchForCutoffUnmetEpisodes": False})
        try:   # Sonarr v3 wants a language profile too; v4 ignores it
            langs = self.call("GET", "/languageprofile") or []
            if langs:
                body["languageProfileId"] = langs[0]["id"]
        except HTTPError:
            pass
        return body
