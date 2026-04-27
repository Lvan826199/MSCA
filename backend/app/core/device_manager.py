import asyncio
import logging
import os
import shutil

import adbutils

from app.models.device import DeviceInfo

logger = logging.getLogger(__name__)

POLL_INTERVAL = 2.5  # 秒

# iOS 版本阈值：≤15.x 用 tidevice，≥16.x 用 go-ios
IOS_GOIOS_MIN_VERSION = 16


def _parse_ios_major(version: str) -> int:
    """解析 iOS 版本号的主版本。"""
    try:
        return int(version.split(".")[0])
    except (ValueError, IndexError):
        return 0


def _find_goios_bin() -> str:
    """查找 go-ios 可执行文件路径。

    查找顺序：
    1. MSCA_RESOURCES_PATH 环境变量（Electron 打包后传入）
    2. 项目内 bin/ios/ios.exe（开发模式）
    3. 系统 PATH
    """
    # Electron 打包后的资源路径
    res_path = os.environ.get("MSCA_RESOURCES_PATH", "")
    if res_path:
        packaged_bin = os.path.join(res_path, "bin", "ios", "ios.exe")
        if os.path.isfile(packaged_bin):
            return packaged_bin

    # 开发模式：项目根目录（backend/ 的上一级）
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    project_root = os.path.dirname(backend_dir)
    local_bin = os.path.join(project_root, "bin", "ios", "ios.exe")
    if os.path.isfile(local_bin):
        return local_bin

    # 系统 PATH
    system_bin = shutil.which("ios")
    if system_bin:
        return system_bin
    return ""


class DeviceManager:
    """设备管理器：轮询 ADB + iOS 设备列表，检测插拔变化，通知订阅者。

    同时支持 tidevice（iOS ≤15.x）和 go-ios（iOS ≥16.x），根据设备版本自动选择。
    """

    def __init__(self):
        self._devices: dict[str, DeviceInfo] = {}
        self._subscribers: list[asyncio.Queue] = []
        self._poll_task: asyncio.Task | None = None
        self._ios_enabled = False
        self._tidevice_available = False
        self._goios_available = False
        self._goios_bin = ""
        # 缓存已知 ADB 设备的属性（model, version, resolution），避免每次轮询都执行 shell 命令
        self._adb_device_cache: dict[str, dict] = {}

    @property
    def devices(self) -> list[DeviceInfo]:
        return list(self._devices.values())

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    def start(self):
        if self._poll_task is None:
            self._detect_ios_support()
            self._poll_task = asyncio.create_task(self._poll_loop())
            logger.info("DeviceManager 轮询已启动")

    def stop(self):
        if self._poll_task:
            self._poll_task.cancel()
            self._poll_task = None

    async def refresh(self) -> list[DeviceInfo]:
        """手动刷新一次设备列表。"""
        await self._scan()
        return self.devices

    def _detect_ios_support(self):
        """检测 iOS 支持库是否可用（tidevice 和 go-ios 可同时启用）。"""
        # 检测 tidevice
        try:
            import tidevice  # noqa: F401
            self._tidevice_available = True
            logger.info("iOS 支持: tidevice 可用（适用于 iOS ≤15.x）")
        except ImportError:
            logger.info("iOS 支持: tidevice 不可用")

        # 检测 go-ios
        self._goios_bin = _find_goios_bin()
        if self._goios_bin:
            self._goios_available = True
            logger.info(f"iOS 支持: go-ios 可用 @ {self._goios_bin}（适用于 iOS ≥16.x）")
        else:
            logger.info("iOS 支持: go-ios 不可用")

        self._ios_enabled = self._tidevice_available or self._goios_available
        if not self._ios_enabled:
            logger.info("iOS 支持未启用（tidevice 和 go-ios 均不可用）")

    async def _poll_loop(self):
        while True:
            try:
                await self._scan()
            except Exception as e:
                logger.error(f"设备扫描异常: {e}")
            await asyncio.sleep(POLL_INTERVAL)

    async def _scan(self):
        # Android 设备
        android_devices = await asyncio.to_thread(self._get_adb_devices)

        # iOS 设备
        ios_devices = []
        if self._ios_enabled:
            try:
                ios_devices = await self._get_ios_devices()
            except Exception as e:
                logger.debug(f"iOS 设备扫描失败: {e}")

        current = android_devices + ios_devices
        current_ids = {d.id for d in current}
        old_ids = set(self._devices.keys())

        changed = current_ids != old_ids
        if not changed:
            return

        self._devices = {d.id: d for d in current}
        await self._notify()

    def _get_adb_devices(self) -> list[DeviceInfo]:
        devices = []
        try:
            current_serials = set()
            for d in adbutils.adb.device_list():
                serial = d.serial
                current_serials.add(serial)

                # 使用缓存的属性，避免投屏期间频繁执行 ADB shell 命令
                cached = self._adb_device_cache.get(serial)
                if cached:
                    model = cached["model"]
                    version = cached["version"]
                    resolution = cached["resolution"]
                else:
                    try:
                        model = d.prop.model or ""
                        version = d.prop.get("ro.build.version.release", "")
                        size = d.shell("wm size").strip()
                        resolution = size.split(": ")[-1] if ": " in size else ""
                    except Exception:
                        model, version, resolution = "", "", ""
                    self._adb_device_cache[serial] = {
                        "model": model,
                        "version": version,
                        "resolution": resolution,
                    }

                devices.append(DeviceInfo(
                    id=serial,
                    platform="android",
                    model=model,
                    version=version,
                    resolution=resolution,
                    status="online",
                ))

            # 清理已断开设备的缓存
            for stale in set(self._adb_device_cache) - current_serials:
                del self._adb_device_cache[stale]

        except Exception as e:
            logger.error(f"ADB 设备列表获取失败: {e}")
        return devices

    async def _get_ios_devices(self) -> list[DeviceInfo]:
        """获取 iOS 设备列表（合并 tidevice 和 go-ios 结果，去重）。"""
        seen_udids: set[str] = set()
        devices: list[DeviceInfo] = []

        # tidevice 扫描
        if self._tidevice_available:
            try:
                from app.drivers.adapters.tidevice_adapter import TideviceAdapter
                adapter = TideviceAdapter(udid="")
                for d in await adapter.list_devices():
                    udid = d.get("udid", "")
                    if not udid or udid in seen_udids:
                        continue
                    seen_udids.add(udid)
                    devices.append(DeviceInfo(
                        id=udid,
                        platform="ios",
                        model=d.get("model", "") or d.get("name", ""),
                        version=d.get("version", ""),
                        resolution="",
                        status="online",
                    ))
            except Exception as e:
                logger.debug(f"tidevice 设备扫描失败: {e}")

        # go-ios 扫描（补充 tidevice 未发现的设备）
        if self._goios_available:
            try:
                from app.drivers.adapters.goios_adapter import GoIOSAdapter
                adapter = GoIOSAdapter(udid="", ios_bin=self._goios_bin)
                for d in await adapter.list_devices():
                    udid = d.get("udid", "")
                    if not udid or udid in seen_udids:
                        continue
                    seen_udids.add(udid)
                    devices.append(DeviceInfo(
                        id=udid,
                        platform="ios",
                        model=d.get("model", "") or d.get("name", ""),
                        version=d.get("version", ""),
                        resolution="",
                        status="online",
                    ))
            except Exception as e:
                logger.debug(f"go-ios 设备扫描失败: {e}")

        return devices

    def create_ios_adapter(self, udid: str, version: str = ""):
        """为指定 iOS 设备创建适配器实例，根据版本自动选择。

        Args:
            udid: 设备 UDID
            version: iOS 版本号（如 "15.1"、"18.3"），为空时从已知设备中查找
        """
        # 尝试从已知设备中获取版本
        if not version:
            dev = self._devices.get(udid)
            if dev:
                version = dev.version

        major = _parse_ios_major(version)

        # iOS ≤15.x 优先 tidevice，≥16.x 优先 go-ios
        if major > 0 and major < IOS_GOIOS_MIN_VERSION:
            if self._tidevice_available:
                from app.drivers.adapters.tidevice_adapter import TideviceAdapter
                return TideviceAdapter(udid=udid)
            elif self._goios_available:
                logger.warning(f"[{udid}] iOS {version} 推荐 tidevice，但不可用，回退到 go-ios")
                from app.drivers.adapters.goios_adapter import GoIOSAdapter
                return GoIOSAdapter(udid=udid, ios_bin=self._goios_bin)
        else:
            if self._goios_available:
                from app.drivers.adapters.goios_adapter import GoIOSAdapter
                return GoIOSAdapter(udid=udid, ios_bin=self._goios_bin)
            elif self._tidevice_available:
                logger.warning(f"[{udid}] iOS {version} 推荐 go-ios，但不可用，回退到 tidevice")
                from app.drivers.adapters.tidevice_adapter import TideviceAdapter
                return TideviceAdapter(udid=udid)

        raise RuntimeError("iOS 支持未启用（tidevice 和 go-ios 均不可用）")

    async def _notify(self):
        data = [d.model_dump() for d in self._devices.values()]
        for q in list(self._subscribers):
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                pass


device_manager = DeviceManager()
