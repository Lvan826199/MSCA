import unittest

from app.drivers.base import MirrorOptions
from app.drivers.ios import IOSDriver


class FakeAdapter:
    def __init__(self):
        self.wda_info = None
        self.start_calls = 0
        self.stop_calls = 0

    async def start_wda(self, wda_port, mjpeg_port):
        del wda_port, mjpeg_port
        self.start_calls += 1

    async def stop_wda(self):
        self.stop_calls += 1


class IOSDriverLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_failure_when_wda_info_missing_stops_wda_and_does_not_mark_mirroring(self):
        adapter = FakeAdapter()
        driver = IOSDriver("device-1", adapter)

        with self.assertRaises(RuntimeError):
            await driver.start_mirroring(MirrorOptions())

        self.assertEqual(adapter.stop_calls, 1)
        self.assertIsNone(driver._http)
        self.assertFalse(driver.is_mirroring)


if __name__ == "__main__":
    unittest.main()
