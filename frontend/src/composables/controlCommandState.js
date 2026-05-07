export function createMouseUpCommand(pos) {
  return { type: "touch", action: "up", ...pos }
}

export function normalizeControlCommand(cmd, width, height) {
  if (cmd.x === undefined || !width || !height) return cmd
  return { ...cmd, nx: cmd.x / width, ny: cmd.y / height }
}
