export function createMouseUpCommand(pos) {
  // 始终发送 touch up：
  // - Android 后端无 tap 分支，必须依赖 up 注入 ACTION_UP
  // - iOS 后端会根据 down/up 序列的位移自动合成 tap/swipe
  return { type: "touch", action: "up", ...pos }
}

export function normalizeControlCommand(cmd, width, height) {
  if (cmd.x === undefined || !width || !height) return cmd
  return { ...cmd, nx: cmd.x / width, ny: cmd.y / height }
}
