import unittest

from app.drivers.adapters.goios_adapter import _build_runwda_command


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


if __name__ == "__main__":
    unittest.main()
