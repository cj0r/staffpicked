# Command line

[← Previous: Settings and the config folder](settings.md) · [User guide](README.md) · [Next: Security →](security.md)

Every action in the web UI is also available as a command, in the container or straight from the repo with Python 3.11 or newer:

```bash
docker exec -it staffpicked staffpicked check    # in the running container
python3 -m scripts check                         # from the repo, no Docker
```

From a container console (Dockge, Portainer and the like), leave off the `docker exec` part: `staffpicked check`.

| Command | What it does |
|---|---|
| `check` | Validates the settings and configs and lists every problem. Needs no server. |
| `sync` | Builds and updates everything once. |
| `remove` | Deletes every configured collection and playlist from the server (the media is untouched), and takes StaffPicked's artwork off the configured genres (the genres stay). |
| `import` | Lists the collections, playlists and genres with artwork already on the server and whether StaffPicked manages them. With `--adopt "NAME"` (repeatable, or `--adopt all`), imports or links them; see [Importing what's on your server](importing.md). `collection:NAME`, `playlist:NAME` or `genre:NAME` picks one kind. |
| `schedule` | Runs `sync` on the schedule (`SYNC_TIME` or `SYNC_EVERY`) without the web UI. |
| `reset-login` | Takes off the web UI's password and two-factor sign-in and signs every browser out, for a lost password or authenticator. In Docker only (`docker exec -it staffpicked staffpicked reset-login`). |

| Option | What it does |
|---|---|
| `--dry-run` | Shows every change without making it. |
| `--only "NAME"` | Runs just one collection, playlist or genre. |
| `--server "NAME"` | Runs on just one media server, by its name or its number (see [Several media servers](multiple-servers.md)). Without it, every server gets everything meant for it. |
| `--date 2026-10-15` | Pretends it's another day, to test seasonal windows. |
| `--allow-removals` | Lets this run take most of a list off the server; without it, a sync that would remove more than `REMOVAL_LIMIT` percent of a list is held back. |
| `--config DIR` | The config folder. Default: `$STAFFPICKED_CONFIG`, else `/config`, else `config/` next to the code. |
| `--env FILE` | A settings file other than `staffpicked.env` in the config folder. |

---

[← Previous: Settings and the config folder](settings.md) · [User guide](README.md) · [Next: Security →](security.md)
