"""AndroidDriver: 基于 scrcpy 协议的 Android 设备驱动。

实现 AbstractDeviceDriver 接口，通过 ScrcpyServerManager 管理投屏与控制。
"""

import asyncio
import logging

from app.drivers.base import AbstractDeviceDriver, ControlEvent, MirrorOptions
from app.scrcpy.protocol import (
    ACTION_DOWN,
    ACTION_MOVE,
    ACTION_UP,
    KEYCODE_BACK,
    KEYCODE_HOME,
    KEYCODE_POWER,
    KEYCODE_VOLUME_DOWN,
    KEYCODE_VOLUME_UP,
    encode_back_or_screen_on,
    encode_inject_keycode,
    encode_inject_text,
    encode_inject_touch,
)
from app.scrcpy.server_manager import ScrcpyServerManager

logger = logging.getLogger(__name__)

# 按键名称到 keycode 的映射
KEYCODE_MAP = {
    "home": KEYCODE_HOME,
    "back": KEYCODE_BACK,
    "power": KEYCODE_POWER,
    "volume_up": KEYCODE_VOLUME_UP,
    "volume_down": KEYCODE_VOLUME_DOWN,
}


class AndroidDriver(AbstractDeviceDriver):
    """Android 设备驱动，桌面端/Web 端共用。"""

    def __init__(self, device_serial: str):
        self.device_serial = device_serial
        self._server_manager: ScrcpyServerManager | None = None
        self._video_task: asyncio.Task | None = None
        self._video_subscribers: list[asyncio.Queue] = []

    @property
    def is_mirroring(self) -> bool:
        return self._server_manager is not None and self._server_manager.running

    @property
    def screen_size(self) -> tuple[int, int]:
        if self._server_manager:
            return self._server_manager.screen_size
        return 0, 0

    def subscribe_video(self) -> asyncio.Queue:
        """订阅视频帧推送。"""
        q: asyncio.Queue = asyncio.Queue(maxsize=30)
        self._video_subscribers.append(q)
        return q

    def unsubscribe_video(self, q: asyncio.Queue) -> None:
        """取消视频帧订阅。"""
        if q in self._video_subscribers:
            self._video_subscribers.remove(q)

    async def start_mirroring(self, options: MirrorOptions) -> str:
        """启动投屏。"""
        if self.is_mirroring:
            return self.device_serial

        self._server_manager = ScrcpyServerManager(self.device_serial)
        await self._server_manager.start(
            max_size=max(options.width, options.height) or 0,
            max_fps=options.max_fps,
            bitrate=options.bitrate,
        )

        # 启动视频帧读取任务
        self._video_task = asyncio.create_task(self._read_video_loop())

        return self.device_serial

    async def stop_mirroring(self) -> None:
        """停止投屏。"""
        if self._video_task:
            self._video_task.cancel()
            try:
                await self._video_task
            except asyncio.CancelledError:
                pass
            self._video_task = None

        if self._server_manager:
            await self._server_manager.stop()
            self._server_manager = None

        # 清空订阅者
        self._video_subscribers.clear()

        logger.info(f"[{self.device_serial}] 投屏已停止")

    async def send_event(self, event: ControlEvent) -> bool:
        """发送控制指令。"""
        if not self._server_manager or not self._server_manager.running:
            return False

        try:
            data = self._encode_event(event)
            if data:
                await self._server_manager.send_control(data)
                return True
        except Exception as e:
            logger.error(f"[{self.device_serial}] 发送控制指令失败: {e}")
        return False

    async def get_screenshot(self) -> bytes:
        """获取截图（通过 ADB screencap）。"""
        import adbutils

        device = adbutils.adb.device(serial=self.device_serial)
        return await asyncio.to_thread(device.screenshot)

    async def _read_video_loop(self) -> None:
        """持续读取视频帧并分发给订阅者。"""
        while self._server_manager and self._server_manager.running:
            try:
                frame = await self._server_manager.read_video_frame()
                if frame is None:
                    await asyncio.sleep(0.001)
                    continue

                # 分发给所有订阅者
                for q in self._video_subscribers:
                    try:
                        q.put_nowait(frame)
                    except asyncio.QueueFull:
                        # 丢弃旧帧，保持最新
                        try:
                            q.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                        try:
                            q.put_nowait(frame)
                        except asyncio.QueueFull:
                            pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[{self.device_serial}] 视频帧读取异常: {e}")
                await asyncio.sleep(0.1)

    def _encode_event(self, event: ControlEvent) -> bytes | None:
        """将 ControlEvent 编码为 scrcpy 二进制协议。"""
        action = event.action
        params = event.params
        w, h = self.screen_size

        if action == "tap":
            x = params.get("x", 0)
            y = params.get("y", 0)
            # 发送 DOWN + UP
            down = encode_inject_touch(ACTION_DOWN, -1, x, y, w, h)
            up = encode_inject_touch(ACTION_UP, -1, x, y, w, h)
            return down + up

        if action == "swipe":
            x1, y1 = params.get("x1", 0), params.get("y1", 0)
            x2, y2 = params.get("x2", 0), params.get("y2", 0)
            steps = params.get("steps", 20)
            frames = []
            frames.append(encode_inject_touch(ACTION_DOWN, -1, x1, y1, w, h))
            for i in range(1, steps + 1):
                cx = x1 + (x2 - x1) * i // steps
                cy = y1 + (y2 - y1) * i // steps
                frames.append(encode_inject_touch(ACTION_MOVE, -1, cx, cy, w, h))
            frames.append(encode_inject_touch(ACTION_UP, -1, x2, y2, w, h))
            return b"".join(frames)

        if action == "keyevent":
            key = params.get("key", "")
            keycode = KEYCODE_MAP.get(key.lower())
            if keycode is None:
                keycode = params.get("keycode", 0)
            if action == "back":
                return encode_back_or_screen_on(ACTION_DOWN) + encode_back_or_screen_on(ACTION_UP)
            down = encode_inject_keycode(ACTION_DOWN, keycode)
            up = encode_inject_keycode(ACTION_UP, keycode)
            return down + up

        if action == "text":
            text = params.get("text", "")
            if text:
                return encode_inject_text(text)

        if action == "touch_down":
            return encode_inject_touch(
                ACTION_DOWN, params.get("pointer_id", -1),
                params.get("x", 0), params.get("y", 0), w, h,
            )

        if action == "touch_move":
            return encode_inject_touch(
                ACTION_MOVE, params.get("pointer_id", -1),
                params.get("x", 0), params.get("y", 0), w, h,
            )

        if action == "touch_up":
            return encode_inject_touch(
                ACTION_UP, params.get("pointer_id", -1),
                params.get("x", 0), params.get("y", 0), w, h,
            )

        logger.warning(f"未知控制指令: {action}")
        return None
