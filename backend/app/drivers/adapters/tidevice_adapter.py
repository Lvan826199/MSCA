"""Tidevice 适配器 — 支持 iOS ≤15.x 设备。

通过 tidevice 库管理 WDA 服务、端口转发和设备信息获取。
核心改进：
- 分别转发 WDA API（设备 8100）和 MJPEG 流（设备 9100）到不同本地端口
- 支持 WDA bundle ID 自动检测（fnmatch 模糊匹配，参考 tidevice/Airtest）
"""

import asyncio
import fnmatch
import logging
import subprocess

from .base import IOSAdapterBase, WDAInfo, load_wda_config, is_port_free, kill_process_on_port

logger = logging.getLogger(__name__)


class TideviceAdapter(IOSAdapterBase):
    """基于 tidevice 的 iOS 适配器，适用于 iOS ≤15.x。"""

    def __init__(self, udid: str):
        super().__init__(udid)
        self._proxy_process: subprocess.Popen | None = None
        self._mjpeg_relay_process: subprocess.Popen | None = None
        self._relay_processes: list[subprocess.Popen] = []

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

    async def detect_wda_bundle_id(self) -> str:
        """自动检测设备上已安装的 WDA bundle ID（参考 tidevice fnmatch 方式）。"""
        config = load_wda_config()
        configured = config.get("wda_bundle_id", "")
        if configured:
            logger.info(f"[{self.udid}] 使用配置的 WDA bundle ID: {configured}")
            return configured

        pattern = config.get("wda_bundle_id_pattern", "com.*.xctrunner")
        try:
            import tidevice
            td = tidevice.Device(self.udid)
            bundle_ids = []
            for binfo in td.installation.iter_installed(attrs=['CFBundleIdentifier']):
                bid = binfo.get('CFBundleIdentifier', '')
                if fnmatch.fnmatch(bid, pattern):
                    bundle_ids.append(bid)
            if bundle_ids:
                # 优先选择非 facebook 的（用户自定义签名的 WDA）
                bundle_ids.sort(key=lambda x: 'facebook' in x.lower())
                logger.info(f"[{self.udid}] 自动检测到 WDA bundle ID: {bundle_ids[0]} (候选: {bundle_ids})")
                return bundle_ids[0]
            logger.warning(f"[{self.udid}] 未找到匹配 '{pattern}' 的 WDA，将使用默认值")
        except Exception as e:
            logger.warning(f"[{self.udid}] WDA bundle ID 检测失败: {e}")
        return ""

    async def start_wda(self, port: int = 8100, mjpeg_port: int = 0) -> WDAInfo:
        """启动 WDA 代理 + MJPEG 端口转发。"""
        await self.stop_wda()
        config = load_wda_config()
        mjpeg_device_port = config.get("mjpeg_port_on_device", 9100)

        # 确保端口空闲
        if not is_port_free(port):
            logger.warning(f"[{self.udid}] WDA 端口 {port} 被占用，尝试清理")
            kill_process_on_port(port)
            await asyncio.sleep(0.5)
            if not is_port_free(port):
                raise RuntimeError(f"端口 {port} 仍被占用")

        if mjpeg_port and not is_port_free(mjpeg_port):
            logger.warning(f"[{self.udid}] MJPEG 端口 {mjpeg_port} 被占用，尝试清理")
            kill_process_on_port(mjpeg_port)
            await asyncio.sleep(0.3)

        logger.info(f"[{self.udid}] tidevice start_wda: WDA={port}, MJPEG={mjpeg_port}, 设备MJPEG={mjpeg_device_port}")

        # 先尝试 relay 模式
        if await self._try_relay_mode(port, mjpeg_port, mjpeg_device_port):
            return self.wda_info

        # WDA 未在运行，启动完整的 wdaproxy
        return await self._start_wdaproxy(port, mjpeg_port, mjpeg_device_port)

    async def _try_relay_mode(self, port: int, mjpeg_port: int, mjpeg_device_port: int) -> bool:
        """尝试 relay 模式：端口转发到设备 8100，检测 WDA 是否已在运行。"""
        logger.info(f"[{self.udid}] 尝试 relay 模式（检测 WDA 是否已在设备上运行）")
        self._proxy_process = subprocess.Popen(
            ["tidevice", "-u", self.udid, "relay", str(port), "8100"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

        for attempt in range(5):
            await asyncio.sleep(0.5)
            if self._proxy_process.poll() is not None:
                logger.debug(f"[{self.udid}] relay 进程退出，WDA 可能未在运行")
                self._proxy_process = None
                return False

            self.wda_info = WDAInfo(host="127.0.0.1", port=port, mjpeg_port=mjpeg_port)
            if await self.check_wda_health():
                logger.info(f"[{self.udid}] WDA 已在设备上运行，relay 模式就绪 @ {port}")
                if mjpeg_port:
                    await self._start_mjpeg_relay(mjpeg_port, mjpeg_device_port)
                return True

        logger.debug(f"[{self.udid}] relay 模式超时，WDA 未在设备上运行")
        self._kill_process(self._proxy_process)
        self._proxy_process = None
        self.wda_info = None
        return False

    async def _start_wdaproxy(self, port: int, mjpeg_port: int, mjpeg_device_port: int) -> WDAInfo:
        """启动完整的 wdaproxy（启动 WDA + 端口转发）。"""
        bundle_id = await self.detect_wda_bundle_id()
        cmd = ["tidevice", "-u", self.udid, "wdaproxy", "-p", str(port)]
        if bundle_id:
            cmd.extend(["-B", bundle_id])
            logger.info(f"[{self.udid}] 启动 wdaproxy，端口 {port}，bundle ID: {bundle_id}")
        else:
            logger.info(f"[{self.udid}] 启动 wdaproxy，端口 {port}（默认 bundle ID）")

        self._proxy_process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

        for i in range(30):
            await asyncio.sleep(1)
            if self._proxy_process.poll() is not None:
                stderr = self._proxy_process.stderr.read().decode(errors='replace') if self._proxy_process.stderr else ""
                raise RuntimeError(f"WDA 代理进程退出: {stderr[:500]}")

            self.wda_info = WDAInfo(host="127.0.0.1", port=port, mjpeg_port=mjpeg_port)
            if await self.check_wda_health():
                logger.info(f"[{self.udid}] WDA 就绪 @ {port}")
                if mjpeg_port:
                    await self._start_mjpeg_relay(mjpeg_port, mjpeg_device_port)
                return self.wda_info

        raise TimeoutError(f"[{self.udid}] WDA 启动超时（30s）")

    async def _start_mjpeg_relay(self, mjpeg_port: int, mjpeg_device_port: int) -> None:
        """启动 MJPEG 端口转发（设备端 9100 → 本地 mjpeg_port）。"""
        logger.info(f"[{self.udid}] 启动 MJPEG relay: 本地 {mjpeg_port} → 设备 {mjpeg_device_port}")
        self._mjpeg_relay_process = subprocess.Popen(
            ["tidevice", "-u", self.udid, "relay", str(mjpeg_port), str(mjpeg_device_port)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        await asyncio.sleep(0.5)
        if self._mjpeg_relay_process.poll() is not None:
            stderr = ""
            if self._mjpeg_relay_process.stderr:
                stderr = self._mjpeg_relay_process.stderr.read().decode(errors='replace')
            logger.warning(f"[{self.udid}] MJPEG relay 进程立即退出: {stderr[:300]}")
            self._mjpeg_relay_process = None
        else:
            logger.info(f"[{self.udid}] MJPEG relay 已启动 @ {mjpeg_port}")

    def _kill_process(self, proc: subprocess.Popen | None) -> None:
        """安全终止子进程。"""
        if not proc:
            return
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    async def stop_wda(self) -> None:
        """停止 WDA 代理和 MJPEG relay 进程。"""
        self._kill_process(self._proxy_process)
        self._proxy_process = None
        self._kill_process(self._mjpeg_relay_process)
        self._mjpeg_relay_process = None
        self.wda_info = None
        logger.debug(f"[{self.udid}] tidevice 所有子进程已清理")

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
