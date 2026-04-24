import { ref, shallowRef } from "vue"
import { useConnection } from "./useConnection"

/**
 * 视频解码与 WebSocket 流管理。
 *
 * 使用 WebCodecs VideoDecoder 解码 H.264 裸流，渲染到 Canvas。
 * 协议：服务端发送 [1字节帧类型 + H.264 数据]
 *   0x01 = key frame, 0x00 = delta frame
 * 首条 JSON 消息为 config: { width, height, codec }
 */
export function useVideoDecoder(deviceId) {
  const connected = ref(false)
  const videoWidth = ref(0)
  const videoHeight = ref(0)
  const fps = ref(0)
  const error = ref(null)
  const canvasRef = shallowRef(null)

  let ws = null
  let decoder = null
  let frameCount = 0
  let fpsTimer = null
  let configData = null // 缓存 SPS/PPS 用于 decoder configure

  function getVideoWsUrl() {
    const { getBackendUrl } = useConnection()
    return getBackendUrl().replace(/^http/, "ws") + `/ws/video/${deviceId}`
  }

  function start(canvas) {
    if (ws) return
    canvasRef.value = canvas
    error.value = null

    ws = new WebSocket(getVideoWsUrl())
    ws.binaryType = "arraybuffer"

    ws.onopen = () => {
      connected.value = true
      startFpsCounter()
    }

    ws.onmessage = (event) => {
      if (typeof event.data === "string") {
        handleJsonMessage(event.data)
      } else {
        handleBinaryFrame(event.data)
      }
    }

    ws.onclose = () => {
      connected.value = false
      cleanup()
    }

    ws.onerror = () => {
      error.value = "WebSocket 连接失败"
      ws?.close()
    }
  }

  function stop() {
    if (ws) {
      ws.onclose = null
      ws.close()
      ws = null
    }
    cleanup()
  }

  function handleJsonMessage(data) {
    try {
      const msg = JSON.parse(data)
      if (msg.type === "config") {
        videoWidth.value = msg.width
        videoHeight.value = msg.height
      }
    } catch { /* ignore */ }
  }

  function handleBinaryFrame(buffer) {
    const view = new Uint8Array(buffer)
    if (view.length < 2) return

    const isKey = view[0] === 0x01
    const h264Data = view.slice(1)

    // 如果是关键帧且包含 SPS/PPS，缓存为 codec 配置
    if (isKey && !decoder) {
      configData = h264Data
      initDecoder(h264Data)
      return
    }

    if (!decoder) return

    try {
      const chunk = new EncodedVideoChunk({
        type: isKey ? "key" : "delta",
        timestamp: performance.now() * 1000, // 微秒
        data: h264Data,
      })
      decoder.decode(chunk)
      frameCount++
    } catch (e) {
      // 解码错误时尝试重置
      if (e.name === "InvalidStateError") {
        resetDecoder()
      }
    }
  }

  function initDecoder(firstKeyFrame) {
    if (decoder) return

    const canvas = canvasRef.value
    if (!canvas) return

    const ctx = canvas.getContext("2d")

    try {
      decoder = new VideoDecoder({
        output: (frame) => {
          // 自适应 canvas 尺寸
          if (canvas.width !== frame.displayWidth || canvas.height !== frame.displayHeight) {
            canvas.width = frame.displayWidth
            canvas.height = frame.displayHeight
            videoWidth.value = frame.displayWidth
            videoHeight.value = frame.displayHeight
          }
          ctx.drawImage(frame, 0, 0)
          frame.close()
        },
        error: (e) => {
          error.value = `解码错误: ${e.message}`
          resetDecoder()
        },
      })

      decoder.configure({
        codec: "avc1.640028", // H.264 High Profile Level 4.0
        optimizeForLatency: true,
      })

      // 送入第一个关键帧
      const chunk = new EncodedVideoChunk({
        type: "key",
        timestamp: performance.now() * 1000,
        data: firstKeyFrame,
      })
      decoder.decode(chunk)
      frameCount++
    } catch (e) {
      error.value = `初始化解码器失败: ${e.message}`
      decoder = null
    }
  }

  function resetDecoder() {
    if (decoder) {
      try { decoder.close() } catch { /* ignore */ }
      decoder = null
    }
  }

  function startFpsCounter() {
    frameCount = 0
    fpsTimer = setInterval(() => {
      fps.value = frameCount
      frameCount = 0
    }, 1000)
  }

  function cleanup() {
    connected.value = false
    clearInterval(fpsTimer)
    fpsTimer = null
    resetDecoder()
    configData = null
  }

  return {
    connected,
    videoWidth,
    videoHeight,
    fps,
    error,
    start,
    stop,
  }
}
