"""iOS 设备驱动 — 实现 AbstractDeviceDriver。

通过 WDA（WebDriverAgent）实现 iOS 设备的投屏（MJPEG）和控制（REST API）。
自动选择 TideviceAdapter 或 GoIOSAdapter 管理 WDA 生命周期。
"""

import asyncio
import logging
from typing import Callable

import aiohttp

from app.drivers.base import AbstractDeviceDriver, ControlEvent, MirrorOptions
from app.drivers.adapters.base import IOSAdapterBase

logger = logging.getLogger(__name__)

# iOS WDA 端口基数，每设备递增 10
IOS_WDA_BASE_PORT = 8100
IOS_WDA_PORT_STEP = 10

# 全局端口分配计数器
_port_counter = 0


def _allocate_wda_port() -> int:
    """分配 WDA 端口。"""
    global _port_counter
    port = IOS_WDA_BASE_PORT + _port_counter * IOS_WDA_PORT_STEP
    _port_counter += 1
    return port


def _release_wda_port():
    """释放 WDA 端口（简单递减）。"""
    global _port_counter
    if _port_counter > 0:
        _port_counter -= 1


class IOSDriver(AbstractDeviceDriver):
    """iOS 设备驱动。"""

    def __init__(self, device_id: str, adapter: IOSAdapterBase):
        self.device_id = device_id
        self._adapter = adapter
        self._is_mirroring = False
        self._mjpeg_task: asyncio.Task | None = None
        self._video_subscribers: list[asyncio.Queue] = []
        self._wda_port: int = 0
        self._session_id: str = ""
        self._screen_width: int = 0
        self._screen_height: int = 0
        self._http: aiohttp.ClientSession | None = None
        self._session_id: str = ""
        self._screen_width: int = 0
        self._screen_height: int = 0

    @property
    def is_mirroring(self) -> bool:
        return self._is_mirroring

    @property
    def screen_size(self) -> tuple[int, int]:
        return (self._screen_width, self._screen_height)

    async def start_mirroring(self, options: MirrorOptions) -> str:
        """启动 iOS 投屏（WDA MJPEG 流）。"""
        if self._is_mirroring:
            return f"ios-{self.device_id}"

        # 分配端口并启动 WDA
        self._wda_port = _allocate_wda_port()
        try:
            wda_info = await self._adapter.start_wda(self._wda_port)
        except Exception as e:
            _release_wda_port()
            raise RuntimeError(f"WDA 启动失败: {e}") from e

        # 创建共享 HTTP session
        self._http = aiohttp.ClientSession()

        # 创建 WDA session
        try:
            self._session_id = await self._create_session()
        except Exception as e:
            logger.warning(f"[{self.device_id}] WDA session 创建失败（非致命）: {e}")

        # 获取屏幕尺寸
        try:
            size = await self._get_window_size()
            self._screen_width = size.get("width", 375)
            self._screen_height = size.get("height", 812)
        except Exception:
            self._screen_width, self._screen_height = 375, 812

        # 启动 MJPEG 流读取
        self._is_mirroring = True
        self._mjpeg_task = asyncio.create_task(self._read_mjpeg_loop())

        logger.info(
            f"[{self.device_id}] iOS 投屏已启动 "
            f"({self._screen_width}x{self._screen_height} @ port {self._wda_port})"
        )
        return f"ios-{self.device_id}"

    async def stop_mirroring(self) -> None:
        """停止 iOS 投屏。"""
        self._is_mirroring = False

        if self._mjpeg_task:
            self._mjpeg_task.cancel()
            try:
                await self._mjpeg_task
            except (asyncio.CancelledError, Exception):
                pass
            self._mjpeg_task = None

        if self._http:
            await self._http.close()
            self._http = None

        await self._adapter.stop_wda()
        _release_wda_port()
        self._video_subscribers.clear()
        logger.info(f"[{self.device_id}] iOS 投屏已停止")

    async def send_event(self, event: ControlEvent) -> bool:
        """发送控制指令到 iOS 设备（通过 WDA REST API）。"""
        if not self._adapter.wda_info or not self._http:
            return False

        base = f"http://{self._adapter.wda_info.host}:{self._adapter.wda_info.port}"
        session_path = f"/session/{self._session_id}" if self._session_id else ""
        http = self._http

        try:
            if event.action == "tap":
                x = event.params.get("x", 0)
                y = event.params.get("y", 0)
                await http.post(
                    f"{base}{session_path}/wda/tap/0",
                    json={"x": x, "y": y},
                )

            elif event.action == "swipe":
                await http.post(
                    f"{base}{session_path}/wda/dragfromtoforduration",
                    json={
                        "fromX": event.params.get("fromX", 0),
                        "fromY": event.params.get("fromY", 0),
                        "toX": event.params.get("toX", 0),
                        "toY": event.params.get("toY", 0),
                        "duration": event.params.get("duration", 0.5),
                    },
                )

            elif event.action == "keyevent":
                key = event.params.get("key", "")
                if key == "home":
                    await http.post(f"{base}/wda/homescreen")
                elif key == "lock":
                    await http.post(f"{base}/wda/lock")
                elif key == "volumeUp":
                    await http.post(
                        f"{base}{session_path}/wda/pressButton",
                        json={"name": "volumeUp"},
                    )
                elif key == "volumeDown":
                    await http.post(
                        f"{base}{session_path}/wda/pressButton",
                        json={"name": "volumeDown"},
                    )

            elif event.action == "text":
                text = event.params.get("text", "")
                if text:
                    await http.post(
                        f"{base}{session_path}/wda/keys",
                        json={"value": list(text)},
                    )

            else:
                logger.warning(f"[{self.device_id}] 未知 iOS 控制指令: {event.action}")
                return False

            return True
        except Exception as e:
            logger.error(f"[{self.device_id}] iOS 控制指令失败: {e}")
            return False

    async def get_screenshot(self) -> bytes:
        """获取 iOS 设备截图。"""
        if not self._adapter.wda_info or not self._http:
            return b""
        base = f"http://{self._adapter.wda_info.host}:{self._adapter.wda_info.port}"
        try:
            async with self._http.get(f"{base}/screenshot") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    import base64
                    return base64.b64decode(data.get("value", ""))
        except Exception as e:
            logger.error(f"[{self.device_id}] 截图失败: {e}")
        return b""

    def subscribe_video(self) -> asyncio.Queue:
        """订阅 MJPEG 视频帧。"""
        q = asyncio.Queue(maxsize=5)
        self._video_subscribers.append(q)
        return q

    def unsubscribe_video(self, q: asyncio.Queue) -> None:
        """取消订阅。"""
        if q in self._video_subscribers:
            self._video_subscribers.remove(q)

    # ─── 内部方法 ───

    async def _create_session(self) -> str:
        """创建 WDA session。"""
        base = f"http://{self._adapter.wda_info.host}:{self._adapter.wda_info.port}"
        async with self._http.post(
            f"{base}/session",
            json={"capabilities": {}},
        ) as resp:
            data = await resp.json()
            return data.get("sessionId", "") or data.get("value", {}).get("sessionId", "")

    async def _get_window_size(self) -> dict:
        """获取设备窗口尺寸。"""
        base = f"http://{self._adapter.wda_info.host}:{self._adapter.wda_info.port}"
        session_path = f"/session/{self._session_id}" if self._session_id else ""
        async with self._http.get(f"{base}{session_path}/window/size") as resp:
            data = await resp.json()
            return data.get("value", {})

    async def _read_mjpeg_loop(self):
        """持续读取 WDA MJPEG 流并分发给订阅者。"""
        base = f"http://{self._adapter.wda_info.host}:{self._adapter.wda_info.port}"
        url = f"{base}/stream"

        while self._is_mirroring:
            try:
                async with self._http.get(url, timeout=aiohttp.ClientTimeout(total=None)) as resp:
                    boundary = None
                    content_type = resp.headers.get("Content-Type", "")
                    if "boundary=" in content_type:
                        boundary = content_type.split("boundary=")[1].strip()

                    buffer = b""
                    async for chunk in resp.content.iter_any():
                        if not self._is_mirroring:
                            break
                        buffer += chunk
                        while True:
                            start = buffer.find(b"\xff\xd8")
                            if start == -1:
                                break
                            end = buffer.find(b"\xff\xd9", start + 2)
                            if end == -1:
                                break
                            frame = buffer[start : end + 2]
                            buffer = buffer[end + 2 :]
                            for q in list(self._video_subscribers):
                                try:
                                    q.put_nowait(frame)
                                except asyncio.QueueFull:
                                    try:
                                        q.get_nowait()
                                    except asyncio.QueueEmpty:
                                        pass
                                    q.put_nowait(frame)
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._is_mirroring:
                    logger.warning(f"[{self.device_id}] MJPEG 流中断: {e}，2 秒后重连")
                    await asyncio.sleep(2)
