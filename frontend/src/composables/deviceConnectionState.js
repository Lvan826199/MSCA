export function shouldOpenDeviceSocket(socket) {
  return !socket || socket.readyState === WebSocket.CLOSING || socket.readyState === WebSocket.CLOSED
}

export function buildDevicesApiUrl(baseUrl) {
  return `${baseUrl || ""}/api/devices`
}

export function buildDeviceAliasApiUrl(baseUrl, deviceId) {
  return `${baseUrl || ""}/api/devices/${encodeURIComponent(deviceId)}/alias`
}
