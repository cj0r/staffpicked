# Several media servers

[← Previous: Importing what's on your server](importing.md) · [User guide](README.md) · [Next: Settings and the config folder →](settings.md)

Emby and Jellyfin are supported equally: every feature works on both, and you pick the kind for each server in the setup screen (or with `SERVER_TYPE`). StaffPicked can keep several servers in step at once, for example an Emby server and a Jellyfin server, or two Emby servers in different houses.

In the web UI, **Settings → Media Servers** has a card per server with **Add Server**, **Test** and **Remove**, and writes the settings below for you.

## Settings

The `SERVER_*` settings in `staffpicked.env` (see [Settings](settings.md#staffpickedenv)) are server 1. Each further server takes the same settings with a number after `SERVER_`, and its own playlist viewers:

```
SERVER_2_NAME=Living Room          # optional; blank = its type ("Jellyfin")
SERVER_2_TYPE=jellyfin
SERVER_2_URL=http://192.168.1.20:8096
SERVER_2_API_KEY=...
SERVER_2_USER=                     # and SERVER_2_PASSWORD, SERVER_2_WATCHED_BY,
                                   # SERVER_2_PLAYLIST_USERS, SERVER_2_LINKED_USERS
```

Server 1 can also be named, with `SERVER_NAME`. Two servers can't share a name; unnamed ones of the same type are called "Emby" and "Emby 2".

## How it works

- **What goes where:** every collection, playlist and genre goes to every server. To keep one to some servers, give it `servers = ["Living Room"]` (names, any capitalization). `check` warns about a name that isn't set up, and a sync sends the entry to the rest of its servers.
- **Syncing:** each sync goes through the servers in turn, and a server that's down is reported without stopping the others. Lists are read once and shared. On the dashboard, each On the Shelves tab has a server picker for Sync and the remove buttons, the header shows each server's connection, and Recent Runs shows how each server did. On the command line, `--server NAME` runs on just one.
- **Users differ per server:** admin user, password, watched-by, per-person and linked users are set per server, since each server has its own accounts.
- **Removing a server** from the settings stops syncing to it; what StaffPicked built there stays until you remove it first (pick the server and use the remove buttons, or `remove --server NAME`).

---

[← Previous: Importing what's on your server](importing.md) · [User guide](README.md) · [Next: Settings and the config folder →](settings.md)
