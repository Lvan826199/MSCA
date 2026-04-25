"""go-ios 适配器 — 支持 iOS ≥16.x 设备。

通过 go-ios CLI 工具管理 WDA 服务、端口转发和设备信息获取。
"""

import asyncio
import json
import logging
import subprocess

from .base import IOSAdapterBase, WDAInfo

logger = logging.getLogger(__name__)


class GoIOSAdapter(IOSAdapterBase):
    """基于 go-ios 的 iOS 适配器，适用于 iOS ≥16.x。"""

    def __init__(self, udid: str, ios_bin: str = "ios"):
        super().__init__(udid)
        self._ios_bin = ios_bin
        self._wda_process: subprocess.Popen | None = None
        self._tunnel_process: subprocess.Popen | None = None

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
            raise RuntimeError(f"go-ios 命令失败: {' '.join(cmd)}\n{stderr.decode()}")
        return stdout.decode()

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
                stderr = self._wda_process.stderr.read().decode() if self._wda_process.stderr else ""
                await self.stop_wda()
                raise RuntimeError(f"WDA 进程退出: {stderr}")

            self.wda_info = WDAInfo(host="127.0.0.1", port=port)
            if await self.check_wda_health():
                logger.info(f"[{self.udid}] WDA 就绪 @ {port} (go-ios)")
                return self.wda_info

        await self.stop_wda()
        raise TimeoutError(f"[{self.udid}] WDA 启动超时（30s）")

    async def stop_wda(self) -> None:
        """停止 WDA 和端口转发进程。"""
        for proc in [self._wda_process, self._tunnel_process]:
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
        self.wda_info = None

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
