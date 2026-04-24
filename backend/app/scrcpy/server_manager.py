"""ScrcpyServerManager: 管理 scrcpy-server 的推送、启动与 socket 连接。

负责：
1. 将 scrcpy-server jar 推送到设备
2. 通过 ADB 启动 scrcpy-server 进程
3. 建立 video socket（接收 H.264 流）
4. 建立 control socket（发送控制指令）
"""

import asyncio
import logging
import socket
import struct
import time
from pathlib import Path

import adbutils

logger = logging.getLogger(__name__)

# scrcpy-server 二进制文件路径（项目根目录 bin/android/scrcpy-server）
SERVER_JAR_PATH = Path(__file__).resolve().parents[3] / "bin" / "android" / "scrcpy-server"

# 设备端存储路径
DEVICE_SERVER_PATH = "/data/local/tmp/scrcpy-server.jar"

# scrcpy-server 版本
SCRCPY_VERSION = "3.1"

# 默认投屏参数
DEFAULT_MAX_SIZE = 0  # 0 表示不限制
DEFAULT_MAX_FPS = 30
DEFAULT_BITRATE = 8_000_000
DEFAULT_LOCK_VIDEO_ORIENTATION = -1  # -1 表示不锁定

# 连接参数
CONNECT_MAX_RETRIES = 10
CONNECT_RETRY_INTERVAL = 0.5  # 秒
SOCKET_CONNECT_TIMEOUT = 5  # 秒
VIDEO_READ_TIMEOUT = 0.1  # 秒，视频帧读取超时


class ScrcpyServerManager:
    """管理单个设备的 scrcpy-server 生命周期。"""

    def __init__(self, device_serial: str):
        self.device_serial = device_serial
        self._device: adbutils.AdbDevice | None = None
        self._server_stream: adbutils.AdbConnection | None = None
        self._video_socket: socket.socket | None = None
        self._control_socket: socket.socket | None = None
        self._running = False
        self._device_name: str = ""
        self._screen_width: int = 0
        self._screen_height: int = 0
        self._local_port: int = 0

    @property
    def running(self) -> bool:
        return self._running

    @property
    def device_name(self) -> str:
        return self._device_name

    @property
    def screen_size(self) -> tuple[int, int]:
        return self._screen_width, self._screen_height

    async def start(
        self,
        max_size: int = DEFAULT_MAX_SIZE,
        max_fps: int = DEFAULT_MAX_FPS,
        bitrate: int = DEFAULT_BITRATE,
    ) -> None:
        """推送 scrcpy-server 并启动，建立 video/control socket。"""
        if self._running:
            logger.warning(f"[{self.device_serial}] scrcpy-server 已在运行")
            return

        self._device = adbutils.adb.device(serial=self.device_serial)

        try:
            # 1. 推送 scrcpy-server 到设备
            await asyncio.to_thread(self._push_server)

            # 2. 创建 adb forward 隧道
            self._local_port = await asyncio.to_thread(self._setup_forward)

            # 3. 启动 scrcpy-server
            await asyncio.to_thread(self._start_server, max_size, max_fps, bitrate)

            # 4. 带重试地连接 video/control socket
            await asyncio.to_thread(self._connect_sockets_with_retry, self._local_port)

            self._running = True
            logger.info(
                f"[{self.device_serial}] scrcpy-server 已启动 "
                f"(name={self._device_name}, size={self._screen_width}x{self._screen_height})"
            )
        except Exception:
            # 启动失败时清理已分配的资源
            await self._cleanup_resources()
            raise

    def _push_server(self) -> None:
        """推送 scrcpy-server.jar 到设备。"""
        if not SERVER_JAR_PATH.exists():
            raise FileNotFoundError(f"scrcpy-server 不存在: {SERVER_JAR_PATH}")

        logger.info(f"[{self.device_serial}] 推送 scrcpy-server...")
        self._device.sync.push(str(SERVER_JAR_PATH), DEVICE_SERVER_PATH)

    def _setup_forward(self) -> int:
        """创建 ADB 端口转发，返回本地端口号。"""
        local_port = self._device.forward_port("localabstract:scrcpy")
        logger.info(f"[{self.device_serial}] ADB forward → 本地端口 {local_port}")
        return local_port

    def _start_server(self, max_size: int, max_fps: int, bitrate: int) -> None:
        """通过 ADB shell 启动 scrcpy-server。"""
        cmd = (
            f"CLASSPATH={DEVICE_SERVER_PATH} "
            f"app_process / com.genymobile.scrcpy.Server "
            f"{SCRCPY_VERSION} "
            f"tunnel_forward=true "
            f"video=true "
            f"audio=false "
            f"control=true "
            f"max_size={max_size} "
            f"max_fps={max_fps} "
            f"video_bit_rate={bitrate} "
            f"video_codec=h264 "
            f"send_device_meta=true "
            f"send_frame_meta=true "
            f"send_dummy_byte=true "
        )
        logger.info(f"[{self.device_serial}] 启动 scrcpy-server: {cmd}")
        # 使用 shell_stream 保持 server 进程存活
        self._server_stream = self._device.shell(cmd, stream=True)

    def _connect_sockets_with_retry(self, local_port: int) -> None:
        """带重试地连接 video/control socket。

        scrcpy-server 启动需要时间，socket 连接可能暂时失败，
        通过重试机制等待 server 就绪。
        """
        last_error = None
        for attempt in range(1, CONNECT_MAX_RETRIES + 1):
            try:
                self._connect_sockets(local_port)
                return
            except (ConnectionRefusedError, ConnectionError, TimeoutError, OSError) as e:
                last_error = e
                logger.debug(
                    f"[{self.device_serial}] 连接尝试 {attempt}/{CONNECT_MAX_RETRIES} 失败: {e}"
                )
                # 关闭可能半开的 socket
                for sock in (self._video_socket, self._control_socket):
                    if sock:
                        try:
                            sock.close()
                        except Exception:
                            pass
                self._video_socket = None
                self._control_socket = None
                time.sleep(CONNECT_RETRY_INTERVAL)

        raise ConnectionError(
            f"[{self.device_serial}] 连接 scrcpy-server 失败，"
            f"已重试 {CONNECT_MAX_RETRIES} 次: {last_error}"
        )

    def _connect_sockets(self, local_port: int) -> None:
        """连接 video 和 control socket，读取设备元信息。"""
        # 连接 video socket
        self._video_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._video_socket.settimeout(SOCKET_CONNECT_TIMEOUT)
        self._video_socket.connect(("127.0.0.1", local_port))

        # 读取 dummy byte（scrcpy-server 就绪标志）
        dummy = self._video_socket.recv(1)
        if not dummy:
            raise ConnectionError("未收到 dummy byte，scrcpy-server 可能未就绪")

        # 连接 control socket
        self._control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._control_socket.settimeout(SOCKET_CONNECT_TIMEOUT)
        self._control_socket.connect(("127.0.0.1", local_port))

        # 从 video socket 读取设备元信息
        # 设备名称：64 字节 UTF-8 字符串
        meta = self._recv_exact(self._video_socket, 64)
        self._device_name = meta.decode("utf-8").rstrip("\x00")

        # scrcpy v3 codec header: codec_id(4) + width(4) + height(4)
        codec_header = self._recv_exact(self._video_socket, 12)
        _codec_id = struct.unpack(">I", codec_header[0:4])[0]
        self._screen_width = struct.unpack(">I", codec_header[4:8])[0]
        self._screen_height = struct.unpack(">I", codec_header[8:12])[0]

        # video socket 设为阻塞模式 + 短超时，用于后续帧读取
        self._video_socket.settimeout(VIDEO_READ_TIMEOUT)
        # control socket 设为非阻塞
        self._control_socket.setblocking(False)

    @staticmethod
    def _recv_exact(sock: socket.socket, n: int) -> bytes:
        """从 socket 精确读取 n 字节。"""
        data = b""
        while len(data) < n:
            chunk = sock.recv(n - len(data))
            if not chunk:
                raise ConnectionError(f"连接断开，已收到 {len(data)}/{n} 字节")
            data += chunk
        return data

    async def read_video_frame(self) -> bytes | None:
        """读取一个视频帧（带 frame meta）。

        Frame meta 格式（scrcpy v3，send_frame_meta=true）：
        - pts: 8 字节 uint64 大端序（微秒时间戳）
        - packet_size: 4 字节 uint32 大端序

        返回原始 H.264 数据包（不含 meta）。
        """
        if not self._video_socket:
            return None

        try:
            # 读取帧元信息（12 字节：pts 8 + size 4）
            meta = await asyncio.get_event_loop().run_in_executor(
                None, self._recv_exact, self._video_socket, 12
            )
            packet_size = struct.unpack(">I", meta[8:12])[0]

            if packet_size == 0:
                return None

            # 读取 H.264 数据包
            data = await asyncio.get_event_loop().run_in_executor(
                None, self._recv_exact, self._video_socket, packet_size
            )
            return data
        except TimeoutError:
            # socket 超时，无新帧可读
            return None
        except (BlockingIOError, OSError) as e:
            if isinstance(e, OSError) and e.errno not in (10035, 11):
                # 非 EAGAIN/EWOULDBLOCK 的真实错误
                logger.error(f"[{self.device_serial}] 读取视频帧失败: {e}")
            return None
        except Exception as e:
            logger.error(f"[{self.device_serial}] 读取视频帧失败: {e}")
            return None

    async def send_control(self, data: bytes) -> None:
        """向 control socket 发送控制指令。"""
        if not self._control_socket:
            return
        try:
            # control socket 是非阻塞的，临时切为阻塞发送
            self._control_socket.setblocking(True)
            self._control_socket.settimeout(2)
            await asyncio.get_event_loop().run_in_executor(
                None, self._control_socket.sendall, data
            )
            self._control_socket.setblocking(False)
        except Exception as e:
            logger.error(f"[{self.device_serial}] 发送控制指令失败: {e}")

    async def stop(self) -> None:
        """停止 scrcpy-server，释放所有资源。"""
        self._running = False
        await self._cleanup_resources()
        logger.info(f"[{self.device_serial}] scrcpy-server 已停止")

    async def _cleanup_resources(self) -> None:
        """清理所有已分配的资源（socket、server 进程、端口转发）。"""
        for name, sock in [("video", self._video_socket), ("control", self._control_socket)]:
            if sock:
                try:
                    sock.close()
                except Exception as e:
                    logger.debug(f"[{self.device_serial}] 关闭 {name} socket: {e}")

        self._video_socket = None
        self._control_socket = None

        if self._server_stream:
            try:
                self._server_stream.close()
            except Exception:
                pass
            self._server_stream = None

        # 移除端口转发
        if self._device and self._local_port:
            try:
                await asyncio.to_thread(
                    self._device.forward_remove, f"tcp:{self._local_port}"
                )
            except Exception:
                pass
            self._local_port = 0
