import struct
import unittest

from test_h264_sps import build_sps

from app.scrcpy import protocol
from app.scrcpy.server_manager import ScrcpyServerManager

# scrcpy frame meta 中 pts 字段的配置包标志位（bit 63）
PACKET_FLAG_CONFIG = 1 << 63


class ChunkedSocket:
    def __init__(self, chunks):
        self.chunks = list(chunks)

    def recv(self, size):
        del size
        if not self.chunks:
            raise BlockingIOError()
        return self.chunks.pop(0)


class TimeoutChunkSocket:
    """模拟分片 + 超时的 video socket。chunks 中 None 表示一次超时。"""

    def __init__(self, chunks):
        self.chunks = list(chunks)

    def recv(self, size):
        if not self.chunks:
            raise TimeoutError()
        item = self.chunks.pop(0)
        if item is None:
            raise TimeoutError()
        if len(item) > size:
            # 超出请求量的部分放回队头
            self.chunks.insert(0, item[size:])
            item = item[:size]
        return item


class VideoFrameBufferTests(unittest.IsolatedAsyncioTestCase):
    """视频帧读取超时不应丢弃已读字节，否则 H.264 帧边界永久失步。"""

    async def test_read_video_frame_resumes_after_timeout_in_meta(self):
        frame_data = b"ABCD"
        meta = struct.pack(">QI", 1000, len(frame_data))
        manager = ScrcpyServerManager("device-1")
        # meta 前 5 字节 → 超时 → meta 剩余部分 + 帧数据
        manager._video_socket = TimeoutChunkSocket([meta[:5], None, meta[5:], frame_data])

        self.assertIsNone(await manager.read_video_frame())
        self.assertEqual(await manager.read_video_frame(), frame_data)

    async def test_read_video_frame_resumes_after_timeout_in_packet(self):
        frame_data = b"ABCDEFGH"
        meta = struct.pack(">QI", 1000, len(frame_data))
        manager = ScrcpyServerManager("device-1")
        # meta 完整 → 包体前 3 字节 → 超时 → 包体剩余部分
        manager._video_socket = TimeoutChunkSocket([meta, frame_data[:3], None, frame_data[3:]])

        self.assertIsNone(await manager.read_video_frame())
        self.assertEqual(await manager.read_video_frame(), frame_data)

    async def test_read_video_frame_reads_consecutive_frames(self):
        first = b"AAAA"
        second = b"BB"
        stream = (
            struct.pack(">QI", 1, len(first)) + first
            + struct.pack(">QI", 2, len(second)) + second
        )
        manager = ScrcpyServerManager("device-1")
        manager._video_socket = TimeoutChunkSocket([stream])

        self.assertEqual(await manager.read_video_frame(), first)
        self.assertEqual(await manager.read_video_frame(), second)


class ScreenSizeRotationTests(unittest.IsolatedAsyncioTestCase):
    """设备旋转后 server 重发配置包（新 SPS），screen_size 必须同步更新，
    否则 scrcpy server 校验触控消息宽高不一致会丢弃所有触控事件。"""

    @staticmethod
    def _config_packet(sps: bytes) -> bytes:
        payload = b"\x00\x00\x00\x01" + sps + b"\x00\x00\x00\x01\x68\xce\x3c\x80"
        meta = struct.pack(">QI", PACKET_FLAG_CONFIG, len(payload))
        return meta + payload

    async def test_config_packet_updates_screen_size_on_rotation(self):
        manager = ScrcpyServerManager("device-1")
        manager._screen_width, manager._screen_height = 1080, 1920
        # 旋转为横屏：1920x1080（编码尺寸 1920x1088 + crop_bottom=4）
        sps = build_sps(pic_width_mbs=120, pic_height_map_units=68, crop=(0, 0, 0, 4))
        manager._video_socket = TimeoutChunkSocket([self._config_packet(sps)])

        frame = await manager.read_video_frame()

        self.assertIsNotNone(frame)
        self.assertEqual(manager.screen_size, (1920, 1080))

    async def test_normal_frame_does_not_touch_screen_size(self):
        manager = ScrcpyServerManager("device-1")
        manager._screen_width, manager._screen_height = 1080, 1920
        frame_data = b"\x00\x00\x00\x01\x65\x88\x84\x00"
        meta = struct.pack(">QI", 1000, len(frame_data))
        manager._video_socket = TimeoutChunkSocket([meta + frame_data])

        self.assertEqual(await manager.read_video_frame(), frame_data)
        self.assertEqual(manager.screen_size, (1080, 1920))


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
