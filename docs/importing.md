# Importing what's on your server

[← Previous: Genre artwork](genres.md) · [User guide](README.md) · [Next: Several media servers →](multiple-servers.md)

If your server already has collections and playlists, StaffPicked can take them over instead of building second copies. Open **Import** on the On the Shelves card (or run `import`; see [Command line](command-line.md)) to see each one on the server marked as:

- **Managed:** a StaffPicked entry has the same name (capitalization doesn't matter), so sync already updates that one. Collections and playlists are both updated in place.
- **Similar name:** a StaffPicked entry has nearly the same name, like "Indepedence Day" and "Independence Day". **Link** renames the entry to the server's name, so sync updates the existing one instead of building another.
- **Not in StaffPicked:** **Import** saves its poster and backdrop to `images/` and adds an entry for it. [How a collection finds its list](#how-a-collection-finds-its-list) is below. Imported playlists get `include_watched = true` and `share = "private"`, so nothing about them changes until you edit those settings. Anything without an IMDb ID (or an episode in a playlist) can't go in a list file; it's listed in a comment at the end of the file, and a collection loses it at the next sync.
- **Fixed copy:** a collection StaffPicked manages from a list file (say, from an earlier import). **Use list** switches its entry to the MDBList or Trakt list it was found to come from; when none was found, **Add list** asks for the list's link. The list file stays in `collections/`.
- **Genres:** genres that already have artwork on the server (set by hand in Emby or Jellyfin, or by a metadata plugin) are listed too. **Import** saves the genre's poster, thumb and backdrops to `images/` (`genre-horror-poster.jpg` and so on) and adds a `[[genre]]` entry pointing at them, so StaffPicked keeps that artwork and you can swap any image later. A genre already in `genres.toml` shows as managed. Use `genre:NAME` with `--adopt` for just a genre.
- **Duplicate:** the server already has two with this name. StaffPicked updates only the first collection; for playlists, a sync replaces every playlist with a name StaffPicked manages.

You pick which ones to bring in and review the list before anything is written. Importing and linking only change the config folder: nothing on the server is changed or deleted until the next sync, which then keeps them up to date like any other entry. Playlists are read from the admin user (`SERVER_USER`). With several servers, the import screen has a server picker and `import` goes through each server in turn (`--server` picks one); an imported entry goes to every server like any other.

## How a collection finds its list

For a collection, StaffPicked first looks for the list it was built from: an MDBList or Trakt link in its overview or tags, or else an MDBList list (yours, or a public one with a similar name) whose films in your library are nearly the same as the collection's, combining up to three lists. When it finds one, the collection follows that list, gaining and losing films as the list does. Looking on MDBList needs `MDBLIST_API_KEY`.

When no list is found, and for playlists, the films are written, in the server's order, to a new list file (in `collections/` or `playlists/`) as a fixed list. For a collection with no list found, the import screen first asks for its MDBList or Trakt link: paste it and the collection follows that list (the link is checked before anything is saved), or **Skip** to import it as a fixed list. The import screen says which each one gets before you approve it.

---

[← Previous: Genre artwork](genres.md) · [User guide](README.md) · [Next: Several media servers →](multiple-servers.md)
