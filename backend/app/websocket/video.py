"""视频流 WebSocket 端点：将 H.264 帧实时推送给前端。

端点：/ws/video/{device_id}
协议：
- 服务端发送二进制帧（H.264 NAL 数据）
- 首帧为 codec 配置帧（SPS/PPS + IDR），前端用于初始化 VideoDecoder
- 后续帧为视频数据，前端通过 WebCodecs 解码渲染
- 客户端可发送 JSON 控制消息（如 ping/pong 心跳）

注意：scrcpy 可能将 SPS/PPS 和 IDR 分成不同的 packet 发送，
后端需要缓冲 config NAL，确保发给前端的关键帧包含完整的 SPS+PPS+IDR。
"""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.mirror import get_active_driver
from app.scrcpy.protocol import (
    NAL_TYPE_MASK,
    NAL_IDR,
    NAL_SPS,
    NAL_PPS,
    has_config_data,
    is_key_frame,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _has_idr(data: bytes) -> bool:
    """快速检查数据中是否包含 IDR NAL。"""
    i = 0
    while i < len(data) - 4:
        if data[i] == 0 and data[i + 1] == 0:
            sc_len = 0
            if data[i + 2] == 1:
                sc_len = 3
            elif data[i + 2] == 0 and data[i + 3] == 1:
                sc_len = 4
            if sc_len > 0:
                nal_idx = i + sc_len
                if nal_idx < len(data) and (data[nal_idx] & NAL_TYPE_MASK) == NAL_IDR:
                    return True
                i += sc_len
                continue
        i += 1
    return False


@router.websocket("/ws/video/{device_id}")
async def video_stream(websocket: WebSocket, device_id: str):
    """视频流 WebSocket 端点。

    前端连接后，订阅对应设备的视频帧队列，持续推送 H.264 数据。
    如果 scrcpy 将 SPS/PPS 和 IDR 分开发送，后端会缓冲 config 数据，
    等 IDR 到来时合并为一个完整的关键帧再推送。
    """
    await websocket.accept()
    logger.info(f"[{device_id}] 视频 WS 已连接")

    try:
        driver = get_active_driver(device_id)
    except Exception:
        await websocket.close(code=4004, reason=f"设备 {device_id} 未在投屏")
        return

    queue = driver.subscribe_video()

    w, h = driver.screen_size
    await websocket.send_json({
        "type": "config",
        "width": w,
        "height": h,
        "codec": "h264",
    })

    try:
        frame_count = 0
        config_buf = b""  # 缓冲 SPS/PPS 数据

        while True:
            try:
                frame = await asyncio.wait_for(queue.get(), timeout=5.0)
            except TimeoutError:
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
                continue

            if frame is None:
                continue

            has_config = has_config_data(frame)
            has_idr = _has_idr(frame)

            if has_config and has_idr:
                # 完整关键帧（SPS+PPS+IDR 在同一个 packet）
                config_buf = b""
                header = b"\x01"
                payload = frame
            elif has_config and not has_idr:
                # 只有 SPS/PPS，缓冲等待 IDR
                config_buf = frame
                continue
            elif not has_config and has_idr and config_buf:
                # IDR 到了，与缓冲的 config 合并
                header = b"\x01"
                payload = config_buf + frame
                config_buf = b""
            elif has_idr:
                # IDR 但没有缓冲的 config（不太常见，直接发）
                header = b"\x01"
                payload = frame
            else:
                # 普通 P/B 帧
                header = b"\x00"
                payload = frame

            try:
                await websocket.send_bytes(header + payload)
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
