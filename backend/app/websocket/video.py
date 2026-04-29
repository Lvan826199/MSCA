"""视频流 WebSocket 端点：将视频帧实时推送给前端。

支持两种流协议：
- Android (H.264)：scrcpy 二进制帧，前端 WebCodecs 解码
- iOS (MJPEG)：JPEG 帧序列，前端 img/Canvas 渲染

端点：/ws/video/{device_id}
"""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..api.mirror import get_active_driver
from ..drivers.ios import IOSDriver
from ..scrcpy.protocol import (
    NAL_IDR,
    NAL_TYPE_MASK,
    has_config_data,
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
    """视频流 WebSocket 端点。根据设备平台选择 H.264 或 MJPEG 协议。"""
    await websocket.accept()
    logger.info(f"[{device_id}] 视频 WS 已连接")

    try:
        driver = get_active_driver(device_id)
    except Exception:
        await websocket.close(code=4004, reason=f"设备 {device_id} 未在投屏")
        return

    if isinstance(driver, IOSDriver):
        await _stream_mjpeg(websocket, device_id, driver)
    else:
        await _stream_h264(websocket, device_id, driver)


async def _stream_mjpeg(websocket: WebSocket, device_id: str, driver: IOSDriver):
    """iOS MJPEG 流推送。"""
    queue = driver.subscribe_video()

    w, h = driver.screen_size
    await websocket.send_json({
        "type": "config",
        "width": w,
        "height": h,
        "codec": "mjpeg",
    })

    frame_count = 0
    try:
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

            try:
                # MJPEG 帧直接发送二进制 JPEG 数据
                await websocket.send_bytes(frame)
                frame_count += 1
            except Exception:
                break

    except WebSocketDisconnect:
        logger.info(f"[{device_id}] 视频 WS 断开 (MJPEG)")
    except Exception as e:
        logger.error(f"[{device_id}] 视频 WS 异常 (MJPEG): {e}")
    finally:
        driver.unsubscribe_video(queue)
        logger.info(f"[{device_id}] 视频 WS 清理完成 (MJPEG)，共发送 {frame_count} 帧")


async def _stream_h264(websocket: WebSocket, device_id: str, driver):
    """Android H.264 流推送。"""
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
