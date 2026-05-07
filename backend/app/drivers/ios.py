"""iOS 设备驱动。"""

import asyncio
import base64
import logging
import socket
from collections.abc import Callable

import aiohttp

from .adapters.base import IOSAdapterBase, WDAFailureHint, diagnose_wda_failure
from .base import AbstractDeviceDriver, ControlEvent, InstallResult, MirrorOptions

logger = logging.getLogger(__name__)

IOS_WDA_BASE_PORT = 8100
IOS_WDA_PORT_STEP = 10


def _jpeg_size(data: bytes) -> dict:
    """解析 JPEG 图片尺寸，避免为尺寸探测引入 Pillow 依赖。"""
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        index += 2
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > len(data):
            break
        segment_len = int.from_bytes(data[index:index + 2], "big")
        if segment_len < 2 or index + segment_len > len(data):
            break
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            height = int.from_bytes(data[index + 3:index + 5], "big")
            width = int.from_bytes(data[index + 5:index + 7], "big")
            return {"width": width, "height": height}
        index += segment_len
    return {}


_port_counter = 0


def _is_port_available(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False


def _allocate_wda_ports() -> tuple[int, int]:
    """分配 WDA API 端口和 MJPEG 端口。"""
    global _port_counter

    wda_port = 0
    for _ in range(20):
        candidate = IOS_WDA_BASE_PORT + _port_counter * IOS_WDA_PORT_STEP
        _port_counter += 1
        if _is_port_available(candidate):
            wda_port = candidate
            break
        logger.warning("WDA 端口 %s 已被占用，跳过", candidate)

    if not wda_port:
        wda_port = IOS_WDA_BASE_PORT + _port_counter * IOS_WDA_PORT_STEP
        _port_counter += 1

    mjpeg_port = 0
    for offset in range(1, IOS_WDA_PORT_STEP):
        candidate = wda_port + offset
        if _is_port_available(candidate):
            mjpeg_port = candidate
            if offset > 1:
                logger.warning("MJPEG 端口 %s 已被占用，改用 %s", wda_port + 1, mjpeg_port)
            break

    if not mjpeg_port:
        mjpeg_port = wda_port + IOS_WDA_PORT_STEP - 1
        logger.warning("MJPEG 端口段均被占用，最后尝试 %s", mjpeg_port)

    logger.info("分配端口: WDA=%s, MJPEG=%s", wda_port, mjpeg_port)
    return wda_port, mjpeg_port


def _release_wda_port() -> None:
    """端口由系统释放；计数器保持递增，避免复用仍被转发进程占用的端口。"""
    return None


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
            hint = diagnose_wda_failure(err)
            logger.error(
                "[%s] WDA 启动失败，分类=%s，原始错误=%s，建议=%s",
                self.device_id,
                hint.category,
                err,
                hint.suggestion,
            )
            raise RuntimeError(hint.format()) from err

        self._http = aiohttp.ClientSession()

        try:
            if not self._adapter.wda_info:
                raise RuntimeError("WDA 启动后未返回连接信息")
            try:
                self._session_id = await self._create_session()
                logger.info("[%s] WDA session 创建成功: %s...", self.device_id, self._session_id[:16])
            except Exception as err:
                logger.warning("[%s] WDA session 创建失败: %s", self.device_id, err)

            try:
                size = await self._get_screenshot_size()
                if not size:
                    size = await self._get_window_size()
                self._screen_width = size.get("width", 375)
                self._screen_height = size.get("height", 812)
            except Exception as err:
                logger.warning("[%s] iOS 屏幕尺寸获取失败，使用默认值: %s", self.device_id, err)
                self._screen_width, self._screen_height = 375, 812

            self._is_mirroring = True
            self._frame_count = 0
            self._mjpeg_task = asyncio.create_task(self._read_mjpeg_loop())
        except Exception:
            await self.stop_mirroring()
            raise

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

    def diagnose_control_failure(self, error: object | None = None) -> str:
        """返回 iOS 控制失败的可定位提示。"""
        if error is not None:
            hint = diagnose_wda_failure(error)
        elif not self._adapter.wda_info or not self._http:
            hint = WDAFailureHint(
                "wda_not_ready",
                "WDA 控制通道未就绪",
                "先确认设备投屏已成功启动；如仍失败，停止投屏后重新启动 WDA",
            )
        elif not self._session_id:
            hint = WDAFailureHint(
                "wda_session_failed",
                "WDA session 不可用，控制指令可能无法执行",
                "重启设备上的 WDA Runner，确认 /status 正常后重新启动投屏",
            )
        else:
            hint = WDAFailureHint(
                "wda_control_failed",
                "WDA 控制接口返回失败",
                "确认设备未锁屏、WDA Runner 仍在前台可用，并查看后端日志中的 HTTP 状态与响应内容",
            )
        return hint.format()

    async def _post_wda(self, url: str, payload: dict | None = None) -> bool:
        if not self._http:
            logger.warning("[%s] iOS 控制 HTTP 会话不可用", self.device_id)
            return False

        kwargs = {"json": payload} if payload is not None else {}
        async with self._http.post(url, **kwargs) as resp:
            text = await resp.text()
            if 200 <= resp.status < 300:
                logger.debug("[%s] WDA 控制成功: %s", self.device_id, url)
                return True
            logger.warning(
                "[%s] WDA 控制失败: HTTP %s %s，响应: %s，提示: %s",
                self.device_id,
                resp.status,
                url,
                text[:500],
                self.diagnose_control_failure(f"HTTP {resp.status}: {text[:500]}"),
            )
            return False

    async def send_event(self, event: ControlEvent) -> bool:
        if not self._adapter.wda_info or not self._http:
            logger.warning("[%s] WDA 信息或 HTTP 会话不可用，无法发送 iOS 控制指令", self.device_id)
            return False

        base = f"http://{self._adapter.wda_info.host}:{self._adapter.wda_info.port}"
        session_path = f"/session/{self._session_id}" if self._session_id else ""
        if not session_path:
            logger.warning("[%s] WDA session 不可用，iOS 控制可能失败", self.device_id)

        try:
            if event.action == "tap":
                return await self._post_wda(
                    f"{base}{session_path}/wda/tap/0",
                    {"x": event.params.get("x", 0), "y": event.params.get("y", 0)},
                )
            elif event.action == "touch":
                action = event.params.get("action", "")
                endpoint_map = {
                    "down": "/wda/touch/down",
                    "move": "/wda/touch/move",
                    "up": "/wda/touch/up",
                }
                endpoint = endpoint_map.get(action)
                if not endpoint:
                    logger.warning("[%s] 未知 iOS 触控动作: %s", self.device_id, action)
                    return False
                payload = {"x": event.params.get("x", 0), "y": event.params.get("y", 0)}
                success = await self._post_wda(f"{base}{session_path}{endpoint}", payload)
                if success:
                    return True
                if action == "down":
                    logger.warning("[%s] WDA touch/down 失败，回退到 tap 兼容路径", self.device_id)
                    return await self._post_wda(f"{base}{session_path}/wda/tap/0", payload)
                return False
            elif event.action == "swipe":
                return await self._post_wda(
                    f"{base}{session_path}/wda/dragfromtoforduration",
                    {
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
                    return await self._post_wda(f"{base}/wda/homescreen")
                elif key == "lock":
                    return await self._post_wda(f"{base}/wda/lock")
                elif key == "volumeUp":
                    return await self._post_wda(
                        f"{base}{session_path}/wda/pressButton",
                        {"name": "volumeUp"},
                    )
                elif key == "volumeDown":
                    return await self._post_wda(
                        f"{base}{session_path}/wda/pressButton",
                        {"name": "volumeDown"},
                    )
                logger.warning("[%s] 未知 iOS 按键: %s", self.device_id, key)
                return False
            elif event.action == "text":
                text = event.params.get("text", "")
                if text:
                    return await self._post_wda(
                        f"{base}{session_path}/wda/keys",
                        {"value": list(text)},
                    )
                return True
            else:
                logger.warning("[%s] 未知 iOS 控制指令: %s", self.device_id, event.action)
                return False
        except Exception as err:
            logger.error(
                "[%s] iOS 控制指令失败: %s，提示: %s",
                self.device_id,
                err,
                self.diagnose_control_failure(err),
            )
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
            text = await resp.text()
            if resp.status < 200 or resp.status >= 300:
                raise RuntimeError(f"HTTP {resp.status}: {text[:500]}")
            try:
                data = await resp.json(content_type=None)
            except Exception as err:
                raise RuntimeError(f"session 响应不是有效 JSON: {text[:500]}") from err
            session_id = data.get("sessionId", "") or data.get("value", {}).get("sessionId", "")
            if not session_id:
                raise RuntimeError(f"sessionId 缺失: {text[:500]}")
            return session_id

    async def _read_wda_json(self, url: str) -> dict:
        if not self._http:
            return {}
        try:
            async with self._http.get(url) as resp:
                text = await resp.text()
                if resp.status < 200 or resp.status >= 300:
                    logger.debug("[%s] WDA GET 失败: HTTP %s %s，响应: %s", self.device_id, resp.status, url, text[:300])
                    return {}
                data = await resp.json(content_type=None)
                return data if isinstance(data, dict) else {}
        except Exception as err:
            logger.debug("[%s] WDA GET 异常: %s %s", self.device_id, url, err)
            return {}

    async def _get_window_size(self) -> dict:
        base = f"http://{self._adapter.wda_info.host}:{self._adapter.wda_info.port}"
        session_path = f"/session/{self._session_id}" if self._session_id else ""
        data = await self._read_wda_json(f"{base}{session_path}/window/size")
        value = data.get("value", {})
        return value if isinstance(value, dict) else {}

    async def _get_screenshot_size(self) -> dict:
        base = f"http://{self._adapter.wda_info.host}:{self._adapter.wda_info.port}"
        data = await self._read_wda_json(f"{base}/screenshot")
        value = data.get("value", "")
        if not isinstance(value, str) or not value:
            return {}
        try:
            image = base64.b64decode(value)
            return _jpeg_size(image)
        except Exception as err:
            logger.debug("[%s] 截图尺寸解析失败: %s", self.device_id, err)
            return {}

    async def _read_mjpeg_loop(self) -> None:
        wda_info = self._adapter.wda_info
        if not wda_info:
            logger.error("[%s] WDA 信息不可用，无法启动 MJPEG 流", self.device_id)
            return

        stream_url = await self._resolve_mjpeg_url(wda_info)
        if not stream_url:
            logger.error("[%s] 未找到可用的 MJPEG 流端点", self.device_id)
            return

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

    async def _resolve_mjpeg_url(self, wda_info) -> str | None:
        mjpeg_port = wda_info.mjpeg_port or self._mjpeg_port
        if mjpeg_port:
            stream_url = await self._find_mjpeg_url(f"http://127.0.0.1:{mjpeg_port}")
            if stream_url:
                logger.info("[%s] MJPEG 流使用独立端口 %s", self.device_id, stream_url)
                return stream_url

        wda_base = f"http://{wda_info.host}:{wda_info.port}"
        stream_url = await self._find_mjpeg_url(wda_base)
        if stream_url:
            logger.info("[%s] MJPEG 流回退到 WDA 端口 %s", self.device_id, stream_url)
        return stream_url

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
