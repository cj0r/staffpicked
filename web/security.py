"""Sign-in and network helpers for the web UI: authenticator-app codes (TOTP), recovery codes,
password hashing, and working out who a request really comes from behind a reverse proxy.
Standard library only."""
import base64, hashlib, hmac, ipaddress, re, secrets, struct, time, urllib.parse

# ---------------------------------------------------------------- passwords

PBKDF2_ROUNDS = 600_000      # OWASP's figure for PBKDF2-HMAC-SHA256
OLD_ROUNDS = 200_000         # hashes saved before "rounds" was stored


def hash_password(pw, salt=None, rounds=PBKDF2_ROUNDS):
    salt = salt or secrets.token_hex(16)
    return {"salt": salt, "rounds": rounds,
            "hash": hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), rounds).hex()}


def password_matches(pw, saved):
    """Whether pw matches a saved {"salt", "hash", "rounds"}."""
    if not saved.get("hash") or not saved.get("salt"):
        return False
    got = hash_password(pw, saved["salt"], int(saved.get("rounds") or OLD_ROUNDS))["hash"]
    return hmac.compare_digest(got, saved["hash"])


# ---------------------------------------------------------------- TOTP (RFC 6238)

TOTP_STEP = 30
TOTP_DIGITS = 6
ISSUER = "StaffPicked"


def new_totp_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret, step):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    mac = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    n = struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF
    return str(n % 10 ** TOTP_DIGITS).zfill(TOTP_DIGITS)


def totp_now(secret, at=None):
    return _code(secret, int((time.time() if at is None else at) // TOTP_STEP))


def totp_check(secret, code, last_step=None, at=None):
    """The time step code belongs to, or None. A code from the step before or after counts,
    so a clock a little off still works; a step at or before last_step was used already."""
    code = re.sub(r"\s", "", str(code or ""))
    if not re.fullmatch(r"\d{%d}" % TOTP_DIGITS, code):
        return None
    now = int((time.time() if at is None else at) // TOTP_STEP)
    for step in (now - 1, now, now + 1):
        if hmac.compare_digest(_code(secret, step), code) and (last_step is None or step > last_step):
            return step
    return None


def totp_uri(secret, account="admin"):
    label = urllib.parse.quote(f"{ISSUER}:{account}")
    return (f"otpauth://totp/{label}?secret={secret}&issuer={urllib.parse.quote(ISSUER)}"
            f"&algorithm=SHA1&digits={TOTP_DIGITS}&period={TOTP_STEP}")


# ---------------------------------------------------------------- recovery codes

RECOVERY_COUNT = 10
_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"     # no 0/o, 1/l/i to misread


def new_recovery_codes():
    """(codes to show once, their hashes to keep). Each code is used once."""
    codes = ["-".join("".join(secrets.choice(_ALPHABET) for _ in range(5)) for _ in range(2))
             for _ in range(RECOVERY_COUNT)]
    return codes, [recovery_hash(c) for c in codes]


def recovery_hash(code):
    # the codes are random, so a plain hash is enough; spaces, dashes and case don't matter
    return hashlib.sha256(re.sub(r"[\s-]", "", str(code)).lower().encode()).hexdigest()


def recovery_use(code, hashes):
    """hashes without code's, or None when code isn't one of them."""
    h = recovery_hash(code)
    for i, saved in enumerate(hashes or []):
        if hmac.compare_digest(h, saved):
            return hashes[:i] + hashes[i + 1:]
    return None


# ---------------------------------------------------------------- networks

def parse_networks(text):
    """TRUSTED_PROXIES: comma- or space-separated addresses and ranges (10.0.0.2, 172.16.0.0/12).
    Returns (networks, the entries that aren't one)."""
    nets, bad = [], []
    for part in re.split(r"[,\s]+", str(text or "").strip()):
        if not part:
            continue
        try:
            nets.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            bad.append(part)
    return nets, bad


def _ip(text):
    text = str(text or "").strip()
    if text.startswith("[") and "]" in text:            # [2001:db8::1]:443
        text = text[1:text.index("]")]
    elif text.count(":") == 1:                           # 1.2.3.4:5678
        text = text.split(":")[0]
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return None
    return ip.ipv4_mapped or ip if ip.version == 6 else ip


def in_networks(ip, nets):
    ip = _ip(ip) if not isinstance(ip, (ipaddress.IPv4Address, ipaddress.IPv6Address)) else ip
    return ip is not None and any(ip.version == n.version and ip in n for n in nets)


FORWARD_HEADERS = ("X-Forwarded-For", "X-Real-IP", "Forwarded", "CF-Connecting-IP", "True-Client-IP",
                   "X-Forwarded-Host", "X-Forwarded-Proto")


def client(peer, headers, trusted):
    """Who a request comes from: (client address, https?, came through a proxy?).
    X-Forwarded-For and X-Forwarded-Proto count only when the connection itself comes from
    one of the trusted proxies; then the client is the last address in X-Forwarded-For that
    isn't a trusted proxy too."""
    forwarded = any(headers.get(h) for h in FORWARD_HEADERS)
    if not in_networks(peer, trusted):
        return peer, False, forwarded
    ip = None
    hops = [h.strip() for h in ",".join(headers.get_all("X-Forwarded-For") or []).split(",") if h.strip()]
    for hop in reversed(hops):
        if not in_networks(hop, trusted):
            ip = _ip(hop)
            break
    if ip is None and headers.get("X-Real-IP"):
        ip = _ip(headers["X-Real-IP"])
    proto = (headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower()
    return (str(ip) if ip else peer), proto == "https", True


CGNAT = ipaddress.ip_network("100.64.0.0/10")    # Tailscale and other overlay networks


def local_address(ip):
    """Loopback, a private LAN range, link-local, or a Tailscale-style 100.64/10 address."""
    ip = _ip(ip)
    if ip is None:
        return False
    return ip.is_loopback or ip.is_private or ip.is_link_local or (ip.version == 4 and ip in CGNAT)


LOCAL_SUFFIXES = (".local", ".lan", ".home", ".home.arpa", ".internal", ".localdomain", ".localhost")


def local_host(host):
    """Whether a Host header names this machine the way a home network does: an IP address,
    localhost, a one-word name (tower), or a name under .local, .lan, .home.arpa and the like.
    Anything else could be a public name pointed at a LAN address by a hostile web page
    (DNS rebinding)."""
    host = str(host or "").strip().lower().rstrip(".")
    if host.startswith("["):
        host = host[1:host.find("]")] if "]" in host else host
    elif host.count(":") == 1:
        host = host.split(":")[0]
    if not host:
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    return host == "localhost" or "." not in host or host.endswith(LOCAL_SUFFIXES)


def clean_base(text):
    """URL_BASE as /path with no slash at the end; "" for none."""
    parts = [p for p in str(text or "").strip().split("/") if p]
    if any(not re.fullmatch(r"[A-Za-z0-9._~-]+", p) or p in (".", "..") for p in parts):
        return None
    return "/" + "/".join(parts) if parts else ""
