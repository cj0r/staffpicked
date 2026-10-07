# List files

[← Previous: Collections and playlists](collections-and-playlists.md) · [User guide](README.md) · [Next: Sources and artwork →](sources-and-artwork.md)

A list file is a Markdown file of films in the order you want them, for lists you write yourself rather than follow on MDBList or Trakt. Lists for playlists go in `playlists/`, lists for collections in `collections/`. Put one film per line: its IMDb ID, a `|`, then your own notes (the title, a reason, or nothing at all). A playlist plays them from the top of the file down.

```markdown
# 80s Horror

Carpenter first, then the rest of the decade.

- tt0084787 | The Thing (1982)
- tt0080749 | The Fog (1980), perfect for October
- tt0089175 | Fright Night (1985)
```

Only the IMDb ID is read: the first `tt` number on each line (find it in the film's imdb.com address, like `imdb.com/title/tt0084787/`). Lines without one, such as the title, a description and blank lines, are ignored. Keep the films as one flat list: Emby and Jellyfin playlists have no sections, so headings between films only make the file look like it has some. Shows work too. `check` warns about an ID listed twice and about a line that looks like a film but has no ID.

## Adding a list

The web UI can do all of this for you: **New** starts an empty list or takes a whole list pasted in, AI-written ones included, and the list icon on an entry opens its films to search, reorder and annotate (see [Editing a list's films](web-ui.md#editing-a-lists-films)).

By hand: copy `list-template.md` into `playlists/` or `collections/` (or give an AI agent the prompt at its bottom), add a `[[playlist]]` or `[[collection]]` entry pointing at it, and run `check`.

## Freezing an MDBList or Trakt list

The file icon in a list window saves what an MDBList or Trakt list holds today as a list file of your own, to freeze it and edit it by hand. It can switch the entry to that file, so it stops following the list and changes only when you edit it.

---

[← Previous: Collections and playlists](collections-and-playlists.md) · [User guide](README.md) · [Next: Sources and artwork →](sources-and-artwork.md)
