"""Telling you how the scheduled syncs went, through a webhook. Standard library only.

NOTIFY_URL in staffpicked.env is where the message goes; its shape follows the service:

  Discord   https://discord.com/api/webhooks/...         {"content": "..."}
  Slack     https://hooks.slack.com/services/...         {"text": "..."}
  Gotify    https://gotify.example/message?token=...     {"title", "message", "priority"}
  ntfy      https://ntfy.sh/your-topic                   the text itself, with a Title header
  other     any URL                                      {"title", "message", "text", "content"}

NOTIFY_ON is "failures" (the default: only runs with a problem) or "always"."""
import json, urllib.parse, urllib.request

LABELS = {"collections": "Collections", "playlists": "Playlists", "genres": "Genres"}
TRIGGERS = {"start": "Startup sync", "schedule": "Scheduled sync", "manual": "Sync", "test": "Test",
            "arrival": "New film sync", "setup": "First sync"}


def failed(runs):
    return any(r.get("status") != "ok" or (r.get("summary") or {}).get("errors") for r in runs)


def message(runs, trigger):
    """(title, one line) for a finished set of runs: [{job, status, summary, ...}]."""
    bad = failed(runs)
    title = f"StaffPicked: {TRIGGERS.get(trigger, 'Sync')} {'had problems' if bad else 'done'}"
    parts = []
    for r in runs:
        label = LABELS.get(r.get("job"), r.get("job", "?"))
        s = r.get("summary") or {}
        if r.get("status") == "aborted":
            parts.append(f"{label} stopped")
        elif r.get("status") != "ok" and not s:
            parts.append(f"{label} failed")
        else:
            bits = []
            if s.get("added"):
                bits.append(f"+{s['added']}")
            if s.get("removed"):
                bits.append(f"-{s['removed']}")
            if s.get("errors"):
                bits.append(f"{s['errors']} error{'s' if s['errors'] != 1 else ''}")
            failing = [n for n, v in (r.get("servers") or {}).items() if v != "ok"]
            if failing:
                bits.append("failed on " + ", ".join(failing))
            parts.append(f"{label} {', '.join(bits) if bits else 'no changes'}")
    return title, "; ".join(parts) or "nothing ran"


def wanted(env, runs, trigger):
    """Whether these runs call for a message under NOTIFY_ON. Runs you start yourself don't."""
    if not (env.get("NOTIFY_URL") or "").strip() or trigger == "manual" or not runs:
        return False
    return (env.get("NOTIFY_ON") or "failures").strip().lower() == "always" or failed(runs)


def request(url, title, text, failure=False):
    """The HTTP request that posts this message to url."""
    u = urllib.parse.urlsplit(url)
    host, path = u.netloc.lower(), u.path.rstrip("/")
    headers = {"User-Agent": "StaffPicked"}
    if host.endswith(("discord.com", "discordapp.com")) and "/webhooks/" in path:
        body = {"content": f"**{title}**\n{text}"}
    elif host == "hooks.slack.com":
        body = {"text": f"*{title}*\n{text}"}
    elif path.endswith("/message") and "token=" in u.query:
        body = {"title": title, "message": text, "priority": 8 if failure else 4}
    elif "ntfy" in host:
        headers.update({"Title": title.encode("utf-8").decode("latin-1", "replace"),
                        "Tags": "warning" if failure else "white_check_mark", "Content-Type": "text/plain; charset=utf-8"})
        return urllib.request.Request(url, data=text.encode(), headers=headers, method="POST")
    else:
        body = {"title": title, "message": text, "text": f"{title}: {text}", "content": f"{title}: {text}"}
    headers["Content-Type"] = "application/json"
    return urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")


def send(url, title, text, failure=False, timeout=15):
    """Post the message; raises on a bad URL or a reply that isn't 2xx."""
    if not urllib.parse.urlsplit(url).scheme in ("http", "https"):
        raise ValueError("The notification URL must start with http:// or https://")
    with urllib.request.urlopen(request(url, title, text, failure), timeout=timeout) as r:
        r.read()
