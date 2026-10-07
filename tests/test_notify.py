"""Webhook notifications: when they go out, what they say, and the shape each service wants."""
import json, os, sys, unittest
from tests.helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "web"))
import notify  # noqa: E402

OK = {"job": "collections", "status": "ok", "summary": {"added": 3, "removed": 1, "errors": 0}, "servers": {"Emby": "ok"}}
BAD = {"job": "playlists", "status": "failed", "summary": {"added": 0, "removed": 0, "errors": 2},
       "servers": {"Emby": "ok", "Jellyfin": "failed"}}


class Notify(unittest.TestCase):
    def test_message(self):
        title, text = notify.message([OK, BAD], "schedule")
        self.assertEqual(title, "StaffPicked: Scheduled sync had problems")
        self.assertEqual(text, "Collections +3, -1; Playlists 2 errors, failed on Jellyfin")
        self.assertEqual(notify.message([OK], "start")[0], "StaffPicked: Startup sync done")
        self.assertEqual(notify.message([{"job": "genres", "status": "failed"}], "schedule")[1], "Genres failed")

    def test_when_it_goes_out(self):
        env = {"NOTIFY_URL": "https://example.com/hook"}
        self.assertTrue(notify.wanted(env, [OK, BAD], "schedule"))
        self.assertFalse(notify.wanted(env, [OK], "schedule"))               # failures only, by default
        self.assertTrue(notify.wanted({**env, "NOTIFY_ON": "always"}, [OK], "start"))
        self.assertFalse(notify.wanted({**env, "NOTIFY_ON": "always"}, [BAD], "manual"))   # you were watching
        self.assertFalse(notify.wanted({}, [BAD], "schedule"))

    def body(self, url, **kw):
        req = notify.request(url, "Title", "Text", **kw)
        return req, req.data.decode()

    def test_shapes(self):
        _, b = self.body("https://discord.com/api/webhooks/1/abc")
        self.assertEqual(json.loads(b), {"content": "**Title**\nText"})
        _, b = self.body("https://hooks.slack.com/services/x")
        self.assertEqual(json.loads(b), {"text": "*Title*\nText"})
        _, b = self.body("https://gotify.example/message?token=t", failure=True)
        self.assertEqual(json.loads(b), {"title": "Title", "message": "Text", "priority": 8})
        req, b = self.body("https://ntfy.sh/my-topic")
        self.assertEqual((b, req.get_header("Title")), ("Text", "Title"))
        _, b = self.body("https://example.com/hook")
        self.assertEqual(json.loads(b)["message"], "Text")

    def test_only_http(self):
        with self.assertRaises(ValueError):
            notify.send("file:///etc/passwd", "t", "x")


if __name__ == "__main__":
    unittest.main()
