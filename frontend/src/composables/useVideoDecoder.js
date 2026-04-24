import { ref, shallowRef } from "vue"
import { useConnection } from "./useConnection"

/**
 * 视频解码与 WebSocket 流管理。
 *
 * 使用 WebCodecs VideoDecoder 解码 H.264 裸流，渲染到 Canvas。
 * 协议：服务端发送 [1字节帧类型 + H.264 数据]
 *   0x01 = key frame, 0x00 = delta frame
 * 首条 JSON 消息为 config: { width, height, codec }
 *
 * scrcpy 发送的是 Annex B 格式（start code 前缀）。
 * WebCodecs 配置了 description（AVCDecoderConfigurationRecord）后，
 * 期望 AVC 格式（4 字节长度前缀），且帧数据中不应包含 SPS/PPS。
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
  let hasDescription = false // 是否成功构建了 AVC description
  let timestampCounter = 0

  // ─── NAL 解析工具 ───

  /**
   * 从 Annex B 数据中解析所有 NAL 单元的位置。
   * 返回 [{ scOffset, offset, end, nalType }, ...]
   *   scOffset: start code 起始位置
   *   offset:   NAL 数据起始位置（start code 之后）
   *   end:      NAL 数据结束位置（下一个 start code 之前）
   *   nalType:  NAL 类型 (data[offset] & 0x1f)
   */
  function parseNalUnits(data) {
    const units = []
    let i = 0
    while (i < data.length - 3) {
      if (data[i] === 0 && data[i + 1] === 0) {
        if (data[i + 2] === 1) {
          units.push({ scOffset: i, offset: i + 3 })
          i += 3
          continue
        }
        if (data[i + 2] === 0 && i + 3 < data.length && data[i + 3] === 1) {
          units.push({ scOffset: i, offset: i + 4 })
          i += 4
          continue
        }
      }
      i++
    }
    for (let j = 0; j < units.length; j++) {
      const u = units[j]
      u.end = j + 1 < units.length ? units[j + 1].scOffset : data.length
      u.nalType = u.offset < u.end ? (data[u.offset] & 0x1f) : -1
    }
    return units
  }

  /**
   * 从 SPS 构建 codec 字符串，如 "avc1.640028"
   */
  function codecFromSps(spsData) {
    if (spsData.length < 4) return "avc1.640028"
    const hex = (b) => b.toString(16).padStart(2, "0")
    return `avc1.${hex(spsData[1])}${hex(spsData[2])}${hex(spsData[3])}`
  }

  /**
   * 构建 AVCDecoderConfigurationRecord (ISO 14496-15)。
   * 返回 { description: ArrayBuffer, codec: string } 或 null。
   */
  function buildAvcConfig(data) {
    const units = parseNalUnits(data)
    let sps = null
    let pps = null
    for (const u of units) {
      if (u.nalType === 7 && !sps) sps = data.slice(u.offset, u.end) // SPS
      if (u.nalType === 8 && !pps) pps = data.slice(u.offset, u.end) // PPS
    }
    if (!sps || !pps) return null

    const codec = codecFromSps(sps)
    // AVCDecoderConfigurationRecord
    const size = 11 + sps.length + pps.length
    const buf = new ArrayBuffer(size)
    const dv = new DataView(buf)
    const arr = new Uint8Array(buf)
    let o = 0
    dv.setUint8(o++, 1)              // configurationVersion
    dv.setUint8(o++, sps[1])         // AVCProfileIndication
    dv.setUint8(o++, sps[2])         // profile_compatibility
    dv.setUint8(o++, sps[3])         // AVCLevelIndication
    dv.setUint8(o++, 0xff)           // lengthSizeMinusOne = 3 → 4 bytes
    dv.setUint8(o++, 0xe1)           // numOfSPS = 1
    dv.setUint16(o, sps.length); o += 2
    arr.set(sps, o); o += sps.length
    dv.setUint8(o++, 1)              // numOfPPS = 1
    dv.setUint16(o, pps.length); o += 2
    arr.set(pps, o)
    return { description: buf, codec }
  }

  /**
   * 将 Annex B 帧转为 AVC 格式：
   * - 剥离 SPS(7)/PPS(8)/AUD(9)/SEI(6) 等非 VCL NAL
   * - 将 start code 替换为 4 字节大端长度前缀
   * 只保留 VCL NAL（IDR=5, non-IDR slice=1, slice_a=2, slice_b=3, slice_c=4）
   */
  function annexBToAvc(data) {
    const units = parseNalUnits(data)
    // VCL NAL types: 1-5
    const vclUnits = units.filter((u) => u.nalType >= 1 && u.nalType <= 5)
    if (vclUnits.length === 0) return null

    let totalLen = 0
    for (const u of vclUnits) totalLen += 4 + (u.end - u.offset)

    const out = new Uint8Array(totalLen)
    const view = new DataView(out.buffer)
    let pos = 0
    for (const u of vclUnits) {
      const nalLen = u.end - u.offset
      view.setUint32(pos, nalLen)
      pos += 4
      out.set(data.subarray(u.offset, u.end), pos)
      pos += nalLen
    }
    return out
  }

  /**
   * 判断 Annex B 数据中是否包含 IDR NAL（真正的关键帧）
   */
  function containsIdr(data) {
    const units = parseNalUnits(data)
    return units.some((u) => u.nalType === 5)
  }

  // ─── WebSocket 处理 ───

  function start(canvas) {
    if (ws) return
    canvasRef.value = canvas
    error.value = null
    timestampCounter = 0

    const { toWsUrl } = useConnection()
    ws = new WebSocket(toWsUrl(`/ws/video/${deviceId}`))
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

    // 首个关键帧用于初始化解码器
    if (isKey && !decoder) {
      initDecoder(h264Data)
      return
    }

    if (!decoder) return

    decodeFrame(h264Data, isKey)
  }

  function decodeFrame(h264Data, isKey) {
    try {
      let frameData
      let chunkType

      if (hasDescription) {
        // AVC 模式：转换格式，剥离 SPS/PPS
        frameData = annexBToAvc(h264Data)
        if (!frameData) return // 没有 VCL NAL，跳过
        // 根据实际 NAL 内容判断是否为关键帧
        chunkType = containsIdr(h264Data) ? "key" : "delta"
      } else {
        // Annex B 模式：直接送入
        frameData = h264Data
        chunkType = isKey ? "key" : "delta"
      }

      const chunk = new EncodedVideoChunk({
        type: chunkType,
        timestamp: timestampCounter++,
        data: frameData,
      })
      decoder.decode(chunk)
      frameCount++
    } catch (e) {
      if (e.name === "InvalidStateError") {
        resetDecoder()
      }
    }
  }

  // ─── 解码器管理 ───

  function initDecoder(firstKeyFrame) {
    if (decoder) return
    const canvas = canvasRef.value
    if (!canvas) return
    const ctx = canvas.getContext("2d")

    try {
      const avcConfig = buildAvcConfig(firstKeyFrame)
      hasDescription = !!avcConfig

      decoder = new VideoDecoder({
        output: (frame) => {
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

      const config = {
        codec: avcConfig ? avcConfig.codec : "avc1.640028",
        optimizeForLatency: true,
      }
      if (avcConfig) {
        config.description = avcConfig.description
      }
      decoder.configure(config)

      // 送入第一个关键帧
      decodeFrame(firstKeyFrame, true)
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
    hasDescription = false
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
