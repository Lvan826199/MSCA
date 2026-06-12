// 后端进程管理的纯逻辑部分，抽离自 backend-manager.js，便于 node:test 单测

/**
 * 判断子进程是否仍然存活。
 * 注意：不能用 proc.killed —— 它仅表示“已发送过信号”，SIGTERM 发出后恒为 true。
 * exitCode 与 signalCode 均为 null 才表示进程尚未退出。
 */
function isProcessAlive(proc) {
  return proc != null && proc.exitCode === null && proc.signalCode === null
}

function shouldRestartBackend({ stopping, restartCount, maxRestartAttempts }) {
  return !stopping && restartCount < maxRestartAttempts
}

/**
 * 崩溃后的重启决策，区分三种情况：
 * - stopping：正在主动停止，静默忽略，不弹窗
 * - give-up：超过最大重试次数，提示用户
 * - restart：继续重启，附带本次等待延迟（越界时回退到最后一档）
 */
function restartDecision({ stopping, restartCount, maxRestartAttempts, restartDelays }) {
  if (stopping) return { action: "stopping" }
  if (restartCount >= maxRestartAttempts) return { action: "give-up" }
  const delays = restartDelays || []
  const delay = delays[restartCount] !== undefined ? delays[restartCount] : delays[delays.length - 1] || 0
  return { action: "restart", delay }
}

/**
 * 解析 .backend-port 文件内容，返回合法端口号；内容非法或越界时返回 null。
 */
function parsePortFile(text) {
  const port = Number.parseInt(String(text).trim(), 10)
  return Number.isInteger(port) && port > 0 && port < 65536 ? port : null
}

function backendStatus({ port, running }) {
  return { port, running }
}

/**
 * 生成清理本应用目录下 ios.exe 残留进程的 PowerShell 脚本。
 * ios.exe 名称过于通用，必须按可执行文件路径前缀过滤，避免误杀无关进程。
 */
function buildIosCleanupScript(iosDir) {
  // PowerShell 单引号字符串中仅需把单引号翻倍转义
  const escaped = String(iosDir).replace(/'/g, "''")
  return (
    `$p='${escaped}'; ` +
    "Get-CimInstance Win32_Process -Filter \"Name='ios.exe'\" | " +
    "Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($p, 'OrdinalIgnoreCase') } | " +
    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
  )
}

module.exports = { isProcessAlive, shouldRestartBackend, restartDecision, parsePortFile, backendStatus, buildIosCleanupScript }
