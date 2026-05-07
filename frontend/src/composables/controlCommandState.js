export function createMouseUpCommand(pos, moved = false) {
  if (moved) {
    return { type: "touch", action: "up", ...pos }
  }
  return { type: "tap", ...pos }
}

export function normalizeControlCommand(cmd, width, height) {
  if (cmd.x === undefined || !width || !height) return cmd
  return { ...cmd, nx: cmd.x / width, ny: cmd.y / height }
}
