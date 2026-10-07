# Settings and the config folder

[← Previous: Several media servers](multiple-servers.md) · [User guide](README.md) · [Next: Command line →](command-line.md)

## The config folder

Everything you edit lives in one folder, mounted at `/config` in the container:

```
staffpicked.env       shared settings: servers, what to build, API keys, users, schedule
collections.toml      one [[collection]] per collection (created from collections.toml.example)
playlists.toml        one [[playlist]] per playlist (created from playlists.toml.example)
genres.toml           one [[genre]] per genre you give your own artwork (created from genres.toml.example)
collections/          your own lists (*.md) for collections, and their artwork
playlists/            your own ordered lists (*.md) for playlists, and their artwork
list-template.md      the list format, with a prompt for an AI agent to write one
images/               your poster, thumb and backdrop files, plus copies of downloaded ones
  archive/            replaced copies, kept rather than deleted
cache/                remembers uploaded images, renames waiting for a sync, what each list's
                      last sync found, and MDBList scores (created by the app)
backups/              the last 10 versions of each config and list file, from before each save
  restores/           the whole config as it was before each Restore from File (a zip)
web/                  the web UI's password hash, run history and logs (created by the app)
```

Your own `staffpicked.env`, `collections.toml`, `playlists.toml`, `genres.toml` and list files are git-ignored, so pulling updates never conflicts with them; the repository only carries the `.example` copies, the two `example-list.md` files and the template. All four are created from the examples on first start; `staffpicked.env` holds API keys and user names. The TOML configs hold no secrets. Paths inside them are relative to the config folder.

Each of the four opens with a commented-out key listing every setting it takes, the values each one accepts and an example, so you can check a setting without leaving the file. The settings in `collections.toml` and `playlists.toml` are explained in [Collections and playlists](collections-and-playlists.md), and `genres.toml` in [Genre artwork](genres.md).

## Backups

**Settings > Backup > Download Config** saves all of it (everything above except `cache/`, `backups/` and the logs) as one zip, and **Restore from File** (Admin Mode) puts one back: its files replace the ones there, others are left alone, and the config as it was is saved in `backups/restores/` first. The zip holds every API key, password hash and the two-factor key, so keep it private.

Every save in the web UI also keeps the file's previous version in `backups/`; **Restore Previous** in Config Files brings one back.

## staffpicked.env

The web UI's Settings page edits these; you can also edit the file by hand.

| Setting | What it is |
|---|---|
| `ENABLE_COLLECTIONS`, `ENABLE_PLAYLISTS` | `true` or `false`: what to build. If neither is set, both are built. |
| `ENABLE_GENRES` | `true` (default) or `false`: set the artwork in `genres.toml`. It has nothing to do until you add a genre. |
| `SERVER_TYPE` | `emby` (default) or `jellyfin` |
| `SERVER_URL`, `SERVER_API_KEY` | server address and an API key. Inside the container `localhost` is the container itself, so use the server's LAN address (e.g. `http://192.168.1.10:8096`), or its container name if both share a Docker network. |
| `SERVER_USER`, `SERVER_PASSWORD` | an admin user (name or ID) that owns the shared playlists, and its password, used only to share playlists (and on Jellyfin, to reorder them). Blank user = the first admin. |
| `WATCHED_BY` | users whose viewing drops a film from shared playlists; blank = only `SERVER_USER` |
| `PLAYLIST_USERS`, `LINKED_USERS` | optional per-person playlists (see [Per-person playlists](collections-and-playlists.md#per-person-playlists)) |
| `MDBLIST_API_KEY` | MDBList lists, including your own private ones |
| `TRAKT_CLIENT_ID`, `TRAKT_ACCESS_TOKEN` | Trakt lists. The client ID is enough for public lists; private lists and watchlists also need an access token for the owner's account. |
| `TMDB_API_TOKEN` | TMDB images (the v4 "API Read Access Token") |
| `FANARTTV_API_KEY` | fanart.tv images |
| `MEDIUX_API_TOKEN` | MediUX images looked up by movie, collection or set: your own token from your MediUX account |
| `SYNC_TIME`, `SYNC_EVERY`, `SYNC_ON_START` | sync times every day (`HH:MM`, 24-hour, in `TIME_ZONE`; several separated by commas, like `06:00, 18:00`; default `06:00`); or an interval instead (`6h`, `90m`, `1h30m`; at least 15 minutes, counted from the last scheduled sync; blank = use `SYNC_TIME`); and whether to also sync when the container starts (default `true`). A sync still running holds the next one until it ends. |
| `TIME_ZONE` | your time zone, e.g. `America/Chicago`, for the sync time and for which day it is for season windows. Blank = the container's `TZ`. |
| `NOTIFY_URL`, `NOTIFY_ON` | where to hear how the startup and scheduled syncs went: a Discord or Slack webhook, Gotify (`https://gotify.example/message?token=...`), an ntfy topic (`https://ntfy.sh/your-topic`) or any URL that takes a JSON post; and `failures` (default) or `always`. Runs you start yourself don't notify. |
| `REQUEST_SERVICE` | where a missing title is requested from a list window, one at a time: `seerr` (default) sends films and TV shows to Seerr; `arr` sends films to Radarr and shows to Sonarr |
| `SEERR_URL`, `SEERR_API_KEY` | Seerr (Overseerr and Jellyseerr work too). Requests go in as the admin, so they're approved straight away. |
| `RADARR_URL`, `RADARR_API_KEY` | Radarr, for films when `REQUEST_SERVICE=arr` |
| `RADARR_QUALITY_PROFILE`, `RADARR_ROOT_FOLDER`, `RADARR_SEARCH` | the quality profile (by name) and root folder new films get, picked in Settings from what Radarr has (blank = Radarr's first), and whether Radarr starts searching as each is added (default `true`) |
| `SONARR_URL`, `SONARR_API_KEY` | Sonarr, for TV shows when `REQUEST_SERVICE=arr` |
| `SONARR_QUALITY_PROFILE`, `SONARR_ROOT_FOLDER`, `SONARR_SEARCH` | the same for new shows in Sonarr (default `true`) |
| `REMOVAL_LIMIT` | the share of a list, in percent, one sync may take off the server (default `50`; `0` = no limit). A sync that would take more, and at least 3 films, changes nothing for that list and reports it as an error (so it notifies); its list window then offers **Sync Anyway**. Films leaving a playlist because they were watched don't count. |
| `NEW_FILM_CHECK` | how often the web UI looks for films just added to the server: `5m`, `15m` (default), `30m`, `1h` or `off`. A collection or playlist that was missing one syncs straight away, just that list. Nothing needs setting up on Emby or Jellyfin. |
| `DRY_RUN` | `1` previews without changing anything |
| `TRUSTED_PROXIES` | the IP addresses or ranges of your reverse proxy (e.g. `172.18.0.0/16`), comma-separated. Only requests from these may say which browser they're for and that it used https. Blank = trust no proxy. See [Reverse proxy](security.md#reverse-proxy). |
| `URL_BASE` | the path when a proxy serves StaffPicked under one, like `/staffpicked` for `https://example.com/staffpicked/`. Blank = at the root. |

Keys are only needed for the sources and images your configs use; `check` says which ones are missing. Further media servers take the same `SERVER_*` settings with a number; see [Several media servers](multiple-servers.md).

---

[← Previous: Several media servers](multiple-servers.md) · [User guide](README.md) · [Next: Command line →](command-line.md)
