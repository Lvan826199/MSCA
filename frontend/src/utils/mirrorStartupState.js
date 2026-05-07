export const MIRROR_CANVAS_MISSING_MESSAGE = "投屏画布未就绪，请重试"

export function shouldFailWhenCanvasMissing(canvas) {
  return !canvas
}
