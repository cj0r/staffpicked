# Using the web UI

[← Previous: Getting started](getting-started.md) · [User guide](README.md) · [Next: Collections and playlists →](collections-and-playlists.md)

The web UI at `http://<host>:9343` runs syncs, dry runs and config checks, streams their output live, edits the settings and config files, and runs the scheduled syncs. It works on a phone too.

![The dashboard: lists on the shelf, what's in season, the next sync and recent runs](screenshots/dashboard.webp)

## First run

Until a media server is set up, a setup screen opens over the dashboard: server type, URL and API key (Next tests them), optional MDBList and Trakt keys, then a password, or "Skip it, I only use it at home" (without a password the UI only opens from the local network). Finishing saves them and starts the first sync. **Later** closes it; the server badge in the header then reads **Set up a server** and opens it again. Nothing syncs, on start or on schedule, until some server has a real URL and key.

## Admin Mode and Screen Effects

**Admin Mode** (top of Settings) is disabled at first. Enable it to show Config Files, Artwork, Live Logs, the Dry run checkbox and every delete and remove button. Disabled hides them for a cleaner screen; it changes nothing on its own and is remembered per browser.

**Screen Effects** (Settings, under Admin Mode) is enabled at first. Disable it to drop the worn-tape effects (the tracking band that rolls down the screen, tape grain, scanlines, the tube vignette and the blinking PLAY); colors, signage and layout stay. Saved in `web.json`, so it holds for every browser, sign-in and restart.

## The dashboard

A tab per job (Collections, Playlists, Genres) with Sync (Stop while it runs) and a Dry run checkbox to preview a sync. Each can run just one collection or playlist. While a job runs, a VCR-style display shows which list it's on ("PLAY 03/17").

Each row says when the list last synced, how many of its films are in the library, and shows a warning when its last sync had a problem (hover it for the reason). A list whose last sync was held back by the removal limit says so at the top of its list window, with **Sync Anyway** to let that one list through. The two buttons by Import switch the shelf between rows and tape covers (each list's poster as a rental box), remembered per browser. The trash button on a row removes that one collection or playlist from the media server, after you review it.

The dashboard also shows which lists are in season today, the next scheduled run, and whether each server answers.

### Filters

Filters above the shelf narrow the lists: a search by name, a menu to show one list, and season chips (All, Active, Inactive, In season, Out of season, Year round), all used together. The shelf opens on Active. A click picks one chip; Ctrl+click (Cmd+click on a Mac, or a long press on a phone) adds or drops a chip to see lists matching any of those picked. Active means on the server now (in season or year round), Inactive means not. Chips that overlap don't stay on together: picking Active drops In season and Year round, In season plus Year round becomes Active, and picks that cover every list (Active and Inactive, say) go back to All.

### Mode

**Mode** (top right): playlists, collections or both. It sets `ENABLE_COLLECTIONS` / `ENABLE_PLAYLISTS` in `staffpicked.env`, so it decides what Run All and the schedule run. The buttons on each card always run that job.

## A list up close

Click a row or cover to see the films it gets, in order, under a summary of it: type, film count, season, its settings, its sources (MDBList and Trakt links, list files) and its poster and backdrops, with Edit and Remove buttons.

![A playlist's artwork, season and films, with which are in the library](screenshots/list-window.webp)

- Each film is marked as on the server or not, as of the last sync, and **Copy IDs** copies the IMDb IDs of the ones it doesn't have.
- Each film shows its MDBList score, which links to its MDBList page. Films from MDBList lists bring their score along; others are looked up 200 at a time and remembered for a week in `cache/mdblist-scores.json`.
- When a list can't be read for want of a key, a button goes straight to it in Settings.
- Once a request service is set up in Settings (Seerr, or Radarr and Sonarr), each title the library doesn't have is marked **Requested** (the service has it but it hasn't downloaded yet), **Available** (downloaded; the next sync sees it) or **Missing** (no service has it), with a count under the library line. A missing title has its own **Request** button that sends just that one; a whole list is never requested.
- The file icon saves what a list's MDBList or Trakt sources give today as a list file of your own (`collections/` or `playlists/`), and can switch the entry to it, so it stops following the list and changes only when you edit it.

## Building collections and playlists

**New** on the On the Shelves card, or the pencil on any row, opens a form for one collection or playlist: name, sources (MDBList or Trakt links, or your own list files), season, artwork, and the collection or playlist options. [Collections and playlists](collections-and-playlists.md) explains each option.

- Artwork can be uploaded from the device you're on (saved to `images/`), picked from the images already in the config folder, or given as a web link or a path on the server (in Docker, a path inside a folder mounted into the container).
- Saving writes just that entry to `collections.toml` or `playlists.toml`, keeping the rest of the file and its comments as they were, and lists anything `check` would warn about.
- A new collection or playlist can start its own list file, in `collections/` or `playlists/`, either empty or from a whole list pasted into the form (one `- tt0084787 | Title (Year)` line per film; its `# title` fills in the name). Picking one of your existing list files under Sources unticks the new list box.
- **Watched by** on a playlist is a tick list of the users on its servers (a user only some servers have says which).
- Renaming a collection or playlist removes the old one from the server on the next sync, instead of leaving a duplicate.
- **Duplicate** starts a new entry with the same settings and sources, named "Copy of …", for a seasonal variant; nothing is saved until you save it.

## Editing a list's films

The list icon on a collection or playlist opens its list file as a film list, in order. Find films by title (MDBList, or TMDB if there's no MDBList key) or paste an IMDb ID or link, drag or move them into order, edit the notes, and save. It's one flat list, like the playlist on the server: saving takes out any headings between the films. See [List files](list-files.md) for the file format.

![Editing a list file: search for films, drag to reorder](screenshots/list-editor.webp)

## Genre artwork

The Genres tab on the On the Shelves card. **New** there gives one of the server's genres your own poster, thumb (a wide 16:9 card) and backdrops, saved to `genres.toml`; the genre name field suggests the server's own genre names. The trash button, or Delete with its box ticked, takes the artwork StaffPicked set back off the genre; the genre itself is never deleted. Genres have their own job card and run in every mode unless Settings turns Genre artwork (`ENABLE_GENRES`) off. See [Genre artwork](genres.md).

## Import

On the On the Shelves card. Lists the collections, playlists and genres already on the media server and whether StaffPicked manages them, and brings in the ones you pick. It shows what it will do and waits for you to approve it, and it only writes the config folder. [Importing what's on your server](importing.md) has the details.

## Season calendar

Click **In Season Today** for the year at a glance: a bar for each collection and playlist across the dates it's on the server, a strip merging every seasonal window (its gaps are stretches with nothing seasonal on), and a marker for today. Year-round lists show as a faint full bar. The arrows step through the years (a one-time window only shows in its own year); click a list to see its films.

![The season calendar: when each collection and playlist is on the server across the year](screenshots/season-calendar.webp)

## Recent Runs

**Recent Runs** says how each run started (on startup, scheduled, manual, after setup, or for a new film) and what it did ("+3 films, 1 error"). Click one to read its own log, under a summary of what it changed on each list: the films added and removed, by title, and any artwork set. A dry run you start opens that summary when it's done ("What this dry run would change").

![What one sync changed: films added and artwork set, list by list, on each server](screenshots/sync-summary.webp)

## New films

Every `NEW_FILM_CHECK` (15 minutes unless changed in Settings > Options) the UI asks each server for its newest films. One that a collection or playlist was missing at its last sync makes that list sync straight away; the run shows in Recent Runs as "New film".

## Deleting

A collection or playlist (from its form, optionally also removing it from the server first) and image files (from **Artwork**, one at a time or in bulk). Every delete first shows exactly what will go and waits for you to approve it. Artwork in use by a collection or playlist can't be deleted; unused and archived files can.

## Settings

Settings edits `staffpicked.env` (see [Settings and the config folder](settings.md) for every setting):

- A card per media server with its admin user and playlist viewers, **Add Server**, **Test** and **Remove** (see [Several media servers](multiple-servers.md)).
- MDBList, Trakt, TMDB, fanart.tv and MediUX keys.
- The schedule (set times each day, or every N hours or minutes) and time zone (a list of zones to pick from; the dashboard shows the next run in it).
- The notification webhook with **Send Test**.
- Requests: Seerr, or Radarr for films and Sonarr for TV, each with a **Test** button, and Radarr's and Sonarr's quality profiles and root folders to pick from; only the chosen service's settings show.
- The removal limit and how often to check for new films.
- Reverse Proxy (trusted proxies and URL base), Web Access (an optional password) and Two-Factor Sign-In; see [Security](security.md).
- Backup: **Download Config** saves the whole config folder as a zip, showing a spinner and how much has come down while it works; **Restore from File**, in Admin Mode, puts one back after saving the current config to `backups/restores/`.
- Bulk Operations to remove every configured collection or playlist from the media server (after you review the list).

Keys are never sent back to the browser, and they are masked in the logs.

![Settings with an Emby server and a Jellyfin server side by side](screenshots/media-servers.webp)

## Config Files

Edit `collections.toml`, `playlists.toml`, `genres.toml` and your list `.md` files in the browser, create a list file from the template, and **Check Config** (saves your edits, then runs `check`). **Restore Previous** opens one of the file's last 10 versions in the editor; Save brings it back. Every save, from here or from the forms, keeps the old version in `backups/` first, and so does deleting a list file.

## Live Logs

Output of each job as it runs, plus the saved log to download.

<p align="center"><img src="screenshots/phone.webp" alt="StaffPicked on a phone" width="300"></p>
<p align="center"><b>On a phone.</b> The whole UI works on a small screen.</p>

---

[← Previous: Getting started](getting-started.md) · [User guide](README.md) · [Next: Collections and playlists →](collections-and-playlists.md)
