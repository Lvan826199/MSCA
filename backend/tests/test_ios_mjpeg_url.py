import unittest

from app.drivers.ios import IOSDriver


class FakeWDAInfo:
    host = "127.0.0.1"
    port = 8100
    mjpeg_port = 9100


class IOSMjpegUrlTests(unittest.IsolatedAsyncioTestCase):
    async def test_independent_mjpeg_port_probes_stream_endpoints(self):
        driver = IOSDriver("device-1", object())
        driver._mjpeg_port = 9100
        urls = []

        async def fake_find_mjpeg_url(base):
            urls.append(base)
            return f"{base}/stream.mjpeg"

        driver._find_mjpeg_url = fake_find_mjpeg_url

        stream_url = await driver._resolve_mjpeg_url(FakeWDAInfo())

        self.assertEqual(stream_url, "http://127.0.0.1:9100/stream.mjpeg")
        self.assertEqual(urls, ["http://127.0.0.1:9100"])

    async def test_resolve_mjpeg_falls_back_to_wda_port_when_independent_port_missing(self):
        driver = IOSDriver("device-1", object())
        driver._mjpeg_port = 9100
        urls = []

        async def fake_find_mjpeg_url(base):
            urls.append(base)
            if base.endswith(":9100"):
                return None
            return f"{base}/stream.mjpeg"

        driver._find_mjpeg_url = fake_find_mjpeg_url

        stream_url = await driver._resolve_mjpeg_url(FakeWDAInfo())

        self.assertEqual(stream_url, "http://127.0.0.1:8100/stream.mjpeg")
        self.assertEqual(urls, ["http://127.0.0.1:9100", "http://127.0.0.1:8100"])

    async def test_ios_13_disables_mjpeg_relay(self):
        class FakeAdapter:
            wda_info = None

            def __init__(self):
                self.start_args = None
                self.stop_calls = 0

            async def start_wda(self, wda_port, mjpeg_port):
                self.start_args = (wda_port, mjpeg_port)

            async def stop_wda(self):
                self.stop_calls += 1

        adapter = FakeAdapter()
        driver = IOSDriver("device-1", adapter, ios_version="13.6.1")

        with self.assertRaises(RuntimeError):
            await driver.start_mirroring(object())

        self.assertEqual(adapter.start_args[1], 0)
        self.assertTrue(driver._use_screenshot_stream)


if __name__ == "__main__":
    unittest.main()
