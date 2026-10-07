"""The web UI's sign-in and network safety: two-factor codes, the local-network rule without a
password, trusted reverse proxies, URL_BASE, and the headers every answer carries."""
import json, os, subprocess, sys, time, unittest, urllib.error, urllib.request
from email.message import Message
from tests.helpers import ROOT, clean_env, config_dir
from tests.test_web import free_port

sys.path.insert(0, os.path.join(ROOT, "web"))
import security  # noqa: E402


def headers(**kv):
    m = Message()
    for k, v in kv.items():
        m[k.replace("_", "-")] = v
    return m


class Helpers(unittest.TestCase):
    def test_totp_matches_rfc_6238(self):
        # RFC 6238 appendix B, SHA-1, 8 digits there; the last 6 of them here
        secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"      # "12345678901234567890"
        for at, code in ((59, "287082"), (1111111109, "081804"), (1234567890, "005924"), (2000000000, "279037")):
            with self.subTest(at=at):
                self.assertEqual(security.totp_now(secret, at), code)

    def test_totp_window_and_reuse(self):
        secret = security.new_totp_secret()
        now = 1_800_000_000
        step = security.totp_check(secret, security.totp_now(secret, now), at=now)
        self.assertIsNotNone(step)
        self.assertIsNotNone(security.totp_check(secret, security.totp_now(secret, now - 30), at=now))
        self.assertIsNone(security.totp_check(secret, security.totp_now(secret, now - 90), at=now))
        self.assertIsNone(security.totp_check(secret, security.totp_now(secret, now), last_step=step, at=now))
        self.assertIsNone(security.totp_check(secret, "12345", at=now))

    def test_recovery_codes_work_once(self):
        codes, hashes = security.new_recovery_codes()
        self.assertEqual(len(set(codes)), 10)
        left = security.recovery_use(codes[3].upper().replace("-", " "), hashes)
        self.assertEqual(len(left), 9)
        self.assertIsNone(security.recovery_use(codes[3], left))
        self.assertIsNone(security.recovery_use("nope-nope", hashes))

    def test_password_hash_rounds(self):
        old = security.hash_password("correct horse", rounds=security.OLD_ROUNDS)
        del old["rounds"]                              # as saved before rounds were stored
        self.assertTrue(security.password_matches("correct horse", old))
        self.assertFalse(security.password_matches("wrong", old))
        self.assertEqual(security.hash_password("x")["rounds"], security.PBKDF2_ROUNDS)

    def test_client_behind_trusted_proxy(self):
        trusted, bad = security.parse_networks("172.18.0.0/16, 10.0.0.2 nonsense")
        self.assertEqual(bad, ["nonsense"])
        h = headers(X_Forwarded_For="6.6.6.6, 203.0.113.7, 172.18.0.5", X_Forwarded_Proto="https")
        self.assertEqual(security.client("172.18.0.9", h, trusted), ("203.0.113.7", True, True))
        # the same headers from anyone else are ignored, but still mark the request as proxied
        self.assertEqual(security.client("192.168.1.20", h, trusted), ("192.168.1.20", False, True))
        self.assertEqual(security.client("192.168.1.20", headers(), trusted), ("192.168.1.20", False, False))

    def test_local_addresses_and_names(self):
        for ip in ("127.0.0.1", "192.168.1.5", "10.1.2.3", "172.17.0.1", "100.101.102.103", "::1", "fd00::5"):
            self.assertTrue(security.local_address(ip), ip)
        for ip in ("8.8.8.8", "1.1.1.1", "2001:4860::8888"):
            self.assertFalse(security.local_address(ip), ip)
        for host in ("192.168.1.5:9343", "tower:9343", "localhost", "nas.local", "media.home.arpa", "[::1]:9343"):
            self.assertTrue(security.local_host(host), host)
        for host in ("evil.example.com:9343", "staffpicked.example.com", ""):
            self.assertFalse(security.local_host(host), host)

    def test_url_base(self):
        self.assertEqual(security.clean_base("staffpicked/"), "/staffpicked")
        self.assertEqual(security.clean_base("/"), "")
        self.assertIsNone(security.clean_base("/../etc"))
        self.assertIsNone(security.clean_base("/a b"))


class Server(unittest.TestCase):
    ENV = {}
    PASSWORD = None

    def setUp(self):
        self.base = config_dir("http://127.0.0.1:9", **{"collections.toml": "", "playlists.toml": "", "genres.toml": ""})
        if self.ENV:
            with open(os.path.join(self.base, "staffpicked.env"), "a") as f:
                f.writelines(f"{k}={v}\n" for k, v in self.ENV.items())
        if self.PASSWORD:
            os.makedirs(os.path.join(self.base, "web"))
            with open(os.path.join(self.base, "web", "web.json"), "w") as f:
                json.dump({"auth": security.hash_password(self.PASSWORD)}, f)
        self.port = free_port()
        self.cookie = ""
        self.proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "web", "server.py")], cwd=ROOT,
                                     env=clean_env(STAFFPICKED_CONFIG=self.base, PORT=str(self.port), TZ="UTC",
                                                   STAFFPICKED_DEFAULTS=os.path.join(ROOT, "config")),
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.stop)
        for _ in range(100):
            try:
                self.call("GET", "/api/health")
                return
            except OSError:
                time.sleep(0.1)

    def stop(self):
        self.proc.terminate()
        self.proc.wait(timeout=10)

    def raw(self, method, path, body=None, **extra):
        h = {"Content-Type": "application/json"} if body is not None else {}
        if self.cookie:
            h["Cookie"] = self.cookie
        h.update({k.replace("_", "-"): v for k, v in extra.items()})
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method=method, headers=h,
                                     data=None if body is None else json.dumps(body).encode())

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a):
                return None
        try:
            r = urllib.request.build_opener(NoRedirect).open(req, timeout=20)
        except urllib.error.HTTPError as e:
            r = e
        with r:
            data = r.read()
            set_cookie = r.headers.get("Set-Cookie") or ""
            if set_cookie.startswith("session=") and "Max-Age=0" not in set_cookie:
                self.cookie = set_cookie.split(";")[0]
            return r.status, r.headers, data

    def call(self, method, path, body=None, **extra):
        code, _, data = self.raw(method, path, body, **extra)
        return code, json.loads(data or b"{}")

    def web_json(self):
        with open(os.path.join(self.base, "web", "web.json")) as f:
            return json.load(f)


class Access(Server):
    def test_without_a_password_only_the_local_network_gets_in(self):
        self.assertEqual(self.call("GET", "/api/status")[0], 200)
        # a public name pointed at this machine (DNS rebinding), a proxy, or a stranger: no
        for extra in ({"Host": "evil.example.com:9343"}, {"X_Forwarded_For": "203.0.113.7"}):
            with self.subTest(**extra):
                code, body = self.call("GET", "/api/status", **extra)
                self.assertEqual(code, 403)
                self.assertIn("password", body["error"])
                self.assertEqual(self.raw("GET", "/", **extra)[0], 403)
        self.assertEqual(self.call("GET", "/api/health", Host="evil.example.com")[0], 200)
        # a password lifts it: then a sign-in decides
        self.assertEqual(self.call("PUT", "/api/password", {"new": "correct horse"})[0], 200)
        self.assertEqual(self.call("GET", "/api/status", Host="staffpicked.example.com")[0], 200)

    def test_headers_and_cross_site_requests(self):
        code, h, _ = self.raw("GET", "/")
        self.assertEqual(code, 200)
        self.assertEqual(h["X-Frame-Options"], "DENY")
        self.assertIn("frame-ancestors 'none'", h["Content-Security-Policy"])
        self.assertEqual(h["Server"], "StaffPicked")
        code, _ = self.call("PUT", "/api/settings", {"env": {}}, Sec_Fetch_Site="cross-site")
        self.assertEqual(code, 403)
        self.assertEqual(self.call("PUT", "/api/settings", {"env": {}}, Sec_Fetch_Site="same-origin")[0], 200)
        self.assertEqual(self.call("POST", "/api/logout", {}, Content_Length="-1")[0], 400)

    def test_two_factor_sign_in(self):
        self.call("PUT", "/api/password", {"new": "correct horse"})
        code, r = self.call("POST", "/api/mfa/setup", {"current": "wrong"})
        self.assertEqual(code, 403)
        code, r = self.call("POST", "/api/mfa/setup", {"current": "correct horse"})
        self.assertEqual(code, 200)
        self.assertTrue(r["uri"].startswith("otpauth://totp/StaffPicked"))
        secret = r["secret"]
        self.assertEqual(self.call("POST", "/api/mfa/enable", {"code": "000000"})[0], 400)
        code, r = self.call("POST", "/api/mfa/enable", {"code": security.totp_now(secret)})
        self.assertEqual(code, 200)
        recovery = r["recovery_codes"]
        self.assertEqual(len(recovery), 10)
        saved = json.dumps(self.web_json())
        self.assertNotIn(recovery[0], saved)                   # only hashes are kept
        self.assertEqual(self.call("GET", "/api/mfa")[1]["recovery_left"], 10)

        self.cookie = ""
        code, r = self.call("POST", "/api/login", {"password": "correct horse"})
        self.assertEqual((code, r.get("mfa")), (401, True))
        self.assertFalse(self.cookie)
        # the code just used to turn it on can't be used again
        self.assertEqual(self.call("POST", "/api/login", {"password": "correct horse", "code": security.totp_now(secret)})[0], 401)
        self.assertEqual(self.call("POST", "/api/login", {"password": "correct horse", "code": recovery[0]})[0], 200)
        self.assertTrue(self.cookie)
        self.assertEqual(self.call("GET", "/api/mfa")[1]["recovery_left"], 9)
        self.assertEqual(self.call("PUT", "/api/password", {"current": "correct horse", "new": "battery staple"})[0], 403)

        self.cookie = ""
        self.assertEqual(self.call("POST", "/api/login", {"password": "correct horse", "code": recovery[0]})[0], 401)
        self.assertEqual(self.call("GET", "/api/status")[0], 401)

    def test_too_many_wrong_passwords(self):
        self.call("PUT", "/api/password", {"new": "correct horse"})
        self.cookie = ""
        codes = [self.call("POST", "/api/login", {"password": "nope"})[0] for _ in range(6)]
        self.assertEqual(codes, [401] * 5 + [429])
        self.assertEqual(self.call("POST", "/api/login", {"password": "correct horse"})[0], 429)

    def test_reset_login(self):
        self.call("PUT", "/api/password", {"new": "correct horse"})
        out = subprocess.run([sys.executable, os.path.join(ROOT, "web", "server.py"), "reset-login"], cwd=ROOT,
                             env=clean_env(STAFFPICKED_CONFIG=self.base), capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        web = self.web_json()
        self.assertEqual((web["auth"], web["sessions"]), ({}, {}))


    def test_settings_check_the_proxy_values(self):
        self.assertEqual(self.call("PUT", "/api/settings", {"env": {"TRUSTED_PROXIES": "10.0.0.0/8, bogus"}})[0], 400)
        self.assertEqual(self.call("PUT", "/api/settings", {"env": {"URL_BASE": "/../x"}})[0], 400)
        self.assertEqual(self.call("PUT", "/api/settings", {"env": {"TRUSTED_PROXIES": "10.0.0.1/8 172.18.0.2",
                                                                       "URL_BASE": "sp/"}})[0], 200)
        with open(os.path.join(self.base, "staffpicked.env")) as f:
            text = f.read()
        self.assertIn("TRUSTED_PROXIES=10.0.0.0/8, 172.18.0.2\n", text)
        self.assertIn("URL_BASE=/sp\n", text)



class Proxy(Server):
    ENV = {"TRUSTED_PROXIES": "127.0.0.1", "URL_BASE": "/staffpicked"}
    PASSWORD = "correct horse"

    def test_behind_a_proxy_under_a_path(self):
        code, h, _ = self.raw("GET", "/staffpicked")
        self.assertEqual((code, h["Location"]), (301, "/staffpicked/"))
        # prefix passed on or stripped by the proxy: both are the same page
        self.assertEqual(self.raw("GET", "/staffpicked/")[:1], (302,))
        self.assertEqual(self.raw("GET", "/")[1]["Location"], "login.html")
        _, h, _ = self.raw("POST", "/staffpicked/api/login", {"password": "correct horse"},
                           X_Forwarded_For="203.0.113.7", X_Forwarded_Proto="https")
        self.assertIn("; Secure", h["Set-Cookie"])
        self.assertEqual(self.call("GET", "/staffpicked/api/status")[0], 200)
        # wrong passwords count against the browser's address, not the proxy's
        self.cookie = ""
        for _ in range(5):
            self.call("POST", "/api/login", {"password": "nope"}, X_Forwarded_For="203.0.113.66")
        self.assertEqual(self.call("POST", "/api/login", {"password": "nope"}, X_Forwarded_For="203.0.113.66")[0], 429)
        self.assertEqual(self.call("POST", "/api/login", {"password": "correct horse"}, X_Forwarded_For="203.0.113.8")[0], 200)

if __name__ == "__main__":
    unittest.main()
