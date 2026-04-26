"""应用安装 API — 支持 APK/APKS/AAB/IPA 文件上传安装到设备。"""

import logging
import os
import tempfile

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.core.device_manager import device_manager
from app.drivers.android import AndroidDriver
from app.drivers.ios import IOSDriver

logger = logging.getLogger(__name__)

router = APIRouter()

# 允许的文件扩展名
ALLOWED_EXTENSIONS = {".apk", ".apks", ".aab", ".ipa"}
# 不限制文件大小（安装包可能很大）
MAX_FILE_SIZE = None


@router.post("/install/{device_id}")
async def install_app(device_id: str, file: UploadFile = File(...)):
    """上传并安装应用到指定设备。

    - Android: 支持 .apk, .apks, .aab
    - iOS: 支持 .ipa
    """
    dm = device_manager
    device = dm._devices.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"设备 {device_id} 未找到")

    # 校验文件扩展名
    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {ext}（支持 {', '.join(ALLOWED_EXTENSIONS)}）",
        )

    # 校验平台与文件格式匹配
    if device.platform == "android" and ext not in {".apk", ".apks", ".aab"}:
        raise HTTPException(status_code=400, detail="Android 设备仅支持 .apk/.apks/.aab 文件")
    if device.platform == "ios" and ext != ".ipa":
        raise HTTPException(status_code=400, detail="iOS 设备仅支持 .ipa 文件")

    # 保存上传文件到临时目录
    try:
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=ext, prefix="msca_install_"
        ) as tmp:
            while chunk := await file.read(1024 * 1024):
                tmp.write(chunk)
            tmp_path = tmp.name
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件保存失败: {e}")

    # 执行安装
    try:
        progress_messages = []

        def on_progress(msg: str):
            progress_messages.append(msg)
            logger.info(f"[{device_id}] 安装进度: {msg}")

        if device.platform == "android":
            driver = AndroidDriver(device_serial=device_id)
            result = await driver.install_app(tmp_path, callback=on_progress)
        elif device.platform == "ios":
            adapter = dm.create_ios_adapter(device_id)
            driver = IOSDriver(device_id=device_id, adapter=adapter)
            result = await driver.install_app(tmp_path, callback=on_progress)
        else:
            raise HTTPException(status_code=400, detail=f"不支持的平台: {device.platform}")

        return {
            "success": result.success,
            "message": result.message,
            "device_id": device_id,
            "filename": filename,
            "progress": progress_messages,
        }
    finally:
        # 清理临时文件
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
