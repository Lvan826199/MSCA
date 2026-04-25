"""Tidevice 适配器 — 支持 iOS ≤15.x 设备。

通过 tidevice 库管理 WDA 服务、端口转发和设备信息获取。
"""

import asyncio
import logging
import subprocess

from .base import IOSAdapterBase, WDAInfo

logger = logging.getLogger(__name__)


class TideviceAdapter(IOSAdapterBase):
    """基于 tidevice 的 iOS 适配器，适用于 iOS ≤15.x。"""

    def __init__(self, udid: str):
        super().__init__(udid)
        self._proxy_process: subprocess.Popen | None = None

    async def list_devices(self) -> list[dict]:
        """通过 tidevice 列出已连接的 iOS 设备。"""
        try:
            import tidevice

            t = tidevice.Usbmux()
            devices = []
            for d in t.device_list():
                udid = d.udid
                try:
                    td = tidevice.Device(udid)
                    info = td.device_info()
                    devices.append({
                        "udid": udid,
                        "name": info.get("DeviceName", ""),
                        "version": info.get("ProductVersion", ""),
                        "model": info.get("ProductType", ""),
                    })
                except Exception as e:
                    logger.warning(f"获取 iOS 设备信息失败 [{udid}]: {e}")
                    devices.append({"udid": udid, "name": "", "version": "", "model": ""})
            return devices
        except ImportError:
            logger.warning("tidevice 未安装，无法发现 iOS 设备")
            return []
        except Exception as e:
            logger.error(f"tidevice 设备列表获取失败: {e}")
            return []

    async def install_wda(self, ipa_path: str) -> bool:
        """通过 tidevice 安装 WDA。"""
        try:
            proc = await asyncio.create_subprocess_exec(
                "tidevice", "-u", self.udid, "install", ipa_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            if proc.returncode == 0:
                logger.info(f"[{self.udid}] WDA 安装成功")
                return True
            logger.error(f"[{self.udid}] WDA 安装失败: {stderr.decode()}")
            return False
        except Exception as e:
            logger.error(f"[{self.udid}] WDA 安装异常: {e}")
            return False

    async def start_wda(self, port: int = 8100) -> WDAInfo:
        """启动 WDA 代理（wdaproxy），自动建立端口转发。"""
        await self.stop_wda()

        logger.info(f"[{self.udid}] 启动 WDA 代理，端口 {port}")
        self._proxy_process = subprocess.Popen(
            ["tidevice", "-u", self.udid, "wdaproxy", "-p", str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # 等待 WDA 就绪
        for i in range(30):
            await asyncio.sleep(1)
            if self._proxy_process.poll() is not None:
                stderr = self._proxy_process.stderr.read().decode() if self._proxy_process.stderr else ""
                raise RuntimeError(f"WDA 代理进程退出: {stderr}")

            self.wda_info = WDAInfo(host="127.0.0.1", port=port)
            if await self.check_wda_health():
                logger.info(f"[{self.udid}] WDA 就绪 @ {port}")
                return self.wda_info

        raise TimeoutError(f"[{self.udid}] WDA 启动超时（30s）")

    async def stop_wda(self) -> None:
        """停止 WDA 代理进程。"""
        if self._proxy_process:
            try:
                self._proxy_process.terminate()
                self._proxy_process.wait(timeout=5)
            except Exception:
                try:
                    self._proxy_process.kill()
                except Exception:
                    pass
            self._proxy_process = None
        self.wda_info = None

    async def get_device_info(self) -> dict:
        """获取设备详细信息。"""
        try:
            import tidevice

            td = tidevice.Device(self.udid)
            info = td.device_info()
            return {
                "udid": self.udid,
                "name": info.get("DeviceName", ""),
                "version": info.get("ProductVersion", ""),
                "model": info.get("ProductType", ""),
                "serial": info.get("SerialNumber", ""),
            }
        except Exception as e:
            logger.error(f"[{self.udid}] 获取设备信息失败: {e}")
            return {"udid": self.udid}
