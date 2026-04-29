"""应用安装 API，支持 APK/APKS/AAB/IPA 上传并安装到设备。"""

import logging
import os
import tempfile

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..core.device_manager import device_manager
from ..drivers.android import AndroidDriver
from ..drivers.ios import IOSDriver

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_EXTENSIONS = {".apk", ".apks", ".aab", ".ipa"}
UPLOAD_FILE_REQUIRED = File(...)


@router.get("/install/keystores")
async def list_keystores():
    return {"keystores": AndroidDriver.list_keystores()}


@router.post("/install/{device_id}")
async def install_app(
    device_id: str,
    file: UploadFile = UPLOAD_FILE_REQUIRED,
    keystore: str | None = Form(None),
    ks_pass: str | None = Form(None),
    key_alias: str | None = Form(None),
    key_pass: str | None = Form(None),
):
    device = device_manager._devices.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"设备 {device_id} 未找到")

    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        supported = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}，支持 {supported}")

    if device.platform == "android" and ext not in {".apk", ".apks", ".aab"}:
        raise HTTPException(status_code=400, detail="Android 设备仅支持 .apk/.apks/.aab 文件")
    if device.platform == "ios" and ext != ".ipa":
        raise HTTPException(status_code=400, detail="iOS 设备仅支持 .ipa 文件")

    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext, prefix="msca_install_") as tmp:
            while chunk := await file.read(1024 * 1024):
                tmp.write(chunk)
            tmp_path = tmp.name
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"文件保存失败: {err}") from err

    try:
        progress_messages: list[str] = []

        def on_progress(message: str) -> None:
            progress_messages.append(message)
            logger.info("[%s] 安装进度: %s", device_id, message)

        if device.platform == "android":
            driver = AndroidDriver(device_serial=device_id)
            result = await driver.install_app(
                tmp_path,
                callback=on_progress,
                keystore=keystore,
                ks_pass=ks_pass,
                key_alias=key_alias,
                key_pass=key_pass,
            )
        elif device.platform == "ios":
            adapter = device_manager.create_ios_adapter(device_id)
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
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
