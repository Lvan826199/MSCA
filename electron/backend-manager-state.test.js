const test = require("node:test")
const assert = require("node:assert/strict")

const { shouldRestartBackend, backendStatus } = require("./backend-manager-state.js")

test("shouldRestartBackend stops restarting after max attempts or explicit stop", () => {
  assert.equal(shouldRestartBackend({ stopping: false, restartCount: 0, maxRestartAttempts: 3 }), true)
  assert.equal(shouldRestartBackend({ stopping: false, restartCount: 3, maxRestartAttempts: 3 }), false)
  assert.equal(shouldRestartBackend({ stopping: true, restartCount: 0, maxRestartAttempts: 3 }), false)
})

test("backendStatus reports port and running state", () => {
  assert.deepEqual(backendStatus({ port: 18001, running: true }), {
    port: 18001,
    running: true,
  })
})
