#!/usr/bin/env bash
# 验证打包后的后端可执行文件是否正常运行
# 用法: npm run backend:verify

set -e

EXE="resources/msca-backend.exe"
PORT=18099
TIMEOUT=15

if [ ! -f "$EXE" ]; then
  echo "[verify] 错误: $EXE 不存在，请先执行 npm run backend:build"
  exit 1
fi

echo "[verify] 启动 $EXE (端口 $PORT)..."
"$EXE" --port $PORT &
PID=$!

# 确保退出时清理进程
cleanup() {
  echo "[verify] 清理进程 $PID..."
  kill $PID 2>/dev/null || true
  wait $PID 2>/dev/null || true
}
trap cleanup EXIT

# 等待健康检查通过
echo "[verify] 等待后端就绪..."
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
  if curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q "200"; then
    echo "[verify] 健康检查通过 (${ELAPSED}s)"

    # 验证返回内容
    RESPONSE=$(curl -s "http://127.0.0.1:$PORT/health")
    echo "[verify] /health 响应: $RESPONSE"

    # 验证设备列表 API
    DEVICES=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/api/devices" 2>/dev/null)
    echo "[verify] /api/devices 状态码: $DEVICES"

    if [ "$DEVICES" = "200" ]; then
      echo ""
      echo "[verify] ✅ 后端打包验证通过！"
      exit 0
    else
      echo "[verify] ❌ API 路由异常"
      exit 1
    fi
  fi
  sleep 1
  ELAPSED=$((ELAPSED + 1))
done

echo "[verify] ❌ 后端启动超时 (${TIMEOUT}s)"
exit 1
