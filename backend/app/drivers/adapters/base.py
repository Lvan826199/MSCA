"""iOS 适配器基类。

定义 Tidevice 和 go-ios 共用的接口，统一 WDA 管理、端口转发、设备信息获取。
"""

import logging
import os
import socket
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def is_port_free(port: int) -> bool:
    """检查本地端口是否空闲。"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))
            return True
    except OSError:
        return False


def kill_process_on_port(port: int) -> None:
    """尝试杀掉占用指定端口的进程（跨平台）。"""
    try:
        if os.name == "nt":
            # Windows: netstat + taskkill
            result = subprocess.run(
                ["netstat", "-ano", "-p", "TCP"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                if f"127.0.0.1:{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    pid = int(parts[-1])
                    if pid > 0:
                        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                                       capture_output=True, timeout=5)
                        logger.info(f"已杀掉占用端口 {port} 的进程 PID={pid}")
        else:
            # macOS / Linux: lsof + kill
            result = subprocess.run(
                ["lsof", "-ti", f"tcp:{port}"],
                capture_output=True, text=True, timeout=5,
            )
            for pid_str in result.stdout.strip().splitlines():
                pid = int(pid_str.strip())
                if pid > 0:
                    subprocess.run(["kill", "-9", str(pid)],
                                   capture_output=True, timeout=5)
                    logger.info(f"已杀掉占用端口 {port} 的进程 PID={pid}")
    except Exception as e:
        logger.debug(f"清理端口 {port} 失败: {e}")


@dataclass
class WDAInfo:
    """WDA 服务信息。"""

    host: str = "127.0.0.1"
    port: int = 8100
    session_id: str = ""


class IOSAdapterBase(ABC):
    """iOS 平台适配器基类。"""

    def __init__(self, udid: str):
        self.udid = udid
        self.wda_info: WDAInfo | None = None
        self._wda_process = None

    @abstractmethod
    async def list_devices(self) -> list[dict]:
        """列出所有已连接的 iOS 设备。

        Returns:
            [{"udid": "...", "name": "...", "version": "...", "model": "..."}]
        """

    @abstractmethod
    async def install_wda(self, ipa_path: str) -> bool:
        """安装 WDA 到设备。"""

    @abstractmethod
    async def start_wda(self, port: int = 8100) -> WDAInfo:
        """启动 WDA 服务并建立端口转发。

        Args:
            port: 本地监听端口

        Returns:
            WDA 服务信息
        """

    @abstractmethod
    async def stop_wda(self) -> None:
        """停止 WDA 服务并释放端口转发。"""

    @abstractmethod
    async def get_device_info(self) -> dict:
        """获取设备详细信息（型号、版本等）。"""

    async def check_wda_health(self) -> bool:
        """检查 WDA 服务是否健康。"""
        if not self.wda_info:
            return False
        import aiohttp

        try:
            url = f"http://{self.wda_info.host}:{self.wda_info.port}/status"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                    return resp.status == 200
        except Exception:
            return False
