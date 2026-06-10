import struct
import unittest

from app.scrcpy import protocol
from app.websocket.control import _encode_command, _get_android_manager


class FakeManager:
    screen_size = (1080, 1920)


class FakeAndroidDriver:
    def __init__(self):
        self._server_manager = FakeManager()


class FakeIOSDriver:
    pass


class ControlEncodingTests(unittest.TestCase):
    def test_explicit_key_down_only_encodes_down_action(self):
        encoded = _encode_command("key", {"action": "down", "keycode": protocol.KEYCODE_HOME}, FakeManager())
        single = protocol.encode_inject_keycode(protocol.ACTION_DOWN, protocol.KEYCODE_HOME)

        self.assertEqual(encoded, single)

    def test_key_without_action_encodes_press_down_and_up(self):
        encoded = _encode_command("key", {"keycode": protocol.KEYCODE_HOME}, FakeManager())
        expected = (
            protocol.encode_inject_keycode(protocol.ACTION_DOWN, protocol.KEYCODE_HOME)
            + protocol.encode_inject_keycode(protocol.ACTION_UP, protocol.KEYCODE_HOME)
        )

        self.assertEqual(encoded, expected)

    def test_get_android_manager_returns_none_for_ios_driver(self):
        self.assertIsNone(_get_android_manager(FakeIOSDriver()))
        self.assertIsNotNone(_get_android_manager(FakeAndroidDriver()))


class ScrollEncodingTests(unittest.TestCase):
    """scroll 编码遵循 scrcpy ≥1.25 协议：hscroll/vscroll 为 i16 定点数，消息共 21 字节。"""

    def test_scroll_message_is_21_bytes_with_i16_fixed_point(self):
        encoded = protocol.encode_inject_scroll(100, 200, 1080, 1920, 0.0, 1.0)

        self.assertEqual(len(encoded), 21)
        msg_type, x, y, w, h, hscroll, vscroll, buttons = struct.unpack(">BiiHHhhI", encoded)
        self.assertEqual(msg_type, protocol.CONTROL_TYPE_INJECT_SCROLL)
        self.assertEqual((x, y, w, h), (100, 200, 1080, 1920))
        self.assertEqual(hscroll, 0)
        self.assertEqual(vscroll, 0x7FFF)
        self.assertEqual(buttons, 0)

    def test_scroll_negative_value_maps_to_negative_i16(self):
        encoded = protocol.encode_inject_scroll(0, 0, 1080, 1920, -1.0, -0.5)

        hscroll, vscroll = struct.unpack(">hh", encoded[13:17])
        self.assertEqual(hscroll, -0x7FFF)
        self.assertEqual(vscroll, round(-0.5 * 0x7FFF))

    def test_scroll_value_out_of_range_is_clamped(self):
        encoded = protocol.encode_inject_scroll(0, 0, 1080, 1920, 120.0, -120.0)

        hscroll, vscroll = struct.unpack(">hh", encoded[13:17])
        self.assertEqual(hscroll, 0x7FFF)
        self.assertEqual(vscroll, -0x7FFF)

    def test_scroll_command_normalizes_frontend_wheel_delta(self):
        # 前端滚轮事件发送 ±120，应被归一化为满量程定点值
        encoded = _encode_command("scroll", {"x": 10, "y": 20, "vScroll": 120, "hScroll": -120}, FakeManager())

        self.assertEqual(len(encoded), 21)
        hscroll, vscroll = struct.unpack(">hh", encoded[13:17])
        self.assertEqual(hscroll, -0x7FFF)
        self.assertEqual(vscroll, 0x7FFF)


if __name__ == "__main__":
    unittest.main()
