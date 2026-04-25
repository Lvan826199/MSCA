#!/usr/bin/env bash
# Nuitka 编译后端为独立可执行文件
# 用法: 在项目根目录执行 npm run backend:build
# 产物输出到 dist/backend/

set -e

DIST_DIR="dist/backend"

echo "[build] 开始编译后端..."

cd backend

# 确保 nuitka 已安装
uv run python -c "import nuitka" 2>/dev/null || {
  echo "[build] 安装 nuitka..."
  uv add --dev nuitka ordered-set
}

# Nuitka 编译
uv run python -m nuitka \
  --standalone \
  --onefile \
  --output-filename=msca-backend.exe \
  --include-package=app \
  --include-package=uvicorn \
  --include-package=fastapi \
  --follow-imports \
  __main__.py

cd ..

# 移动产物到 dist/backend 目录
mkdir -p "$DIST_DIR"
mv backend/msca-backend.exe "$DIST_DIR/msca-backend.exe" 2>/dev/null \
  || mv backend/__main__.exe "$DIST_DIR/msca-backend.exe" 2>/dev/null \
  || true

# 同时复制一份到 resources（Electron 打包需要）
mkdir -p resources
cp "$DIST_DIR/msca-backend.exe" resources/msca-backend.exe 2>/dev/null || true

echo "[build] 后端编译完成 -> $DIST_DIR/msca-backend.exe"
