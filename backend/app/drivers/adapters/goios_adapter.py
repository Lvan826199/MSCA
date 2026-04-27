"""go-ios 适配器 — 支持 iOS ≥16.x 设备。

通过 go-ios CLI 工具管理 WDA 服务、端口转发和设备信息获取。
"""

import asyncio
import json
import logging
import os
import subprocess

from .base import IOSAdapterBase, WDAInfo, is_port_free, kill_process_on_port

logger = logging.getLogger(__name__)


class GoIOSAdapter(IOSAdapterBase):
    """基于 go-ios 的 iOS 适配器，适用于 iOS ≥16.x。"""

    def __init__(self, udid: str, ios_bin: str = "ios"):
        super().__init__(udid)
        self._ios_bin = ios_bin
        self._wda_process: subprocess.Popen | None = None
        self._tunnel_process: subprocess.Popen | None = None
        self._agent_process: subprocess.Popen | None = None

    async def _run_cmd(self, *args, timeout: int = 30) -> str:
        """执行 go-ios 命令并返回 stdout。"""
        cmd = [self._ios_bin] + list(args)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        if proc.returncode != 0:
            raise RuntimeError(f"go-ios 命令失败: {' '.join(cmd)}\n{stderr.decode(errors='replace')}")
        return stdout.decode(errors='replace')

    async def list_devices(self) -> list[dict]:
        """通过 go-ios 列出已连接的 iOS 设备。"""
        try:
            output = await self._run_cmd("list", "--nojson")
        except FileNotFoundError:
            logger.warning("go-ios (ios) 未安装，无法发现 iOS 设备")
            return []
        except Exception as e:
            logger.error(f"go-ios 设备列表获取失败: {e}")
            return []

        # 尝试 JSON 格式解析
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

    async def start_wda(self, port: int = 8100) -> WDAInfo:
        """启动 WDA 并建立端口转发隧道。"""
        await self.stop_wda()

        # 确保端口空闲
        if not is_port_free(port):
            logger.warning(f"[{self.udid}] 端口 {port} 被占用，尝试清理残留进程")
            kill_process_on_port(port)
            await asyncio.sleep(0.5)
            if not is_port_free(port):
                raise RuntimeError(f"端口 {port} 仍被占用，无法启动 WDA")

        # iOS 17+ 需要先启动 tunnel agent
        await self._ensure_tunnel()

        # 启动端口转发隧道
        logger.info(f"[{self.udid}] 启动 go-ios 端口转发 {port}")
        self._tunnel_process = subprocess.Popen(
            [self._ios_bin, "forward", str(port), "8100", f"--udid={self.udid}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # 启动 WDA
        logger.info(f"[{self.udid}] 启动 WDA (go-ios)")
        self._wda_process = subprocess.Popen(
            [self._ios_bin, "runwda", f"--udid={self.udid}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # 等待 WDA 就绪
        for i in range(30):
            await asyncio.sleep(1)
            if self._wda_process.poll() is not None:
                stderr = self._wda_process.stderr.read().decode(errors='replace') if self._wda_process.stderr else ""
                await self.stop_wda()
                raise RuntimeError(f"WDA 进程退出: {stderr}")

            self.wda_info = WDAInfo(host="127.0.0.1", port=port)
            if await self.check_wda_health():
                logger.info(f"[{self.udid}] WDA 就绪 @ {port} (go-ios)")
                return self.wda_info

        await self.stop_wda()
        raise TimeoutError(f"[{self.udid}] WDA 启动超时（30s）")

    async def stop_wda(self) -> None:
        """停止 WDA、端口转发和 tunnel agent 进程。"""
        for proc in [self._wda_process, self._tunnel_process, self._agent_process]:
            if proc:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        self._wda_process = None
        self._tunnel_process = None
        self._agent_process = None
        self.wda_info = None

    async def _ensure_tunnel(self) -> None:
        """确保 go-ios tunnel agent 正在运行（iOS 17+ 必需）。

        go-ios 需要 `ios tunnel start` 来建立与 iOS 17+ 设备的通信隧道。
        如果 agent 已在运行（由其他进程启动），则跳过。
        """
        # 先检查是否已有 agent 在运行（通过 tunnel ls 测试）
        try:
            await self._run_cmd("tunnel", "ls", timeout=5)
            logger.debug(f"[{self.udid}] go-ios tunnel agent 已在运行")
            return
        except Exception:
            pass

        # 尝试多种方式启动 tunnel agent
        tunnel_cmds = [
            # 方式 1: userspace 模式（不需要管理员权限）
            {
                "args": [self._ios_bin, "tunnel", "start", "--userspace"],
                "env": {**os.environ, "ENABLE_GO_IOS_AGENT": "1"},
                "desc": "userspace 模式",
            },
            # 方式 2: 默认模式
            {
                "args": [self._ios_bin, "tunnel", "start"],
                "env": {**os.environ, "ENABLE_GO_IOS_AGENT": "1"},
                "desc": "默认模式",
            },
        ]

        last_error = ""
        for tunnel_cfg in tunnel_cmds:
            logger.info(f"[{self.udid}] 启动 go-ios tunnel agent ({tunnel_cfg['desc']})")
            try:
                self._agent_process = subprocess.Popen(
                    tunnel_cfg["args"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=tunnel_cfg["env"],
                )
                # 等待 tunnel 就绪
                for _ in range(15):
                    await asyncio.sleep(1)
                    if self._agent_process.poll() is not None:
                        stderr = self._agent_process.stderr.read().decode(errors="replace") if self._agent_process.stderr else ""
                        last_error = stderr[:500]
                        logger.warning(f"[{self.udid}] tunnel agent ({tunnel_cfg['desc']}) 退出: {last_error}")
                        self._agent_process = None
                        break
                    # 检查 tunnel 是否就绪
                    try:
                        await self._run_cmd("tunnel", "ls", timeout=3)
                        logger.info(f"[{self.udid}] go-ios tunnel agent 就绪 ({tunnel_cfg['desc']})")
                        return
                    except Exception:
                        continue
                else:
                    # 15 秒超时但进程还活着，再检查一次
                    try:
                        await self._run_cmd("tunnel", "ls", timeout=3)
                        logger.info(f"[{self.udid}] go-ios tunnel agent 就绪 ({tunnel_cfg['desc']})")
                        return
                    except Exception:
                        last_error = f"tunnel agent ({tunnel_cfg['desc']}) 15s 内未就绪"
                        logger.warning(f"[{self.udid}] {last_error}")
                        # 清理未就绪的进程
                        if self._agent_process:
                            try:
                                self._agent_process.terminate()
                                self._agent_process.wait(timeout=3)
                            except Exception:
                                try:
                                    self._agent_process.kill()
                                except Exception:
                                    pass
                            self._agent_process = None
            except Exception as e:
                last_error = str(e)
                logger.warning(f"[{self.udid}] 启动 tunnel agent ({tunnel_cfg['desc']}) 失败: {e}")

        # 所有方式都失败了，抛出明确错误
        raise RuntimeError(
            f"go-ios tunnel 启动失败（iOS 17+ 必需）。"
            f"请确保：1) 以管理员身份运行，或 2) go-ios 版本支持 --userspace 模式。"
            f"最后错误: {last_error}"
        )

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
        """安装 IPA 到 iOS 设备。

        Returns:
            (success, message)
        """
        try:
            output = await self._run_cmd(
                "install", f"--path={ipa_path}", f"--udid={self.udid}"
            )
            logger.info(f"[{self.udid}] IPA 安装成功: {output[:200]}")
            return True, "IPA 安装成功"
        except Exception as e:
            return False, str(e)
