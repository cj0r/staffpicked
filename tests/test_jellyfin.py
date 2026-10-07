"""Where Jellyfin differs from Emby, checked against what Jellyfin 10.11 and 12.1 servers did."""
import base64, unittest
from scripts.importer import Importer
from scripts.playlist_sync import Owner, PlaylistSync
from scripts.server import Jellyfin


class Recording(Jellyfin):
    """A Jellyfin client that records each call instead of making it."""

    def __init__(self, answers=None):
        super().__init__("http://jf:8096", "key")
        self.calls, self.answers = [], answers or {}
        self.logins = []

    def call(self, method, path, token=None, **kw):
        self.calls.append((method, path, token, kw.get("params"), kw.get("json_body")))
        return self.answers.get((method, path))

    def login(self, name, password):
        self.logins.append((name, password))
        if password != "right":
            raise RuntimeError("401")
        return "owner-token"

    def logout(self, token):
        pass


class Log:
    dry_run, noting = False, True

    def __init__(self):
        self.lines = []

    def change(self, text):
        self.lines.append(text)

    warn = __call__ = change


class Server(unittest.TestCase):
    def test_a_playlist_is_made_public_or_private_as_asked(self):
        # Jellyfin makes a playlist public (every user sees it) unless told otherwise
        jf = Recording({("POST", "/Playlists"): {"Id": "p1"}})
        jf.create_playlist("u1", "Mine", ["a"])
        jf.create_playlist("u1", "Everyone's", ["a"], public=True)
        self.assertEqual([c[4]["IsPublic"] for c in jf.calls], [False, True])

    def test_sharing_switches_public_as_the_owner(self):
        jf = Recording()
        jf.share_playlist("owner-token", "p1", ["u2", "u3"])
        jf.unshare_playlist("owner-token", "p1")
        self.assertEqual([(c[0], c[1], c[2], c[4]) for c in jf.calls],
                         [("POST", "/Playlists/p1", "owner-token", {"IsPublic": True}),
                          ("POST", "/Playlists/p1", "owner-token", {"IsPublic": False})])

    def test_a_backdrop_replaces_the_one_in_its_spot(self):
        # Jellyfin adds every backdrop at the end, whatever index it's sent to
        jf = Recording({("GET", "/Items/c1/Images"): [{"ImageType": "Primary"}, {"ImageType": "Backdrop"},
                                                     {"ImageType": "Backdrop"}]})
        jf.set_image("c1", "Backdrop", 0, b"img", "image/jpeg")
        self.assertEqual([(c[0], c[1], c[3]) for c in jf.calls],
                         [("GET", "/Items/c1/Images", None),
                          ("DELETE", "/Items/c1/Images/Backdrop/0", None),
                          ("POST", "/Items/c1/Images/Backdrop", None),
                          ("POST", "/Items/c1/Images/Backdrop/1/Index", {"newIndex": 0})])

    def test_a_new_playlist_waits_for_jellyfins_own_poster(self):
        # Jellyfin covers a new playlist's poster with a collage a few seconds after making it
        jf = Recording()
        polls = iter([[], [], [{"ImageType": "Primary"}]])
        jf.call = lambda method, path, token=None, **kw: (jf.calls.append(path), next(polls))[1]
        jf.settle_new_playlist("p1", wait=1, step=0.01)
        self.assertEqual(jf.calls, ["/Items/p1/Images"] * 3)

    def test_a_new_last_backdrop_needs_no_move(self):
        jf = Recording({("GET", "/Items/c1/Images"): [{"ImageType": "Backdrop"}]})
        jf.set_image("c1", "Backdrop", 1, b"img", "image/jpeg")
        self.assertEqual([c[:2] for c in jf.calls], [("GET", "/Items/c1/Images"), ("POST", "/Items/c1/Images/Backdrop")])


class Playlists(unittest.TestCase):
    def sync(self, server):
        ps = PlaylistSync.__new__(PlaylistSync)
        ps.server, ps.log = server, Log()
        return ps

    def entries(self, order):
        return [(i, f"e-{i}") for i in order]

    def test_reordering_goes_as_the_signed_in_owner(self):
        jf = Recording()
        owner = Owner(jf, {"Id": "u1", "Name": "admin"}, "right")
        self.sync(jf).update(owner, "p1", self.entries("ba"), list("ab"))
        moves = [c for c in jf.calls if "/Move/" in c[1]]
        self.assertEqual([(c[1], c[2]) for c in moves], [("/Playlists/p1/Items/e-a/Move/0", "owner-token")])

    def test_without_the_owners_password_a_reorder_fails_so_the_playlist_is_built_again(self):
        jf = Recording()
        owner = Owner(jf, {"Id": "u1", "Name": "admin"}, "")
        with self.assertRaises(RuntimeError) as e:
            self.sync(jf).update(owner, "p1", self.entries("ba"), list("ab"))
        self.assertIn("only lets the owner reorder", str(e.exception))

    def test_a_person_with_their_own_playlists_is_never_signed_in_as(self):
        # StaffPicked has no PLAYLIST_USERS passwords; guessing could lock them out
        jf = Recording()
        owner = Owner(jf, {"Id": "u2", "Name": "kid"}, None)
        self.assertIsNone(owner.session())
        self.assertEqual(jf.logins, [])

    def test_an_unchanged_order_needs_no_sign_in(self):
        jf = Recording()
        owner = Owner(jf, {"Id": "u1", "Name": "admin"}, "")
        self.sync(jf).update(owner, "p1", self.entries("ab"), list("ab"))
        self.assertEqual(jf.logins, [])


class Import(unittest.TestCase):
    def test_an_imported_public_playlist_stays_public(self):
        jf = Recording({("GET", "/Users"): [{"Id": "u1", "Name": "admin", "Policy": {"IsAdministrator": True}}],
                        ("GET", "/Playlists/p1"): {"OpenAccess": True},
                        ("GET", "/Playlists/p2"): {"OpenAccess": False}})
        imp = Importer(jf, {"SERVER_PASSWORD": "right"}, "/nowhere")
        self.assertEqual((imp.public("p1"), imp.public("p2")), (True, False))

    def test_without_the_password_it_counts_as_private(self):
        jf = Recording({("GET", "/Users"): [{"Id": "u1", "Name": "admin", "Policy": {"IsAdministrator": True}}],
                        ("GET", "/Playlists/p1"): {"OpenAccess": True}})
        self.assertFalse(Importer(jf, {}, "/nowhere").public("p1"))


if __name__ == "__main__":
    unittest.main()
