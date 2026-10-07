# Getting started

[User guide](README.md) · [Next: Using the web UI →](web-ui.md)

StaffPicked runs as one Docker container with a web UI on port 9343. Everything you set up is kept in one config folder mounted at `/config`.

## Install with Docker Compose

1. Get `docker-compose.yml` and start it. Nothing needs editing first:
   ```bash
   mkdir staffpicked && cd staffpicked
   curl -fsSLO https://raw.githubusercontent.com/cj0r/staffpicked/main/docker-compose.yml
   docker compose up -d
   ```
   This pulls the published image, `cj0r/staffpicked` on Docker Hub (also `ghcr.io/cj0r/staffpicked`), built for `linux/amd64` and `linux/arm64`. To build it yourself instead, see [Building from source](#building-from-source).
2. Open `http://<host>:9343`. On first start StaffPicked fills the `config` folder next to `docker-compose.yml` with example settings and opens a setup screen: your media server (with a **Test** button), optional MDBList and Trakt keys, then a password (or skip it if you only use it at home: without a password the UI only opens from your local network). Nothing syncs until a server is set up. Then add collections, playlists and your own lists in the browser.
3. Enable **Admin Mode** at the top of **Settings** to show the admin tools. Run **Check Config** (under **Config Files**), then **Sync** with **Dry run** ticked to see every change it would make, then **Sync** for real.

The container syncs once at start (once a server is set up) and then on its schedule: every day at each `SYNC_TIME`, or every `SYNC_EVERY` (Settings > Schedule). It re-reads the config folder before every sync, so edits need no restart. Everything you set in the browser is saved to plain files in the config folder (`staffpicked.env`, `collections.toml`, `playlists.toml`, `collections/`, `playlists/`), so you can also edit them by hand; see [Settings and the config folder](settings.md). [Using the web UI](web-ui.md) walks through the browser side.

The image has a Docker health check, so Dockge, Portainer and `docker ps` show the container as healthy while the web UI answers and its schedule is running.

Optional settings in `docker-compose.yml`: `TZ` (your time zone, for the schedule; UTC otherwise; **Time zone** in the web UI's Settings overrides it), and `PUID`/`PGID` (see [Permissions](#permissions)).

## Compose managers

Dockge, Portainer, a NAS's container app and the like: paste `docker-compose.yml` in as a new stack and deploy it. The config folder is then created next to the manager's copy of the compose file (Dockge: `/opt/stacks/<stack>/config`); that's the folder to edit or back up.

If the manager itself runs in a container, its stacks folder must have the same path inside and outside it (e.g. `/opt/stacks:/opt/stacks`); otherwise Docker creates a separate, empty `config` folder on the host, and edits in the stacks folder never reach StaffPicked. `docker inspect staffpicked` shows which host folder is mounted at `/config`.

To use a folder somewhere else, set `CONFIG_PATH` in the stack's `.env`, e.g. `CONFIG_PATH=/srv/staffpicked`. Plain `docker run` works too: pass the same port and volume.

## Updating

`docker compose pull && docker compose up -d` (or your manager's update button). Your config folder is kept, and new settings get their defaults.

## Unraid

Once it's listed in Community Applications, install it from the **Apps** tab: search for StaffPicked. The template, kept in [cj0r/unraid-templates](https://github.com/cj0r/unraid-templates), keeps the config folder in `/mnt/user/appdata/staffpicked`, runs as `99:100` (`nobody:users`), and opens the web UI from the container's icon. Finish the setup in the browser as above.

## Building from source

```bash
git clone https://github.com/cj0r/staffpicked.git && cd staffpicked
docker build -t cj0r/staffpicked:latest .
docker compose up -d
```

The compose file then runs your own build instead of pulling one.

## Permissions

There's nothing to set for most installs. The container starts as root just long enough to make the config folder writable, then runs everything as the folder's owner on the host, so the files it writes stay editable there. A folder Docker created itself (owned by root) is given to `1000:1000`. Under rootless Docker or Podman it stays root in the container, which is already your own user. The log's first line says which user it picked.

To choose the user yourself, set `PUID` and `PGID` (for example `99` and `100` for Unraid's `nobody:users`), or use `user:` / `docker run --user`. With `user:` the container skips the ownership step, so the folder must already be writable for that user. If the folder sits on a network share that refuses ownership changes, the container logs a warning and carries on; make the share writable for that user instead.

## Running without Docker

StaffPicked needs only Python 3.11 or newer, with no packages to install. From a checkout of the repository:

```bash
python3 web/server.py      # the web UI and schedule; uses $STAFFPICKED_CONFIG, else /config, else ./config
python3 -m scripts check   # or any other command; see the Command line page
```

See [Command line](command-line.md) for every command.

---

[User guide](README.md) · [Next: Using the web UI →](web-ui.md)
