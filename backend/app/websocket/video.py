"""视频流 WebSocket 端点：将 H.264 帧实时推送给前端。

端点：/ws/video/{device_id}
协议：
- 服务端发送二进制帧（H.264 NAL 数据）
- 首帧为 codec 配置帧（SPS/PPS），前端用于初始化 VideoDecoder
- 后续帧为视频数据，前端通过 WebCodecs 解码渲染
- 客户端可发送 JSON 控制消息（如 ping/pong 心跳）
"""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.mirror import get_active_driver
from app.scrcpy.protocol import is_key_frame

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/video/{device_id}")
async def video_stream(websocket: WebSocket, device_id: str):
    """视频流 WebSocket 端点。

    前端连接后，订阅对应设备的视频帧队列，持续推送 H.264 数据。
    """
    await websocket.accept()
    logger.info(f"[{device_id}] 视频 WS 已连接")

    # 获取驱动实例
    try:
        driver = get_active_driver(device_id)
    except Exception:
        await websocket.close(code=4004, reason=f"设备 {device_id} 未在投屏")
        return

    # 订阅视频帧
    queue = driver.subscribe_video()

    # 发送屏幕尺寸信息
    w, h = driver.screen_size
    await websocket.send_json({
        "type": "config",
        "width": w,
        "height": h,
        "codec": "h264",
    })

    try:
        frame_count = 0
        while True:
            try:
                # 从队列获取帧，超时 5 秒发心跳
                frame = await asyncio.wait_for(queue.get(), timeout=5.0)
            except TimeoutError:
                # 发送心跳保活
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
                continue

            if frame is None:
                continue

            # 发送帧类型标记（1 字节）+ H.264 数据
            # 0x01 = key frame, 0x00 = delta frame
            key = is_key_frame(frame)
            header = b"\x01" if key else b"\x00"

            try:
                await websocket.send_bytes(header + frame)
                frame_count += 1
            except Exception:
                break

    except WebSocketDisconnect:
        logger.info(f"[{device_id}] 视频 WS 断开")
    except Exception as e:
        logger.error(f"[{device_id}] 视频 WS 异常: {e}")
    finally:
        driver.unsubscribe_video(queue)
        logger.info(f"[{device_id}] 视频 WS 清理完成，共发送 {frame_count} 帧")
