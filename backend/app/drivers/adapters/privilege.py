"""跨平台提权工具 — 用于以管理员/root 权限启动 go-ios tunnel。

支持三个平台：
- Windows: ShellExecuteW("runas") 弹出 UAC 提权窗口
- macOS: osascript "with administrator privileges" 弹出密码输入框
- Linux: pkexec（GUI）或 sudo -n（非交互）
"""

import ctypes
import logging
import os
import shlex
import shutil
import subprocess
import sys

logger = logging.getLogger(__name__)


def check_is_admin() -> bool:
    """检测当前进程是否拥有管理员/root 权限。"""
    if os.name == "nt":
        return _is_admin_windows()
    return os.geteuid() == 0


def launch_elevated(args: list[str], env: dict | None = None) -> bool:
    """以管理员权限启动命令（阻塞直到启动完成或用户取消）。

    注意：提权启动的进程是独立的守护进程，不返回 Popen 句柄。
    调用方应通过其他方式（如 `ios tunnel ls`）确认进程是否就绪。

    Returns:
        True 表示命令已成功提交（不代表进程已就绪），False 表示提权失败或被取消。
    """
    if os.name == "nt":
        return _elevate_windows(args)
    if sys.platform == "darwin":
        return _elevate_macos(args, env)
    return _elevate_linux(args, env)


# ─── Windows ───

def _is_admin_windows() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _elevate_windows(args: list[str]) -> bool:
    """通过 ShellExecuteW("runas") 弹出 UAC 提权窗口启动命令。"""
    exe = args[0]
    params = " ".join(args[1:]) if len(args) > 1 else ""
    logger.info(f"Windows UAC 提权启动: {exe} {params}")
    try:
        # ShellExecuteW 返回值 > 32 表示成功
        ret = ctypes.windll.shell32.ShellExecuteW(
            None,    # hwnd
            "runas", # lpOperation
            exe,     # lpFile
            params,  # lpParameters
            None,    # lpDirectory
            0,       # nShowCmd: SW_HIDE
        )
        if ret > 32:
            logger.info(f"UAC 提权启动成功 (返回值={ret})")
            return True
        logger.warning(f"UAC 提权启动失败 (返回值={ret})")
        return False
    except Exception as e:
        logger.error(f"Windows 提权异常: {e}")
        return False


# ─── macOS ───

def _elevate_macos(args: list[str], env: dict | None = None) -> bool:
    """通过 osascript 弹出系统密码输入框以管理员权限执行命令。"""
    cmd_str = " ".join(shlex.quote(a) for a in args)
    # 注入必要的环境变量
    if env:
        env_parts = []
        for k in ("ENABLE_GO_IOS_AGENT",):
            if k in env:
                env_parts.append(f"{k}={shlex.quote(env[k])}")
        if env_parts:
            cmd_str = " ".join(env_parts) + " " + cmd_str

    # nohup + & 使进程在后台持续运行
    script = f'do shell script "nohup {cmd_str} > /dev/null 2>&1 &" with administrator privileges'
    logger.info(f"macOS osascript 提权启动: {cmd_str}")
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            logger.info("macOS 提权启动成功")
            return True
        logger.warning(f"macOS 提权失败: {result.stderr.strip()}")
        return False
    except subprocess.TimeoutExpired:
        logger.warning("macOS 提权超时（用户可能未响应密码框）")
        return False
    except Exception as e:
        logger.error(f"macOS 提权异常: {e}")
        return False


# ─── Linux ───

def _elevate_linux(args: list[str], env: dict | None = None) -> bool:
    """Linux 提权：优先 pkexec（GUI），回退 sudo -n（非交互）。"""
    # 方案 1: pkexec（PolicyKit，有 GUI 弹窗）
    if shutil.which("pkexec"):
        logger.info(f"Linux pkexec 提权启动: {' '.join(args)}")
        try:
            result = subprocess.run(
                ["pkexec"] + args,
                capture_output=True, text=True, timeout=120,
                env=env,
            )
            if result.returncode == 0:
                logger.info("Linux pkexec 提权启动成功")
                return True
            logger.warning(f"pkexec 失败 (rc={result.returncode}): {result.stderr.strip()[:200]}")
        except subprocess.TimeoutExpired:
            logger.warning("pkexec 超时")
        except Exception as e:
            logger.warning(f"pkexec 异常: {e}")

    # 方案 2: sudo -n（非交互，仅在配置了免密 sudo 时有效）
    if shutil.which("sudo"):
        logger.info(f"Linux sudo -n 提权启动: {' '.join(args)}")
        try:
            result = subprocess.run(
                ["sudo", "-n"] + args,
                capture_output=True, text=True, timeout=30,
                env=env,
            )
            if result.returncode == 0:
                logger.info("Linux sudo 提权启动成功")
                return True
            logger.warning(f"sudo -n 失败: {result.stderr.strip()[:200]}")
        except Exception as e:
            logger.warning(f"sudo 异常: {e}")

    logger.error("Linux 提权失败：pkexec 和 sudo 均不可用或被拒绝")
    return False
