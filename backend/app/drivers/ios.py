"""iOS 设备驱动。"""

import asyncio
import base64
import logging
import socket
import time
from collections.abc import Callable

import aiohttp

from .adapters.base import IOSAdapterBase, WDAFailureHint, diagnose_wda_failure
from .base import AbstractDeviceDriver, ControlEvent, InstallResult, MirrorOptions

logger = logging.getLogger(__name__)

IOS_WDA_BASE_PORT = 8100
IOS_WDA_PORT_STEP = 10
IOS_MJPEG_MIN_MAJOR = 15
IOS_SCREENSHOT_FALLBACK_FPS = 2
IOS_SCREENSHOT_CONTROL_PAUSE_SECONDS = 0.45
IOS_LEGACY_SCROLL_MIN_INTERVAL_SECONDS = 0.35
IOS_SESSION_RECREATE_ATTEMPTS = 2
IOS_SESSION_RECREATE_RETRY_DELAY_SECONDS = 0.3


def _is_invalid_session_response(status: int, text: str) -> bool:
    if status not in {404, 500}:
        return False
    lower_text = text.lower()
    return "invalid session id" in lower_text or "session does not exist" in lower_text


def _jpeg_size(data: bytes) -> dict:
    """解析 WDA 截图尺寸，避免为尺寸探测引入 Pillow 依赖。"""
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return {
            "width": int.from_bytes(data[16:20], "big"),
            "height": int.from_bytes(data[20:24], "big"),
        }
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return {}
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


def _parse_ios_major(version: str) -> int:
    try:
        return int(str(version).strip().split(".", 1)[0])
    except (TypeError, ValueError):
        return 0


class IOSDriver(AbstractDeviceDriver):
    """基于 WDA 的 iOS 设备驱动。"""

    def __init__(self, device_id: str, adapter: IOSAdapterBase, ios_version: str = ""):
        self.device_id = device_id
        self._adapter = adapter
        self._ios_version = ios_version
        self._ios_major = _parse_ios_major(ios_version)
        self._is_mirroring = False
        self._mjpeg_task: asyncio.Task | None = None
        self._use_screenshot_stream = False
        self._video_subscribers: list[asyncio.Queue] = []
        self._wda_port = 0
        self._mjpeg_port = 0
        self._session_id = ""
        self._screen_width = 0
        self._screen_height = 0
        # WDA 坐标系为点（point，逻辑分辨率），MJPEG 帧为像素（点 × scale）。
        # 控制指令必须把前端的帧像素坐标换算为窗口点坐标，否则 2x/3x 设备触控位置整体偏移。
        self._window_width = 0
        self._window_height = 0
        self._http: aiohttp.ClientSession | None = None
        self._frame_count = 0
        self._control_in_flight = 0
        self._last_control_at = 0.0
        self._wda_request_lock = asyncio.Lock()
        # 投屏生命周期锁：防止并发 start/stop 重复分配端口、泄漏资源
        self._lifecycle_lock = asyncio.Lock()

    @property
    def is_mirroring(self) -> bool:
        return self._is_mirroring

    @property
    def screen_size(self) -> tuple[int, int]:
        return self._screen_width, self._screen_height

    @property
    def uses_screenshot_stream(self) -> bool:
        return self._use_screenshot_stream

    async def start_mirroring(self, options: MirrorOptions) -> str:
        del options
        async with self._lifecycle_lock:
            if self._is_mirroring:
                return f"ios-{self.device_id}"

            self._wda_port, self._mjpeg_port = _allocate_wda_ports()
            await self._resolve_ios_version()
            if 0 < self._ios_major < IOS_MJPEG_MIN_MAJOR:
                logger.info(
                    "[%s] iOS %s uses WDA screenshot polling; skip independent MJPEG relay",
                    self.device_id,
                    self._ios_version,
                )
                self._mjpeg_port = 0
                self._use_screenshot_stream = True
            else:
                self._use_screenshot_stream = False
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
                    window = await self._get_window_size()
                    self._window_width = int(window.get("width") or 0)
                    self._window_height = int(window.get("height") or 0)

                    pixel = await self._get_screenshot_size()
                    self._screen_width = int(pixel.get("width") or self._window_width or 375)
                    self._screen_height = int(pixel.get("height") or self._window_height or 812)
                    if self._window_width and self._screen_width:
                        logger.info(
                            "[%s] iOS 屏幕尺寸: 窗口 %sx%s pt, 帧 %sx%s px (scale≈%.2f)",
                            self.device_id,
                            self._window_width,
                            self._window_height,
                            self._screen_width,
                            self._screen_height,
                            self._screen_width / self._window_width,
                        )
                except Exception as err:
                    logger.warning("[%s] iOS 屏幕尺寸获取失败，使用默认值: %s", self.device_id, err)
                    self._screen_width, self._screen_height = 375, 812

                self._is_mirroring = True
                self._frame_count = 0
                self._mjpeg_task = asyncio.create_task(self._read_mjpeg_loop())
            except Exception:
                await self._stop_mirroring_locked()
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
        async with self._lifecycle_lock:
            await self._stop_mirroring_locked()

    async def _stop_mirroring_locked(self) -> None:
        """停止投屏的内部实现（调用方需已持有 _lifecycle_lock）。"""
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
        current_url = url
        retry_invalid_session = True
        post_kwargs = dict(kwargs)
        post_kwargs["timeout"] = aiohttp.ClientTimeout(total=8, sock_connect=3)
        self._control_in_flight += 1
        try:
            async with self._wda_request_lock:
                while True:
                    try:
                        async with self._http.post(current_url, **post_kwargs) as resp:
                            text = await resp.text()
                            if 200 <= resp.status < 300:
                                logger.debug("[%s] WDA 控制成功: %s", self.device_id, current_url)
                                return True

                            old_session_id = self._session_id
                            if (
                                retry_invalid_session
                                and old_session_id
                                and f"/session/{old_session_id}/" in current_url
                                and _is_invalid_session_response(resp.status, text)
                                and await self._recreate_session()
                            ):
                                current_url = current_url.replace(
                                    f"/session/{old_session_id}/",
                                    f"/session/{self._session_id}/",
                                    1,
                                )
                                retry_invalid_session = False
                                logger.info(
                                    "[%s] WDA session 已重建，重试控制请求",
                                    self.device_id,
                                )
                                continue

                            logger.warning(
                                "[%s] WDA 控制失败: HTTP %s %s，响应: %s，提示: %s",
                                self.device_id,
                                resp.status,
                                current_url,
                                text[:500],
                                self.diagnose_control_failure(f"HTTP {resp.status}: {text[:500]}"),
                            )
                            return False
                    except (aiohttp.ClientError, TimeoutError) as err:
                        old_session_id = self._session_id
                        if (
                            retry_invalid_session
                            and old_session_id
                            and f"/session/{old_session_id}/" in current_url
                            and await self._recreate_session()
                        ):
                            current_url = current_url.replace(
                                f"/session/{old_session_id}/",
                                f"/session/{self._session_id}/",
                                1,
                            )
                            retry_invalid_session = False
                            logger.info(
                                "[%s] WDA 控制请求异常后 session 已重建，重试一次: %s",
                                self.device_id,
                                err,
                            )
                            continue
                        logger.warning(
                            "[%s] WDA 控制请求异常: %s，提示: %s",
                            self.device_id,
                            err,
                            self.diagnose_control_failure(err),
                        )
                        return False
        finally:
            self._control_in_flight = max(0, self._control_in_flight - 1)
            self._last_control_at = time.monotonic()

    async def _recreate_session(
        self,
        attempts: int = IOS_SESSION_RECREATE_ATTEMPTS,
        retry_delay: float = IOS_SESSION_RECREATE_RETRY_DELAY_SECONDS,
    ) -> bool:
        attempts = max(1, attempts)
        for attempt in range(1, attempts + 1):
            try:
                self._session_id = await self._create_session()
                logger.info("[%s] WDA session 重建成功: %s...", self.device_id, self._session_id[:16])
                return True
            except Exception as err:
                self._session_id = ""
                if attempt >= attempts:
                    logger.warning("[%s] WDA session 重建失败: %s", self.device_id, err)
                    return False
                logger.info(
                    "[%s] WDA session 重建失败，%.1fs 后重试: %s",
                    self.device_id,
                    retry_delay,
                    err,
                )
                await asyncio.sleep(retry_delay)
        return False

    async def _ensure_session(self) -> bool:
        if self._session_id:
            return True
        if not self._http or not self._adapter.wda_info:
            return False
        async with self._wda_request_lock:
            if self._session_id:
                return True
            return await self._recreate_session()

    async def _session_path_or_none(self, action: str) -> str:
        if await self._ensure_session():
            return f"/session/{self._session_id}"
        logger.warning("[%s] WDA session 不可用，跳过 iOS %s 控制请求", self.device_id, action)
        return ""

    def _should_pause_screenshot_for_control(self) -> bool:
        if self._control_in_flight > 0:
            return True
        if not self._last_control_at:
            return False
        return time.monotonic() - self._last_control_at < IOS_SCREENSHOT_CONTROL_PAUSE_SECONDS

    def should_drop_legacy_scroll(self) -> bool:
        """低版本截图回退模式下丢弃过密滚动，避免 WDA 控制请求排队造成滞后。"""
        if not self._use_screenshot_stream:
            return False
        if self._control_in_flight > 0:
            return True
        if not self._last_control_at:
            return False
        return time.monotonic() - self._last_control_at < IOS_LEGACY_SCROLL_MIN_INTERVAL_SECONDS

    def _to_window_points(
        self, x: float, y: float, frame_width: int = 0, frame_height: int = 0
    ) -> tuple[int, int]:
        """把前端 MJPEG 帧像素坐标换算为 WDA 窗口点坐标。

        frame_width/frame_height 为前端实际渲染帧尺寸（随事件携带，旋转后仍准确）；
        缺失时回退到驱动启动时探测的帧尺寸。窗口点尺寸不可用时原样透传。
        """
        src_w = frame_width or self._screen_width
        src_h = frame_height or self._screen_height
        win_w, win_h = self._window_width, self._window_height
        if win_w > 0 and win_h > 0 and src_w > 0 and src_h > 0:
            # 进入横屏游戏后，WDA window/size 有时仍保留启动时的竖屏值；
            # 画面帧尺寸会先变成横屏，此时交换窗口宽高可保持坐标系方向一致。
            if (src_w > src_h and win_w < win_h) or (src_w < src_h and win_w > win_h):
                win_w, win_h = win_h, win_w
            if src_w != win_w or src_h != win_h:
                x = x * win_w / src_w
                y = y * win_h / src_h
            x = min(max(x, 0), win_w - 1)
            y = min(max(y, 0), win_h - 1)
        return round(x), round(y)

    async def send_event(self, event: ControlEvent) -> bool:
        if not self._adapter.wda_info or not self._http:
            logger.warning("[%s] WDA 信息或 HTTP 会话不可用，无法发送 iOS 控制指令", self.device_id)
            return False

        base = f"http://{self._adapter.wda_info.host}:{self._adapter.wda_info.port}"

        try:
            if event.action == "tap":
                session_path = await self._session_path_or_none("tap")
                if not session_path:
                    return False
                x, y = self._to_window_points(
                    event.params.get("x", 0),
                    event.params.get("y", 0),
                    int(event.params.get("width", 0)),
                    int(event.params.get("height", 0)),
                )
                logger.debug("[%s] iOS tap -> (%s, %s) pt", self.device_id, x, y)
                actions_payload = {
                    "actions": [
                        {
                            "type": "pointer",
                            "id": "finger1",
                            "parameters": {"pointerType": "touch"},
                            "actions": [
                                {"type": "pointerMove", "duration": 0, "x": x, "y": y},
                                {"type": "pointerDown", "button": 0},
                                {"type": "pause", "duration": 50},
                                {"type": "pointerUp", "button": 0},
                            ],
                        }
                    ]
                }
                return await self._post_wda(f"{base}{session_path}/actions", actions_payload)
            elif event.action == "touch":
                logger.warning("[%s] iOS touch down/move/up 已废弃，应由上层聚合为 tap 或 swipe", self.device_id)
                return False
            elif event.action == "swipe":
                session_path = await self._session_path_or_none("swipe")
                if not session_path:
                    return False
                frame_w = int(event.params.get("width", 0))
                frame_h = int(event.params.get("height", 0))
                from_x, from_y = self._to_window_points(
                    event.params.get("fromX", 0), event.params.get("fromY", 0), frame_w, frame_h
                )
                to_x, to_y = self._to_window_points(
                    event.params.get("toX", 0), event.params.get("toY", 0), frame_w, frame_h
                )
                duration_ms = int(event.params.get("duration", 0.3) * 1000)
                logger.debug(
                    "[%s] iOS swipe -> (%s, %s) => (%s, %s) pt",
                    self.device_id, from_x, from_y, to_x, to_y,
                )
                actions_payload = {
                    "actions": [
                        {
                            "type": "pointer",
                            "id": "finger1",
                            "parameters": {"pointerType": "touch"},
                            "actions": [
                                {"type": "pointerMove", "duration": 0, "x": from_x, "y": from_y},
                                {"type": "pointerDown", "button": 0},
                                {"type": "pause", "duration": 50},
                                {"type": "pointerMove", "duration": duration_ms, "x": to_x, "y": to_y},
                                {"type": "pointerUp", "button": 0},
                            ],
                        }
                    ]
                }
                return await self._post_wda(f"{base}{session_path}/actions", actions_payload)
            elif event.action == "keyevent":
                key = event.params.get("key", "")
                if key == "home":
                    return await self._post_wda(f"{base}/wda/homescreen")
                elif key == "lock":
                    return await self._post_wda(f"{base}/wda/lock")
                elif key == "volumeUp":
                    session_path = await self._session_path_or_none("volumeUp")
                    if not session_path:
                        return False
                    return await self._post_wda(
                        f"{base}{session_path}/wda/pressButton",
                        {"name": "volumeUp"},
                    )
                elif key == "volumeDown":
                    session_path = await self._session_path_or_none("volumeDown")
                    if not session_path:
                        return False
                    return await self._post_wda(
                        f"{base}{session_path}/wda/pressButton",
                        {"name": "volumeDown"},
                    )
                logger.warning("[%s] 未知 iOS 按键: %s", self.device_id, key)
                return False
            elif event.action == "text":
                text = event.params.get("text", "")
                if text:
                    session_path = await self._session_path_or_none("text")
                    if not session_path:
                        return False
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

    async def get_screenshot(self, log_errors: bool = True) -> bytes:
        if not self._adapter.wda_info or not self._http:
            return b""

        base = f"http://{self._adapter.wda_info.host}:{self._adapter.wda_info.port}"
        try:
            async with self._wda_request_lock:
                async with self._http.get(
                    f"{base}/screenshot",
                    timeout=aiohttp.ClientTimeout(total=3, sock_connect=2),
                ) as resp:
                    if resp.status != 200:
                        return b""
                    data = await resp.json()
                    return base64.b64decode(data.get("value", ""))
        except Exception as err:
            if log_errors:
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

    async def _resolve_ios_version(self) -> None:
        if self._ios_major:
            return
        try:
            info = await self._adapter.get_device_info()
            version = str(info.get("version") or info.get("ProductVersion") or "")
            self._ios_version = version
            self._ios_major = _parse_ios_major(version)
        except Exception as err:
            logger.debug("[%s] iOS version probe failed; keep default MJPEG strategy: %s", self.device_id, err)

    async def _read_mjpeg_loop(self) -> None:
        wda_info = self._adapter.wda_info
        if not wda_info:
            logger.error("[%s] WDA 信息不可用，无法启动 MJPEG 流", self.device_id)
            return

        if self._use_screenshot_stream:
            await self._read_screenshot_loop()
            return

        stream_url = await self._resolve_mjpeg_url(wda_info)
        if not stream_url:
            logger.warning("[%s] No available MJPEG endpoint; fallback to WDA screenshot polling", self.device_id)
            await self._read_screenshot_loop()
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

    async def _read_screenshot_loop(self) -> None:
        interval = 1 / IOS_SCREENSHOT_FALLBACK_FPS
        logger.info(
            "[%s] iOS video uses WDA screenshot fallback (%s fps)",
            self.device_id,
            IOS_SCREENSHOT_FALLBACK_FPS,
        )
        consecutive_failures = 0
        while self._is_mirroring:
            if self._should_pause_screenshot_for_control():
                await asyncio.sleep(0.1)
                continue
            started = time.monotonic()
            frame = await self.get_screenshot(log_errors=False)
            if frame:
                consecutive_failures = 0
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
            else:
                consecutive_failures += 1
                if consecutive_failures == 1 or consecutive_failures % 10 == 0:
                    logger.warning(
                        "[%s] WDA screenshot fallback has no frame, consecutive failures=%s",
                        self.device_id,
                        consecutive_failures,
                    )

            elapsed = time.monotonic() - started
            await asyncio.sleep(max(0.1, interval - elapsed))

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
            f"{base}/mjpegstream",
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

        logger.warning("[%s] 无法探测 MJPEG 端点", self.device_id)
        return None
