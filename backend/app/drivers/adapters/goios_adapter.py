"""go-ios 适配器 — 支持 iOS ≥16.x 设备。

通过 go-ios CLI 工具管理 WDA 服务、端口转发和设备信息获取。
核心改进：
- 支持 WDA bundle ID 自动检测和配置（解决 com.facebook vs com.ascript 问题）
- 分别转发 WDA API（设备 8100）和 MJPEG 流（设备 9100）
- 支持 relay 模式（WDA 已在运行时只做端口转发）
"""

import asyncio
import datetime
import fnmatch
import json
import logging
import os
import re
import subprocess

from .base import (
    IOSAdapterBase,
    WDAInfo,
    diagnose_wda_failure,
    is_port_free,
    kill_process_on_port,
    load_wda_config,
)

logger = logging.getLogger(__name__)

# 共享 tunnel agent 进程注册表：agent 是主机级守护进程，多设备共用，
# 设备级 stop_wda() 不杀；应用关闭时由 shutdown_tunnel_agents() 统一清理，
# 否则 ios.exe 残留会占用打包目录、阻塞下次 electron-builder 清理
_shared_agent_processes: list[subprocess.Popen] = []


def shutdown_tunnel_agents() -> None:
    """终止本进程启动的所有 go-ios tunnel agent（应用关闭时调用）。

    提权（UAC）方式启动的 agent 为独立守护进程，无句柄可杀，不在此列。
    """
    while _shared_agent_processes:
        proc = _shared_agent_processes.pop()
        if proc.poll() is not None:
            continue
        try:
            proc.terminate()
            proc.wait(timeout=3)
            logger.info("go-ios tunnel agent 已终止 (pid=%s)", proc.pid)
        except Exception:
            try:
                proc.kill()
                logger.info("go-ios tunnel agent 已强制终止 (pid=%s)", proc.pid)
            except Exception as err:
                logger.warning("go-ios tunnel agent 终止失败 (pid=%s): %s", proc.pid, err)


class GoIOSAdapter(IOSAdapterBase):
    """基于 go-ios 的 iOS 适配器，适用于 iOS ≥16.x。"""

    def __init__(self, udid: str, ios_bin: str = "ios"):
        super().__init__(udid)
        self._ios_bin = ios_bin
        self._wda_process: subprocess.Popen | None = None
        self._tunnel_process: subprocess.Popen | None = None
        self._mjpeg_forward_process: subprocess.Popen | None = None
        self._agent_process: subprocess.Popen | None = None
        self._wda_log_path = ""

    async def _run_cmd(self, *args, timeout: int = 30) -> str:
        """执行 go-ios 命令并返回 stdout。"""
        cmd = [self._ios_bin] + list(args)
        logger.debug(f"[{self.udid}] 执行: {' '.join(cmd)}")
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            # 超时必须杀掉子进程，避免残留
            proc.kill()
            await proc.wait()
            raise
        if proc.returncode != 0:
            raw_error = f"go-ios 命令失败: {' '.join(cmd)}\n{stderr.decode(errors='replace')}"
            raise RuntimeError(diagnose_wda_failure(raw_error).format())
        return stdout.decode(errors='replace')

    # ─── 设备列表 ───

    async def list_devices(self) -> list[dict]:
        """通过 go-ios 列出已连接的 iOS 设备。"""
        try:
            await self._run_cmd("list", "--nojson")
        except FileNotFoundError:
            logger.warning("go-ios (ios) 未安装，无法发现 iOS 设备")
            return []
        except Exception as e:
            logger.error(f"go-ios 设备列表获取失败: {e}")
            return []

        try:
            output_json = await self._run_cmd("list")
            data = json.loads(output_json)
            devices = []
            for d in data.get("deviceList", []):
                devices.append({
                    "udid": d.get("serialNumber", ""),
                    "name": d.get("properties", {}).get("DeviceName", ""),
                    "version": d.get("properties", {}).get("ProductVersion", ""),
                    "model": d.get("properties", {}).get("ProductType", ""),
                })
            return devices
        except Exception:
            return []

    async def install_wda(self, ipa_path: str) -> bool:
        """通过 go-ios 安装 WDA。"""
        try:
            await self._run_cmd(
                "install", f"--path={ipa_path}", f"--udid={self.udid}",
                timeout=120,
            )
            logger.info(f"[{self.udid}] WDA 安装成功 (go-ios)")
            return True
        except Exception as e:
            logger.error(f"[{self.udid}] WDA 安装失败: {e}")
            return False

    # ─── WDA Bundle ID 自动检测 ───

    async def detect_wda_bundle_id(self) -> str:
        """自动检测设备上已安装的 WDA bundle ID（通过 go-ios apps）。"""
        config = load_wda_config()
        configured = config.get("wda_bundle_id", "")
        if configured:
            logger.info(f"[{self.udid}] 使用配置的 WDA bundle ID: {configured}")
            return configured

        pattern = config.get("wda_bundle_id_pattern", "com.*.xctrunner")
        try:
            output = await self._run_cmd("apps", f"--udid={self.udid}", timeout=15)
            apps = json.loads(output)
            bundle_ids = []
            if isinstance(apps, list):
                for app in apps:
                    bid = app.get("CFBundleIdentifier", "")
                    if bid and fnmatch.fnmatch(bid, pattern):
                        bundle_ids.append(bid)
            elif isinstance(apps, dict):
                for bid in apps:
                    if fnmatch.fnmatch(bid, pattern):
                        bundle_ids.append(bid)
            if bundle_ids:
                # 优先选择非 facebook 的（用户自定义签名的 WDA）
                bundle_ids.sort(key=lambda x: 'facebook' in x.lower())
                logger.info(f"[{self.udid}] go-ios 检测到 WDA: {bundle_ids[0]} (候选: {bundle_ids})")
                return bundle_ids[0]
            logger.warning(f"[{self.udid}] go-ios 未找到匹配 '{pattern}' 的 WDA")
        except Exception as e:
            logger.warning(f"[{self.udid}] go-ios WDA bundle ID 检测失败: {e}")
        return ""

    # ─── WDA 启动 ───

    async def start_wda(self, port: int = 8100, mjpeg_port: int = 0) -> WDAInfo:
        """启动 WDA 并建立端口转发隧道（含 MJPEG 端口）。"""
        await self.stop_wda()
        config = load_wda_config()
        mjpeg_device_port = config.get("mjpeg_port_on_device", 9100)
        wda_device_port = config.get("wda_port_on_device", 8100)

        # 确保端口空闲
        if not is_port_free(port):
            logger.warning(f"[{self.udid}] WDA 端口 {port} 被占用，尝试清理")
            kill_process_on_port(port)
            await asyncio.sleep(0.5)
            if not is_port_free(port):
                raise RuntimeError(diagnose_wda_failure(f"端口 {port} 被占用").format())

        if mjpeg_port and not is_port_free(mjpeg_port):
            logger.warning(f"[{self.udid}] MJPEG 端口 {mjpeg_port} 被占用，尝试清理")
            kill_process_on_port(mjpeg_port)
            await asyncio.sleep(0.3)

        logger.info(f"[{self.udid}] go-ios start_wda: WDA={port}, MJPEG={mjpeg_port}, 设备WDA={wda_device_port}, 设备MJPEG={mjpeg_device_port}")

        # iOS 17+ 需要先启动 tunnel agent
        await self._ensure_tunnel()

        # 先尝试 relay 模式（WDA 已在运行）
        if await self._try_relay_mode(port, mjpeg_port, wda_device_port, mjpeg_device_port):
            return self.wda_info

        # WDA 未在运行，启动完整的 runwda
        return await self._start_runwda(port, mjpeg_port, wda_device_port, mjpeg_device_port)

    async def _try_relay_mode(self, port: int, mjpeg_port: int, wda_device_port: int, mjpeg_device_port: int) -> bool:
        """尝试 relay 模式：只做端口转发，检测 WDA 是否已在运行。"""
        logger.info(f"[{self.udid}] go-ios 尝试 relay 模式（设备WDA={wda_device_port}）")
        # 长生命周期进程：输出重定向到 DEVNULL，避免 PIPE 写满导致子进程死锁
        self._tunnel_process = subprocess.Popen(
            [self._ios_bin, "forward", str(port), str(wda_device_port), f"--udid={self.udid}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

        for _attempt in range(5):
            await asyncio.sleep(0.5)
            if self._tunnel_process.poll() is not None:
                logger.debug(f"[{self.udid}] go-ios forward 进程退出")
                self._tunnel_process = None
                return False

            self.wda_info = WDAInfo(host="127.0.0.1", port=port, mjpeg_port=mjpeg_port)
            if await self.check_wda_health():
                logger.info(f"[{self.udid}] WDA 已在运行，relay 模式就绪 @ {port}")
                if mjpeg_port:
                    await self._start_mjpeg_forward(mjpeg_port, mjpeg_device_port)
                return True

        logger.debug(f"[{self.udid}] relay 模式超时，WDA 未在运行")
        await asyncio.to_thread(self._kill_process, self._tunnel_process)
        self._tunnel_process = None
        self.wda_info = None
        return False

    async def _start_runwda(self, port: int, mjpeg_port: int, wda_device_port: int, mjpeg_device_port: int) -> WDAInfo:
        """启动完整的 runwda + 端口转发。"""
        # 检测 WDA bundle ID
        bundle_id = await self.detect_wda_bundle_id()
        config = load_wda_config()
        xctest_config = config.get("xctest_config", "WebDriverAgentRunner.xctest")

        # 启动 WDA API 端口转发
        logger.info(f"[{self.udid}] 启动 go-ios 端口转发: 本地 {port} → 设备 {wda_device_port}")
        # 长生命周期进程：输出重定向到 DEVNULL，避免 PIPE 写满导致子进程死锁
        self._tunnel_process = subprocess.Popen(
            [self._ios_bin, "forward", str(port), str(wda_device_port), f"--udid={self.udid}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

        # 构建 runwda 命令（关键：传递 --bundleid 和 --testrunnerbundleid）
        wda_cmd = _build_runwda_command(self._ios_bin, self.udid, bundle_id, xctest_config)
        if bundle_id:
            logger.info(f"[{self.udid}] 启动 WDA (go-ios)，bundle ID: {bundle_id}")
        else:
            logger.info(f"[{self.udid}] 启动 WDA (go-ios)，使用默认 bundle ID")

        self._wda_process, self._wda_log_path = self._spawn_logged_process(wda_cmd, "runwda")

        # 等待 WDA 就绪
        for _i in range(30):
            await asyncio.sleep(1)
            if self._wda_process.poll() is not None:
                raw_error = f"WDA 进程退出 (exit code {self._wda_process.returncode})"
                log_tail = self._read_log_tail(self._wda_log_path)
                if log_tail:
                    raw_error = f"{raw_error}\n最近 go-ios runwda 输出:\n{log_tail}"
                hint = diagnose_wda_failure(raw_error)
                logger.error(
                    "[%s] go-ios WDA 进程退出，分类=%s，错误=%s，建议=%s，日志=%s",
                    self.udid,
                    hint.category,
                    raw_error,
                    hint.suggestion,
                    self._wda_log_path or "无",
                )
                await self.stop_wda()
                raise RuntimeError(hint.format())

            self.wda_info = WDAInfo(host="127.0.0.1", port=port, mjpeg_port=mjpeg_port)
            if await self.check_wda_health():
                logger.info(f"[{self.udid}] WDA 就绪 @ {port} (go-ios)")
                if mjpeg_port:
                    await self._start_mjpeg_forward(mjpeg_port, mjpeg_device_port)
                return self.wda_info

        await self.stop_wda()
        raise TimeoutError(diagnose_wda_failure(f"[{self.udid}] WDA 启动超时（30s）").format())

    async def _start_mjpeg_forward(self, mjpeg_port: int, mjpeg_device_port: int) -> None:
        """启动 MJPEG 端口转发（设备端 9100 → 本地 mjpeg_port）。"""
        logger.info(f"[{self.udid}] 启动 MJPEG forward: 本地 {mjpeg_port} → 设备 {mjpeg_device_port}")
        # 长生命周期进程：输出重定向到 DEVNULL，避免 PIPE 写满导致子进程死锁
        self._mjpeg_forward_process = subprocess.Popen(
            [self._ios_bin, "forward", str(mjpeg_port), str(mjpeg_device_port), f"--udid={self.udid}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        await asyncio.sleep(0.5)
        if self._mjpeg_forward_process.poll() is not None:
            logger.warning(
                f"[{self.udid}] MJPEG forward 进程立即退出 (exit code {self._mjpeg_forward_process.returncode})"
            )
            self._mjpeg_forward_process = None
        else:
            logger.info(f"[{self.udid}] MJPEG forward 已启动 @ {mjpeg_port}")

    def _kill_process(self, proc: subprocess.Popen | None) -> None:
        """安全终止子进程。"""
        if not proc:
            return
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    async def stop_wda(self) -> None:
        """停止 WDA 和端口转发进程。

        注意：tunnel agent（_agent_process）是主机级共享守护进程，
        多台 iOS 17+ 设备共用，此处不能杀掉，否则会打断其他设备的投屏。
        """
        for proc in [self._wda_process, self._tunnel_process, self._mjpeg_forward_process]:
            await asyncio.to_thread(self._kill_process, proc)
        self._wda_process = None
        self._tunnel_process = None
        self._mjpeg_forward_process = None
        self.wda_info = None
        logger.debug(f"[{self.udid}] go-ios 设备级子进程已清理（tunnel agent 保留）")

    def _spawn_logged_process(self, cmd: list[str], label: str) -> tuple[subprocess.Popen, str]:
        """启动长生命周期进程，并将输出写入独立日志文件。"""
        log_path = self._process_log_path(label)
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "ab", buffering=0) as log_file:
            header = (
                f"\n--- {datetime.datetime.now().isoformat(timespec='seconds')} "
                f"{' '.join(cmd)} ---\n"
            ).encode("utf-8", errors="replace")
            log_file.write(header)
            proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
        return proc, log_path

    def _process_log_path(self, label: str) -> str:
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        logs_dir = os.path.join(backend_dir, "logs")
        safe_udid = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.udid or "unknown")
        safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "_", label)
        return os.path.join(logs_dir, f"go-ios-{safe_udid}-{safe_label}.log")

    def _read_log_tail(self, path: str, max_bytes: int = 4096) -> str:
        if not path or not os.path.isfile(path):
            return ""
        try:
            with open(path, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - max_bytes))
                return f.read().decode("utf-8", errors="replace").strip()
        except Exception:
            return ""

    def _wintun_available(self) -> bool:
        """检查内核 tunnel 所需的 wintun.dll 是否可被 go-ios 找到。

        go-ios（wintun-go 加载器）以 LOAD_LIBRARY_SEARCH_APPLICATION_DIR |
        LOAD_LIBRARY_SEARCH_SYSTEM32 搜索：ios.exe 同目录或 System32 任一存在即可。
        userspace 模式不需要 wintun，仅影响提权内核模式。
        """
        if os.name != "nt":
            return True
        import shutil
        exe = self._ios_bin if os.path.isabs(self._ios_bin) else (shutil.which(self._ios_bin) or self._ios_bin)
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        candidates = [
            os.path.join(os.path.dirname(os.path.abspath(exe)), "wintun.dll"),
            os.path.join(system_root, "System32", "wintun.dll"),
        ]
        return any(os.path.isfile(p) for p in candidates)

    async def _ensure_tunnel(self) -> None:
        """确保 go-ios tunnel agent 正在运行（iOS 17+ 必需）。

        三阶段策略：
        1. 检测 tunnel 是否已在运行
        2. 尝试 --userspace 模式（无需管理员权限，不依赖 wintun.dll）
        3. 提权启动默认模式（弹出 UAC/密码框，Windows 依赖 wintun.dll）
        """
        tunnel_env = {**os.environ, "ENABLE_GO_IOS_AGENT": "1"}

        # ── 阶段 1：检测 tunnel 是否已在运行 ──
        try:
            await self._run_cmd("tunnel", "ls", timeout=5)
            logger.debug(f"[{self.udid}] go-ios tunnel agent 已在运行")
            return
        except Exception:
            logger.debug(f"[{self.udid}] tunnel 未在运行，开始启动流程")

        # ── 阶段 2：尝试 userspace 模式（无需管理员权限） ──
        logger.info(f"[{self.udid}] 尝试 tunnel start --userspace（无需管理员权限）")
        if await self._try_tunnel_start(
            [self._ios_bin, "tunnel", "start", "--userspace"],
            tunnel_env, "userspace",
        ):
            return

        # ── 阶段 3：提权启动默认模式 ──
        if not self._wintun_available():
            logger.warning(
                "[%s] 未找到 wintun.dll（内核 tunnel 必需）。应用已在 bin/ios/ 内置该文件；"
                "若当前使用 PATH 中的 ios.exe，请将 wintun.dll 放到其同目录或 C:\\Windows\\System32",
                self.udid,
            )
        from .privilege import check_is_admin, launch_elevated

        if check_is_admin():
            # 已是管理员，直接启动
            logger.info(f"[{self.udid}] 当前已是管理员，直接启动 tunnel start")
            if await self._try_tunnel_start(
                [self._ios_bin, "tunnel", "start"],
                tunnel_env, "默认模式（管理员）",
            ):
                return
        else:
            # 需要提权
            logger.info(f"[{self.udid}] 请求管理员权限启动 tunnel start...")
            try:
                launched = await asyncio.to_thread(
                    launch_elevated,
                    [self._ios_bin, "tunnel", "start"],
                    tunnel_env,
                )
                if launched:
                    # 提权启动的是独立守护进程，轮询 tunnel ls 确认就绪
                    for i in range(20):
                        await asyncio.sleep(1)
                        try:
                            await self._run_cmd("tunnel", "ls", timeout=3)
                            logger.info(f"[{self.udid}] tunnel agent 就绪（提权启动，等待 {i+1}s）")
                            return
                        except Exception:
                            continue
                    logger.warning(f"[{self.udid}] 提权启动后 20s 内 tunnel 未就绪")
                else:
                    logger.warning(f"[{self.udid}] 管理员权限请求被拒绝或失败")
            except Exception as e:
                logger.warning(f"[{self.udid}] 提权启动异常: {e}")

        wintun_hint = (
            ""
            if self._wintun_available()
            else "\n注意：未检测到 wintun.dll（Windows 内核 tunnel 必需），"
            "请将 bin/ios/wintun.dll 放到 ios.exe 同目录或 C:\\Windows\\System32"
        )
        raw_error = (
            "go-ios tunnel 启动失败（iOS 17+ 必需）。\n"
            "尝试过的方式：\n"
            "  1) --userspace 模式（无需管理员）\n"
            "  2) 管理员提权启动\n"
            "请手动执行以下任一操作：\n"
            "  - Windows: 以管理员身份运行 scripts/ios-tunnel.bat\n"
            "  - macOS/Linux: 运行 scripts/ios-tunnel.sh\n"
            "  - 或手动执行: ios tunnel start（需管理员/sudo）"
            + wintun_hint
        )
        raise RuntimeError(diagnose_wda_failure(raw_error).format())

    async def _try_tunnel_start(
        self, args: list[str], env: dict, desc: str, timeout_s: int = 15,
    ) -> bool:
        """尝试启动 tunnel 并等待就绪。

        Args:
            args: 命令参数列表
            env: 环境变量
            desc: 描述（用于日志）
            timeout_s: 最大等待秒数

        Returns:
            True 表示 tunnel 已就绪
        """
        try:
            # 长生命周期进程：输出重定向到 DEVNULL，避免 PIPE 写满导致子进程死锁
            self._agent_process = subprocess.Popen(
                args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
            )
            for i in range(timeout_s):
                await asyncio.sleep(1)
                if self._agent_process.poll() is not None:
                    logger.warning(
                        f"[{self.udid}] tunnel ({desc}) 进程退出 (exit code {self._agent_process.returncode})"
                    )
                    self._agent_process = None
                    return False
                try:
                    await self._run_cmd("tunnel", "ls", timeout=3)
                    logger.info(f"[{self.udid}] tunnel agent 就绪 ({desc}，等待 {i+1}s)")
                    _shared_agent_processes.append(self._agent_process)
                    return True
                except Exception:
                    continue

            logger.warning(f"[{self.udid}] tunnel ({desc}) {timeout_s}s 内未就绪")
            await asyncio.to_thread(self._kill_process, self._agent_process)
            self._agent_process = None
            return False
        except Exception as e:
            logger.warning(f"[{self.udid}] tunnel ({desc}) 启动失败: {e}")
            return False

    async def get_device_info(self) -> dict:
        """获取设备详细信息。"""
        try:
            output = await self._run_cmd("info", f"--udid={self.udid}")
            info = json.loads(output)
            return {
                "udid": self.udid,
                "name": info.get("DeviceName", ""),
                "version": info.get("ProductVersion", ""),
                "model": info.get("ProductType", ""),
                "serial": info.get("SerialNumber", ""),
            }
        except Exception as e:
            logger.error(f"[{self.udid}] 获取设备信息失败: {e}")
            return {"udid": self.udid}

    async def install_app(self, ipa_path: str) -> tuple[bool, str]:
        """安装 IPA 到 iOS 设备。"""
        try:
            output = await self._run_cmd(
                "install", f"--path={ipa_path}", f"--udid={self.udid}"
            )
            logger.info(f"[{self.udid}] IPA 安装成功: {output[:200]}")
            return True, "IPA 安装成功"
        except Exception as e:
            return False, str(e)


def _build_runwda_command(
    ios_bin: str,
    udid: str,
    bundle_id: str = "",
    xctest_config: str = "WebDriverAgentRunner.xctest",
) -> list[str]:
    cmd = [ios_bin, "runwda", f"--udid={udid}"]
    if bundle_id:
        cmd.extend([
            f"--bundleid={bundle_id}",
            f"--testrunnerbundleid={bundle_id}",
            f"--xctestconfig={xctest_config}",
        ])
    return cmd
