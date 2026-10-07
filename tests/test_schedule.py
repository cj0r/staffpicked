"""The sync schedule: several daily SYNC_TIMEs, or SYNC_EVERY as an interval between syncs."""
import datetime, unittest
from scripts import settings
from scripts.util import ConfigError

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 10, 4, 10, 30, tzinfo=UTC)


class Schedule(unittest.TestCase):
    def test_times_list(self):
        self.assertEqual(settings.sync_times("18:00, 6:00,18:00"), ["06:00", "18:00"])
        self.assertEqual(settings.sync_times(""), [])
        with self.assertRaises(ConfigError):
            settings.sync_times("06:00, 25:00")

    def test_every(self):
        self.assertEqual(settings.sync_every("6h"), 360)
        self.assertEqual(settings.sync_every("1h30m"), 90)
        self.assertEqual(settings.sync_every("45M"), 45)
        self.assertIsNone(settings.sync_every(" "))
        for bad in ("6", "10m", "0h", "h", "6 days"):
            with self.subTest(bad=bad), self.assertRaises(ConfigError):
                settings.sync_every(bad)

    def test_next_of_several_times(self):
        env = {"SYNC_TIME": "06:00, 12:00, 18:00"}
        self.assertEqual(settings.next_sync(env, NOW), NOW.replace(hour=12, minute=0))
        late = NOW.replace(hour=19)
        self.assertEqual(settings.next_sync(env, late), datetime.datetime(2026, 10, 5, 6, 0, tzinfo=UTC))

    def test_old_single_time_still_works(self):
        self.assertEqual(settings.next_sync({"SYNC_TIME": "06:00"}, NOW), datetime.datetime(2026, 10, 5, 6, 0, tzinfo=UTC))
        self.assertEqual(settings.next_sync({}, NOW), datetime.datetime(2026, 10, 5, 6, 0, tzinfo=UTC))

    def test_interval_counts_from_the_last_sync(self):
        env = {"SYNC_TIME": "06:00", "SYNC_EVERY": "2h"}
        last = NOW - datetime.timedelta(minutes=30)
        self.assertEqual(settings.next_sync(env, NOW, last), NOW + datetime.timedelta(minutes=90))
        self.assertEqual(settings.next_sync(env, NOW), NOW + datetime.timedelta(hours=2))
        long_ago = NOW - datetime.timedelta(hours=5)       # shortened since: due now
        self.assertEqual(settings.next_sync(env, NOW, long_ago), NOW)

    def test_bad_settings_fall_back_to_daily_six(self):
        for env in ({"SYNC_TIME": "noon"}, {"SYNC_EVERY": "5m"}):
            with self.subTest(env=env):
                kind, value, problem = settings.sync_schedule(env)
                self.assertEqual((kind, value), ("times", ["06:00"]))
                self.assertIn("06:00", problem)

    def test_described(self):
        self.assertEqual(settings.describe_schedule({"SYNC_EVERY": "90m"}), "Every 1 hour 30 minutes")
        self.assertEqual(settings.describe_schedule({"SYNC_TIME": "18:00,06:00"}), "Daily at 06:00 and 18:00")
        self.assertEqual(settings.describe_schedule({}), "Daily at 06:00")


if __name__ == "__main__":
    unittest.main()
