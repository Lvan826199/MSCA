"""Tidevice 适配器 — 支持 iOS ≤15.x 设备。

通过 tidevice 库管理 WDA 服务、端口转发和设备信息获取。
"""

import asyncio
import logging
import subprocess

from .base import IOSAdapterBase, WDAInfo, is_port_free, kill_process_on_port

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
            logger.error(f"[{self.udid}] WDA 安装失败: {stderr.decode(errors='replace')}")
            return False
        except Exception as e:
            logger.error(f"[{self.udid}] WDA 安装异常: {e}")
            return False

    async def start_wda(self, port: int = 8100) -> WDAInfo:
        """启动 WDA 代理。

        策略：先检测设备上 WDA 是否已在运行（用户手动启动的场景），
        如果已运行则只做端口转发（relay），否则启动完整的 wdaproxy。
        """
        await self.stop_wda()

        # 确保端口空闲，否则尝试杀掉残留进程
        if not is_port_free(port):
            logger.warning(f"[{self.udid}] 端口 {port} 被占用，尝试清理残留进程")
            kill_process_on_port(port)
            await asyncio.sleep(0.5)
            if not is_port_free(port):
                raise RuntimeError(f"端口 {port} 仍被占用，无法启动 WDA 代理")

        # 先尝试 relay 模式：如果设备上 WDA 已在运行，只需端口转发即可
        if await self._try_relay_mode(port):
            return self.wda_info

        # WDA 未在运行，启动完整的 wdaproxy
        return await self._start_wdaproxy(port)

    async def _try_relay_mode(self, port: int) -> bool:
        """尝试 relay 模式：端口转发到设备 8100，检测 WDA 是否已在运行。"""
        logger.info(f"[{self.udid}] 尝试 relay 模式（检测 WDA 是否已在设备上运行）")
        self._proxy_process = subprocess.Popen(
            ["tidevice", "-u", self.udid, "relay", str(port), "8100"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # 等待 relay 进程启动并检测 WDA 健康
        for _ in range(5):
            await asyncio.sleep(0.5)
            if self._proxy_process.poll() is not None:
                # relay 进程退出了，说明端口转发失败
                logger.debug(f"[{self.udid}] relay 进程退出，WDA 可能未在运行")
                self._proxy_process = None
                return False

            self.wda_info = WDAInfo(host="127.0.0.1", port=port)
            if await self.check_wda_health():
                logger.info(f"[{self.udid}] WDA 已在设备上运行，relay 模式就绪 @ {port}")
                return True

        # 超时，WDA 未响应，清理 relay 进程
        logger.debug(f"[{self.udid}] relay 模式超时，WDA 未在设备上运行")
        if self._proxy_process:
            try:
                self._proxy_process.terminate()
                self._proxy_process.wait(timeout=3)
            except Exception:
                try:
                    self._proxy_process.kill()
                except Exception:
                    pass
            self._proxy_process = None
        self.wda_info = None
        return False

    async def _start_wdaproxy(self, port: int) -> WDAInfo:
        """启动完整的 wdaproxy（启动 WDA + 端口转发）。"""
        logger.info(f"[{self.udid}] 启动 WDA 代理（wdaproxy），端口 {port}")
        self._proxy_process = subprocess.Popen(
            ["tidevice", "-u", self.udid, "wdaproxy", "-p", str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # 等待 WDA 就绪
        for i in range(30):
            await asyncio.sleep(1)
            if self._proxy_process.poll() is not None:
                stderr = self._proxy_process.stderr.read().decode(errors='replace') if self._proxy_process.stderr else ""
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

    async def install_app(self, ipa_path: str) -> tuple[bool, str]:
        """安装 IPA 到 iOS 设备（通过 tidevice）。"""
        try:
            import tidevice

            td = tidevice.Device(self.udid)
            await asyncio.get_event_loop().run_in_executor(
                None, td.app_install, ipa_path
            )
            logger.info(f"[{self.udid}] IPA 安装成功 (tidevice)")
            return True, "IPA 安装成功"
        except Exception as e:
            return False, str(e)
