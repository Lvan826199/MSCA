import { ref, readonly } from "vue"
import { useConnection } from "./useConnection"

const status = ref("disconnected") // connected | connecting | disconnected
let ws = null
let heartbeatTimer = null
let reconnectTimer = null
let reconnectAttempts = 0
const HEARTBEAT_INTERVAL = 30000
const RECONNECT_BASE_DELAY = 1000
const MAX_RECONNECT_DELAY_EXPONENT = 5

function connect() {
  // OPEN / CONNECTING 状态均短路，避免创建第二个 WebSocket 覆盖模块级 ws
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return

  // 新建前关闭旧连接并摘除回调，防止旧 socket 泄漏与回调串扰
  if (ws) {
    ws.onopen = null
    ws.onclose = null
    ws.onerror = null
    ws.onmessage = null
    try { ws.close() } catch { /* ignore */ }
    ws = null
  }

  const { toWsUrl } = useConnection()
  status.value = "connecting"
  try {
    ws = new WebSocket(toWsUrl("/ws/echo"))
  } catch {
    status.value = "disconnected"
    scheduleReconnect()
    return
  }

  ws.onopen = () => {
    status.value = "connected"
    reconnectAttempts = 0
    startHeartbeat()
  }

  ws.onclose = () => {
    status.value = "disconnected"
    stopHeartbeat()
    scheduleReconnect()
  }

  ws.onerror = () => {
    ws.close()
  }

  ws.onmessage = (event) => {
    if (event.data === "pong") return
  }
}

function disconnect() {
  clearTimeout(reconnectTimer)
  stopHeartbeat()
  if (ws) {
    ws.onclose = null
    ws.close()
    ws = null
  }
  status.value = "disconnected"
}

function startHeartbeat() {
  stopHeartbeat()
  heartbeatTimer = setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send("ping")
    }
  }, HEARTBEAT_INTERVAL)
}

function stopHeartbeat() {
  clearInterval(heartbeatTimer)
  heartbeatTimer = null
}

function scheduleReconnect() {
  // 先清理旧定时器，避免重复调度叠加。持续重连，防止后端启动较慢时状态永久停在未连接。
  clearTimeout(reconnectTimer)
  const delay = RECONNECT_BASE_DELAY * Math.pow(
    2,
    Math.min(reconnectAttempts, MAX_RECONNECT_DELAY_EXPONENT)
  )
  reconnectAttempts++
  reconnectTimer = setTimeout(connect, delay)
}

export function useWebSocket() {
  // 首次调用时等待后端 URL 就绪后自动连接
  if (!ws && status.value === "disconnected" && reconnectAttempts === 0) {
    const { ready } = useConnection()
    ready.then(() => connect())
  }

  return {
    status: readonly(status),
    connect,
    disconnect,
  }
}
