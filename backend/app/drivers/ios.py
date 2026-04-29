"""iOS 设备驱动。"""

import asyncio
import base64
import logging
import socket
from collections.abc import Callable

import aiohttp

from .adapters.base import IOSAdapterBase
from .base import AbstractDeviceDriver, ControlEvent, InstallResult, MirrorOptions

logger = logging.getLogger(__name__)

IOS_WDA_BASE_PORT = 8100
IOS_WDA_PORT_STEP = 10

_port_counter = 0


def _allocate_wda_ports() -> tuple[int, int]:
    """分配 WDA API 端口和 MJPEG 端口。"""
    global _port_counter

    wda_port = 0
    for _ in range(20):
        candidate = IOS_WDA_BASE_PORT + _port_counter * IOS_WDA_PORT_STEP
        _port_counter += 1
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind(("127.0.0.1", candidate))
            wda_port = candidate
            break
        except OSError:
            logger.warning("WDA 端口 %s 已被占用，跳过", candidate)

    if not wda_port:
        wda_port = IOS_WDA_BASE_PORT + _port_counter * IOS_WDA_PORT_STEP
        _port_counter += 1

    mjpeg_port = wda_port + 1
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", mjpeg_port))
    except OSError:
        mjpeg_port = wda_port + 2
        logger.warning("MJPEG 端口 %s 已被占用，改用 %s", wda_port + 1, mjpeg_port)

    logger.info("分配端口: WDA=%s, MJPEG=%s", wda_port, mjpeg_port)
    return wda_port, mjpeg_port


def _release_wda_port() -> None:
    global _port_counter
    if _port_counter > 0:
        _port_counter -= 1


class IOSDriver(AbstractDeviceDriver):
    """基于 WDA 的 iOS 设备驱动。"""

    def __init__(self, device_id: str, adapter: IOSAdapterBase):
        self.device_id = device_id
        self._adapter = adapter
        self._is_mirroring = False
        self._mjpeg_task: asyncio.Task | None = None
        self._video_subscribers: list[asyncio.Queue] = []
        self._wda_port = 0
        self._mjpeg_port = 0
        self._session_id = ""
        self._screen_width = 0
        self._screen_height = 0
        self._http: aiohttp.ClientSession | None = None
        self._frame_count = 0

    @property
    def is_mirroring(self) -> bool:
        return self._is_mirroring

    @property
    def screen_size(self) -> tuple[int, int]:
        return self._screen_width, self._screen_height

    async def start_mirroring(self, options: MirrorOptions) -> str:
        del options
        if self._is_mirroring:
            return f"ios-{self.device_id}"

        self._wda_port, self._mjpeg_port = _allocate_wda_ports()
        logger.info(
            "[%s] 分配端口: WDA=%s, MJPEG=%s",
            self.device_id,
            self._wda_port,
            self._mjpeg_port,
        )

        try:
            await self._adapter.start_wda(self._wda_port, self._mjpeg_port)
        except Exception as err:
            _release_wda_port()
            raise RuntimeError(f"WDA 启动失败: {err}") from err

        self._http = aiohttp.ClientSession()

        try:
            self._session_id = await self._create_session()
            logger.info("[%s] WDA session 创建成功: %s...", self.device_id, self._session_id[:16])
        except Exception as err:
            logger.warning("[%s] WDA session 创建失败: %s", self.device_id, err)

        try:
            size = await self._get_window_size()
            self._screen_width = size.get("width", 375)
            self._screen_height = size.get("height", 812)
        except Exception:
            self._screen_width, self._screen_height = 375, 812

        self._is_mirroring = True
        self._frame_count = 0
        self._mjpeg_task = asyncio.create_task(self._read_mjpeg_loop())

        logger.info(
            "[%s] iOS 投屏已启动 (%sx%s @ WDA:%s MJPEG:%s)",
            self.device_id,
            self._screen_width,
            self._screen_height,
            self._wda_port,
            self._mjpeg_port,
        )
        return f"ios-{self.device_id}"

    async def stop_mirroring(self) -> None:
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
        logger.info("[%s] iOS 投屏已停止", self.device_id)

    async def send_event(self, event: ControlEvent) -> bool:
        if not self._adapter.wda_info or not self._http:
            return False

        base = f"http://{self._adapter.wda_info.host}:{self._adapter.wda_info.port}"
        session_path = f"/session/{self._session_id}" if self._session_id else ""

        try:
            if event.action == "tap":
                await self._http.post(
                    f"{base}{session_path}/wda/tap/0",
                    json={"x": event.params.get("x", 0), "y": event.params.get("y", 0)},
                )
            elif event.action == "swipe":
                await self._http.post(
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
                    await self._http.post(f"{base}/wda/homescreen")
                elif key == "lock":
                    await self._http.post(f"{base}/wda/lock")
                elif key == "volumeUp":
                    await self._http.post(
                        f"{base}{session_path}/wda/pressButton",
                        json={"name": "volumeUp"},
                    )
                elif key == "volumeDown":
                    await self._http.post(
                        f"{base}{session_path}/wda/pressButton",
                        json={"name": "volumeDown"},
                    )
            elif event.action == "text":
                text = event.params.get("text", "")
                if text:
                    await self._http.post(
                        f"{base}{session_path}/wda/keys",
                        json={"value": list(text)},
                    )
            else:
                logger.warning("[%s] 未知 iOS 控制指令: %s", self.device_id, event.action)
                return False
            return True
        except Exception as err:
            logger.error("[%s] iOS 控制指令失败: %s", self.device_id, err)
            return False

    async def get_screenshot(self) -> bytes:
        if not self._adapter.wda_info or not self._http:
            return b""

        base = f"http://{self._adapter.wda_info.host}:{self._adapter.wda_info.port}"
        try:
            async with self._http.get(f"{base}/screenshot") as resp:
                if resp.status != 200:
                    return b""
                data = await resp.json()
                return base64.b64decode(data.get("value", ""))
        except Exception as err:
            logger.error("[%s] 截图失败: %s", self.device_id, err)
            return b""

    async def install_app(
        self, file_path: str, callback: Callable[[str], None] | None = None
    ) -> InstallResult:
        ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
        if ext != "ipa":
            return InstallResult(success=False, message=f"iOS 仅支持 .ipa 文件，收到 {file_path}")

        if callback:
            callback("正在安装 IPA...")

        success, message = await self._adapter.install_app(file_path)

        if callback:
            callback("安装完成" if success else f"安装失败: {message}")

        return InstallResult(success=success, message=message)

    def subscribe_video(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=5)
        self._video_subscribers.append(queue)
        return queue

    def unsubscribe_video(self, queue: asyncio.Queue) -> None:
        if queue in self._video_subscribers:
            self._video_subscribers.remove(queue)

    async def _create_session(self) -> str:
        base = f"http://{self._adapter.wda_info.host}:{self._adapter.wda_info.port}"
        async with self._http.post(f"{base}/session", json={"capabilities": {}}) as resp:
            data = await resp.json()
            return data.get("sessionId", "") or data.get("value", {}).get("sessionId", "")

    async def _get_window_size(self) -> dict:
        base = f"http://{self._adapter.wda_info.host}:{self._adapter.wda_info.port}"
        session_path = f"/session/{self._session_id}" if self._session_id else ""
        async with self._http.get(f"{base}{session_path}/window/size") as resp:
            data = await resp.json()
            return data.get("value", {})

    async def _read_mjpeg_loop(self) -> None:
        wda_info = self._adapter.wda_info
        if not wda_info:
            logger.error("[%s] WDA 信息不可用，无法启动 MJPEG 流", self.device_id)
            return

        mjpeg_port = wda_info.mjpeg_port or self._mjpeg_port
        if mjpeg_port:
            stream_url = f"http://127.0.0.1:{mjpeg_port}"
            logger.info("[%s] MJPEG 流使用独立端口 %s", self.device_id, stream_url)
        else:
            wda_base = f"http://{wda_info.host}:{wda_info.port}"
            stream_url = await self._find_mjpeg_url(wda_base)
            if not stream_url:
                logger.error("[%s] 未找到可用的 MJPEG 流端点", self.device_id)
                return
            logger.info("[%s] MJPEG 流回退到 WDA 端口 %s", self.device_id, stream_url)

        while self._is_mirroring:
            try:
                async with self._http.get(
                    stream_url,
                    timeout=aiohttp.ClientTimeout(total=None, sock_connect=10),
                ) as resp:
                    if resp.status != 200:
                        logger.warning(
                            "[%s] MJPEG 流返回 HTTP %s，2 秒后重试", self.device_id, resp.status
                        )
                        await asyncio.sleep(2)
                        continue

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
                            self._frame_count += 1
                            for queue in list(self._video_subscribers):
                                try:
                                    queue.put_nowait(frame)
                                except asyncio.QueueFull:
                                    try:
                                        queue.get_nowait()
                                    except asyncio.QueueEmpty:
                                        pass
                                    try:
                                        queue.put_nowait(frame)
                                    except asyncio.QueueFull:
                                        pass
            except asyncio.CancelledError:
                break
            except Exception as err:
                if self._is_mirroring:
                    logger.warning("[%s] MJPEG 流中断: %s，2 秒后重连", self.device_id, err)
                    await asyncio.sleep(2)

    async def _find_mjpeg_url(self, base: str) -> str | None:
        candidates = [
            f"{base}/stream.mjpeg",
            f"{base}/stream",
            f"{base}/screenshot/stream",
        ]
        for url in candidates:
            try:
                async with self._http.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=8, sock_connect=5),
                ) as resp:
                    if resp.status != 200:
                        continue
                    content_type = resp.headers.get("Content-Type", "")
                    if any(
                        keyword in content_type
                        for keyword in ("multipart", "jpeg", "octet", "image", "stream")
                    ):
                        logger.info("[%s] MJPEG 流端点: %s (%s)", self.device_id, url, content_type)
                        return url
                    head = await resp.content.read(2)
                    if head == b"\xff\xd8":
                        logger.info("[%s] MJPEG 流端点(JPEG 头匹配): %s", self.device_id, url)
                        return url
            except TimeoutError:
                logger.debug("[%s] MJPEG 端点探测超时: %s", self.device_id, url)
            except Exception as err:
                logger.debug("[%s] MJPEG 端点探测失败: %s -> %s", self.device_id, url, err)

        logger.warning("[%s] 无法探测 MJPEG 端点，使用默认 /stream.mjpeg", self.device_id)
        return candidates[0]
