"""控制指令 WebSocket 端点。

接收前端 JSON 控制指令，编码为 scrcpy 二进制协议，写入 control_socket。
"""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.mirror import get_active_driver
from app.scrcpy import protocol

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/control/{device_id}")
async def control_websocket(websocket: WebSocket, device_id: str):
    """控制指令 WebSocket 端点。

    接收 JSON 格式的控制指令：
    - touch: { type: "touch", action: "down"|"up"|"move", x, y, width, height }
    - key: { type: "key", action: "down"|"up", keycode }
    - text: { type: "text", text: "..." }
    - scroll: { type: "scroll", x, y, width, height, hScroll, vScroll }
    - back: { type: "back" }
    - home: { type: "home" }
    - power: { type: "power" }
    """
    await websocket.accept()
    logger.info(f"[{device_id}] 控制 WS 已连接")

    try:
        while True:
            data = await websocket.receive_json()
            cmd_type = data.get("type", "")

            try:
                driver = get_active_driver(device_id)
            except Exception:
                await websocket.send_json({"error": "设备未在投屏中"})
                continue

            manager = driver._server_manager
            if not manager or not manager.running:
                await websocket.send_json({"error": "投屏会话未就绪"})
                continue

            encoded = _encode_command(cmd_type, data, manager)
            if encoded:
                await manager.send_control(encoded)
            else:
                await websocket.send_json({"error": f"未知指令类型: {cmd_type}"})

    except WebSocketDisconnect:
        logger.info(f"[{device_id}] 控制 WS 已断开")
    except Exception as e:
        logger.error(f"[{device_id}] 控制 WS 异常: {e}")


def _encode_command(cmd_type: str, data: dict, manager) -> bytes | None:
    """将 JSON 指令编码为 scrcpy 二进制协议。"""
    w, h = manager.screen_size

    if cmd_type == "touch":
        action_map = {"down": protocol.ACTION_DOWN, "up": protocol.ACTION_UP, "move": protocol.ACTION_MOVE}
        action = action_map.get(data.get("action", ""), protocol.ACTION_DOWN)
        x = int(data.get("x", 0))
        y = int(data.get("y", 0))
        sw = int(data.get("width", w))
        sh = int(data.get("height", h))
        pressure = float(data.get("pressure", 1.0 if action != protocol.ACTION_UP else 0.0))
        return protocol.encode_inject_touch(action, -1, x, y, sw, sh, pressure)

    elif cmd_type == "key":
        action_map = {"down": protocol.ACTION_DOWN, "up": protocol.ACTION_UP}
        action = action_map.get(data.get("action", ""), protocol.ACTION_DOWN)
        keycode = int(data.get("keycode", 0))
        return (
            protocol.encode_inject_keycode(protocol.ACTION_DOWN, keycode)
            + protocol.encode_inject_keycode(protocol.ACTION_UP, keycode)
        )

    elif cmd_type == "text":
        text = data.get("text", "")
        if text:
            return protocol.encode_inject_text(text)

    elif cmd_type == "scroll":
        x = int(data.get("x", 0))
        y = int(data.get("y", 0))
        sw = int(data.get("width", w))
        sh = int(data.get("height", h))
        h_scroll = int(data.get("hScroll", 0))
        v_scroll = int(data.get("vScroll", 0))
        return protocol.encode_inject_scroll(x, y, sw, sh, h_scroll, v_scroll)

    elif cmd_type == "back":
        return (
            protocol.encode_back_or_screen_on(protocol.ACTION_DOWN)
            + protocol.encode_back_or_screen_on(protocol.ACTION_UP)
        )

    elif cmd_type == "home":
        return (
            protocol.encode_inject_keycode(protocol.ACTION_DOWN, protocol.KEYCODE_HOME)
            + protocol.encode_inject_keycode(protocol.ACTION_UP, protocol.KEYCODE_HOME)
        )

    elif cmd_type == "power":
        return (
            protocol.encode_inject_keycode(protocol.ACTION_DOWN, protocol.KEYCODE_POWER)
            + protocol.encode_inject_keycode(protocol.ACTION_UP, protocol.KEYCODE_POWER)
        )

    return None
