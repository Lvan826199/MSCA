import test from "node:test"
import assert from "node:assert/strict"

import { createVideoSocketCloseHandler } from "./videoSocketState.js"

test("video socket unexpected close clears socket reference so decoder can restart", () => {
  let socket = { readyState: 3 }
  let connected = true
  let cleanupCalls = 0

  const onclose = createVideoSocketCloseHandler({
    clearSocket() { socket = null },
    setConnected(value) { connected = value },
    cleanup() { cleanupCalls += 1 },
  })

  onclose()

  assert.equal(socket, null)
  assert.equal(connected, false)
  assert.equal(cleanupCalls, 1)
})
