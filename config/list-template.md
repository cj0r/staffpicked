# List Name Here

One or two sentences on what this list is and how the order was chosen.

<!--
HOW THIS FILE WORKS (this comment is ignored; leave it out of real lists if you like)

Put one film per line: its IMDb ID, a "|", then your own notes (the title, the year,
why it's here, or nothing at all), like "- tt0084787 | The Thing (1982)". A playlist
plays them from the top of the file down, as one flat list: Emby and Jellyfin playlists have no
sections, so don't split the films under headings. Lines without an IMDb ID are ignored.

To find an IMDb ID, open the film on imdb.com: it's the part of the address that starts
with "tt", like tt0084787 in imdb.com/title/tt0084787/.

Lists for playlists go in the playlists folder, and lists for collections in the collections
folder. The settings (name, season window, artwork, ...) live in playlists.toml or
collections.toml in the config folder, in an entry that points at this file:

  [[playlist]]
  name = "Playlist Name Here"
  sources = ["playlists/my-list.md"]
  active = "09-25 to 10-31"      # optional season window; leave it out for all year
-->

- tt0084787 | The Thing (1982)
- tt0080749 | The Fog (1980), perfect for October
- tt0089175 | Fright Night (1985)

---

Prompt for an AI agent: copy everything between the lines below into the AI chat, and fill in the bracketed parts.

```text
Create a new StaffPicked list file in exactly the format below, and add an entry for it
to playlists.toml or collections.toml (in the config folder).

What I want:
- It's for a: [playlist (plays in this order) / collection (a shelf of films)]
- Name: [e.g. 80s Sci-Fi]
- Theme / films: [describe the list, or paste the titles you want]
- How to order it: [e.g. must-sees first, release order, best for a first-time viewer]
- Season window: [e.g. 09-25 to 10-31, or "all year"]
- Keep films I've already watched in the playlist (playlists only): [yes / no]

Rules you must follow:
1. The file looks exactly like this (a Markdown file; the films below are only examples):

     # <name>

     <One or two sentences on what this list is and how the order was chosen.>

     - tt0084787 | The Thing (1982)
     - tt0080749 | The Fog (1980), perfect for October
     - tt0089175 | Fright Night (1985)

   Nothing else goes in the file: no tables, comments or extra sections.
2. Every film is one list line: "- <IMDb ID> | <Title> (<Year>)", optionally followed by a
   short note, e.g. "- tt0084787 | The Thing (1982), the gold standard for creature FX".
   - The first film is watched first. One film per line; split double features and
     series into separate lines. No film twice.
   - Look up each IMDb ID (tt followed by 7 or more digits) and double-check it is the
     right film and year, especially for remakes and films that share a title.
3. One flat list of films after the description: no headings, tiers or sections
   between them (playlists have none).
   Order it the way I asked. Unless I said otherwise:
   - Rank by how essential each film is to the theme: reputation and standing first,
     ratings (e.g. the MDBList, IMDb or TMDB score) second to break ties. Don't group
     films by type, country or subgenre; a strong cult or foreign film sits right next
     to the mainstream classics it ranks with.
   - Every sequel comes after the film it follows; a strong sequel can still rank high,
     weaker ones go toward the end.
   - Give a small boost to films that fit the season window, and put films set at a
     different holiday (e.g. Christmas films in an October list) near the end.
   - Put anything with content many viewers want to know about first (e.g. real animal
     cruelty) lower, and say why in its note.
   - Use the description to say in one or two sentences how the order was chosen.
4. Save it as [lowercase-name-with-dashes].md in the playlists folder for a playlist, or the
   collections folder for a collection. The file name must not contain the word "template".
5. For a playlist, append this to playlists.toml (in the config folder); the name must not
   match another playlist there:
     [[playlist]]
     name = "<name>"
     sources = ["playlists/<file name>.md"]
     active = "<MM-DD> to <MM-DD>"      (leave this line out for "all year")
     include_watched = true             (only if I said yes; otherwise leave it out)
   For a collection, append this to collections.toml instead (same rules for the name):
     [[collection]]
     name = "<name>"
     sources = ["collections/<file name>.md"]
     active = "<MM-DD> to <MM-DD>"      (leave this line out for "all year")
   Do not add watched_by, share, poster or backdrop lines or any user names.
6. If you can run commands, validate and fix every problem it reports:
   python3 -m scripts check   (from the repo folder), or:
   docker exec -it staffpicked staffpicked check
7. Finish by listing the films in order and noting any IMDb ID you weren't sure of.
```
