"""AndroidDriver: 基于 scrcpy 协议的 Android 设备驱动。

实现 AbstractDeviceDriver 接口，通过 ScrcpyServerManager 管理投屏与控制。
"""

import asyncio
import logging
import os
import subprocess
import tempfile
import zipfile
from collections.abc import Callable

import adbutils

from ..scrcpy.protocol import (
    ACTION_DOWN,
    ACTION_MOVE,
    ACTION_UP,
    KEYCODE_BACK,
    KEYCODE_HOME,
    KEYCODE_POWER,
    KEYCODE_VOLUME_DOWN,
    KEYCODE_VOLUME_UP,
    encode_back_or_screen_on,
    encode_inject_keycode,
    encode_inject_text,
    encode_inject_touch,
)
from ..scrcpy.server_manager import ScrcpyServerManager
from .base import AbstractDeviceDriver, ControlEvent, InstallResult, MirrorOptions

logger = logging.getLogger(__name__)

# 按键名称到 keycode 的映射
KEYCODE_MAP = {
    "home": KEYCODE_HOME,
    "back": KEYCODE_BACK,
    "power": KEYCODE_POWER,
    "volume_up": KEYCODE_VOLUME_UP,
    "volume_down": KEYCODE_VOLUME_DOWN,
}


class AndroidDriver(AbstractDeviceDriver):
    """Android 设备驱动，桌面端/Web 端共用。"""

    def __init__(self, device_serial: str):
        self.device_serial = device_serial
        self._server_manager: ScrcpyServerManager | None = None
        self._video_task: asyncio.Task | None = None
        self._video_subscribers: list[asyncio.Queue] = []

    @property
    def is_mirroring(self) -> bool:
        return self._server_manager is not None and self._server_manager.running

    @property
    def screen_size(self) -> tuple[int, int]:
        if self._server_manager:
            return self._server_manager.screen_size
        return 0, 0

    def subscribe_video(self) -> asyncio.Queue:
        """订阅视频帧推送。"""
        q: asyncio.Queue = asyncio.Queue(maxsize=30)
        self._video_subscribers.append(q)
        return q

    def unsubscribe_video(self, q: asyncio.Queue) -> None:
        """取消视频帧订阅。"""
        if q in self._video_subscribers:
            self._video_subscribers.remove(q)

    async def start_mirroring(self, options: MirrorOptions) -> str:
        """启动投屏。"""
        if self.is_mirroring:
            return self.device_serial

        self._server_manager = ScrcpyServerManager(self.device_serial)
        await self._server_manager.start(
            max_size=max(options.width, options.height) or 0,
            max_fps=options.max_fps,
            bitrate=options.bitrate,
        )

        # 启动视频帧读取任务
        self._video_task = asyncio.create_task(self._read_video_loop())

        return self.device_serial

    async def stop_mirroring(self) -> None:
        """停止投屏。"""
        if self._video_task:
            self._video_task.cancel()
            try:
                await self._video_task
            except asyncio.CancelledError:
                pass
            self._video_task = None

        if self._server_manager:
            await self._server_manager.stop()
            self._server_manager = None

        # 清空订阅者
        self._video_subscribers.clear()

        logger.info(f"[{self.device_serial}] 投屏已停止")

    async def send_event(self, event: ControlEvent) -> bool:
        """发送控制指令。"""
        if not self._server_manager or not self._server_manager.running:
            return False

        try:
            data = self._encode_event(event)
            if data:
                await self._server_manager.send_control(data)
                return True
        except Exception as e:
            logger.error(f"[{self.device_serial}] 发送控制指令失败: {e}")
        return False

    async def get_screenshot(self) -> bytes:
        """获取截图（通过 ADB screencap）。"""
        import adbutils

        device = adbutils.adb.device(serial=self.device_serial)
        return await asyncio.to_thread(device.screenshot)

    async def _read_video_loop(self) -> None:
        """持续读取视频帧并分发给订阅者。"""
        while self._server_manager and self._server_manager.running:
            try:
                frame = await self._server_manager.read_video_frame()
                if frame is None:
                    await asyncio.sleep(0.001)
                    continue

                # 分发给所有订阅者
                for q in self._video_subscribers:
                    try:
                        q.put_nowait(frame)
                    except asyncio.QueueFull:
                        # 丢弃旧帧，保持最新
                        try:
                            q.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                        try:
                            q.put_nowait(frame)
                        except asyncio.QueueFull:
                            pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[{self.device_serial}] 视频帧读取异常: {e}")
                await asyncio.sleep(0.1)

    def _encode_event(self, event: ControlEvent) -> bytes | None:
        """将 ControlEvent 编码为 scrcpy 二进制协议。"""
        action = event.action
        params = event.params
        w, h = self.screen_size

        if action == "tap":
            x = params.get("x", 0)
            y = params.get("y", 0)
            # 发送 DOWN + UP
            down = encode_inject_touch(ACTION_DOWN, -1, x, y, w, h)
            up = encode_inject_touch(ACTION_UP, -1, x, y, w, h)
            return down + up

        if action == "swipe":
            x1, y1 = params.get("x1", 0), params.get("y1", 0)
            x2, y2 = params.get("x2", 0), params.get("y2", 0)
            steps = params.get("steps", 20)
            frames = []
            frames.append(encode_inject_touch(ACTION_DOWN, -1, x1, y1, w, h))
            for i in range(1, steps + 1):
                cx = x1 + (x2 - x1) * i // steps
                cy = y1 + (y2 - y1) * i // steps
                frames.append(encode_inject_touch(ACTION_MOVE, -1, cx, cy, w, h))
            frames.append(encode_inject_touch(ACTION_UP, -1, x2, y2, w, h))
            return b"".join(frames)

        if action == "keyevent":
            key = params.get("key", "")
            keycode = KEYCODE_MAP.get(key.lower())
            if keycode is None:
                keycode = params.get("keycode", 0)
            if action == "back":
                return encode_back_or_screen_on(ACTION_DOWN) + encode_back_or_screen_on(ACTION_UP)
            down = encode_inject_keycode(ACTION_DOWN, keycode)
            up = encode_inject_keycode(ACTION_UP, keycode)
            return down + up

        if action == "text":
            text = params.get("text", "")
            if text:
                return encode_inject_text(text)

        if action == "touch_down":
            return encode_inject_touch(
                ACTION_DOWN, params.get("pointer_id", -1),
                params.get("x", 0), params.get("y", 0), w, h,
            )

        if action == "touch_move":
            return encode_inject_touch(
                ACTION_MOVE, params.get("pointer_id", -1),
                params.get("x", 0), params.get("y", 0), w, h,
            )

        if action == "touch_up":
            return encode_inject_touch(
                ACTION_UP, params.get("pointer_id", -1),
                params.get("x", 0), params.get("y", 0), w, h,
            )

        logger.warning(f"未知控制指令: {action}")
        return None

    async def install_app(
        self,
        file_path: str,
        callback: Callable[[str], None] | None = None,
        keystore: str | None = None,
        ks_pass: str | None = None,
        key_alias: str | None = None,
        key_pass: str | None = None,
    ) -> InstallResult:
        """安装 APK/APKS/AAB 到 Android 设备。"""
        ext = os.path.splitext(file_path)[1].lower()

        try:
            if ext == ".apk":
                return await self._install_apk(file_path, callback)
            elif ext == ".apks":
                return await self._install_apks(file_path, callback)
            elif ext == ".aab":
                return await self._install_aab(
                    file_path, callback,
                    keystore=keystore, ks_pass=ks_pass,
                    key_alias=key_alias, key_pass=key_pass,
                )
            else:
                return InstallResult(
                    success=False,
                    message=f"不支持的文件格式: {ext}（支持 .apk, .apks, .aab）",
                )
        except Exception as e:
            logger.error(f"[{self.device_serial}] 安装失败: {e}")
            return InstallResult(success=False, message=str(e))

    async def _install_apk(
        self, file_path: str, callback: Callable[[str], None] | None
    ) -> InstallResult:
        """安装单个 APK 文件。"""
        device = adbutils.adb.device(serial=self.device_serial)

        def _progress(msg: str):
            if callback:
                callback(msg)

        _progress("正在安装 APK...")
        await asyncio.to_thread(
            device.install, file_path, silent=True, callback=_progress
        )
        _progress("安装完成")
        return InstallResult(success=True, message="APK 安装成功")

    async def _install_apks(
        self, file_path: str, callback: Callable[[str], None] | None
    ) -> InstallResult:
        """安装 APKS 文件（split APKs 压缩包）。"""
        def _progress(msg: str):
            if callback:
                callback(msg)

        _progress("正在解压 APKS...")

        # APKS 是 zip 格式，内含多个 split APK
        with tempfile.TemporaryDirectory() as tmpdir:
            with zipfile.ZipFile(file_path, "r") as zf:
                apk_files = [n for n in zf.namelist() if n.endswith(".apk")]
                if not apk_files:
                    return InstallResult(success=False, message="APKS 中未找到 APK 文件")
                zf.extractall(tmpdir, apk_files)

            apk_paths = [os.path.join(tmpdir, f) for f in apk_files]
            _progress(f"正在安装 {len(apk_paths)} 个 split APK...")

            # 使用 adb install-multiple 命令
            cmd = ["adb", "-s", self.device_serial, "install-multiple", "-r"] + apk_paths
            proc = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True, timeout=120
            )

            if proc.returncode == 0:
                _progress("安装完成")
                return InstallResult(success=True, message="APKS 安装成功")
            else:
                err = proc.stderr.strip() or proc.stdout.strip()
                return InstallResult(success=False, message=f"安装失败: {err}")

    @staticmethod
    def _get_project_root() -> str:
        """获取项目根目录。"""
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

    @staticmethod
    def _get_android_bin_dir() -> str:
        """获取 Android 内置工具目录。"""
        res_path = os.environ.get("MSCA_RESOURCES_PATH", "")
        if res_path:
            packaged_dir = os.path.join(res_path, "bin", "android")
            if os.path.isdir(packaged_dir):
                return packaged_dir
        return os.path.join(AndroidDriver._get_project_root(), "bin", "android")

    @staticmethod
    def _find_bundletool() -> str | None:
        """查找 bundletool.jar 路径。优先级：MSCA_RESOURCES_PATH > bin/android/ > BUNDLETOOL_PATH。"""
        builtin = os.path.join(AndroidDriver._get_android_bin_dir(), "bundletool.jar")
        if os.path.isfile(builtin):
            return builtin

        # 环境变量
        env_path = os.environ.get("BUNDLETOOL_PATH")
        if env_path and os.path.isfile(env_path):
            return env_path

        return None

    @staticmethod
    def list_keystores() -> list[dict]:
        """列出 bin/android/aab_keys/ 下可用的签名文件。

        返回格式: [{"name": "xxx.keystore", "path": "绝对路径"}, ...]
        """
        keys_dir = os.path.join(AndroidDriver._get_android_bin_dir(), "aab_keys")
        if not os.path.isdir(keys_dir):
            return []

        result = []
        for fname in sorted(os.listdir(keys_dir)):
            fpath = os.path.join(keys_dir, fname)
            if not os.path.isfile(fpath):
                continue
            # 匹配 .keystore 文件和无扩展名的签名文件
            _, ext = os.path.splitext(fname)
            if ext == ".keystore":
                result.append({"name": fname, "path": fpath})
            elif ext == "" and "." not in fname:
                # 无扩展名文件视为签名文件（如 avidly_signature）
                result.append({"name": fname, "path": fpath})
        return result

    async def _install_aab(
        self,
        file_path: str,
        callback: Callable[[str], None] | None,
        keystore: str | None = None,
        ks_pass: str | None = None,
        key_alias: str | None = None,
        key_pass: str | None = None,
    ) -> InstallResult:
        """安装 AAB 文件：通过 bundletool 转换为 APKS 后安装到设备。

        签名参数均为可选，不传则使用 debug 签名。
        """
        def _progress(msg: str):
            if callback:
                callback(msg)

        bundletool = self._find_bundletool()
        if not bundletool:
            return InstallResult(
                success=False,
                message="未找到 bundletool.jar，请将其放置到 bin/android/bundletool.jar 或设置 BUNDLETOOL_PATH 环境变量",
            )

        # 检查 Java 是否可用
        try:
            await asyncio.to_thread(
                subprocess.run, ["java", "-version"],
                capture_output=True, timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return InstallResult(
                success=False,
                message="未找到 Java 运行时，bundletool 需要 Java 11+ 才能运行",
            )

        _progress("正在通过 bundletool 将 AAB 转换为 APKS...")

        with tempfile.TemporaryDirectory() as tmpdir:
            apks_path = os.path.join(tmpdir, "output.apks")

            # bundletool build-apks: AAB → APKS
            build_cmd = [
                "java", "-jar", bundletool,
                "build-apks",
                "--bundle", file_path,
                "--output", apks_path,
                "--connected-device",
                "--device-id", self.device_serial,
                "--overwrite",
            ]

            # 附加签名参数
            if keystore:
                build_cmd += [
                    f"--ks={keystore}",
                    f"--ks-pass=pass:{ks_pass or ''}",
                    f"--ks-key-alias={key_alias or ''}",
                    f"--key-pass=pass:{key_pass or ''}",
                ]

            proc = await asyncio.to_thread(
                subprocess.run, build_cmd,
                capture_output=True, text=True, timeout=300,
            )
            if proc.returncode != 0:
                err = proc.stderr.strip() or proc.stdout.strip()
                return InstallResult(success=False, message=f"AAB 转换失败: {err}")

            _progress("转换完成，正在安装到设备...")

            # bundletool install-apks: 安装到设备
            install_cmd = [
                "java", "-jar", bundletool,
                "install-apks",
                "--apks", apks_path,
                "--device-id", self.device_serial,
            ]
            proc = await asyncio.to_thread(
                subprocess.run, install_cmd,
                capture_output=True, text=True, timeout=120,
            )
            if proc.returncode != 0:
                err = proc.stderr.strip() or proc.stdout.strip()
                return InstallResult(success=False, message=f"AAB 安装失败: {err}")

            _progress("安装完成")
            return InstallResult(success=True, message="AAB 安装成功")
