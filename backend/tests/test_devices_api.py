import tempfile
import unittest

from fastapi import HTTPException

from app.api import devices as devices_api
from app.core.alias_manager import alias_manager
from app.models.device import DeviceInfo


class DeviceAliasApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original_devices = devices_api.device_manager._devices
        self.original_aliases = alias_manager._aliases.copy()
        self.original_config_path = alias_manager._config_path
        self.original_last_mtime = alias_manager._last_mtime
        self.temp_dir = tempfile.TemporaryDirectory()
        alias_manager.init(self.temp_dir.name)
        devices_api.device_manager._devices = {
            "device-1": DeviceInfo(id="device-1", platform="android", model="Pixel")
        }

    async def asyncTearDown(self):
        devices_api.device_manager._devices = self.original_devices
        alias_manager._aliases = self.original_aliases
        alias_manager._config_path = self.original_config_path
        alias_manager._last_mtime = self.original_last_mtime
        self.temp_dir.cleanup()

    async def test_update_device_alias_returns_updated_device(self):
        response = await devices_api.update_device_alias(
            "device-1",
            devices_api.DeviceAliasUpdate(alias=" QA Phone "),
        )

        self.assertEqual(response["device"]["alias"], "QA Phone")
        self.assertEqual(devices_api.device_manager._devices["device-1"].alias, "QA Phone")
        self.assertEqual(alias_manager.get_alias("device-1"), "QA Phone")

    async def test_clear_device_alias_returns_default_alias(self):
        await devices_api.update_device_alias(
            "device-1",
            devices_api.DeviceAliasUpdate(alias="QA Phone"),
        )

        response = await devices_api.clear_device_alias("device-1")

        self.assertEqual(response["device"]["alias"], "")
        self.assertEqual(alias_manager.get_alias("device-1"), "")

    async def test_update_unknown_device_returns_404(self):
        with self.assertRaises(HTTPException) as ctx:
            await devices_api.update_device_alias(
                "missing-device",
                devices_api.DeviceAliasUpdate(alias="QA Phone"),
            )

        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
