/**
 * useDeviceControl - 设备触控/按键控制 composable
 *
 * 功能：
 * 1. 建立控制 WebSocket 连接
 * 2. 捕获 canvas 上的触控/鼠标事件
 * 3. 将屏幕坐标转换为设备坐标
 * 4. 发送控制指令到后端
 */

import { ref, onUnmounted } from "vue"
import { useConnection } from "./useConnection"

export function useDeviceControl(deviceId) {
  const connected = ref(false)
  const error = ref("")
  let ws = null
  let canvasEl = null
  let videoWidth = 0
  let videoHeight = 0

  function getWsUrl() {
    const { getBackendUrl } = useConnection()
    const base = getBackendUrl()
    const wsBase = base.replace(/^http/, "ws")
    return `${wsBase}/ws/control/${deviceId}`
  }

  function connect() {
    if (ws) return

    const url = getWsUrl()
    ws = new WebSocket(url)

    ws.onopen = () => {
      connected.value = true
      error.value = ""
    }

    ws.onclose = () => {
      connected.value = false
      ws = null
    }

    ws.onerror = (e) => {
      error.value = "控制连接失败"
      connected.value = false
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.error) {
          error.value = data.error
        }
      } catch {
        /* binary or non-json, ignore */
      }
    }
  }

  function disconnect() {
    if (ws) {
      ws.close()
      ws = null
    }
    connected.value = false
  }

  function send(cmd) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(cmd))
    }
  }

  /**
   * 将 canvas 上的鼠标/触控坐标转换为设备坐标
   */
  function canvasToDevice(clientX, clientY) {
    if (!canvasEl || !videoWidth || !videoHeight) return null

    const rect = canvasEl.getBoundingClientRect()
    // canvas 显示区域内的相对坐标
    const relX = clientX - rect.left
    const relY = clientY - rect.top

    // canvas 显示尺寸与视频实际尺寸的比例
    const scaleX = videoWidth / rect.width
    const scaleY = videoHeight / rect.height

    const devX = Math.round(relX * scaleX)
    const devY = Math.round(relY * scaleY)

    return {
      x: Math.max(0, Math.min(devX, videoWidth)),
      y: Math.max(0, Math.min(devY, videoHeight)),
      width: videoWidth,
      height: videoHeight,
    }
  }

  /**
   * 绑定 canvas 触控/鼠标事件
   */
  function bindCanvas(canvas, vw, vh) {
    canvasEl = canvas
    videoWidth = vw
    videoHeight = vh

    // 鼠标事件
    canvas.addEventListener("mousedown", onMouseDown)
    canvas.addEventListener("mousemove", onMouseMove)
    canvas.addEventListener("mouseup", onMouseUp)
    canvas.addEventListener("wheel", onWheel, { passive: false })

    // 触控事件
    canvas.addEventListener("touchstart", onTouchStart, { passive: false })
    canvas.addEventListener("touchmove", onTouchMove, { passive: false })
    canvas.addEventListener("touchend", onTouchEnd, { passive: false })

    // 阻止右键菜单
    canvas.addEventListener("contextmenu", (e) => e.preventDefault())
  }

  function unbindCanvas() {
    if (!canvasEl) return
    canvasEl.removeEventListener("mousedown", onMouseDown)
    canvasEl.removeEventListener("mousemove", onMouseMove)
    canvasEl.removeEventListener("mouseup", onMouseUp)
    canvasEl.removeEventListener("wheel", onWheel)
    canvasEl.removeEventListener("touchstart", onTouchStart)
    canvasEl.removeEventListener("touchmove", onTouchMove)
    canvasEl.removeEventListener("touchend", onTouchEnd)
    canvasEl = null
  }

  let mouseDown = false

  function onMouseDown(e) {
    if (e.button !== 0) return
    mouseDown = true
    const pos = canvasToDevice(e.clientX, e.clientY)
    if (pos) send({ type: "touch", action: "down", ...pos })
  }

  function onMouseMove(e) {
    if (!mouseDown) return
    const pos = canvasToDevice(e.clientX, e.clientY)
    if (pos) send({ type: "touch", action: "move", ...pos })
  }

  function onMouseUp(e) {
    if (!mouseDown) return
    mouseDown = false
    const pos = canvasToDevice(e.clientX, e.clientY)
    if (pos) send({ type: "touch", action: "up", ...pos })
  }

  function onWheel(e) {
    e.preventDefault()
    const pos = canvasToDevice(e.clientX, e.clientY)
    if (pos) {
      send({
        type: "scroll",
        ...pos,
        hScroll: Math.sign(-e.deltaX) * 120,
        vScroll: Math.sign(-e.deltaY) * 120,
      })
    }
  }

  function onTouchStart(e) {
    e.preventDefault()
    const touch = e.touches[0]
    if (!touch) return
    const pos = canvasToDevice(touch.clientX, touch.clientY)
    if (pos) send({ type: "touch", action: "down", ...pos })
  }

  function onTouchMove(e) {
    e.preventDefault()
    const touch = e.touches[0]
    if (!touch) return
    const pos = canvasToDevice(touch.clientX, touch.clientY)
    if (pos) send({ type: "touch", action: "move", ...pos })
  }

  function onTouchEnd(e) {
    e.preventDefault()
    const touch = e.changedTouches[0]
    if (!touch) return
    const pos = canvasToDevice(touch.clientX, touch.clientY)
    if (pos) send({ type: "touch", action: "up", ...pos })
  }

  // 快捷按键方法
  function sendBack() { send({ type: "back" }) }
  function sendHome() { send({ type: "home" }) }
  function sendPower() { send({ type: "power" }) }
  function sendVolumeUp() { send({ type: "key", action: "down", keycode: 24 }) }
  function sendVolumeDown() { send({ type: "key", action: "down", keycode: 25 }) }

  onUnmounted(() => {
    unbindCanvas()
    disconnect()
  })

  return {
    connected,
    error,
    connect,
    disconnect,
    send,
    bindCanvas,
    unbindCanvas,
    sendBack,
    sendHome,
    sendPower,
    sendVolumeUp,
    sendVolumeDown,
  }
}
