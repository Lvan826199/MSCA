"""MSCA 后端入口 — 供 Nuitka 编译和独立运行使用。"""

import argparse
import uvicorn


def main():
    parser = argparse.ArgumentParser(description="MSCA Backend Server")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=18000, help="监听端口")
    args = parser.parse_args()

    uvicorn.run("app.main:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
