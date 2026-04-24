import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.device_manager import device_manager

router = APIRouter()


@router.websocket("/ws/devices")
async def ws_devices(websocket: WebSocket):
    await websocket.accept()
    queue = device_manager.subscribe()

    # 连接后立即推送当前设备列表
    current = [d.model_dump() for d in device_manager.devices]
    await websocket.send_text(json.dumps({"type": "devices", "data": current}))

    try:
        while True:
            data = await queue.get()
            await websocket.send_text(json.dumps({"type": "devices", "data": data}))
    except WebSocketDisconnect:
        pass
    finally:
        device_manager.unsubscribe(queue)
