<h1 align="center"><img src="docs/logo/banner.webp" alt="StaffPicked" width="100%"></h1>

<p align="center">
  <a href="https://hub.docker.com/r/cj0r/staffpicked"><img src="https://img.shields.io/docker/v/cj0r/staffpicked?sort=semver&style=flat-square&label=docker" alt="Docker image version"></a>
  <a href="https://hub.docker.com/r/cj0r/staffpicked"><img src="https://img.shields.io/docker/pulls/cj0r/staffpicked?style=flat-square" alt="Docker pulls"></a>
  <a href="https://github.com/cj0r/staffpicked/actions/workflows/tests.yml"><img src="https://img.shields.io/github/actions/workflow/status/cj0r/staffpicked/tests.yml?branch=main&style=flat-square&label=tests" alt="Tests"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL--3.0-blue?style=flat-square" alt="License: GPL-3.0"></a>
</p>

Named for the shelf of staff picks at the old video store: a few carefully chosen lists, put together by people who care.

StaffPicked builds collections and playlists on Emby and Jellyfin from MDBList lists, Trakt lists and your own Markdown lists, with artwork from TMDB, fanart.tv, MediUX or your own files. It can also give the genres on your server your own artwork. Collections and playlists can be seasonal, appearing only inside a date window. Playlists keep the list's order and can skip what you've already watched. It runs as one Docker container with a web UI, and keeps everything in sync on a schedule (set times each day, or every few hours), on one media server or several at once.

Emby and Jellyfin are supported equally: every feature works on both, you pick the kind for each server in the setup screen (or with `SERVER_TYPE`), and one StaffPicked can keep an Emby server and a Jellyfin server in step at once.

![StaffPicked's shelf of collections, shown as tape covers](docs/screenshots/poster-view.webp)

> [!WARNING]
> StaffPicked is provided **as is, with no warranty, and you use it at your own risk**. It creates, changes and **deletes collections and playlists** on your media servers and replaces their artwork, and it holds the API keys for your servers and list services. Try a **dry run** first, and read [Security](docs/security.md) and the [Disclaimer](#disclaimer-use-at-your-own-risk) before you put it on a server you care about.

## What it does

- Collections and playlists from MDBList, Trakt and your own Markdown lists, kept in sync on a schedule.
- Seasonal date windows, so a list is on the server only while it's in season.
- Playlists in list order that drop films once they're watched, shared or built per person.
- Posters and backdrops from TMDB, fanart.tv, MediUX or your own files, for collections, playlists and genres.
- A web UI to set it all up, preview every change with a dry run, see what's in your library and what's missing, and read the logs.
- One server or several, Emby and Jellyfin side by side.

The [user guide](docs/README.md#what-staffpicked-does) has the full list.

## Quick start

1. Get `docker-compose.yml` and start it. Nothing needs editing first:
   ```bash
   mkdir staffpicked && cd staffpicked
   curl -fsSLO https://raw.githubusercontent.com/cj0r/staffpicked/main/docker-compose.yml
   docker compose up -d
   ```
2. Open `http://<host>:9343`. A setup screen asks for your media server (with a **Test** button), optional MDBList and Trakt keys, and a password. Then add collections, playlists and your own lists in the browser.
3. Enable **Admin Mode** at the top of **Settings**, run **Sync** with **Dry run** ticked to see every change it would make, then **Sync** for real.

To update: `docker compose pull && docker compose up -d`. Compose managers (Dockge, Portainer), Unraid, building from source and permissions are in [Getting started](docs/getting-started.md).

## Screenshots

| | |
|---|---|
| ![The dashboard: lists on the shelf, what's in season, the next sync and recent runs](docs/screenshots/dashboard.webp) | ![A playlist's artwork, season and films, with which are in the library](docs/screenshots/list-window.webp) |
| **The shelf.** Every list, whether it's in season, when it last synced and how much of it is in your library. | **A list up close.** Its artwork, season and sharing, and each film marked in the library or missing. |
| ![The season calendar: when each collection and playlist is on the server across the year](docs/screenshots/season-calendar.webp) | ![Settings with an Emby server and a Jellyfin server side by side](docs/screenshots/media-servers.webp) |
| **Season calendar.** When each list is on the server, across the whole year. | **Emby and Jellyfin together.** One server or several, of either kind, each with its own Test button. |

## User guide

Everything else is in the [user guide](docs/README.md):

- [Getting started](docs/getting-started.md)
- [Using the web UI](docs/web-ui.md)
- [Collections and playlists](docs/collections-and-playlists.md)
- [List files](docs/list-files.md)
- [Sources and artwork](docs/sources-and-artwork.md)
- [Genre artwork](docs/genres.md)
- [Importing what's on your server](docs/importing.md)
- [Several media servers](docs/multiple-servers.md)
- [Settings and the config folder](docs/settings.md)
- [Command line](docs/command-line.md)
- [Security](docs/security.md)
- [Troubleshooting](docs/troubleshooting.md)

## Disclaimer: use at your own risk

**StaffPicked is provided "as is", without warranty of any kind, express or implied.** The [LICENSE](LICENSE) has the full legal text. In plain terms:

- **You use it entirely at your own risk.** The author and contributors accept no responsibility or liability for lost or changed collections, playlists or artwork, wrong metadata, service interruptions, exposed API keys, security incidents, suspended accounts at the services it connects to, or any other damage from using or misusing it.
- **It changes and deletes things on your media servers.** Syncs add and remove films in collections and playlists, a list's season ending deletes its collection or playlist, `remove` deletes everything configured, and artwork is replaced. A collection or playlist you made yourself is changed too if a StaffPicked entry has the same name. Your media files are never touched, but run a **dry run** first and keep backups of your server's data.
- **Check your configuration before running it against a real server.** A wrong list, server or name can change far more than intended, and the author can't undo it for you.
- **Your deployment's security is yours**: network exposure, the password and two-factor sign-in, HTTPS, the reverse proxy and who can read the config folder. See [Security](docs/security.md).
- **You're responsible for following the terms of the services you connect it to** (MDBList, Trakt, TMDB, fanart.tv, MediUX and the rest) and of your own API keys, and for having the right to the artwork you use.
- **StaffPicked isn't affiliated with or endorsed by** Emby, Jellyfin, or any of the services it works with. Their names belong to their owners.

It's a hobby project maintained on a best-effort basis, with no guarantee of support or fixes. Report security problems privately, as [SECURITY.md](SECURITY.md) describes, rather than in a public issue.

## Support the project

If StaffPicked keeps your shelves stocked, you can support its development. Every bit is appreciated.

<p>
  <a href="https://ko-fi.com/cj000r"><img src="https://img.shields.io/badge/Ko--fi-F16061?style=for-the-badge&logo=ko-fi&logoColor=white" alt="Support on Ko-fi"></a>
  <a href="https://www.buymeacoffee.com/cj0r"><img src="https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black" alt="Buy Me a Coffee"></a>
</p>

## Contributing and license

Bug reports and pull requests are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md), and [SECURITY.md](SECURITY.md) for reporting a security problem privately. What changed in each release is in [CHANGELOG.md](CHANGELOG.md).

StaffPicked is free software under the [GNU General Public License v3.0](LICENSE). The icons, QR code library and fonts it bundles are under their own licenses, listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
