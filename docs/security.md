# Security

[← Previous: Command line](command-line.md) · [User guide](README.md) · [Next: Troubleshooting →](troubleshooting.md)

StaffPicked holds the API keys for your media servers and list services and can change what's on those servers, so treat it like the servers themselves. Set a password, don't forward its port to the internet, and reach it from outside your home only through a reverse proxy with HTTPS and two-factor sign-in, as described below.

## Sign-in

Set a password on the setup screen or in **Settings > Web Access**. Sign-ins last 30 days and survive restarts; only hashes of the password and of each sign-in are kept (`web/web.json`). Changing the password signs out every other browser. Five wrong tries from one address lock it out for five minutes, and each failed attempt is written to the container log with its address (`[auth] wrong password from 203.0.113.7`), so a tool like fail2ban can act on it.

**Without a password, the UI only opens for browsers on your local network** (a private LAN address, or a Tailscale-style `100.x` address) that connect to it directly, by its IP address or a local name like `tower` or `nas.local`. Anything coming in through a reverse proxy, a tunnel, or from the internet gets a page asking for a password to be set first. That keeps a forgotten port forward from exposing your API keys, and stops a hostile web page from reaching the UI through your browser (DNS rebinding).

## Two-factor sign-in

With a password set, **Settings > Two-Factor Sign-In > Set Up** adds a code from an authenticator app (Google or Microsoft Authenticator, 1Password, Bitwarden, Aegis, 2FAS and the like) to every sign-in. Scan the QR code (or type the key), enter the code it shows, and StaffPicked shows 10 recovery codes once: each one signs you in once without the app, so keep them in a password manager. Turning it on signs out every other browser. Turning it off, making new recovery codes and changing the password each ask for the password and a current code. Removing the password turns two-factor sign-in off too.

Lost the password, or the phone and the recovery codes? This takes both off and signs everyone out; then set them again in Settings from your local network (more in [Troubleshooting](troubleshooting.md#locked-out-of-the-web-ui)):

```bash
docker exec -it staffpicked staffpicked reset-login
```

## Reverse proxy

To reach StaffPicked from outside your home, put it behind a reverse proxy with HTTPS (Caddy, nginx, Nginx Proxy Manager, Traefik, SWAG, a Cloudflare tunnel and the like), set a password, and turn on two-factor sign-in. Then:

1. Set **Trusted proxies** (`TRUSTED_PROXIES`, in **Settings > Reverse Proxy**) to your proxy's address, or its Docker network's range (`docker network inspect <network>` shows it, e.g. `172.18.0.0/16`). Then StaffPicked takes the browser's real address from `X-Forwarded-For` (for the sign-in lockout and the log) and knows the browser used HTTPS from `X-Forwarded-Proto`, so the sign-in cookie is marked Secure. Requests from anywhere else can't set those headers.
2. To serve it under a path (`https://example.com/staffpicked/`) instead of its own name (`https://staffpicked.example.com`), set **URL base** (`URL_BASE`) to that path, `/staffpicked`. The proxy may pass the path on or strip it; both work.
3. Live logs and progress come over a long-lived event stream (`/api/events`), so the proxy mustn't buffer responses (StaffPicked sends `X-Accel-Buffering: no` for nginx) or close a connection that's quiet for a while (it sends a keep-alive every 15 seconds).
4. With only the proxy using it, publish the port on the host's loopback address alone, `"127.0.0.1:9343:9343"` in `docker-compose.yml`, or don't publish it at all and put the proxy on the same Docker network.

Caddy:

```
staffpicked.example.com {
    reverse_proxy staffpicked:9343
}
```

nginx, under a path (Caddy sends the forwarded headers by itself; nginx needs them spelled out):

```nginx
location /staffpicked/ {
    proxy_pass http://staffpicked:9343;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;
    proxy_read_timeout 1h;
}
```

with `URL_BASE=/staffpicked` and `TRUSTED_PROXIES` set to nginx's address. Traefik needs only its router and the trusted range; a `StripPrefix` middleware is optional with `URL_BASE`.

## Good to know

- Every page and API answer carries a strict Content-Security-Policy and no-framing, no-sniffing and no-referrer headers. Changes need a JSON body and a same-site sign-in cookie, and browsers that say a request comes from another site are turned away, so another site can't act through your browser.
- `staffpicked.env` and `web/web.json` are readable only by the container's user. **Download Config** holds every API key, password hash and the two-factor key, so keep that zip private.
- The logs hide every API key, token and password StaffPicked knows, and Settings never sends a saved secret back to the browser, only whether it's set.
- `docker-compose.yml` starts the container with `no-new-privileges`, and it drops root before StaffPicked itself starts.
- Keep it updated: `docker compose pull && docker compose up -d` brings the newest release, with the newest Python and Alpine fixes.

Report security problems privately, as [SECURITY.md](../SECURITY.md) describes, rather than in a public issue.

---

[← Previous: Command line](command-line.md) · [User guide](README.md) · [Next: Troubleshooting →](troubleshooting.md)
