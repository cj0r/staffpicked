# Changelog

Every release of StaffPicked, newest first. Versions follow [semantic versioning](https://semver.org): a new major version means a config or setting has to change by hand.

## 1.1.1 (2026-10-07)

- The README is now a short introduction and quick start, and everything else moved to a multi-page user guide in `docs/`.

## 1.1.0 (2026-10-07)

- A Screen Effects switch in Settings turns off the worn-tape effects (the tracking band that rolls down the screen, tape grain, scanlines, the tube vignette and the blinking PLAY). Enabled by default; the choice is saved on the server, so it holds for every browser, sign-in and restart.

## 1.0.0 (2026-10-07)

The first public release.

- Collections and playlists on Emby and Jellyfin alike, from MDBList lists (public and private), Trakt lists and watchlists, and your own Markdown list files.
- Posters and backdrops from TMDB, fanart.tv, MediUX, any URL or a local file (posters from ThePosterDB are added by hand), plus your own artwork on the server's genres.
- Seasonal date windows with a season calendar, so a collection or playlist exists only while it's in season.
- Playlists in list order that drop watched films, shared or per person, edited in place so pins and resume spots survive.
- Several media servers at once, with each list able to pick its servers.
- A web UI with a first-run setup screen, scheduled and on-demand syncs, dry runs, logs, config editing with restore, config backup and restore as a zip, and imports of the collections and playlists already on a server.
- Missing films checked against Seerr, Radarr and Sonarr, with one-click requests.
- A safety brake that holds back a sync that would empty most of a list.
- Notifications to Discord, Slack, Gotify, ntfy or any webhook.
- Password sign-in with optional two-factor codes and recovery codes, local-network-only access without a password, and reverse proxy support (`TRUSTED_PROXIES`, `URL_BASE`).
