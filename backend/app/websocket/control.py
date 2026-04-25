"""控制指令 WebSocket 端点。

接收前端 JSON 控制指令，编码为 scrcpy 二进制协议，写入 control_socket。
同时轮询设备消息（剪贴板回传等），推送给前端。
"""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.mirror import get_active_driver
from app.scrcpy import protocol

logger = logging.getLogger(__name__)

router = APIRouter()

# 设备消息轮询间隔（秒）
DEVICE_MSG_POLL_INTERVAL = 0.5


@router.websocket("/ws/control/{device_id}")
async def control_websocket(websocket: WebSocket, device_id: str):
    """控制指令 WebSocket 端点。

    双向通信：
    - 接收前端 JSON 控制指令 → 编码为 scrcpy 二进制 → 发送到设备
    - 轮询设备消息（剪贴板回传等） → JSON 推送给前端
    """
    await websocket.accept()
    logger.info(f"[{device_id}] 控制 WS 已连接")

    async def receive_commands():
        """接收前端控制指令并转发到设备。"""
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
            pass

    async def poll_device_messages():
        """轮询设备消息并推送给前端。"""
        try:
            while True:
                try:
                    driver = get_active_driver(device_id)
                    manager = driver._server_manager
                    if manager and manager.running:
                        msg = await manager.read_device_message()
                        if msg:
                            await websocket.send_json({"device_msg": msg})
                except Exception:
                    pass
                await asyncio.sleep(DEVICE_MSG_POLL_INTERVAL)
        except asyncio.CancelledError:
            pass

    # 并发运行：接收指令 + 轮询设备消息
    recv_task = asyncio.create_task(receive_commands())
    poll_task = asyncio.create_task(poll_device_messages())

    try:
        done, pending = await asyncio.wait(
            [recv_task, poll_task], return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
    except Exception as e:
        logger.error(f"[{device_id}] 控制 WS 异常: {e}")
        recv_task.cancel()
        poll_task.cancel()

    logger.info(f"[{device_id}] 控制 WS 已断开")


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
        metastate = int(data.get("metastate", 0))
        repeat = int(data.get("repeat", 0))
        return (
            protocol.encode_inject_keycode(protocol.ACTION_DOWN, keycode, repeat, metastate)
            + protocol.encode_inject_keycode(protocol.ACTION_UP, keycode, 0, metastate)
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

    elif cmd_type == "expand_notification":
        return protocol.encode_expand_notification_panel()

    elif cmd_type == "expand_settings":
        return protocol.encode_expand_settings_panel()

    elif cmd_type == "collapse_panels":
        return protocol.encode_collapse_panels()

    elif cmd_type == "clipboard":
        text = data.get("text", "")
        paste = data.get("paste", False)
        if text:
            return protocol.encode_set_clipboard(text, paste)

    elif cmd_type == "rotate":
        return protocol.encode_rotate_device()

    return None
