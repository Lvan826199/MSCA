export function shouldOpenDeviceSocket(socket) {
  return !socket || socket.readyState === WebSocket.CLOSING || socket.readyState === WebSocket.CLOSED
}

export function buildDevicesApiUrl(baseUrl) {
  return `${baseUrl || ""}/api/devices`
}
