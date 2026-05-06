"""go-ios 适配器 — 支持 iOS ≥16.x 设备。

通过 go-ios CLI 工具管理 WDA 服务、端口转发和设备信息获取。
核心改进：
- 支持 WDA bundle ID 自动检测和配置（解决 com.facebook vs com.ascript 问题）
- 分别转发 WDA API（设备 8100）和 MJPEG 流（设备 9100）
- 支持 relay 模式（WDA 已在运行时只做端口转发）
"""

import asyncio
import fnmatch
import json
import logging
import os
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


class GoIOSAdapter(IOSAdapterBase):
    """基于 go-ios 的 iOS 适配器，适用于 iOS ≥16.x。"""

    def __init__(self, udid: str, ios_bin: str = "ios"):
        super().__init__(udid)
        self._ios_bin = ios_bin
        self._wda_process: subprocess.Popen | None = None
        self._tunnel_process: subprocess.Popen | None = None
        self._mjpeg_forward_process: subprocess.Popen | None = None
        self._agent_process: subprocess.Popen | None = None

    async def _run_cmd(self, *args, timeout: int = 30) -> str:
        """执行 go-ios 命令并返回 stdout。"""
        cmd = [self._ios_bin] + list(args)
        logger.debug(f"[{self.udid}] 执行: {' '.join(cmd)}")
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
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
        self._tunnel_process = subprocess.Popen(
            [self._ios_bin, "forward", str(port), str(wda_device_port), f"--udid={self.udid}"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
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
        self._kill_process(self._tunnel_process)
        self._tunnel_process = None
        self.wda_info = None
        return False

    async def _start_runwda(self, port: int, mjpeg_port: int, wda_device_port: int, mjpeg_device_port: int) -> WDAInfo:
        """启动完整的 runwda + 端口转发。"""
        # 检测 WDA bundle ID
        bundle_id = await self.detect_wda_bundle_id()

        # 启动 WDA API 端口转发
        logger.info(f"[{self.udid}] 启动 go-ios 端口转发: 本地 {port} → 设备 {wda_device_port}")
        self._tunnel_process = subprocess.Popen(
            [self._ios_bin, "forward", str(port), str(wda_device_port), f"--udid={self.udid}"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

        # 构建 runwda 命令（关键：传递 --bundleid）
        wda_cmd = [self._ios_bin, "runwda", f"--udid={self.udid}"]
        if bundle_id:
            wda_cmd.extend([f"--bundleid={bundle_id}", f"--testbundleid={bundle_id}"])
            logger.info(f"[{self.udid}] 启动 WDA (go-ios)，bundle ID: {bundle_id}")
        else:
            logger.info(f"[{self.udid}] 启动 WDA (go-ios)，使用默认 bundle ID")

        self._wda_process = subprocess.Popen(
            wda_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

        # 等待 WDA 就绪
        for _i in range(30):
            await asyncio.sleep(1)
            if self._wda_process.poll() is not None:
                stderr = self._wda_process.stderr.read().decode(errors='replace') if self._wda_process.stderr else ""
                raw_error = f"WDA 进程退出: {stderr[:500]}"
                hint = diagnose_wda_failure(raw_error)
                logger.error(
                    "[%s] go-ios WDA 进程退出，分类=%s，错误=%s，建议=%s",
                    self.udid,
                    hint.category,
                    raw_error,
                    hint.suggestion,
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
        self._mjpeg_forward_process = subprocess.Popen(
            [self._ios_bin, "forward", str(mjpeg_port), str(mjpeg_device_port), f"--udid={self.udid}"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        await asyncio.sleep(0.5)
        if self._mjpeg_forward_process.poll() is not None:
            stderr = ""
            if self._mjpeg_forward_process.stderr:
                stderr = self._mjpeg_forward_process.stderr.read().decode(errors='replace')
            logger.warning(f"[{self.udid}] MJPEG forward 进程立即退出: {stderr[:300]}")
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
        """停止 WDA、端口转发和 tunnel agent 进程。"""
        for proc in [self._wda_process, self._tunnel_process, self._mjpeg_forward_process, self._agent_process]:
            self._kill_process(proc)
        self._wda_process = None
        self._tunnel_process = None
        self._mjpeg_forward_process = None
        self._agent_process = None
        self.wda_info = None
        logger.debug(f"[{self.udid}] go-ios 所有子进程已清理")

    async def _ensure_tunnel(self) -> None:
        """确保 go-ios tunnel agent 正在运行（iOS 17+ 必需）。

        三阶段策略：
        1. 检测 tunnel 是否已在运行
        2. 尝试 --userspace 模式（无需管理员权限）
        3. 提权启动默认模式（弹出 UAC/密码框）
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

        raw_error = (
            "go-ios tunnel 启动失败（iOS 17+ 必需）。\n"
            "尝试过的方式：\n"
            "  1) --userspace 模式（无需管理员）\n"
            "  2) 管理员提权启动\n"
            "请手动执行以下任一操作：\n"
            "  - Windows: 以管理员身份运行 scripts/ios-tunnel.bat\n"
            "  - macOS/Linux: 运行 scripts/ios-tunnel.sh\n"
            "  - 或手动执行: ios tunnel start（需管理员/sudo）"
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
            self._agent_process = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
            )
            for i in range(timeout_s):
                await asyncio.sleep(1)
                if self._agent_process.poll() is not None:
                    stderr = ""
                    if self._agent_process.stderr:
                        stderr = self._agent_process.stderr.read().decode(errors="replace")
                    logger.warning(f"[{self.udid}] tunnel ({desc}) 进程退出: {stderr[:500]}")
                    self._agent_process = None
                    return False
                try:
                    await self._run_cmd("tunnel", "ls", timeout=3)
                    logger.info(f"[{self.udid}] tunnel agent 就绪 ({desc}，等待 {i+1}s)")
                    return True
                except Exception:
                    continue

            logger.warning(f"[{self.udid}] tunnel ({desc}) {timeout_s}s 内未就绪")
            self._kill_process(self._agent_process)
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
