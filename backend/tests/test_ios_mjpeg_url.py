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


if __name__ == "__main__":
    unittest.main()
