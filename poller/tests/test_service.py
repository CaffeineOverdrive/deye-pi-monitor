import unittest
from unittest import mock

from deye_monitor.config import Config
from deye_monitor.service import Poller


class FlakyReader:
    """Fails `fails` times, then answers."""
    def __init__(self, fails):
        self.fails = fails

    def read_raw(self):
        if self.fails:
            self.fails -= 1
            raise OSError("No socket available")
        return {}


class AvailabilityTest(unittest.TestCase):
    def poller_after(self, fails):
        p = Poller(Config())
        p._reader, p._mqtt = FlakyReader(fails), mock.Mock()
        with mock.patch("deye_monitor.service.decode", return_value={"pv_power": 1.0}):
            for _ in range(fails + 1):
                p._poll_once()
        return p

    def test_outage_marks_offline_then_online_again(self):
        p = self.poller_after(4)
        p._mqtt.mark_offline.assert_called_once()
        p._mqtt.mark_online.assert_called_once()
        self.assertEqual(p.failures, 0)

    def test_short_blip_changes_nothing(self):
        p = self.poller_after(2)
        p._mqtt.mark_offline.assert_not_called()
        p._mqtt.mark_online.assert_not_called()


if __name__ == "__main__":
    unittest.main()
