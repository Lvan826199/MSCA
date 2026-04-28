"""iOS 适配器基类。

定义 Tidevice 和 go-ios 共用的接口，统一 WDA 管理、端口转发、设备信息获取。
"""

import json
import logging
import os
import socket
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ─── WDA 配置加载 ───

_wda_config_cache: dict | None = None


def load_wda_config() -> dict:
    """加载 WDA 配置（backend/config/wda_config.json），带缓存。"""
    global _wda_config_cache
    if _wda_config_cache is not None:
        return _wda_config_cache

    # backend/app/drivers/adapters/base.py → backend/config/wda_config.json
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.normpath(os.path.join(base_dir, "..", "..", "..", "config", "wda_config.json"))

    defaults = {
        "wda_bundle_id": "",
        "wda_bundle_id_pattern": "com.*.xctrunner",
        "mjpeg_port_on_device": 9100,
        "wda_port_on_device": 8100,
    }

    if os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            defaults.update({k: v for k, v in data.items() if k in defaults})
            logger.info(f"WDA 配置已加载: {config_path}")
        except Exception as e:
            logger.warning(f"WDA 配置加载失败，使用默认值: {e}")
    else:
        logger.info("WDA 配置文件不存在，使用默认值")

    _wda_config_cache = defaults
    return defaults


def reload_wda_config() -> dict:
    """强制重新加载 WDA 配置。"""
    global _wda_config_cache
    _wda_config_cache = None
    return load_wda_config()


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
    mjpeg_port: int = 0  # MJPEG 流本地端口（设备端 9100 转发到此端口）
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
    async def start_wda(self, port: int = 8100, mjpeg_port: int = 0) -> WDAInfo:
        """启动 WDA 服务并建立端口转发。

        Args:
            port: WDA API 本地监听端口
            mjpeg_port: MJPEG 流本地监听端口（转发设备端 9100）

        Returns:
            WDA 服务信息（含 mjpeg_port）
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
                    if resp.status == 200:
                        logger.debug(f"[{self.udid}] WDA 健康检查通过 @ {url}")
                        return True
                    logger.debug(f"[{self.udid}] WDA 健康检查返回 {resp.status}")
                    return False
        except Exception as e:
            logger.debug(f"[{self.udid}] WDA 健康检查失败: {e}")
            return False

    async def detect_wda_bundle_id(self) -> str:
        """自动检测设备上已安装的 WDA bundle ID。

        参考 tidevice 的 fnmatch 模糊匹配方式（com.*.xctrunner）。
        子类可覆盖此方法提供平台特定实现。
        """
        return ""
