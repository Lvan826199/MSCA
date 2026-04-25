"""投屏 REST API：启动/停止投屏、查询投屏状态。"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.drivers.android import AndroidDriver
from app.drivers.base import MirrorOptions

logger = logging.getLogger(__name__)

router = APIRouter()

# 全局驱动实例注册表：device_serial → AndroidDriver
_drivers: dict[str, AndroidDriver] = {}


def get_driver(device_id: str) -> AndroidDriver:
    """获取或创建设备驱动实例。"""
    if device_id not in _drivers:
        _drivers[device_id] = AndroidDriver(device_id)
    return _drivers[device_id]


def get_active_driver(device_id: str) -> AndroidDriver:
    """获取正在投屏的驱动实例，不存在则抛 404。"""
    driver = _drivers.get(device_id)
    if not driver or not driver.is_mirroring:
        raise HTTPException(status_code=404, detail=f"设备 {device_id} 未在投屏")
    return driver


class MirrorStartRequest(BaseModel):
    max_fps: int = 30
    bitrate: int = 8_000_000
    max_size: int = 0


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
        w, h = driver.screen_size
        return {"status": "started", "device_id": device_id, "width": w, "height": h}
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e)) from None
    except ConnectionError as e:
        raise HTTPException(status_code=502, detail=f"连接设备失败: {e}") from None
    except Exception as e:
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
