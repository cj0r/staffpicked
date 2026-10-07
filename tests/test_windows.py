"""Season windows: when a collection or playlist is on the server."""
import datetime, unittest
from scripts.util import ConfigError, is_active, parse_window

D = datetime.date


class SeasonWindows(unittest.TestCase):
    def test_no_window_is_all_year(self):
        self.assertIsNone(parse_window(""))
        self.assertTrue(is_active("", D(2026, 3, 1)))
        self.assertTrue(is_active(None, D(2026, 3, 1)))

    def test_yearly_window(self):
        w = "09-25 to 10-31"
        self.assertEqual(parse_window(w), [(None, 9, 25), (None, 10, 31)])
        self.assertTrue(is_active(w, D(2026, 9, 25)))       # first day counts
        self.assertTrue(is_active(w, D(2026, 10, 31)))      # last day counts
        self.assertTrue(is_active(w, D(2031, 10, 3)))       # any year
        self.assertFalse(is_active(w, D(2026, 9, 24)))
        self.assertFalse(is_active(w, D(2026, 11, 1)))

    def test_window_that_wraps_the_new_year(self):
        w = "11-30 to 01-01"
        self.assertTrue(is_active(w, D(2026, 11, 30)))
        self.assertTrue(is_active(w, D(2026, 12, 31)))
        self.assertTrue(is_active(w, D(2027, 1, 1)))
        self.assertFalse(is_active(w, D(2027, 1, 2)))
        self.assertFalse(is_active(w, D(2026, 11, 29)))

    def test_one_time_window(self):
        w = "2026-09-30 to 2026-11-02"
        self.assertTrue(is_active(w, D(2026, 10, 15)))
        self.assertFalse(is_active(w, D(2027, 10, 15)))     # only that year
        self.assertFalse(is_active(w, D(2026, 11, 3)))

    def test_leap_day(self):
        self.assertEqual(parse_window("02-29 to 03-01"), [(None, 2, 29), (None, 3, 1)])
        self.assertTrue(is_active("02-29 to 03-01", D(2028, 2, 29)))
        self.assertTrue(is_active("02-20 to 02-29", D(2027, 2, 28)))   # a non-leap year still works
        self.assertFalse(is_active("02-29 to 03-01", D(2027, 2, 28)))
        with self.assertRaises(ConfigError):
            parse_window("2027-02-29 to 2027-03-01")         # not a real date that year

    def test_single_digit_and_spacing(self):
        self.assertEqual(parse_window("  9-5   to 10-1 "), [(None, 9, 5), (None, 10, 1)])

    def test_mistakes_are_config_errors(self):
        for bad in ("09-25", "09-25 - 10-31", "13-01 to 10-31", "02-30 to 03-01", "2026-09-25 to 10-31", "soon to later"):
            with self.subTest(bad=bad), self.assertRaises(ConfigError):
                parse_window(bad)


if __name__ == "__main__":
    unittest.main()
