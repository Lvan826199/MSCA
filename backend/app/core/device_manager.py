import asyncio
import logging

import adbutils

from app.models.device import DeviceInfo

logger = logging.getLogger(__name__)

POLL_INTERVAL = 2.5  # 秒


class DeviceManager:
    """设备管理器：轮询 ADB + iOS 设备列表，检测插拔变化，通知订阅者。"""

    def __init__(self):
        self._devices: dict[str, DeviceInfo] = {}
        self._subscribers: list[asyncio.Queue] = []
        self._poll_task: asyncio.Task | None = None
        self._ios_enabled = False
        self._ios_adapter_class = None

    @property
    def devices(self) -> list[DeviceInfo]:
        return list(self._devices.values())

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        self._subscribers.remove(q)

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
        """检测 iOS 支持库是否可用。"""
        try:
            from app.drivers.adapters.tidevice_adapter import TideviceAdapter
            self._ios_adapter_class = TideviceAdapter
            self._ios_enabled = True
            logger.info("iOS 支持已启用 (tidevice)")
            return
        except ImportError:
            pass

        try:
            import shutil
            if shutil.which("ios"):
                from app.drivers.adapters.goios_adapter import GoIOSAdapter
                self._ios_adapter_class = GoIOSAdapter
                self._ios_enabled = True
                logger.info("iOS 支持已启用 (go-ios)")
                return
        except Exception:
            pass

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
            for d in adbutils.adb.device_list():
                try:
                    model = d.prop.model or ""
                    version = d.prop.get("ro.build.version.release", "")
                    size = d.shell("wm size").strip()
                    resolution = size.split(": ")[-1] if ": " in size else ""
                except Exception:
                    model, version, resolution = "", "", ""

                devices.append(DeviceInfo(
                    id=d.serial,
                    platform="android",
                    model=model,
                    version=version,
                    resolution=resolution,
                    status="online",
                ))
        except Exception as e:
            logger.error(f"ADB 设备列表获取失败: {e}")
        return devices

    async def _get_ios_devices(self) -> list[DeviceInfo]:
        """获取 iOS 设备列表。"""
        if not self._ios_adapter_class:
            return []

        adapter = self._ios_adapter_class(udid="")
        raw_devices = await adapter.list_devices()

        devices = []
        for d in raw_devices:
            devices.append(DeviceInfo(
                id=d.get("udid", ""),
                platform="ios",
                model=d.get("model", "") or d.get("name", ""),
                version=d.get("version", ""),
                resolution="",
                status="online",
            ))
        return devices

    def create_ios_adapter(self, udid: str):
        """为指定 iOS 设备创建适配器实例。"""
        if not self._ios_adapter_class:
            raise RuntimeError("iOS 支持未启用")
        return self._ios_adapter_class(udid=udid)

    async def _notify(self):
        data = [d.model_dump() for d in self._devices.values()]
        for q in self._subscribers:
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                pass


device_manager = DeviceManager()
