import unittest

from app.drivers.ios import _jpeg_size


class IosImageSizeTests(unittest.TestCase):
    def test_png_screenshot_size_is_parsed(self):
        png_header = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR"
            + (700).to_bytes(4, "big")
            + (992).to_bytes(4, "big")
        )

        self.assertEqual(_jpeg_size(png_header), {"width": 700, "height": 992})

    def test_non_jpeg_or_png_data_is_ignored(self):
        self.assertEqual(_jpeg_size(b"not an image with random \xff\xc0 bytes"), {})


if __name__ == "__main__":
    unittest.main()
