"""MDBList scores for the list window, kept in cache/mdblist-scores.json so they're asked for
once, not every time a list is opened.

Films read from an MDBList list bring their score along for free. Films from list files and
Trakt lists are looked up in batches of 200 (one API request each), and only when they're
new to the cache or their score is more than MAX_AGE old. Films MDBList doesn't know are
remembered too, so they aren't asked about again until then either.

The file holds {imdb id: [score or null, unix time it was read]}."""
import json, os, time

from .util import request

FILE = os.path.join("cache", "mdblist-scores.json")
MAX_AGE = 7 * 24 * 3600     # scores move slowly; a week keeps them fresh for a few calls a list
BATCH = 200                 # the most MDBList answers in one lookup


def load(base_dir):
    try:
        with open(os.path.join(base_dir, FILE), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(base_dir, data):
    path = os.path.join(base_dir, FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    os.replace(tmp, path)


def scores(base_dir, api_key, imdbs, known=None, shows=()):
    """{imdb id: score} for imdbs. known holds scores already in hand ({imdb id: score}, from an
    MDBList list); they're stored and never looked up. shows are the IDs that are TV shows, which
    MDBList looks up separately. Without an API key, or if MDBList can't be reached, it answers
    from the cache alone."""
    data, now, changed = load(base_dir), time.time(), False
    for imdb, score in (known or {}).items():     # fresh from the list, so never stale
        old = data.get(imdb)
        if score is not None and (not isinstance(old, list) or old[0] != score or now - old[1] > MAX_AGE / 2):
            data[imdb], changed = [score, now], True
    stale = [i for i in dict.fromkeys(imdbs)
             if i and (i not in data or not isinstance(data[i], list) or now - data[i][1] > MAX_AGE)]
    shows = set(shows)
    batches = [(kind, ids[n:n + BATCH]) for kind, ids in (("movie", [i for i in stale if i not in shows]),
                                                         ("show", [i for i in stale if i in shows]))
               for n in range(0, len(ids) if api_key else 0, BATCH)]
    for kind, batch in batches:
        try:
            got = request("POST", f"https://api.mdblist.com/imdb/{kind}", {"apikey": api_key},
                          json_body={"ids": batch}) or []
        except Exception:
            break       # no scores this time; the list window still opens
        for it in got if isinstance(got, list) else []:
            imdb = str((it.get("ids") or {}).get("imdb") or "").lower()
            if imdb:
                data[imdb] = [it.get("score"), now]
        for imdb in batch:      # ones MDBList didn't answer for: don't ask again until MAX_AGE
            if imdb not in data or not isinstance(data[imdb], list) or data[imdb][1] != now:
                old = data.get(imdb)
                data[imdb] = [old[0] if isinstance(old, list) else None, now]
        changed = True
    if changed:
        try:
            save(base_dir, data)
        except OSError:
            pass
    return {i: data[i][0] for i in imdbs if i in data and isinstance(data[i], list) and data[i][0] is not None}
