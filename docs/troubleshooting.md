# Troubleshooting

[← Previous: Security](security.md) · [User guide](README.md)

## Locked out of the web UI

Lost password, lost authenticator, or a password that won't take. Run `reset-login` inside the container. It takes off the password and two-factor sign-in and signs every browser out; no restart needed. Then set a new password in **Settings > Web Access** from your local network.

- From a host shell: `docker exec -it staffpicked staffpicked reset-login`
- From a container console (Dockge, Portainer, Unraid's Docker tab and the like): `staffpicked reset-login`

## "Too many attempts. Try again in a few minutes."

Five wrong passwords or codes from one address lock it out for five minutes. Wait it out, or restart the container to clear it.

## Sent back to the sign-in page right after signing in

Clear the site's cookies for StaffPicked's address and sign in again. Browsers share cookies between apps on the same address (ports don't separate them), so another app on the same IP can overwrite StaffPicked's sign-in; opening StaffPicked by its own hostname avoids that.

## A page asks for a password to be set first

Without a password the UI only opens from your local network, by IP address or a local name (see [Sign-in](security.md#sign-in)). Open it that way and set a password; after that it opens through a reverse proxy too (see [Reverse proxy](security.md#reverse-proxy)).

## The container stops with "StaffPicked can't write to /config"

The config folder belongs to a different user than the one StaffPicked runs as. See [Permissions](getting-started.md#permissions).

## Edits in my compose manager's folder never reach StaffPicked

The manager runs in a container whose stacks folder has a different path inside and outside it, so Docker made a separate `config` folder. See [Compose managers](getting-started.md#compose-managers).

## Nothing syncs, or a server shows red

Open **Settings > Media Servers** and press **Test** on each server. The answer says what's wrong, such as an unreachable address or a rejected API key. Inside the container `localhost` is the container itself, so use the server's LAN address. **Check Config** (under **Config Files**, with Admin Mode enabled) lists any setting a sync would trip on.

## A film on the list never shows up in the collection

Open the list (click its row): every film is marked in the library or missing. A missing film has to be in your server's library first, and a title with no IMDb ID can't be matched.

## A sync changed nothing for a list and reported an error

It would have taken more than `REMOVAL_LIMIT` percent of the list off the server, so it was held back. Check that the list and the library look right, then use **Sync Anyway** in the list window. See [The safety brake](collections-and-playlists.md#the-safety-brake).

## A shared playlist isn't shared, or a Jellyfin playlist keeps being rebuilt

Sharing on Emby, and reordering or changing sharing on Jellyfin, need the owner's `SERVER_PASSWORD`. See the Sharing and Jellyfin notes under [playlists.toml](collections-and-playlists.md#playliststoml).

---

[← Previous: Security](security.md) · [User guide](README.md)
