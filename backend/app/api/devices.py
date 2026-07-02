from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..core.device_manager import device_manager

router = APIRouter()


class DeviceAliasUpdate(BaseModel):
    alias: str = Field(default="", max_length=64)


@router.get("/devices")
async def list_devices():
    return {"devices": [d.model_dump() for d in device_manager.devices]}


@router.post("/devices/refresh")
async def refresh_devices():
    devices = await device_manager.refresh()
    return {"devices": [d.model_dump() for d in devices]}


@router.put("/devices/{device_id}/alias")
async def update_device_alias(device_id: str, payload: DeviceAliasUpdate):
    try:
        device = await device_manager.set_device_alias(device_id, payload.alias)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not device:
        raise HTTPException(status_code=404, detail="device not found")
    return {"device": device.model_dump()}


@router.delete("/devices/{device_id}/alias")
async def clear_device_alias(device_id: str):
    device = await device_manager.set_device_alias(device_id, "")
    if not device:
        raise HTTPException(status_code=404, detail="device not found")
    return {"device": device.model_dump()}
