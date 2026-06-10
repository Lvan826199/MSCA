const test = require("node:test")
const assert = require("node:assert/strict")

const {
  isProcessAlive,
  shouldRestartBackend,
  restartDecision,
  parsePortFile,
  backendStatus,
} = require("./backend-manager-state.js")

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

test("isProcessAlive 用 exitCode/signalCode 判断存活，而非 killed", () => {
  // SIGTERM 已发送但进程尚未退出：killed=true 但 exitCode/signalCode 仍为 null，应判为存活
  assert.equal(isProcessAlive({ killed: true, exitCode: null, signalCode: null }), true)
  // 正常退出
  assert.equal(isProcessAlive({ killed: false, exitCode: 0, signalCode: null }), false)
  // 被信号杀死
  assert.equal(isProcessAlive({ killed: true, exitCode: null, signalCode: "SIGKILL" }), false)
  // 进程对象不存在
  assert.equal(isProcessAlive(null), false)
  assert.equal(isProcessAlive(undefined), false)
})

test("restartDecision 区分 stopping / give-up / restart 三种情况", () => {
  const base = { maxRestartAttempts: 3, restartDelays: [0, 3000, 5000] }
  // 正在主动停止：静默忽略，优先级高于超限
  assert.deepEqual(restartDecision({ ...base, stopping: true, restartCount: 0 }), { action: "stopping" })
  assert.deepEqual(restartDecision({ ...base, stopping: true, restartCount: 5 }), { action: "stopping" })
  // 超过最大重试次数：弹窗提示
  assert.deepEqual(restartDecision({ ...base, stopping: false, restartCount: 3 }), { action: "give-up" })
  // 正常重启：延迟按次数递增（立即 → 3s → 5s）
  assert.deepEqual(restartDecision({ ...base, stopping: false, restartCount: 0 }), { action: "restart", delay: 0 })
  assert.deepEqual(restartDecision({ ...base, stopping: false, restartCount: 1 }), { action: "restart", delay: 3000 })
  assert.deepEqual(restartDecision({ ...base, stopping: false, restartCount: 2 }), { action: "restart", delay: 5000 })
})

test("restartDecision 延迟越界时回退到最后一档", () => {
  const decision = restartDecision({
    stopping: false,
    restartCount: 3,
    maxRestartAttempts: 5,
    restartDelays: [0, 3000, 5000],
  })
  assert.deepEqual(decision, { action: "restart", delay: 5000 })
})

test("parsePortFile 解析合法端口并拒绝非法内容", () => {
  assert.equal(parsePortFile("18001"), 18001)
  assert.equal(parsePortFile(" 18002\n"), 18002)
  assert.equal(parsePortFile(""), null)
  assert.equal(parsePortFile("abc"), null)
  assert.equal(parsePortFile("0"), null)
  assert.equal(parsePortFile("-1"), null)
  assert.equal(parsePortFile("70000"), null)
})
