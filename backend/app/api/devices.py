from fastapi import APIRouter

router = APIRouter()


@router.get("/devices")
async def list_devices():
    # TODO: M2 阶段实现 ADB 设备发现
    return {"devices": []}
