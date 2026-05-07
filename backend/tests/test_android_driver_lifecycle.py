import unittest

from app.drivers.android import AndroidDriver
from app.drivers.base import ControlEvent, MirrorOptions


class FailingScrcpyManager:
    def __init__(self, serial):
        self.serial = serial
        self.running = False
        self.stop_calls = 0

    async def start(self, max_size=0, max_fps=30, bitrate=8_000_000):
        del max_size, max_fps, bitrate
        raise RuntimeError("scrcpy start failed")

    async def stop(self):
        self.stop_calls += 1


class AndroidDriverLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_failure_resets_partial_scrcpy_manager(self):
        driver = AndroidDriver("device-1")
        import app.drivers.android as android_module

        original_manager = android_module.ScrcpyServerManager
        android_module.ScrcpyServerManager = FailingScrcpyManager
        try:
            with self.assertRaises(RuntimeError):
                await driver.start_mirroring(MirrorOptions())
        finally:
            android_module.ScrcpyServerManager = original_manager

        self.assertIsNone(driver._server_manager)
        self.assertFalse(driver.is_mirroring)

    async def test_back_keyevent_uses_back_or_screen_on_encoding(self):
        driver = AndroidDriver("device-1")
        event = ControlEvent(action="keyevent", params={"key": "back"})

        encoded = driver._encode_event(event)

        self.assertEqual(len(encoded), 4)


if __name__ == "__main__":
    unittest.main()
