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


if __name__ == "__main__":
    unittest.main()
