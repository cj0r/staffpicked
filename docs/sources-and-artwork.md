# Sources and artwork

[← Previous: List files](list-files.md) · [User guide](README.md) · [Next: Genre artwork →](genres.md)

The same source and image strings work in every config (genres take images only), and in the web UI's forms.

## Sources

A list's items keep its order.

| Write | For |
|---|---|
| `https://mdblist.com/lists/<user>/<list>` or `mdblist:<user>/<list>` or `mdblist:<list id>` | an MDBList list |
| `https://trakt.tv/users/<user>/lists/<list>` or `trakt:<user>/<list>` | a Trakt list |
| `trakt:<user>/watchlist` | a Trakt watchlist (needs `TRAKT_ACCESS_TOKEN`) |
| `collections/<file>.md`, `playlists/<file>.md` | one of your own [list files](list-files.md) |

Movies and shows from MDBList and Trakt are matched to your library by IMDb, TMDB or TVDB id, then by title and year. List files are matched by IMDb ID. Anything not in the library is listed in the output and skipped until it arrives.

MDBList lists need `MDBLIST_API_KEY` (your own private lists work too). Trakt lists need `TRAKT_CLIENT_ID`; private lists and watchlists also need `TRAKT_ACCESS_TOKEN` for the owner's account. StaffPicked rides out rate limits and brief outages at MDBList, Trakt and TMDB by trying again.

## Images

`poster`, `backdrops` for one or more backdrops, and for genres `thumb`:

| Write | For |
|---|---|
| `images/<file>.jpg` | a file in the config folder (`.jpg`, `.jpeg`, `.png`, `.webp`) |
| `https://...` | any image URL |
| `tmdb:movie/<id>`, `tmdb:tv/<id>`, `tmdb:collection/<id>` | TMDB's best image: textless backdrops first, English posters and thumbs first |
| `tmdb:/<file>.jpg` | one exact TMDB image |
| `fanart:movie/<TMDB or IMDb id>`, `fanart:tv/<TVDB id>` | fanart.tv's most liked image (for a thumb, its wide movie or TV thumb) |
| `mediux:movie/<TMDB id>`, `mediux:collection/<TMDB id>` | MediUX's best set for it: English or textless first, then the most popular |
| `mediux:set/<set id>` or a `https://mediux.pro/sets/<id>` link | that MediUX set's poster or backdrop |
| `mediux:<asset id>` | one exact MediUX image (needs no token) |

TMDB images need `TMDB_API_TOKEN`, fanart.tv images `FANARTTV_API_KEY`, and MediUX lookups by movie, collection or set `MEDIUX_API_TOKEN`. MediUX images are downloaded once and kept in `cache/mediux/`; MediUX has no thumbs.

ThePosterDB has no API for apps, so StaffPicked doesn't download from it. To use one of its posters, download it from theposterdb.com yourself, then upload it in the web UI or save it in `images/` and point the config at that file.

## Saved copies

Every image that isn't a local file is also saved to `images/`, named after its collection or playlist: `collection-80s-horror-poster.jpg`, `collection-80s-horror-backdrop.jpg`, `collection-80s-horror-backdrop-2.jpg`, and `playlist-...` and `genre-...` for playlists and genres. When the image changes, the old copy is moved to `images/archive/` with the date and time added to its name. Nothing there is ever deleted. You can point a config at a saved copy to stop depending on the URL. Switching a poster or backdrop to a local file leaves the old copy where it is; the Images list shows it as unused.

Images are uploaded again only when the image changes. If an image can't be fetched, the output warns and everything else still syncs.

---

[← Previous: List files](list-files.md) · [User guide](README.md) · [Next: Genre artwork →](genres.md)
