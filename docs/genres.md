# Genre artwork

[← Previous: Sources and artwork](sources-and-artwork.md) · [User guide](README.md) · [Next: Importing what's on your server →](importing.md)

StaffPicked can give the genres on your server (Horror, Comedy, ...) your own poster, thumb and backdrops. Use the Genres tab in the web UI, or edit `genres.toml`:

```toml
[[genre]]
name = "Horror"                                # the genre's name on the server
poster = "images/horror-poster.jpg"            # optional
thumb = "images/horror-thumb.jpg"              # optional; a wide 16:9 card
backdrops = ["images/horror-backdrop.jpg"]     # optional
servers = ["Jellyfin"]                         # optional; only these servers (default: every server)
```

Images take the same strings as collections and playlists; see [Sources and artwork](sources-and-artwork.md#images).

- **What it changes:** the server makes its genres from your films' metadata, so StaffPicked never creates, renames or deletes one. It finds each genre by name (capitalization doesn't matter) and sets the images you give it. A name that isn't on the server is reported and skipped. The web UI suggests the server's genre names as you type, and **Import** brings in genres that already have artwork on the server (see [Importing what's on your server](importing.md)).
- **Which image shows where:** `poster` is the genre's main (Primary) image, the card both Emby and Jellyfin show for it. `thumb` is a wide 16:9 card that Emby uses in its genre rows when it's set. `backdrops` sit behind the genre's page.
- **Taking it back off:** removing a genre from `genres.toml` leaves its artwork on the server. Delete it in the web UI with **Also take the artwork off** ticked, or run `remove --only "Horror"` first, to remove the images StaffPicked set. Artwork set any other way is left alone.
- **Turning it off:** `ENABLE_GENRES=false` (Genre artwork in Settings) skips genres. It has nothing to do until you add a genre.

---

[← Previous: Sources and artwork](sources-and-artwork.md) · [User guide](README.md) · [Next: Importing what's on your server →](importing.md)
