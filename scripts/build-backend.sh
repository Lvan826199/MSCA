#!/usr/bin/env bash
# Nuitka 编译后端为独立可执行文件
# 用法: 在项目根目录执行 npm run backend:build

set -e

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

# 移动产物到 resources 目录
mkdir -p ../resources
mv msca-backend.exe ../resources/msca-backend.exe 2>/dev/null || mv __main__.exe ../resources/msca-backend.exe 2>/dev/null || true

echo "[build] 后端编译完成 -> resources/msca-backend.exe"
