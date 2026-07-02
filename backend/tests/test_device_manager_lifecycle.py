import asyncio
import unittest

from app.core.device_manager import DeviceManager
from app.drivers.adapters.goios_adapter import GoIOSAdapter
from app.drivers.adapters.tidevice_adapter import TideviceAdapter
from app.models.device import DeviceInfo


class DeviceManagerStopTests(unittest.IsolatedAsyncioTestCase):
    async def test_stop_async_awaits_cancelled_poll_task(self):
        manager = DeviceManager()
        cancelled = False

        async def poll_forever():
            nonlocal cancelled
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                cancelled = True
                raise

        manager._poll_task = asyncio.create_task(poll_forever())
        await asyncio.sleep(0)

        await manager.stop_async()

        self.assertTrue(cancelled)
        self.assertIsNone(manager._poll_task)
        self.assertTrue(manager._subscribers == [])


class DeviceManagerIOSAdapterTests(unittest.TestCase):
    def test_known_low_ios_version_still_uses_tidevice(self):
        manager = DeviceManager()
        manager._goios_available = True
        manager._goios_bin = "ios.exe"
        manager._tidevice_available = True

        adapter = manager.create_ios_adapter("ios-15-device", "15.1")

        self.assertIsInstance(adapter, TideviceAdapter)

    def test_known_modern_ios_versions_use_goios(self):
        manager = DeviceManager()
        manager._goios_available = True
        manager._goios_bin = "ios.exe"
        manager._tidevice_available = True

        for version in ("16.7.8", "18.3", "26.2"):
            with self.subTest(version=version):
                adapter = manager.create_ios_adapter(f"ios-{version}", version)
                self.assertIsInstance(adapter, GoIOSAdapter)

    def test_unknown_version_without_goios_visibility_keeps_tidevice_fallback(self):
        manager = DeviceManager()
        manager._goios_available = True
        manager._goios_bin = "ios.exe"
        manager._tidevice_available = True
        manager._probe_goios_device_info = lambda udid: {}
        manager._probe_goios_device_seen = lambda udid: False

        adapter = manager.create_ios_adapter("unknown-ios-device")

        self.assertIsInstance(adapter, TideviceAdapter)

    def test_unknown_version_uses_goios_probe_before_adapter_selection(self):
        manager = DeviceManager()
        manager._goios_available = True
        manager._goios_bin = "ios.exe"
        manager._tidevice_available = True
        manager._devices = {
            "00008110-00112DA90E07801E": DeviceInfo(
                id="00008110-00112DA90E07801E",
                platform="ios",
                version="",
            )
        }
        manager._probe_goios_device_info = lambda udid: {
            "version": "26.2",
            "model": "iPhone14,3",
        }

        adapter = manager.create_ios_adapter("00008110-00112DA90E07801E")

        self.assertIsInstance(adapter, GoIOSAdapter)
        self.assertEqual(manager._devices["00008110-00112DA90E07801E"].version, "26.2")
        self.assertEqual(manager._devices["00008110-00112DA90E07801E"].model, "iPhone14,3")

    def test_unknown_version_prefers_goios_when_device_was_seen_by_goios(self):
        manager = DeviceManager()
        manager._goios_available = True
        manager._goios_bin = "ios.exe"
        manager._tidevice_available = True
        manager._goios_seen_udids = {"00008110-00112DA90E07801E"}
        manager._probe_goios_device_info = lambda udid: {}

        adapter = manager.create_ios_adapter("00008110-00112DA90E07801E")

        self.assertIsInstance(adapter, GoIOSAdapter)

    def test_unknown_version_prefers_goios_when_sync_list_sees_device(self):
        manager = DeviceManager()
        manager._goios_available = True
        manager._goios_bin = "ios.exe"
        manager._tidevice_available = True
        manager._probe_goios_device_info = lambda udid: {}
        manager._probe_goios_device_seen = lambda udid: True

        adapter = manager.create_ios_adapter("00008110-00112DA90E07801E")

        self.assertIsInstance(adapter, GoIOSAdapter)


if __name__ == "__main__":
    unittest.main()
