import json
import unittest

from app.drivers.adapters.goios_adapter import GoIOSAdapter, _build_runwda_command


class GoIosRunwdaCommandTests(unittest.TestCase):
    def test_uses_go_ios_1_2_testrunner_bundle_flag(self):
        cmd = _build_runwda_command(
            "ios.exe",
            "device-1",
            "com.gamehausQaTest.WebDriverAgentRunner.xctrunner",
            "WebDriverAgentRunner.xctest",
        )

        self.assertIn("--bundleid=com.gamehausQaTest.WebDriverAgentRunner.xctrunner", cmd)
        self.assertIn("--testrunnerbundleid=com.gamehausQaTest.WebDriverAgentRunner.xctrunner", cmd)
        self.assertIn("--xctestconfig=WebDriverAgentRunner.xctest", cmd)
        self.assertNotIn("--testbundleid=com.gamehausQaTest.WebDriverAgentRunner.xctrunner", cmd)


class GoIosListDevicesTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_devices_hydrates_string_udids_with_info(self):
        class FakeGoIOSAdapter(GoIOSAdapter):
            async def _run_cmd(self, *args, timeout=30):
                del timeout
                if args == ("list", "--nojson"):
                    return "00008110-00112DA90E07801E"
                if args == ("list",):
                    return json.dumps({"deviceList": ["00008110-00112DA90E07801E"]})
                if args == ("info", "--udid=00008110-00112DA90E07801E"):
                    return json.dumps({
                        "UniqueDeviceID": "00008110-00112DA90E07801E",
                        "DeviceName": "iPhone",
                        "ProductVersion": "26.2",
                        "ProductType": "iPhone14,3",
                    })
                raise AssertionError(args)

        devices = await FakeGoIOSAdapter("").list_devices()

        self.assertEqual(devices, [{
            "udid": "00008110-00112DA90E07801E",
            "name": "iPhone",
            "version": "26.2",
            "model": "iPhone14,3",
        }])


if __name__ == "__main__":
    unittest.main()
