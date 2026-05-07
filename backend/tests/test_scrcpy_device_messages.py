import struct
import unittest

from app.scrcpy import protocol
from app.scrcpy.server_manager import ScrcpyServerManager


class ChunkedSocket:
    def __init__(self, chunks):
        self.chunks = list(chunks)

    def recv(self, size):
        del size
        if not self.chunks:
            raise BlockingIOError()
        return self.chunks.pop(0)


class DeviceMessageBufferTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_device_message_waits_for_complete_clipboard_message(self):
        text = "hello"
        payload = bytes([protocol.DEVICE_MSG_TYPE_CLIPBOARD]) + struct.pack(">I", len(text)) + text.encode()
        manager = ScrcpyServerManager("device-1")
        manager._control_socket = ChunkedSocket([payload[:3], payload[3:]])

        self.assertIsNone(await manager.read_device_message())
        self.assertEqual(await manager.read_device_message(), {"type": "clipboard", "text": text})

    async def test_read_device_message_keeps_second_coalesced_message_for_next_read(self):
        first = bytes([protocol.DEVICE_MSG_TYPE_ACK_CLIPBOARD]) + struct.pack(">q", 1)
        second = bytes([protocol.DEVICE_MSG_TYPE_ACK_CLIPBOARD]) + struct.pack(">q", 2)
        manager = ScrcpyServerManager("device-1")
        manager._control_socket = ChunkedSocket([first + second])

        self.assertEqual(await manager.read_device_message(), {"type": "ack_clipboard", "sequence": 1})
        self.assertEqual(await manager.read_device_message(), {"type": "ack_clipboard", "sequence": 2})


if __name__ == "__main__":
    unittest.main()
