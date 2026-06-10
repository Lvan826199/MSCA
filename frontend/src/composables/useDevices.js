import { ref, readonly } from "vue"
import { useConnection } from "./useConnection"
import { buildDevicesApiUrl, shouldOpenDeviceSocket } from "./deviceConnectionState.js"

const devices = ref([])
let ws = null
let reconnectTimer = null
// 代际 token：disconnect 后使挂起中的 connect 失效，避免泄漏新建的 WebSocket
let connectGeneration = 0

async function connect() {
  if (!shouldOpenDeviceSocket(ws)) return
  const generation = ++connectGeneration

  const { ready, toWsUrl } = useConnection()
  await ready
  if (generation !== connectGeneration || !shouldOpenDeviceSocket(ws)) return

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
  connectGeneration++
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
  const { ready, getBackendUrl } = useConnection()
  try {
    await ready
    const res = await fetch(buildDevicesApiUrl(getBackendUrl()))
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
