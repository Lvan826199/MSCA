#!/usr/bin/env bash
# ============================================================
# ios-tunnel.sh — 以管理员权限启动 go-ios tunnel（macOS/Linux）
#
# iOS 17+ 设备需要 tunnel 才能使用 WDA 投屏。
# 如果 MSCA 自动提权失败，可手动运行此脚本。
#
# 使用方式：
#   chmod +x scripts/ios-tunnel.sh
#   ./scripts/ios-tunnel.sh
# ============================================================

set -euo pipefail

export ENABLE_GO_IOS_AGENT=1

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IOS_BIN=""

echo "============================================================"
echo "  go-ios tunnel 启动脚本"
echo "============================================================"
echo

# 查找 ios 二进制
if [ -x "$SCRIPT_DIR/../bin/ios/ios" ]; then
    IOS_BIN="$SCRIPT_DIR/../bin/ios/ios"
elif command -v ios &>/dev/null; then
    IOS_BIN="$(command -v ios)"
else
    echo "[ERROR] 未找到 ios 二进制文件"
    echo "  请确保 go-ios 已安装并在 PATH 中，或放置在项目 bin/ios/ 目录下"
    echo "  下载地址: https://github.com/danielpaulus/go-ios/releases"
    exit 1
fi

echo "[INFO] 使用: $IOS_BIN"

# 检查 tunnel 是否已在运行
if "$IOS_BIN" tunnel ls &>/dev/null; then
    echo "[OK] Tunnel 已在运行，无需重复启动"
    exit 0
fi

# 先尝试 userspace 模式（不需要 sudo）
echo "[INFO] 尝试 userspace 模式（无需管理员权限）..."
"$IOS_BIN" tunnel start --userspace &>/dev/null &
USERSPACE_PID=$!
sleep 3

if "$IOS_BIN" tunnel ls &>/dev/null; then
    echo "[OK] Tunnel 已启动 (userspace 模式, PID=$USERSPACE_PID)"
    echo "[INFO] 请保持此终端运行。按 Ctrl+C 停止 tunnel。"
    wait $USERSPACE_PID
    exit 0
fi

# userspace 失败，kill 掉后台进程
kill $USERSPACE_PID 2>/dev/null || true
echo "[INFO] userspace 模式不可用，需要管理员权限"

# 使用 sudo 启动
echo "[INFO] 启动 tunnel（需要输入密码）..."
echo

if [ "$(uname)" = "Darwin" ]; then
    # macOS
    sudo "$IOS_BIN" tunnel start
elif command -v pkexec &>/dev/null && [ -n "${DISPLAY:-}" ]; then
    # Linux with GUI
    pkexec "$IOS_BIN" tunnel start
else
    # Linux without GUI
    sudo "$IOS_BIN" tunnel start
fi
