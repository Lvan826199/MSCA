"""投屏 REST API：启动/停止投屏、查询投屏状态。

支持 Android（scrcpy H.264）和 iOS（WDA MJPEG）设备。
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core.device_manager import device_manager
from ..drivers.android import AndroidDriver
from ..drivers.base import AbstractDeviceDriver, MirrorOptions

logger = logging.getLogger(__name__)

router = APIRouter()

# 全局驱动实例注册表：device_serial → Driver
_drivers: dict[str, AbstractDeviceDriver] = {}


def get_driver(device_id: str) -> AbstractDeviceDriver:
    """获取或创建设备驱动实例（自动识别平台）。"""
    if device_id not in _drivers:
        # 查询设备平台
        device_info = None
        for d in device_manager.devices:
            if d.id == device_id:
                device_info = d
                break

        if device_info and device_info.platform == "ios":
            from ..drivers.ios import IOSDriver
            adapter = device_manager.create_ios_adapter(device_id)
            _drivers[device_id] = IOSDriver(device_id, adapter)
        else:
            _drivers[device_id] = AndroidDriver(device_id)
    return _drivers[device_id]


def get_active_driver(device_id: str) -> AbstractDeviceDriver:
    """获取正在投屏的驱动实例，不存在则抛 404。"""
    driver = _drivers.get(device_id)
    if not driver or not driver.is_mirroring:
        raise HTTPException(status_code=404, detail=f"设备 {device_id} 未在投屏")
    return driver


class MirrorStartRequest(BaseModel):
    max_fps: int = 30
    bitrate: int = 8_000_000
    max_size: int = 0

    def validated(self) -> "MirrorStartRequest":
        """校验参数范围。"""
        self.max_fps = max(1, min(self.max_fps, 120))
        self.bitrate = max(100_000, min(self.bitrate, 50_000_000))
        self.max_size = max(0, min(self.max_size, 4096))
        return self


class MirrorStatusResponse(BaseModel):
    device_id: str
    mirroring: bool
    screen_width: int = 0
    screen_height: int = 0


@router.post("/mirror/{device_id}/start")
async def start_mirror(device_id: str, req: MirrorStartRequest | None = None):
    """启动设备投屏。"""
    if req is None:
        req = MirrorStartRequest()
    req = req.validated()

    driver = get_driver(device_id)
    if driver.is_mirroring:
        w, h = driver.screen_size
        return {"status": "already_mirroring", "device_id": device_id, "width": w, "height": h}

    try:
        options = MirrorOptions(
            max_fps=req.max_fps,
            bitrate=req.bitrate,
            width=req.max_size,
            height=req.max_size,
        )
        await driver.start_mirroring(options)
        device_manager.mark_mirror_success(device_id)
        w, h = driver.screen_size
        return {"status": "started", "device_id": device_id, "width": w, "height": h}
    except FileNotFoundError as e:
        device_manager.mark_mirror_failure(device_id)
        raise HTTPException(status_code=500, detail=str(e)) from None
    except ConnectionError as e:
        device_manager.mark_mirror_failure(device_id)
        raise HTTPException(status_code=502, detail=f"连接设备失败: {e}") from None
    except Exception as e:
        device_manager.mark_mirror_failure(device_id)
        logger.error(f"启动投屏失败 [{device_id}]: {e}")
        raise HTTPException(status_code=500, detail=f"启动投屏失败: {e}") from None


@router.post("/mirror/{device_id}/stop")
async def stop_mirror(device_id: str):
    """停止设备投屏。"""
    driver = _drivers.get(device_id)
    if not driver or not driver.is_mirroring:
        return {"status": "not_mirroring", "device_id": device_id}

    await driver.stop_mirroring()
    _drivers.pop(device_id, None)
    return {"status": "stopped", "device_id": device_id}


@router.get("/mirror/{device_id}/status")
async def mirror_status(device_id: str) -> MirrorStatusResponse:
    """查询设备投屏状态。"""
    driver = _drivers.get(device_id)
    if not driver or not driver.is_mirroring:
        return MirrorStatusResponse(device_id=device_id, mirroring=False)

    w, h = driver.screen_size
    return MirrorStatusResponse(
        device_id=device_id, mirroring=True, screen_width=w, screen_height=h
    )


@router.get("/mirror/sessions")
async def list_sessions():
    """列出所有活跃投屏会话。"""
    sessions = []
    for device_id, driver in _drivers.items():
        if driver.is_mirroring:
            w, h = driver.screen_size
            sessions.append({
                "device_id": device_id,
                "screen_width": w,
                "screen_height": h,
            })
    return {"sessions": sessions}


@router.post("/mirror/stop-all")
async def stop_all_mirrors():
    """批量停止所有投屏会话，每个设备独立处理异常。"""
    results = []
    device_ids = list(_drivers.keys())
    for device_id in device_ids:
        driver = _drivers.get(device_id)
        if not driver:
            continue
        try:
            await driver.stop_mirroring()
            results.append({"device_id": device_id, "status": "stopped"})
        except Exception as e:
            logger.error(f"停止投屏失败 [{device_id}]: {e}")
            results.append({"device_id": device_id, "status": "error", "detail": str(e)})
        finally:
            _drivers.pop(device_id, None)
    return {"results": results}
