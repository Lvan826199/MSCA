"""MSCA 后端入口 — 供 Nuitka 编译和独立运行使用。

启动流程：
1. 从指定端口开始探测可用端口
2. 将实际端口写入 .backend-port 文件
3. 启动 uvicorn 服务
4. 退出时自动清理端口文件
"""

import argparse
import atexit
import signal
import socket
import sys
from pathlib import Path

import uvicorn

DEFAULT_PORT = 18000
MAX_PORT_ATTEMPTS = 10


def find_available_port(start: int, attempts: int = MAX_PORT_ATTEMPTS) -> int:
    """从 start 开始逐个尝试，返回第一个可用端口。"""
    for offset in range(attempts):
        port = start + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"端口 {start}-{start + attempts - 1} 均被占用")


def write_port_file(path: Path, port: int) -> None:
    path.write_text(str(port), encoding="utf-8")


def remove_port_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
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
    args = parser.parse_args()

    port = find_available_port(args.port)

    # 端口文件路径：默认项目根目录
    if args.port_file:
        port_file = Path(args.port_file)
    else:
        port_file = Path(__file__).resolve().parent.parent / ".backend-port"

    write_port_file(port_file, port)
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

    print(f"[backend] 启动于端口 {port}，端口文件: {port_file}")
    uvicorn.run("app.main:app", host=args.host, port=port)


if __name__ == "__main__":
    main()
