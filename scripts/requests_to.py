"""Where a missing film or show is requested, and what each one's request state is.

REQUEST_SERVICE in staffpicked.env picks the service:
  seerr   Seerr for films and shows alike (the default)
  arr     Radarr for films, Sonarr for shows

A title on a list but not in the library is "requested" once the service has it (asked for,
waiting, or monitored but not downloaded yet), "available" once the service has downloaded it
(the media server just hasn't shown it yet), and "missing" when no service has it at all."""
from .arr import Radarr, Sonarr
from .seerr import Seerr
from .util import ServiceError, describe   # describe: the web server words errors with it

SERVICES = ("seerr", "arr")
CLIENTS = {"seerr": Seerr, "radarr": Radarr, "sonarr": Sonarr}


def service(env):
    v = (env.get("REQUEST_SERVICE") or "").strip().lower()
    return v if v in SERVICES else "seerr"


def setup(env):
    """{service, movies, shows}: which service is picked and whether films and shows can be
    requested with the settings saved (a URL and API key for the service each goes to)."""
    def ready(p):
        return bool((env.get(f"{p}_URL") or "").strip() and (env.get(f"{p}_API_KEY") or "").strip())
    which = service(env)
    if which == "seerr":
        return {"service": which, "movies": ready("SEERR"), "shows": ready("SEERR")}
    return {"service": which, "movies": ready("RADARR"), "shows": ready("SONARR")}


def client(env, show):
    """The service a film (show=False) or show (show=True) is requested from."""
    if service(env) == "seerr":
        return Seerr(env)
    return Sonarr(env) if show else Radarr(env)


def states(env, items):
    """{imdb: requested | available | missing} for [(imdb, show)], plus {kind: error} for a service
    that couldn't be asked. Titles a service can't answer for are left out."""
    out, errors = {}, {}
    if service(env) == "seerr":
        groups = {"seerr": items}
    else:
        groups = {"radarr": [i for i in items if not i[1]], "sonarr": [i for i in items if i[1]]}
    for name, group in groups.items():
        if not group:
            continue
        try:
            c = CLIENTS[name](env)
            out.update(c.states(group) if name == "seerr" else c.states([i for i, _ in group]))
        except ServiceError as e:
            errors[name] = str(e)
    return out, errors


def add(env, imdb, show):
    c = client(env, show)
    out = c.add(imdb, show) if isinstance(c, Seerr) else c.add(imdb)
    out["service"] = c.NAME
    return out
