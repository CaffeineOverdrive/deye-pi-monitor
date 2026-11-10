import queue
import sys
import types
import unittest
from unittest import mock

from deye_monitor.reader import SolarmanReader


class NoSocketAvailableError(Exception):
    pass


class V5FrameError(Exception):
    pass


class FakeClient:
    """Stands in for PySolarmanV5: replays a script of replies and errors."""
    created = 0

    def __init__(self, *args, **kwargs):
        FakeClient.created += 1
        self.disconnected = False
        self._data_queue = queue.Queue(maxsize=1)

    def read_holding_registers(self, start, count):
        step = FakeClient.script.pop(0)
        if isinstance(step, BaseException):
            if isinstance(step, queue.Empty):
                self._data_queue.put_nowait(b"late reply")   # arrives after the timeout
            raise step
        return step

    def disconnect(self):
        self.disconnected = True


fake_module = types.SimpleNamespace(PySolarmanV5=FakeClient, NoSocketAvailableError=NoSocketAvailableError,
                                    V5FrameError=V5FrameError)


@mock.patch.dict(sys.modules, {"pysolarmanv5": fake_module})
@mock.patch("deye_monitor.reader.time.sleep", lambda s: None)
class SolarmanReaderTest(unittest.TestCase):
    def setUp(self):
        FakeClient.created = 0

    def reader(self, *script):
        FakeClient.script = list(script)
        return SolarmanReader("192.0.2.1", 1234)

    def test_lost_reply_is_retried_on_the_same_connection(self):
        r = self.reader(queue.Empty(), [7])
        self.assertEqual(r.read_block(0, 1), [7])
        self.assertEqual(FakeClient.created, 1)
        self.assertTrue(r.client._data_queue.empty())     # stale reply dropped

    def test_bad_frame_keeps_the_connection(self):
        r = self.reader(V5FrameError("bad sequence"), [1])
        self.assertEqual(r.read_block(0, 1), [1])
        self.assertEqual(FakeClient.created, 1)

    def test_broken_socket_reconnects(self):
        r = self.reader(NoSocketAvailableError("Connection closed on read"), [2])
        self.assertEqual(r.read_block(0, 1), [2])
        self.assertEqual(FakeClient.created, 2)

    def test_connection_kept_between_polls(self):
        r = self.reader([1], [2])
        r.read_block(0, 1)
        r.read_block(0, 1)
        self.assertEqual(FakeClient.created, 1)

    def test_all_attempts_silent_drops_the_connection(self):
        r = self.reader(queue.Empty(), queue.Empty(), queue.Empty(), [3])
        with self.assertRaises(IOError):
            r.read_block(0, 1)
        self.assertEqual(FakeClient.created, 1)
        self.assertIsNone(r.client)
        self.assertEqual(r.read_block(0, 1), [3])
        self.assertEqual(FakeClient.created, 2)


if __name__ == "__main__":
    unittest.main()
