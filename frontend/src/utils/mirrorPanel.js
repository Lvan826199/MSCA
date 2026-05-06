export const MIRROR_START_TIMEOUT_MESSAGE = "投屏启动超时，请检查设备连接、WDA/scrcpy 服务状态后重试"

export function mirrorFitStyles() {
  return {
    wrap: {
      width: "100%",
      height: "100%",
    },
    canvas: {
      width: "100%",
      height: "100%",
      objectFit: "contain",
    },
  }
}

export function createMirrorStartTimeout(timeoutMs) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)

  return {
    signal: controller.signal,
    clear() {
      clearTimeout(timer)
    },
    getErrorMessage() {
      return MIRROR_START_TIMEOUT_MESSAGE
    },
  }
}
