# StaffPicked user guide

StaffPicked builds collections and playlists on Emby and Jellyfin from MDBList lists, Trakt lists and your own Markdown lists, and keeps them in sync on a schedule. This guide covers everything from installing it to the last setting. New here? Start with [Getting started](getting-started.md), then read the pages as you need them.

## Contents

1. [Getting started](getting-started.md): install with Docker, compose managers, updating, Unraid, building from source, permissions.
2. [Using the web UI](web-ui.md): the dashboard, list windows, the forms, Import, the season calendar, Settings and logs.
3. [Collections and playlists](collections-and-playlists.md): which to use, every setting in `collections.toml` and `playlists.toml`, seasons, sharing, per-person playlists, renaming and the safety brake.
4. [List files](list-files.md): writing your own lists, one IMDb ID per line.
5. [Sources and artwork](sources-and-artwork.md): MDBList and Trakt lists, and posters and backdrops from TMDB, fanart.tv, MediUX or your own files.
6. [Genre artwork](genres.md): your own artwork on the server's genres.
7. [Importing what's on your server](importing.md): taking over collections, playlists and genre artwork you already have.
8. [Several media servers](multiple-servers.md): Emby and Jellyfin side by side, and keeping a list to some servers.
9. [Settings and the config folder](settings.md): every file in the config folder, backups, and every setting in `staffpicked.env`.
10. [Command line](command-line.md): every command and option.
11. [Security](security.md): sign-in, two-factor sign-in, reverse proxies.
12. [Troubleshooting](troubleshooting.md): fixes for the problems people run into most.

## What StaffPicked does

- Collections and playlists from MDBList (public and private lists), Trakt (lists and watchlists) and your own Markdown list files.
- Posters and backdrops from TMDB, fanart.tv, MediUX, any URL or a local file. Posters you download yourself, from ThePosterDB for example, can be uploaded in the web UI.
- Your own poster, thumb and backdrops on the server's genres (Horror, Comedy, ...).
- Seasonal date windows: a collection or playlist exists on the server only while it's in season. A season calendar shows the whole year at a glance, with overlaps and empty stretches.
- Playlists in list order that drop films once they're watched, shared with every user or built per person. Each sync edits the playlist in place, so pins, home-screen shortcuts and resume spots survive.
- A safety brake: a sync that would take most of a list off the server (a list that came back empty, a library halfway through a rescan) changes nothing for that list until you say so.
- Films that arrive on the server join the lists that were missing them within minutes, without waiting for the next scheduled sync.
- Several media servers at once, Emby and Jellyfin side by side: every server gets everything, or a list can pick its servers.
- Scheduled syncs at set times each day or on an interval, plus a web UI to run, preview and check syncs, edit settings and configs, and read the logs.
- A dry run shows, list by list, which films would be added or removed and what artwork would change; every run keeps the same summary.
- A message to Discord, Slack, Gotify, ntfy or any webhook when a scheduled sync fails, or after every one.
- Shows which films on each list are in your library and which are missing, and when each list last synced. A missing film or show says whether it's already Requested (or downloaded and Available) in Seerr, or in Radarr and Sonarr, and one click requests it if it's truly Missing.
- Shows each film's MDBList score, linked to its MDBList page. Scores are cached, so they cost almost no extra MDBList requests.
- Saves what an MDBList or Trakt list holds today as a list file of your own, to freeze it and edit it by hand.
- Keeps the last versions of every config and list file, so a save can be undone, and downloads or restores the whole config folder as one zip.
- A setup screen on first start, for the media server, list keys and a password, so nothing syncs against a placeholder server.
- A password with optional two-factor sign-in (any authenticator app, plus recovery codes), and ready to sit behind a reverse proxy, at its own domain or under a path.
- Rides out rate limits and brief outages at MDBList, Trakt and TMDB by trying again.
- Imports the collections and playlists already on your server, so nothing gets built twice.
- Python standard library only, so the image is small and has no dependencies to keep up to date.

## Before you start

StaffPicked creates, changes and deletes collections and playlists on your media servers. Try a **dry run** first, and read the [disclaimer](../README.md#disclaimer-use-at-your-own-risk).

---

[Back to the README](../README.md) · [Next: Getting started →](getting-started.md)
