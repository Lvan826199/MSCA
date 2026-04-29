from fastapi import APIRouter

from ..core.device_manager import device_manager

router = APIRouter()


@router.get("/devices")
async def list_devices():
    return {"devices": [d.model_dump() for d in device_manager.devices]}


@router.post("/devices/refresh")
async def refresh_devices():
    devices = await device_manager.refresh()
    return {"devices": [d.model_dump() for d in devices]}
