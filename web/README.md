# StaffPicked web UI

A browser control panel for StaffPicked. It runs syncs, dry runs and
config checks, streams their output live, edits the settings and config
files, and runs the scheduled syncs. It is what the StaffPicked image runs by
default, on port 9343.

## What it does

- **Dashboard**: a tab per job (Collections, Playlists, Genres) with Sync (Stop
  while it runs) and a Dry run checkbox to preview a sync. Each can run just one
  collection or playlist. While a job runs, a VCR-style display shows which list
  it's on ("PLAY 03/17"). Each row says when the list last synced, how many of its
  films are in the library, and shows a
  warning when its last sync had a problem (hover it for the reason). A list whose
  last sync was held back by the removal limit says so at the top of its list
  window, with **Sync Anyway** to let that one list through. The two buttons by Import switch the shelf between
  rows and tape covers (each list's poster as a rental box), remembered per browser.
  Click a row or cover to see the films it gets,
  in order, under a summary of it: type, film count, season, its settings, its
  sources (MDBList and Trakt links, list files) and its poster and backdrops, with
  Edit and Remove buttons. Each film is marked as on the server or not, as of
  the last sync, and **Copy IDs** copies the IMDb IDs of the ones it doesn't have. Each
  film shows its MDBList score, which links to its MDBList page. Films from MDBList
  lists bring their score along; others are looked up 200 at a time and remembered
  for a week in `cache/mdblist-scores.json`. When a
  list can't be read for want of a key, a button goes straight to it in Settings.
  Once a request service is set up in Settings (Seerr, or Radarr and Sonarr), each
  title the library doesn't have is marked **Requested** (the service has it but it
  hasn't downloaded yet), **Available** (downloaded; the next sync sees it) or
  **Missing** (no service has it), with a count under the library line. A missing
  title has its own **Request** button that sends just that one; a whole list is
  never requested. The file icon saves what a list's MDBList or
  Trakt sources give today as a list file of your own (`collections/` or
  `playlists/`), and can switch the entry to it, so it stops following the
  list and changes only when you edit it. Filters above the shelf narrow
  the lists: a search by name, a menu to show one list, and season chips (All,
  Active, Inactive, In season, Out of season, Year round), all used together.
  The shelf opens on Active. A click picks one chip;
  Ctrl+click (Cmd+click on a Mac, or a long press on a phone) adds or drops a
  chip to see lists matching any of those picked. Active means on the server
  now (in season or year round), Inactive means not. Chips that overlap don't
  stay on together: picking Active drops In season and Year round, In season
  plus Year round becomes Active, and picks that cover every list (Active and
  Inactive, say) go back to All.
  The trash button on a row removes
  that one collection or playlist from the media server, after you review it. Also shows which lists are in season today, the next
  scheduled run, and whether each server answers. **Recent Runs** says how each
  run started (on startup, scheduled, manual, after setup, or for a new film) and what it did ("+3 films, 1
  error"); click one to read its own log, under a summary of what it changed on
  each list: the films added and removed, by title, and any artwork set. A dry
  run you start opens that summary when it's done ("What this dry run would
  change").
- **Build collections and playlists**: **New** on the On the Shelves card, or the
  pencil on any row, opens a form for one collection or playlist: name, sources
  (MDBList or Trakt links, or your own list files), season, artwork, and the
  collection or playlist options. Artwork can be uploaded from the device you're
  on (saved to `images/`), picked from the images already in the config folder,
  or given as a web link or a path on the server (in Docker, a path inside a
  folder mounted into the container). Saving writes just that entry to
  `collections.toml` or `playlists.toml`, keeping the rest of the file and its
  comments as they were, and lists anything `check` would warn about. A new
  collection or playlist can start its own list file, in `collections/` or
  `playlists/`, either empty or from a whole list pasted into the form (one
  `- tt0084787 | Title (Year)` line per film; its `# title` fills in the name).
  Picking one of your existing list files under Sources unticks the new list box.
  **Watched by** on a playlist is a tick list of the users on its servers (a user
  only some servers have says which). Renaming a collection or playlist removes
  the old one from the server on the next sync, instead of leaving a duplicate.
  **Duplicate** starts a new entry with the same settings and sources, named
  "Copy of …", for a seasonal variant; nothing is saved until you save it.
- **Genre artwork**: the Genres tab on the On the Shelves card. **New** there gives
  one of the server's genres your own poster, thumb (a wide 16:9 card) and
  backdrops, saved to `genres.toml`; the genre name field suggests the server's own
  genre names. The trash button, or Delete with its box ticked, takes the artwork
  StaffPicked set back off the genre; the genre itself is never deleted. Genres
  have their own job card and run in every mode unless Settings turns Genre
  artwork (`ENABLE_GENRES`) off. Import also lists genres that already have
  artwork on the server; importing one saves its images to `images/` and adds it
  to `genres.toml`.
- **List films**: the list icon on a collection or playlist opens its list file as
  a film list, in order. Find films by title (MDBList, or TMDB if there's no MDBList
  key) or paste an IMDb ID or link, drag or move them into order, edit the notes,
  and save. It's one flat list, like the playlist on the server: saving takes
  out any headings between the films.
- **Import**: on the On the Shelves card. Lists the collections and playlists
  already on the media server and whether StaffPicked manages them, and brings in
  the ones you pick: a new one is imported (its artwork goes to `images/` and an
  entry to the config; a collection follows the MDBList or Trakt list it was found
  to come from, or one whose link you paste when asked, and anything else, or a
  collection you Skip, gets a new list file of its films), one whose
  name is nearly the same as a StaffPicked entry is linked (the entry is renamed
  to match it), and a fixed copy from an earlier import can be switched to its list.
  It shows what it will do and waits for you to approve it, and it only writes
  the config folder.
- **Deleting**: a collection or playlist (from its form, optionally also
  removing it from the server first) and image files (from **Artwork**, one at a
  time or in bulk). Every delete first shows exactly what will go and waits for
  you to approve it. Artwork in use by a collection or playlist can't be deleted;
  unused and archived files can.
- **Mode** (top right): playlists, collections or both. It sets
  `ENABLE_COLLECTIONS` / `ENABLE_PLAYLISTS` in staffpicked.env, so it decides what
  Run All and the schedule run. The buttons on each card always run that job.
- **Season calendar**: click **In Season Today** for the year at a glance: a bar
  for each collection and playlist across the dates it's on the server, a strip
  merging every seasonal window (its gaps are stretches with nothing seasonal on),
  and a marker for today. Year-round lists show as a faint full bar. The arrows
  step through the years (a one-time window only shows in its own year); click a
  list to see its films.
- **First run**: until a media server is set up, a setup screen opens over the
  dashboard: server type, URL and API key (Next tests them), optional MDBList and
  Trakt keys, then a password, or "Skip it, I only use it at home" (without a password the
  UI only opens from the local network). Finishing
  saves them and starts the first sync. **Later** closes it; the server badge in
  the header then reads **Set up a server** and opens it again. Nothing syncs,
  on start or on schedule, until some server has a real URL and key.
- **New films**: every `NEW_FILM_CHECK` (15 minutes unless changed in Settings >
  Options) the UI asks each server for its newest films. One that a collection or
  playlist was missing at its last sync makes that list sync straight away; the
  run shows in Recent Runs as "New film".
- **Admin Mode** (top of Settings): disabled at first. Enable it to show Config Files,
  Artwork, Live Logs, the Dry run checkbox and every delete and remove button.
  Disabled hides them for a cleaner screen; it changes nothing on its own and is
  remembered per browser.
- **Settings**: staffpicked.env (a card per media server with its admin user and
  playlist viewers, Add Server, Test and Remove; MDBList, Trakt, TMDB and fanart.tv keys, the schedule (set times each day, or every N hours or minutes)
  and time zone (a list of zones to pick from; the dashboard shows the next run in it), the
  notification webhook with **Send Test**, and Requests: Seerr, or Radarr for films and Sonarr for TV, each with a **Test** button, and Radarr's and Sonarr's quality profiles and root folders to pick from; only the chosen service's settings show),
  the removal limit and how often to check for new films,
  Reverse Proxy (trusted proxies and URL base), an optional password for the UI (sign-ins last 30 days and survive restarts; only a hash of each is kept; without a password the UI only opens from the local network), Two-Factor Sign-In (authenticator app with a QR code, and recovery codes), Backup
  (**Download Config** saves the whole config folder as a zip, showing a spinner and how much has come down while it works; **Restore from File**, in Admin Mode, puts one back after saving the current config to `backups/restores/`), and Bulk Operations to remove every
  configured collection or playlist from the media server (after you review the list). Keys are never sent back to the browser,
  and they are masked in the logs.
- **Config Files**: edit `collections.toml`, `playlists.toml`, `genres.toml` and your list
  `.md` files in the browser, create a list file from the template,
  and Check Config (saves your edits, then runs `python -m scripts check`).
  **Restore Previous** opens one of the file's last 10 versions in the editor;
  Save brings it back. Every save, from here or from the forms, keeps the old
  version in `backups/` first, and so does deleting a list file.
- **Live Logs**: output of each job as it runs, plus the saved log to download.

## Run it

The repo's `Dockerfile` builds one image with StaffPicked and this UI:

```bash
docker compose up -d        # from the repo root; then open http://<host>:9343
```

Mount any folder at `/config`. If it's empty, the UI fills it with the
examples from `config/` on first start, and the setup screen asks for the rest.
The UI also runs the scheduled syncs, the same way `python -m scripts schedule`
does: at each `SYNC_TIME`, or every `SYNC_EVERY` when that's set (in the
Settings time zone, else the container's `TZ`), and once at start unless
`SYNC_ON_START=false` (none of them before a server is set up). Scheduled runs show up in the UI's logs and history.

Without Docker (Python 3.11+, no packages needed), from the repo root:

```bash
python3 web/server.py      # uses $STAFFPICKED_CONFIG, else /config, else ./config
```

## /config

| Path | What |
| :--- | :--- |
| `staffpicked.env` | Shared settings and API keys (KEY=value), including the schedule. |
| `collections.toml`, `playlists.toml` | What to build. |
| `genres.toml` | Artwork for the server's genres. |
| `collections/*.md`, `playlists/*.md` | Your own lists that collections and playlists use as sources. |
| `list-template.md` | The list format, and a prompt for an AI agent to write one. |
| `images/` | Posters, thumbs and backdrops the configs point at, plus saved copies of downloaded ones (replaced copies go to `images/archive/`). |
| `cache/` | StaffPicked's state: uploaded images (`state.json`), renames waiting for a sync (`renames.json`), what each list's last sync found (`results-collection.json` and so on), and the MDBList scores the list window shows (`mdblist-scores.json`, each looked up at most once a week). |
| `backups/` | The last 10 versions of each config and list file, from before each save. |
| `web/` | The UI's own files: password hash and sign-ins (`web.json`, hashed), run history and full job logs (`logs/runs/` keeps each recent run's own log and what it changed). |

## Stack

Plain HTML, CSS and JavaScript with Lucide icons and no build step. The base
`style.css` comes from [lftp-sync-manager](https://github.com/cj0r/lftp-sync-manager), restyled by `theme.css` as an
80s video store after dark: neon magenta and cyan, a synthwave grid floor,
chrome-and-script signage, VHS on-screen-display type and checkerboard tile.
Fonts (Outfit, JetBrains Mono, Bungee, Mr Dafoe, VT323; all SIL OFL) are
self-hosted in `public/vendor/fonts`, so the page makes no outside requests. The
two-factor QR code is drawn by `public/vendor/qrcode.js` (qrcode-generator by Kazuhiko
Arase, MIT) in the browser, so no outside service ever sees the key.
The server is Python standard library, like StaffPicked itself: one runtime in
the image, and the UI runs `python -m scripts` directly. Live output uses
Server-Sent Events.

| File | What |
| :--- | :--- |
| `server.py` | HTTP server, JSON API, job runner, scheduler, login. |
| `security.py` | Password hashing, authenticator codes (TOTP) and recovery codes, and who a request comes from behind a trusted reverse proxy. |
| `builder.py` | The builder: editing one config entry or a list file's films, title search, and image files. |
| `backend.py` | Everything about StaffPicked: env keys, mode switches, commands, config files. |
| `notify.py` | The webhook message after the startup and scheduled syncs. |
| `public/` | The page. `style.css` is the base, `app.css` adds this app's parts, `theme.css` is the 80s look, `builder.js` is the builder. |

## API

The page talks to the server only through this JSON API and one event
stream, so another server that serves `public/` can replace `server.py`
without touching the page.
POST/PUT bodies are JSON and must be sent as `application/json`.

| Method | Path | What |
| :--- | :--- | :--- |
| GET | `/api/status` | Version, mode, sync time, `time_zone`, next run, `setup` ({needed, skipped}: whether no media server is set up yet, and whether the setup screen was put off), `requests` ({service: seerr\|arr, movies, shows}: whether films and shows can be requested), the media servers [{id, name, type}], and per job: state, last run (with `server`, `servers`: each server's result, `summary`, and `progress`), items (with the `servers` each is limited to, `poster`, and `last`: what its last sync found, including `held`). |
| GET | `/api/events` | Server-Sent Events: `log` {job, line}, `status` (a job), `settings`, `files`, `progress` {task, ...} (for a sync: {job, done, total, current}). |
| GET | `/api/health` | {ok, version, scheduler_seconds_ago}; 503 when the scheduler has stopped. No sign-in needed; Docker's HEALTHCHECK calls it. |
| POST | `/api/jobs/{job}/run` | {action: sync, check or remove, dry_run, only, server, allow_removals}. `server` (a name) runs on that server only; blank = every server. `allow_removals` lets a sync past the removal limit (Sync Anyway). |
| POST | `/api/jobs/{job}/abort` | Stop a running job. |
| POST | `/api/jobs/all/run` | {dry_run}: run each job the mode allows (and genres unless `ENABLE_GENRES=false`), one after another. |
| GET, DELETE | `/api/logs/{job}` | Recent lines (`?download=1` for the full log), or delete the log. |
| GET | `/api/history` | The last 50 runs, each with its `id`, `summary` ({added, removed, errors, dry_run}), `changed` (lists it changed) and whether its log is kept (`has_log`). |
| GET | `/api/runs/{id}/log` | One run's own log: {run, lines, changes: [{kind, name, server, person, added: [titles], removed: [titles], changes: [text], dry_run}]}. |
| POST | `/api/notify/test` | {url?}: send a test message to that URL, or the saved `NOTIFY_URL`. |
| POST | `/api/requests/test` | {service: seerr\|radarr\|sonarr, env?: {SEERR_...}}: check that service with these settings over the saved ones. Seerr: {version, user}. Radarr and Sonarr: {version, profiles, folders, profile, folder, problem}; Settings uses the profiles and folders as its choices. |
| POST | `/api/requests/status` | {items: [{imdb, show}]}: {states: {imdb: requested\|available\|missing}, errors: {service: message}} from the chosen service. Answers are kept for two minutes. |
| POST | `/api/requests/add` | {imdb: ID, show}: request that one title: {result: added\|already\|failed, name, state, error, service}. |
| POST | `/api/setup/test` | {server: {type, url, key}}: try a server: {ok, server, version, error}. |
| POST | `/api/setup` | {server: {type, url, key}, keys?: {MDBLIST_API_KEY, TRAKT_CLIENT_ID}, password?}: the setup screen's Finish. Tests the server, saves it as server 1, sets the password if one is given and none is set (and signs this browser in), then starts the first sync. |
| POST | `/api/setup/skip` | Don't open the setup screen again on its own. |
| GET | `/api/config/download` | The config folder as a zip, without `cache/`, `backups/`, the logs and sign-ins. |
| POST | `/api/config/restore` | A zip from Download Config, sent as `application/zip`: its files replace the ones in the config folder (others stay), after the current config is saved to `backups/restores/`. {ok, files, saved}. Refused while a sync runs. |
| GET | `/api/backups?job=&name=` | A config file's saved versions, newest first: {versions: [{id, at, size}]}; with `&id=`, that version's {text}. |
| GET, PUT | `/api/settings` | Env fields and `servers` (each server's values; secrets only say whether they are set); PUT {env, mode, servers: [{id (none for a new one), values}], removed_servers: [id]}. |
| GET, POST | `/api/emby` | Every media server's status: {ok, servers: [{id, name, type, ok, server, version, error}]} (POST re-checks now). |
| GET | `/api/files/{job}` | Editable files for a job. |
| GET, PUT, DELETE | `/api/files/{job}/{name}` | Read, save ({text, create}), or delete a file. `_template` reads the list template. |
| GET | `/api/builder/{job}` | The job's entries as form values, its `[settings]`, its list files, and the file's `version`. |
| POST | `/api/builder/{job}` | {entry, version, new_watchlist?: {title, description, text?}}: add an entry, and optionally a new list file for it (`text` = a whole pasted list, which needs at least one IMDb ID). |
| PUT | `/api/builder/{job}/{index}` | {entry, version}: replace an entry. A new name is recorded in `cache/renames.json` (returned as `renamed`) so the next sync removes the old one. Answers 422 with `problems` and `warnings`, or 409 if the file changed. |
| GET | `/api/builder/{job}/{index}/items` | The films an entry gets from its sources, in sync order: {name, window, sources, details: [[label, value]], feeds: [{spec, kind, url, file, count}], items: [{title, year, notes, imdb, source, duplicate}], artwork: [{what, spec, image, url, remote}], problems, needs (keys a source is missing), library: [{server, at, listed, in_library, missing, missing_count, errors, error}]}; each item also has `in_library` (true, false, or null before a sync), `score` (its MDBList score, or null) and `show` (true for a TV show). Reads MDBList and Trakt live. |
| POST | `/api/builder/{job}/{index}/export` | {use_it}: save the films its sources give now to a new list file: {name, films, skipped, used}. With `use_it`, the entry then uses only that file. |
| DELETE | `/api/builder/{job}/{index}?version=` | Delete an entry. With `&server=1`, removes it from the server first and deletes the entry once that succeeds. |
| GET, PUT | `/api/watchlist?name=playlists/x.md` | A list file as rows (films and the other lines); PUT {rows, version} saves them. |
| GET | `/api/import?server=` | One server's (the first, unless `server` names one) collections, playlists and genres with artwork (`genre` rows carry `art`, what images they have), each `managed`, `similar`, `new` or `duplicate`, with the StaffPicked entry it matches, its `action`, and the list (`source`) a collection was found to come from. |
| POST | `/api/import` | {server, picks: [{kind, id, action: import, link or source, url?}]}, where `url` is a list link given for a collection whose list wasn't found: bring those in. Returns one result line per pick. |
| GET | `/api/users` | Every media server's enabled users, for a playlist's Watched by: {servers: [{name, users}], problems}. |
| GET | `/api/genres` | The movie and show genre names on every media server, for picking a genre's exact name: {genres, server, problems}. |
| GET | `/api/search?q=&type=movie` | Films or shows by title, with IMDb IDs (`type=show` for shows). |
| GET | `/api/images` | Image files in `images/`, `collections/` and `playlists/`, each with what uses it. `/api/images/file?name=` serves one. |
| POST | `/api/images/upload?name=` | The raw image as the body, sent as `image/jpeg`, `image/png` or `image/webp`; saved to `images/` under a safe, unused name, which it returns. |
| POST | `/api/images/delete` | {names}: delete those files. Refuses if any is in use. |
| GET | `/api/auth` | Whether a password is set and this browser is signed in. |
| POST | `/api/login`, `/api/logout` | {password, code?}; sets or clears an HttpOnly, SameSite=Strict session cookie (Secure over HTTPS). With two-factor sign-in on and no code, a right password answers 401 {mfa: true}; code is an authenticator code or a recovery code. Five failures per address in five minutes answer 429. |
| PUT | `/api/password` | {current, new, code?}; an empty `new` removes the password (and two-factor sign-in). With two-factor on, code is required. |
| GET | `/api/mfa` | {enabled, recovery_left, password}. |
| POST | `/api/mfa/setup` | {current}: a new authenticator key {secret, uri}, kept aside for 15 minutes until confirmed. |
| POST | `/api/mfa/enable` | {code} from the app: turns it on, signs out other browsers, answers {recovery_codes} (shown once). |
| POST | `/api/mfa/recovery`, `/api/mfa/disable` | {current, code}: new recovery codes, or turn it off. |
