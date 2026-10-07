"""Small helpers shared by every module: HTTP, dates, logging."""
import datetime, email.utils, json, re, sys, time, urllib.parse, urllib.request, urllib.error

from . import __version__

USER_AGENT = f"StaffPicked/{__version__}"  # some APIs reject Python's default agent
DATE = re.compile(r"^(?:(\d{4})-)?(\d{1,2})-(\d{1,2})$")
HTTPError, URLError = urllib.error.HTTPError, urllib.error.URLError


class ConfigError(Exception):
    """A setting is missing or malformed. The message says which and how to fix it."""


class ServiceError(Exception):
    """Seerr, Radarr or Sonarr can't take a request as set up. The message says why."""


def truthy(v):
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def http_error(e):
    try:
        body = e.read().decode("utf-8", "replace").strip()
    except Exception:
        body = ""
    return f"HTTP {e.code}" + (f": {body[:300]}" if body else "")


def title(item):
    """A server item as "Name (Year)", for lists of what changed."""
    if not item:
        return "an item no longer in the library"
    year = item.get("ProductionYear")
    return f"{item.get('Name', '?')} ({year})" if year else item.get("Name", "?")


def describe(e):
    """One line for any error a run can hit, without dumping a traceback."""
    if isinstance(e, HTTPError):
        return f"{http_error(e)} from {e.url.split('?')[0]}"
    return str(e) or e.__class__.__name__


# A busy service answers 429 (slow down) or a brief 5xx; a second or third try usually works.
RETRY_STATUS = {429, 500, 502, 503, 504}
RETRY_WAITS = (2, 6)       # seconds before the second and third tries, unless Retry-After says more
MAX_WAIT = 60              # longest Retry-After honored; anything longer fails now instead
SAFE_METHODS = ("GET", "HEAD", "DELETE")   # repeating these can't make a second copy of anything
sleep = time.sleep         # tests swap this out


def retry_after(e):
    """Seconds an HTTP error's Retry-After header asks for (a number or a date), or None."""
    value = (e.headers or {}).get("Retry-After") if getattr(e, "headers", None) is not None else None
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return int(value)
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0, round((when - datetime.datetime.now(datetime.timezone.utc)).total_seconds()))


def should_retry(method, e):
    """Whether a failed request is worth another try. A 429 was turned away before anything
    happened, so any method retries it; a 5xx or a dropped connection might have half-happened,
    so only requests that are safe to repeat retry those."""
    if isinstance(e, HTTPError):
        return e.code == 429 or (e.code in RETRY_STATUS and method in SAFE_METHODS)
    return isinstance(e, (URLError, TimeoutError, ConnectionError)) and method in SAFE_METHODS


def request(method, url, params=None, headers=None, data=None, content_type=None, json_body=None,
            raw=False, opener=None, timeout=120, retries=len(RETRY_WAITS)):
    """Make an HTTP request. Returns parsed JSON, or (bytes, content type) with raw=True.
    Rate limits and brief server errors are tried again (see should_retry), waiting a little
    longer each time, or as long as the service's Retry-After asks."""
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None})
    if json_body is not None:
        data, content_type = json.dumps(json_body).encode(), "application/json"
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, method=method, headers={
            "Accept": "*/*" if raw else "application/json", "User-Agent": USER_AGENT, **(headers or {})})
        if data is not None:
            req.data = data
            req.add_header("Content-Type", content_type)
        elif method == "POST":
            req.data = b""
        try:
            with (opener or urllib.request.build_opener()).open(req, timeout=timeout) as r:
                body = r.read()
                if raw:
                    return body, r.headers.get_content_type()
            return json.loads(body) if body else None
        except (HTTPError, URLError, TimeoutError, ConnectionError) as e:
            if attempt >= retries or not should_retry(method, e):
                raise
            wait = RETRY_WAITS[min(attempt, len(RETRY_WAITS) - 1)]
            asked = retry_after(e) if isinstance(e, HTTPError) else None
            if asked is not None:
                if asked > MAX_WAIT:
                    raise
                wait = max(wait, asked)
            why = f"HTTP {e.code}" if isinstance(e, HTTPError) else (str(getattr(e, "reason", "")) or e.__class__.__name__)
            print(f"  {why} from {urllib.parse.urlsplit(url).netloc}; trying again in {wait}s", flush=True)
            if isinstance(e, HTTPError):
                e.close()
            sleep(wait)


def parse_window(window):
    """Season window: "09-25 to 10-31" (yearly; may wrap the new year) or
    "2026-09-30 to 2026-11-02" (one time). Empty means always. Returns two
    (year or None, month, day) tuples, or None."""
    if not window:
        return None
    parts = [p.strip() for p in re.split(r"\s+to\s+", str(window).strip())]
    if len(parts) != 2:
        raise ConfigError(f"active = {window!r} must look like \"09-25 to 10-31\"")
    dates = []
    for p in parts:
        m = DATE.match(p)
        if not m:
            raise ConfigError(f"active date {p!r} must be MM-DD or YYYY-MM-DD")
        y, mo, d = m[1] and int(m[1]), int(m[2]), int(m[3])
        try:
            datetime.date(y or 2000, mo, d)    # 2000 is a leap year, so 02-29 passes
        except ValueError:
            raise ConfigError(f"active date {p!r} is not a real date")
        dates.append((y, mo, d))
    if bool(dates[0][0]) != bool(dates[1][0]):
        raise ConfigError(f"active = {window!r}: give a year on both dates or neither")
    return dates


def is_active(window, today):
    dates = parse_window(window)
    if not dates:
        return True
    (y1, m1, d1), (y2, m2, d2) = dates
    if y1:
        return datetime.date(y1, m1, d1) <= today <= datetime.date(y2, m2, d2)
    now, start, end = (today.month, today.day), (m1, d1), (m2, d2)
    return start <= now <= end if start <= end else (now >= start or now <= end)


class Brake:
    """Holds back a sync that would take most of a list off the server, which usually means
    something went wrong upstream (a list that came back empty, a library halfway through a
    rescan) rather than that the list really changed. REMOVAL_LIMIT is the share, in percent,
    a sync may take off a list (default 50; 0 turns the brake off), and only a loss of 3 films
    or more counts. --allow-removals lets one run through."""
    MIN = 3

    def __init__(self, env=None, allow=False):
        raw = str((env or {}).get("REMOVAL_LIMIT") or "50").strip().rstrip("%")
        try:
            self.limit = max(0, min(100, int(raw)))
        except ValueError:
            self.limit = 50
        self.allow = allow

    def check(self, removing, have):
        """Why removing this many of have films is held back, or None to go ahead."""
        if self.allow or not self.limit or self.limit >= 100 or removing < self.MIN or not have:
            return None
        if removing * 100 <= have * self.limit:
            return None
        return (f"Held back: this sync would take {removing} of its {have} films off the server, more than "
                f"the {self.limit}% removal limit, so nothing changed.")

    HINT = "If the list really shrank, use Sync Anyway in its list window, or run with --allow-removals."


class Log:
    def __init__(self, dry_run=False, out=sys.stdout):
        self.dry_run, self.out, self.problems = dry_run, out, 0
        self.added = self.removed = 0     # films put on or taken off the server (or that would be, in a dry run)
        self.last_error = ""
        self.entry = None        # what the current list changes, for its [diff] line
        self.noting = True       # False while a step's changes aren't worth listing (a playlist built again after a failed edit)

    def __call__(self, text=""):
        print(text, file=self.out, flush=True)

    def change(self, text):
        """A change to the server; marked as such in dry runs."""
        self(f"  {text}" + (" (dry run)" if self.dry_run else ""))
        if self.entry is not None and self.noting:
            self.entry["changes"].append(text)

    def begin(self, kind, name, server, person=""):
        """Start collecting what one list changes (or would change, in a dry run)."""
        self.end()
        self.entry = {"kind": kind, "name": name, "server": server, "person": person,
                      "added": [], "removed": [], "changes": []}
        self.noting = True

    def films(self, added, removed):
        """Titles put on or taken off the current list."""
        if self.entry is not None:
            self.entry["added"] += added
            self.entry["removed"] += removed

    def end(self):
        """The current list's changes as one line the web UI reads: [diff] {...}. Nothing when
        it changed nothing."""
        e, self.entry = self.entry, None
        self.noting = True
        if e and (e["added"] or e["removed"] or e["changes"]):
            self("[diff] " + json.dumps({**e, "dry_run": self.dry_run}))

    def warn(self, text):
        self(f"  WARNING: {text}")

    def error(self, text):
        self.problems += 1
        self.last_error = text
        self(f"  ERROR: {text}")

    def summary(self):
        """The run's outcome as one line the web UI reads: [summary] {"added": 3, ...}."""
        self.end()
        self("[summary] " + json.dumps({"added": self.added, "removed": self.removed, "errors": self.problems,
                                        "dry_run": self.dry_run}))
