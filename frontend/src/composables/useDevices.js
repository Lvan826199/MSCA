import { ref, readonly } from "vue"
import { useConnection } from "./useConnection"

const devices = ref([])
let ws = null
let reconnectTimer = null

function connect() {
  if (ws && ws.readyState === WebSocket.OPEN) return

  const { toWsUrl } = useConnection()
  try {
    ws = new WebSocket(toWsUrl("/ws/devices"))
  } catch {
    scheduleReconnect()
    return
  }

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data)
      if (msg.type === "devices") {
        devices.value = msg.data
      }
    } catch { /* ignore */ }
  }

  ws.onclose = () => scheduleReconnect()
  ws.onerror = () => ws.close()
}

function disconnect() {
  clearTimeout(reconnectTimer)
  if (ws) {
    ws.onclose = null
    ws.close()
    ws = null
  }
}

function scheduleReconnect() {
  clearTimeout(reconnectTimer)
  reconnectTimer = setTimeout(connect, 3000)
}

async function fetchDevices() {
  const { getBackendUrl } = useConnection()
  try {
    const res = await fetch(getBackendUrl() + "/api/devices")
    const data = await res.json()
    devices.value = data.devices || []
  } catch { /* ignore */ }
}

export function useDevices() {
  return {
    devices: readonly(devices),
    connect,
    disconnect,
    fetchDevices,
  }
}
