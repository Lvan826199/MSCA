import test from "node:test"
import assert from "node:assert/strict"

import { createMouseUpCommand, normalizeControlCommand } from "./controlCommandState.js"

test("createMouseUpCommand sends tap for simple click to keep iOS WDA tap compatibility", () => {
  const pos = { x: 10, y: 20, width: 100, height: 200 }

  assert.deepEqual(createMouseUpCommand(pos, false), {
    type: "tap",
    ...pos,
  })
})

test("createMouseUpCommand sends touch up after drag", () => {
  const pos = { x: 10, y: 20, width: 100, height: 200 }

  assert.deepEqual(createMouseUpCommand(pos, true), {
    type: "touch",
    action: "up",
    ...pos,
  })
})

test("normalizeControlCommand includes normalized coordinates for touch sync", () => {
  assert.deepEqual(
    normalizeControlCommand({ type: "touch", action: "move", x: 25, y: 50 }, 100, 200),
    { type: "touch", action: "move", x: 25, y: 50, nx: 0.25, ny: 0.25 },
  )
})
