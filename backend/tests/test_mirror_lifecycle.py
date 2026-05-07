import asyncio
import unittest

from fastapi import HTTPException

from app.api import mirror
from app.models.device import DeviceInfo


class FakeDriver:
    def __init__(self, device_id="device-1", start_error=None, stop_error=None):
        self.device_id = device_id
        self.start_error = start_error
        self.stop_error = stop_error
        self.is_mirroring = False
        self.screen_size = (0, 0)
        self.stop_calls = 0

    async def start_mirroring(self, options):
        del options
        if self.start_error:
            self.is_mirroring = True
            raise self.start_error
        self.is_mirroring = True
        self.screen_size = (1080, 1920)
        return self.device_id

    async def stop_mirroring(self):
        self.stop_calls += 1
        if self.stop_error:
            raise self.stop_error
        self.is_mirroring = False


class MirrorLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        mirror._drivers.clear()
        self.original_devices = mirror.device_manager._devices
        mirror.device_manager._devices = {}

    async def asyncTearDown(self):
        mirror._drivers.clear()
        mirror.device_manager._devices = self.original_devices

    async def test_unknown_device_does_not_create_android_driver(self):
        with self.assertRaises(HTTPException) as ctx:
            mirror.get_driver("missing-device")

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(mirror._drivers, {})

    async def test_start_failure_stops_and_removes_partial_driver(self):
        device = DeviceInfo(id="device-1", name="Pixel", platform="android")
        mirror.device_manager._devices = {device.id: device}
        fake_driver = FakeDriver(start_error=RuntimeError("boom"))
        mirror._drivers[device.id] = fake_driver

        with self.assertRaises(HTTPException):
            await mirror.start_mirror(device.id)

        self.assertEqual(fake_driver.stop_calls, 1)
        self.assertNotIn(device.id, mirror._drivers)

    async def test_stop_failure_removes_driver_and_reports_error(self):
        fake_driver = FakeDriver(stop_error=RuntimeError("stop boom"))
        fake_driver.is_mirroring = True
        mirror._drivers[fake_driver.device_id] = fake_driver

        with self.assertRaises(HTTPException) as ctx:
            await mirror.stop_mirror(fake_driver.device_id)

        self.assertEqual(ctx.exception.status_code, 500)
        self.assertEqual(fake_driver.stop_calls, 1)
        self.assertNotIn(fake_driver.device_id, mirror._drivers)

    async def test_shutdown_all_drivers_stops_and_clears_every_driver(self):
        first = FakeDriver("one")
        second = FakeDriver("two", stop_error=RuntimeError("stop boom"))
        first.is_mirroring = True
        second.is_mirroring = True
        mirror._drivers.update({"one": first, "two": second})

        results = await mirror.shutdown_all_drivers()

        self.assertEqual(first.stop_calls, 1)
        self.assertEqual(second.stop_calls, 1)
        self.assertEqual(mirror._drivers, {})
        self.assertEqual([item["status"] for item in results], ["stopped", "error"])


if __name__ == "__main__":
    unittest.main()
