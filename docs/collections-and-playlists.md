# Collections and playlists

[← Previous: Using the web UI](web-ui.md) · [User guide](README.md) · [Next: List files →](list-files.md)

The web UI's forms write these files for you; this page explains each setting, for the forms and for editing `collections.toml` and `playlists.toml` by hand. Where a list's films come from and where its artwork comes from are on [Sources and artwork](sources-and-artwork.md).

## Collections or playlists?

- **Collections** are library shelves everyone sees. Emby and Jellyfin sort them by name or date only, so the list's order is lost. Use them for broad lists ("Halloween", "Trending Movies").
- **Playlists** keep the exact order of the list and can drop films once they're watched. Use them for "watch these in this order" lists.

A collection and a playlist can share a name. StaffPicked only touches collections and playlists named in its configs.

## collections.toml

```toml
[settings]
use_list_descriptions = false       # use the MDBList/Trakt list description when a collection has none
refresh_new_releases = true         # refresh metadata of new releases so their ratings settle
new_release_added_days = 10         # ...if added within this many days
new_release_released_days = 30      # ...and released within this many days

[[collection]]
name = "80s Horror"
sources = ["https://mdblist.com/lists/someuser/80s-horror"]
active = "09-30 to 11-02"           # optional season window
poster = "images/collection-poster-genre-horror-80s.jpg"
backdrops = ["tmdb:/gE6lGe7f7QtX1R2pRpXu1AgH1hU.jpg"]
description = "Rubber suits and synths."   # optional
sort_name = "0 80s Horror"          # optional; where it sorts on the server
display_order = "release_date"      # optional; release_date or sort_name
servers = ["Emby"]                  # optional; only these servers (default: every server)
```

- **Sync:** each run adds what the lists gained and removes what they lost. Items from all of a collection's sources go into it. To drop a film, remove it from the list, because removing it on the server won't stick.
- **Display order:** `display_order` sets the order of a collection's films on the server, `"release_date"` or `"sort_name"`, the two orders Emby and Jellyfin both offer. Viewers can still pick another sort for themselves in their app. Leave it out to keep whatever is set on the server.
- **Season:** `active = "MM-DD to MM-DD"` repeats every year and may wrap the new year (`"11-30 to 01-01"`); `"2026-09-30 to 2026-11-02"` is a one-off. Outside the window the collection is deleted from the server (the media is untouched) and comes back when the window opens. Leave `active` out to keep it all year.
- **Servers:** `servers` keeps an entry to some of your media servers; see [Several media servers](multiple-servers.md).

## playlists.toml

```toml
[settings]
include_watched = false     # false = drop what the watched-by users already played
share = "view"              # view = every other user can see it; private = owner only

[[playlist]]
name = "80s Horror"
sources = ["playlists/80s-horror.md"]
active = "09-25 to 10-31"
poster = "images/playlist-80s-horror-poster.jpg"
backdrops = ["images/playlist-80s-horror-backdrop.jpg"]
# include_watched, share and watched_by = ["name"] can also be set per playlist,
# and servers = ["name"] to keep it to some servers (default: every server)
```

- **Order:** items play in list order. With several sources, they play one list after another.
- **Updated in place:** each sync adds, removes and moves films on the existing playlist rather than building a new one, so it stays the same playlist on the server. If a server won't edit a playlist in place, it's built again and the output warns.
- **Season:** works like collections: outside its window the playlist is removed.
- **Watched films:** with `include_watched = false`, a film drops off once **any** user in `WATCHED_BY` has played it, so the playlist shrinks as you watch. Other users' viewing never removes anything. A playlist can name its own `watched_by` users, but keeping names in `staffpicked.env` keeps them out of git.
- **Sharing:** `view` lets every other enabled user see and play the playlist but not edit it. Emby only accepts sharing from the owner signed in, so StaffPicked signs in with `SERVER_PASSWORD` for that one step. The owner also needs **Allow sharing personal content** on (Dashboard → Users → the owner → Profile). If either is missing, the playlist is still built and the output warns. On Jellyfin, `view` makes the playlist public and `private` makes it the owner's alone; a new playlist is made that way from the start, and switching one that's already there takes `SERVER_PASSWORD` too.
- **Jellyfin and the order:** Jellyfin only lets a playlist's owner, signed in, move films around in it, so keeping the list's order in place takes `SERVER_PASSWORD` there. Without it, a playlist whose order changed is built again (same name, new playlist).
- **Removing a playlist from the config:** it stays on the server until you delete it there, or run `remove` before taking it out.

### Per-person playlists

A shared playlist is one list for everyone: the server can't hide entries per viewer. To let each person see only the films they haven't watched, set `PLAYLIST_USERS` to their user names. Each of them then gets their own private copy of every playlist, built from their own watched films. No password or sharing is needed in this mode, and `WATCHED_BY` and `share` are ignored. If `SERVER_USER` also has a shared playlist with the same name, it is removed.

To link people, list them in `LINKED_USERS`. When one watches a film, it also drops off the playlists of everyone linked with them. Separate groups with `;`, for example `alice, bob; carol, dan`.

## Renaming

Rename a collection or playlist in the web UI and the next sync removes the one under the old name from each server the entry goes to, then builds it under the new name; the run log shows both. Only that old name is removed, and never one another entry still uses. A rename made by editing the file by hand isn't tracked, so the old one stays on the server until you delete it there.

## The safety brake

A sync that would take most of a list off the server (a list that came back empty, a library halfway through a rescan) changes nothing for that list until you say so. `REMOVAL_LIMIT` sets how much is too much (default `50` percent, and at least 3 films); the list window then offers **Sync Anyway**, or run `sync --allow-removals`. Films leaving a playlist because they were watched don't count.

---

[← Previous: Using the web UI](web-ui.md) · [User guide](README.md) · [Next: List files →](list-files.md)
