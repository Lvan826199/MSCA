/**
 * useMjpegDecoder — iOS MJPEG 流解码 composable。
 *
 * 接收 WebSocket 二进制 JPEG 帧，渲染到 Canvas。
 * 比 H.264 WebCodecs 简单得多：每帧都是独立的 JPEG 图片。
 */

import { ref, onUnmounted } from "vue"

export function useMjpegDecoder() {
  const videoWidth = ref(0)
  const videoHeight = ref(0)

  let canvas = null
  let ctx = null
  let running = false

  /**
   * 初始化解码器，绑定 Canvas。
   */
  function init(canvasEl) {
    canvas = canvasEl
    ctx = canvas.getContext("2d")
    running = true
  }

  /**
   * 处理 MJPEG 帧（JPEG 二进制数据）。
   */
  function feedFrame(jpegData) {
    if (!running || !ctx) return

    const blob = new Blob([jpegData], { type: "image/jpeg" })
    const url = URL.createObjectURL(blob)
    const img = new Image()

    img.onload = () => {
      // 检测尺寸变化（屏幕旋转）
      if (img.width !== videoWidth.value || img.height !== videoHeight.value) {
        videoWidth.value = img.width
        videoHeight.value = img.height
        canvas.width = img.width
        canvas.height = img.height
      }

      ctx.drawImage(img, 0, 0)
      URL.revokeObjectURL(url)
    }

    img.onerror = () => {
      URL.revokeObjectURL(url)
    }

    img.src = url
  }

  /**
   * 停止解码器。
   */
  function stop() {
    running = false
    canvas = null
    ctx = null
  }

  onUnmounted(stop)

  return {
    videoWidth,
    videoHeight,
    init,
    feedFrame,
    stop,
  }
}
