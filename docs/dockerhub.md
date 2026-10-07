# StaffPicked

Emby and Jellyfin collections and playlists from MDBList lists, Trakt lists and your own Markdown lists, with artwork from TMDB, fanart.tv, MediUX or your own files. Emby and Jellyfin are supported equally, and one container can serve both at once. Named for the staff picks shelf at the old video store.

- Collections and playlists that stay in sync on a schedule, on one server or several.
- Seasonal date windows, so a list shows up only while it's in season.
- Playlists in list order that drop what you've watched.
- Your own artwork on collections, playlists and genres.
- A web UI for setup, syncs, dry runs, logs and editing lists, with password and two-factor sign-in.

## Quick start

```yaml
services:
  staffpicked:
    image: cj0r/staffpicked:latest
    container_name: staffpicked
    restart: unless-stopped
    ports:
      - "9343:9343"
    security_opt:
      - no-new-privileges:true
    environment:
      - TZ=Etc/UTC          # your time zone, for the sync schedule
    volumes:
      - ./config:/config
```

Run `docker compose up -d`, open `http://<host>:9343` and the setup screen walks you through connecting your media server. Images are built for `linux/amd64` and `linux/arm64`.

## Tags

- `latest`: the newest release.
- `1`, `1.0`, `1.0.0`: a major, minor or exact release, to update on your own terms.

## More

Full guide, settings reference and source: https://github.com/cj0r/staffpicked. License: GPL-3.0.
