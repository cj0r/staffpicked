"""HTTP requests try again after a rate limit or a brief server error."""
import json, threading, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from scripts import util


class Flaky:
    """A server that answers each path with the next of a list of (status, headers) and then 200."""

    def __init__(self, plan):
        self.plan, self.seen = plan, []
        flaky = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def answer(self):
                flaky.seen.append((self.command, self.path))
                todo = flaky.plan.get(self.path, [])
                code, headers = todo.pop(0) if todo else (200, {})
                body = json.dumps({"ok": code == 200}).encode()
                self.send_response(code)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = do_POST = answer

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class Retry(unittest.TestCase):
    def setUp(self):
        self.waits = []
        self._sleep, util.sleep = util.sleep, self.waits.append

    def tearDown(self):
        util.sleep = self._sleep

    def serve(self, plan):
        s = Flaky(plan)
        self.addCleanup(s.close)
        return s

    def test_rate_limit_then_ok(self):
        s = self.serve({"/a": [(429, {}), (503, {})]})
        self.assertEqual(util.request("GET", s.url + "/a"), {"ok": True})
        self.assertEqual(len(s.seen), 3)
        self.assertEqual(self.waits, list(util.RETRY_WAITS))

    def test_retry_after_is_honored(self):
        s = self.serve({"/a": [(429, {"Retry-After": "9"})]})
        util.request("GET", s.url + "/a")
        self.assertEqual(self.waits, [9])

    def test_retry_after_too_long_fails_now(self):
        s = self.serve({"/a": [(429, {"Retry-After": "3600"})]})
        with self.assertRaises(util.HTTPError) as e:
            util.request("GET", s.url + "/a")
        self.assertEqual(e.exception.code, 429)
        self.assertEqual(self.waits, [])

    def test_gives_up_after_the_last_try(self):
        s = self.serve({"/a": [(502, {})] * 5})
        with self.assertRaises(util.HTTPError) as e:
            util.request("GET", s.url + "/a")
        self.assertEqual(e.exception.code, 502)
        self.assertEqual(len(s.seen), len(util.RETRY_WAITS) + 1)

    def test_post_retries_a_rate_limit_but_not_a_server_error(self):
        s = self.serve({"/a": [(429, {})], "/b": [(500, {})]})
        self.assertEqual(util.request("POST", s.url + "/a"), {"ok": True})
        with self.assertRaises(util.HTTPError):
            util.request("POST", s.url + "/b")      # it may have half-happened; don't do it twice
        self.assertEqual([p for _, p in s.seen].count("/b"), 1)

    def test_other_errors_fail_at_once(self):
        s = self.serve({"/a": [(404, {})]})
        with self.assertRaises(util.HTTPError):
            util.request("GET", s.url + "/a")
        self.assertEqual(self.waits, [])

    def test_unreachable_server_is_tried_again(self):
        s = Flaky({})
        url = s.url
        s.close()      # nothing listens there now
        with self.assertRaises(util.URLError):
            util.request("GET", url + "/a", timeout=2)
        self.assertEqual(len(self.waits), len(util.RETRY_WAITS))

    def test_retries_can_be_turned_off(self):
        s = self.serve({"/a": [(429, {})]})
        with self.assertRaises(util.HTTPError):
            util.request("GET", s.url + "/a", retries=0)


if __name__ == "__main__":
    unittest.main()
