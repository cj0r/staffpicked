# StaffPicked web UI

A browser control panel for StaffPicked. It runs syncs, dry runs and
config checks, streams their output live, edits the settings and config
files, and runs the scheduled syncs. It is what the StaffPicked image runs by
default, on port 9343.

## What it does

Everything the UI does, screen by screen, is in the user guide: [Using the web UI](../docs/web-ui.md). This page covers how it runs and how it's built.

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
| `web/` | The UI's own files: password hash, sign-ins and the Screen Effects choice (`web.json`, hashed), run history and full job logs (`logs/runs/` keeps each recent run's own log and what it changed). |

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
| GET | `/api/status` | Version, mode, sync time, `time_zone`, next run, `setup` ({needed, skipped}: whether no media server is set up yet, and whether the setup screen was put off), `effects` (whether Screen Effects are enabled), `requests` ({service: seerr\|arr, movies, shows}: whether films and shows can be requested), the media servers [{id, name, type}], and per job: state, last run (with `server`, `servers`: each server's result, `summary`, and `progress`), items (with the `servers` each is limited to, `poster`, and `last`: what its last sync found, including `held`). |
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
| POST | `/api/effects` | {effects: true\|false}: enable or disable Screen Effects for everyone; open pages follow along. |
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
