"""TIME_ZONE from Settings wins over the container's TZ, and a bad or blank one falls back."""
import os, time, unittest
from scripts import settings


class TimeZone(unittest.TestCase):
    def setUp(self):
        old = os.environ.get("TZ")
        self.addCleanup(lambda: (os.environ.__setitem__("TZ", old) if old else os.environ.pop("TZ", None), time.tzset()))
        self.addCleanup(setattr, settings, "CONTAINER_TZ", settings.CONTAINER_TZ)
        settings.CONTAINER_TZ = "UTC"

    def test_picked_one_is_used(self):
        self.assertEqual(settings.apply_time_zone({"TIME_ZONE": "America/Chicago"}), "America/Chicago")
        self.assertEqual(os.environ["TZ"], "America/Chicago")
        self.assertIn(time.strftime("%Z"), ("CST", "CDT"))

    def test_blank_or_unknown_means_the_containers(self):
        settings.apply_time_zone({"TIME_ZONE": "Europe/Paris"})
        self.assertEqual(settings.apply_time_zone({"TIME_ZONE": ""}), "UTC")
        self.assertEqual(settings.apply_time_zone({"TIME_ZONE": "Mars/Olympus"}), "UTC")
        self.assertFalse(settings.valid_time_zone("../../etc/passwd"))


if __name__ == "__main__":
    unittest.main()
