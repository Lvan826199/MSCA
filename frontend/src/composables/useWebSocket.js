import { ref, readonly } from "vue"
import { useConnection } from "./useConnection"

const status = ref("disconnected") // connected | connecting | disconnected
let ws = null
let heartbeatTimer = null
let reconnectTimer = null
let reconnectAttempts = 0
const MAX_RECONNECT_ATTEMPTS = 10
const HEARTBEAT_INTERVAL = 30000
const RECONNECT_BASE_DELAY = 1000

function getWsUrl() {
  const { getBackendUrl } = useConnection()
  const url = getBackendUrl()
  return url.replace(/^http/, "ws") + "/ws/echo"
}

function connect() {
  if (ws && ws.readyState === WebSocket.OPEN) return

  status.value = "connecting"
  try {
    ws = new WebSocket(getWsUrl())
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
  if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) return
  const delay = RECONNECT_BASE_DELAY * Math.pow(2, Math.min(reconnectAttempts, 5))
  reconnectAttempts++
  reconnectTimer = setTimeout(connect, delay)
}

export function useWebSocket() {
  return {
    status: readonly(status),
    connect,
    disconnect,
  }
}
