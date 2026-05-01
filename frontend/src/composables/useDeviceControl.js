/**
 * useDeviceControl - 设备触控/按键控制 composable
 *
 * 功能：
 * 1. 建立控制 WebSocket 连接
 * 2. 捕获 canvas 上的触控/鼠标事件
 * 3. 将屏幕坐标转换为设备坐标
 * 4. 发送控制指令到后端
 * 5. 键盘事件映射（浏览器 KeyboardEvent → Android keycode）
 * 6. metaState 修饰键支持（Shift/Ctrl/Alt）
 */

import { ref, onUnmounted } from "vue"
import { useConnection } from "./useConnection"

// ─── 浏览器 KeyboardEvent.code → Android keycode 映射表 ───

const KEY_CODE_MAP = {
  // 字母键 A-Z → KEYCODE_A(29) - KEYCODE_Z(54)
  KeyA: 29, KeyB: 30, KeyC: 31, KeyD: 32, KeyE: 33, KeyF: 34, KeyG: 35,
  KeyH: 36, KeyI: 37, KeyJ: 38, KeyK: 39, KeyL: 40, KeyM: 41, KeyN: 42,
  KeyO: 43, KeyP: 44, KeyQ: 45, KeyR: 46, KeyS: 47, KeyT: 48, KeyU: 49,
  KeyV: 50, KeyW: 51, KeyX: 52, KeyY: 53, KeyZ: 54,
  // 数字键 0-9 → KEYCODE_0(7) - KEYCODE_9(16)
  Digit0: 7, Digit1: 8, Digit2: 9, Digit3: 10, Digit4: 11,
  Digit5: 12, Digit6: 13, Digit7: 14, Digit8: 15, Digit9: 16,
  // 功能键
  Enter: 66, Backspace: 67, Delete: 112, Tab: 61, Space: 62, Escape: 111,
  // 方向键
  ArrowUp: 19, ArrowDown: 20, ArrowLeft: 21, ArrowRight: 22,
  // 符号键
  Comma: 55, Period: 56, Slash: 76, Semicolon: 74, Quote: 75,
  BracketLeft: 71, BracketRight: 72, Backslash: 73, Minus: 69, Equal: 70,
  Backquote: 68,
  // F1-F12
  F1: 131, F2: 132, F3: 133, F4: 134, F5: 135, F6: 136,
  F7: 137, F8: 138, F9: 139, F10: 140, F11: 141, F12: 142,
  // 小键盘
  Numpad0: 144, Numpad1: 145, Numpad2: 146, Numpad3: 147, Numpad4: 148,
  Numpad5: 149, Numpad6: 150, Numpad7: 151, Numpad8: 152, Numpad9: 153,
  NumpadEnter: 66, NumpadAdd: 157, NumpadSubtract: 156,
  NumpadMultiply: 155, NumpadDivide: 154, NumpadDecimal: 158,
  // 其他
  Home: 122, End: 123, PageUp: 92, PageDown: 93, Insert: 124,
  CapsLock: 115, NumLock: 143, ScrollLock: 116,
}

// 需要忽略的修饰键（不单独发送 keycode）
const MODIFIER_CODES = new Set(["ShiftLeft", "ShiftRight", "ControlLeft", "ControlRight", "AltLeft", "AltRight", "MetaLeft", "MetaRight"])

/**
 * 从浏览器 KeyboardEvent 构建 Android metaState
 */
function buildMetaState(e) {
  let meta = 0
  if (e.shiftKey) meta |= 0x01   // META_SHIFT_ON
  if (e.altKey) meta |= 0x02     // META_ALT_ON
  if (e.ctrlKey) meta |= 0x1000  // META_CTRL_ON
  return meta
}

export function useDeviceControl(deviceId) {
  const connected = ref(false)
  const error = ref("")
  let ws = null
  let canvasEl = null
  let videoWidth = 0
  let videoHeight = 0
  let _onSyncEvent = null  // 同步事件回调
  let _isSyncReceiving = false  // 防止同步接收时再次广播

  function connect() {
    if (ws) return

    const { toWsUrl } = useConnection()
    ws = new WebSocket(toWsUrl(`/ws/control/${deviceId}`))

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
        // 处理设备消息回传
        if (data.device_msg) {
          handleDeviceMessage(data.device_msg)
        }
      } catch {
        /* binary or non-json, ignore */
      }
    }
  }

  function disconnect() {
    if (_rafId) { cancelAnimationFrame(_rafId); _rafId = null }
    _pendingMove = null
    if (ws) {
      ws.close()
      ws = null
    }
    connected.value = false
  }

  /**
   * 处理设备消息回传（剪贴板等）
   */
  function handleDeviceMessage(msg) {
    if (msg.type === "clipboard" && msg.text) {
      // 将设备剪贴板内容写入浏览器剪贴板
      navigator.clipboard.writeText(msg.text).catch(() => {})
    }
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
    if (!rect.width || !rect.height) return null

    // object-fit: contain 时，canvas 内容会按比例居中显示，需要扣除左右/上下黑边。
    const canvasRatio = canvasEl.width && canvasEl.height
      ? canvasEl.width / canvasEl.height
      : videoWidth / videoHeight
    const rectRatio = rect.width / rect.height
    let contentWidth = rect.width
    let contentHeight = rect.height
    let offsetX = 0
    let offsetY = 0

    if (rectRatio > canvasRatio) {
      contentWidth = rect.height * canvasRatio
      offsetX = (rect.width - contentWidth) / 2
    } else if (rectRatio < canvasRatio) {
      contentHeight = rect.width / canvasRatio
      offsetY = (rect.height - contentHeight) / 2
    }

    const relX = clientX - rect.left - offsetX
    const relY = clientY - rect.top - offsetY

    const scaleX = videoWidth / contentWidth
    const scaleY = videoHeight / contentHeight

    const devX = Math.round(relX * scaleX)
    const devY = Math.round(relY * scaleY)

    return {
      x: Math.max(0, Math.min(devX, videoWidth - 1)),
      y: Math.max(0, Math.min(devY, videoHeight - 1)),
      width: videoWidth,
      height: videoHeight,
    }
  }

  /**
   * 绑定 canvas 触控/鼠标/键盘事件
   */
  function bindCanvas(canvas, vw, vh) {
    canvasEl = canvas
    videoWidth = vw
    videoHeight = vh

    // 使 canvas 可聚焦以接收键盘事件
    if (!canvas.hasAttribute("tabindex")) {
      canvas.setAttribute("tabindex", "0")
    }

    // 鼠标事件
    canvas.addEventListener("mousedown", onMouseDown)
    canvas.addEventListener("mousemove", onMouseMove)
    canvas.addEventListener("mouseup", onMouseUp)
    canvas.addEventListener("wheel", onWheel, { passive: false })

    // 触控事件
    canvas.addEventListener("touchstart", onTouchStart, { passive: false })
    canvas.addEventListener("touchmove", onTouchMove, { passive: false })
    canvas.addEventListener("touchend", onTouchEnd, { passive: false })

    // 键盘事件
    canvas.addEventListener("keydown", onKeyDown)
    canvas.addEventListener("keyup", onKeyUp)

    // 阻止右键菜单
    canvas.addEventListener("contextmenu", preventDefault)
  }

  function unbindCanvas() {
    if (_documentMouseUpHandler) {
      document.removeEventListener("mouseup", _documentMouseUpHandler)
      _documentMouseUpHandler = null
    }
    mouseDown = false
    mouseMoved = false
    _lastDownPos = null
    if (!canvasEl) return
    canvasEl.removeEventListener("mousedown", onMouseDown)
    canvasEl.removeEventListener("mousemove", onMouseMove)
    canvasEl.removeEventListener("mouseup", onMouseUp)
    canvasEl.removeEventListener("wheel", onWheel)
    canvasEl.removeEventListener("touchstart", onTouchStart)
    canvasEl.removeEventListener("touchmove", onTouchMove)
    canvasEl.removeEventListener("touchend", onTouchEnd)
    canvasEl.removeEventListener("keydown", onKeyDown)
    canvasEl.removeEventListener("keyup", onKeyUp)
    canvasEl.removeEventListener("contextmenu", preventDefault)
    canvasEl = null
  }

  let mouseDown = false
  let mouseMoved = false
  let _pendingMove = null
  let _rafId = null
  let _documentMouseUpHandler = null
  let _lastDownPos = null
  const MOUSE_MOVE_THRESHOLD = 3

  function _emitSync(cmd) {
    if (_isSyncReceiving || !_onSyncEvent || !videoWidth || !videoHeight) return
    if (cmd.x !== undefined) {
      _onSyncEvent({ ...cmd, nx: cmd.x / videoWidth, ny: cmd.y / videoHeight })
    } else {
      _onSyncEvent(cmd)
    }
  }

  function _flushMove() {
    _rafId = null
    if (_pendingMove) {
      send(_pendingMove)
      _emitSync(_pendingMove)
      _pendingMove = null
    }
  }

  function onMouseDown(e) {
    if (e.button !== 0) return
    mouseDown = true
    mouseMoved = false
    const pos = canvasToDevice(e.clientX, e.clientY)
    if (pos) {
      _lastDownPos = pos
      const cmd = { type: "touch", action: "down", ...pos }
      send(cmd)
      _emitSync(cmd)
    }
    // 在 document 上监听 mouseup，防止鼠标滑出 canvas 后丢失 up 事件
    if (_documentMouseUpHandler) {
      document.removeEventListener("mouseup", _documentMouseUpHandler)
    }
    _documentMouseUpHandler = onMouseUp
    document.addEventListener("mouseup", _documentMouseUpHandler)
  }

  function onMouseMove(e) {
    if (!mouseDown) return
    const pos = canvasToDevice(e.clientX, e.clientY)
    if (pos) {
      if (_lastDownPos) {
        const dx = pos.x - _lastDownPos.x
        const dy = pos.y - _lastDownPos.y
        mouseMoved = mouseMoved || Math.hypot(dx, dy) >= MOUSE_MOVE_THRESHOLD
      }
      _pendingMove = { type: "touch", action: "move", ...pos }
      if (!_rafId) _rafId = requestAnimationFrame(_flushMove)
    }
  }

  function onMouseUp(e) {
    if (!mouseDown) return
    mouseDown = false
    // 移除 document 级别的 mouseup 监听
    if (_documentMouseUpHandler) {
      document.removeEventListener("mouseup", _documentMouseUpHandler)
      _documentMouseUpHandler = null
    }
    if (_pendingMove) { send(_pendingMove); _emitSync(_pendingMove); _pendingMove = null }
    if (_rafId) { cancelAnimationFrame(_rafId); _rafId = null }
    const pos = canvasToDevice(e.clientX, e.clientY) || _lastDownPos
    if (pos) {
      const cmd = mouseMoved
        ? { type: "touch", action: "up", ...pos }
        : { type: "tap", ...pos }
      send(cmd)
      _emitSync(cmd)
    }
    _lastDownPos = null
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

  function preventDefault(e) { e.preventDefault() }

  // ─── 键盘事件处理 ───

  function onKeyDown(e) {
    // 忽略纯修饰键按下
    if (MODIFIER_CODES.has(e.code)) return
    e.preventDefault()

    const keycode = KEY_CODE_MAP[e.code]
    if (keycode !== undefined) {
      send({
        type: "key",
        action: "down",
        keycode,
        metastate: buildMetaState(e),
        repeat: e.repeat ? 1 : 0,
      })
    }
  }

  function onKeyUp(e) {
    if (MODIFIER_CODES.has(e.code)) return
    e.preventDefault()
    // key up 由后端自动配对，无需前端单独发送
  }

  // ─── 快捷按键方法 ───

  function sendBack() { send({ type: "back" }) }
  function sendHome() { send({ type: "home" }) }
  function sendPower() { send({ type: "power" }) }
  function sendVolumeUp() { send({ type: "key", action: "down", keycode: 24 }) }
  function sendVolumeDown() { send({ type: "key", action: "down", keycode: 25 }) }
  function sendText(text) { if (text) send({ type: "text", text }) }
  function sendExpandNotification() { send({ type: "expand_notification" }) }
  function sendExpandSettings() { send({ type: "expand_settings" }) }
  function sendCollapsePanels() { send({ type: "collapse_panels" }) }
  function sendClipboard(text, paste = false) { if (text) send({ type: "clipboard", text, paste }) }
  function sendRotate() { send({ type: "rotate" }) }

  /**
   * 接收归一化触控事件（来自同步广播），转换为本设备坐标后发送
   */
  function sendNormalizedTouch(evt) {
    if (!videoWidth || !videoHeight) return
    _isSyncReceiving = true
    try {
      send({
        type: evt.type,
        action: evt.action,
        x: Math.max(0, Math.min(Math.round(evt.nx * videoWidth), videoWidth - 1)),
        y: Math.max(0, Math.min(Math.round(evt.ny * videoHeight), videoHeight - 1)),
        width: videoWidth,
        height: videoHeight,
      })
    } finally {
      _isSyncReceiving = false
    }
  }

  /**
   * 设置同步事件回调（触控操作时触发）
   */
  function setSyncCallback(fn) {
    _onSyncEvent = fn
  }

  // 更新视频尺寸（屏幕旋转时由外部调用）
  function updateVideoSize(vw, vh) {
    videoWidth = vw
    videoHeight = vh
  }

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
    updateVideoSize,
    sendBack,
    sendHome,
    sendPower,
    sendVolumeUp,
    sendVolumeDown,
    sendText,
    sendExpandNotification,
    sendExpandSettings,
    sendCollapsePanels,
    sendClipboard,
    sendRotate,
    sendNormalizedTouch,
    setSyncCallback,
  }
}
