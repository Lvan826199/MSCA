"""MSCA 后端入口 — 供 Nuitka 编译和独立运行使用。

启动流程：
1. 从指定端口开始探测可用端口
2. 将实际端口写入 .backend-port 文件
3. 启动 uvicorn 服务
4. 退出时自动清理端口文件
"""

import argparse
import atexit
import json
import os
import signal
import socket
import sys
import time
from pathlib import Path

import uvicorn

DEFAULT_PORT = 18000
MAX_PORT_ATTEMPTS = 10


def port_available(host: str, port: int) -> bool:
    """探测端口在指定监听地址上是否可绑定。

    探测地址必须与实际监听地址一致，否则 --host 0.0.0.0 时
    探测结论不代表 uvicorn 实际可绑定。
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def find_available_port(start: int, attempts: int = MAX_PORT_ATTEMPTS, host: str = "127.0.0.1") -> int:
    """从 start 开始逐个尝试，返回第一个可用端口。"""
    for offset in range(attempts):
        port = start + offset
        if port_available(host, port):
            return port
    raise RuntimeError(f"端口 {start}-{start + attempts - 1} 均被占用")


def port_metadata_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.json")


def write_port_file(path: Path, port: int, host: str = "127.0.0.1") -> None:
    path.write_text(str(port), encoding="utf-8")
    metadata = {
        "host": host,
        "port": port,
        "pid": os.getpid(),
        "started_at": time.time(),
    }
    try:
        port_metadata_path(path).write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def remove_port_file(path: Path) -> None:
    for target in (path, port_metadata_path(path)):
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="MSCA Backend Server")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="起始端口")
    parser.add_argument(
        "--port-file",
        default=None,
        help="写入实际端口的文件路径（默认: 项目根目录/.backend-port）",
    )
    parser.add_argument(
        "--log-dir",
        default=None,
        help="日志文件目录（默认: backend/logs；打包模式由 Electron 传入 userData/logs）",
    )
    args = parser.parse_args()

    # 通过环境变量传给 app.main 的 setup_logging（uvicorn 按 import 字符串加载 app）
    if args.log_dir:
        os.environ["MSCA_LOG_DIR"] = args.log_dir

    # 端口文件路径：默认项目根目录
    if args.port_file:
        port_file = Path(args.port_file)
    else:
        port_file = Path(__file__).resolve().parent.parent / ".backend-port"

    atexit.register(remove_port_file, port_file)

    # Windows 上 SIGTERM 不一定可用，用 try 包裹
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            original = signal.getsignal(sig)

            def handler(s, f, _orig=original, _pf=port_file):
                remove_port_file(_pf)
                if callable(_orig) and _orig not in (signal.SIG_DFL, signal.SIG_IGN):
                    _orig(s, f)
                else:
                    sys.exit(0)

            signal.signal(sig, handler)
        except (OSError, ValueError):
            pass

    # uvicorn 启动失败退出码（uvicorn.main.STARTUP_FAILURE）
    startup_failure_code = 3

    # 探测可用后逐个端口尝试启动：探测与 uvicorn 实际 bind 之间存在 TOCTOU 窗口，
    # 端口在间隙中被抢占时 uvicorn 以 SystemExit(3) 失败，清理端口文件换下一个端口重试
    for offset in range(MAX_PORT_ATTEMPTS):
        port = args.port + offset
        if not port_available(args.host, port):
            continue

        write_port_file(port_file, port, args.host)
        print(f"[backend] 启动于端口 {port}，端口文件: {port_file}")
        try:
            uvicorn.run("app.main:app", host=args.host, port=port)
            return
        except SystemExit as exc:
            if exc.code == startup_failure_code:
                print(f"[backend] 端口 {port} 启动失败（可能被抢占），尝试下一个端口")
                remove_port_file(port_file)
                continue
            raise

    raise RuntimeError(f"端口 {args.port}-{args.port + MAX_PORT_ATTEMPTS - 1} 均无法启动")


if __name__ == "__main__":
    main()
