import test from "node:test"
import assert from "node:assert/strict"

import { createMirrorStartTimeout, mirrorFitStyles } from "./mirrorPanel.js"

test("mirrorFitStyles constrains canvas to panel area without distorting aspect ratio", () => {
  assert.deepEqual(mirrorFitStyles(), {
    wrap: {
      width: "100%",
      height: "100%",
    },
    canvas: {
      width: "100%",
      height: "100%",
      objectFit: "contain",
    },
  })
})

test("createMirrorStartTimeout aborts startup requests with a user-facing timeout message", async () => {
  const timeout = createMirrorStartTimeout(10)

  await new Promise((resolve) => timeout.signal.addEventListener("abort", resolve, { once: true }))

  assert.equal(timeout.signal.aborted, true)
  assert.equal(timeout.getErrorMessage(), "投屏启动超时，请检查设备连接、WDA/scrcpy 服务状态后重试")
  timeout.clear()
})
