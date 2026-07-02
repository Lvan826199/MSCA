const { spawn, execFile } = require("child_process")
const path = require("path")
const fs = require("fs")
const http = require("http")
const net = require("net")
const { backendStatus, restartDecision, isProcessAlive, parsePortFile, buildIosCleanupScript } = require("./backend-manager-state")

const DEFAULT_PORT = 18000
const MAX_PORT_ATTEMPTS = 3
const HEALTH_CHECK_INTERVAL = 500
const HEALTH_CHECK_TIMEOUT = 15000
const MAX_RESTART_ATTEMPTS = 3
const RESTART_DELAYS = [0, 3000, 5000]

class BackendManager {
  constructor(isPackaged = false) {
    this._process = null
    this._port = DEFAULT_PORT
    this._restartCount = 0
    this._stopping = false
    this._usingExternalBackend = false
    // 重启互斥标志：避免快速反复崩溃时触发多条并行重启链
    this._restarting = false
    // 代际 token：进程更替后使旧的健康检查轮询失效
    this._generation = 0
    this._isPackaged = isPackaged
  }

  get port() {
    return this._port
  }

  get isRunning() {
    return this._usingExternalBackend || isProcessAlive(this._process)
  }

  getStatus() {
    return backendStatus({ port: this._port, running: this.isRunning })
  }

  async start() {
    this._stopping = false
    this._usingExternalBackend = false
    const existingPort = await this._findHealthyExistingPort()
    if (existingPort !== null) {
      this._port = existingPort
      this._usingExternalBackend = true
      try {
        fs.writeFileSync(this._portFilePath(), String(this._port))
      } catch {
        // 写入失败不影响复用已有后端，前端仍可通过 IPC 获取端口
      }
      console.log(`[backend] 复用已有健康后端，端口 ${this._port}`)
      return this._port
    }

    await this._cleanupResidualProcesses()
    this._port = await this._findAvailablePort()
    await this._spawn()
    try {
      await this._waitForHealth()
      return this._port
    } catch (e) {
      await this.stop()
      throw e
    }
  }

  async stop() {
    this._stopping = true
    if (this._usingExternalBackend) {
      this._usingExternalBackend = false
      return
    }
    await this._killProcess()
  }

  // 启动前清理上次异常退出的残留进程（msca-backend.exe 与本应用目录下的 ios.exe），
  // 避免端口被占用、打包目录文件被锁。仅 Windows 需要（强杀不传递到子进程树的平台）。
  async _cleanupResidualProcesses() {
    if (process.platform !== "win32") return
    const run = (cmd, args) =>
      new Promise((resolve) => {
        execFile(cmd, args, { windowsHide: true }, () => resolve())
      })

    // 单实例锁已保证没有其他存活的 MSCA（同构建）实例，残留后端可按映像名清理；
    // dev 模式后端经 uv/python 启动且可能与安装版共存，不按映像名清理
    if (this._isPackaged) {
      await run("taskkill", ["/F", "/T", "/IM", "msca-backend.exe"])
    }

    // ios.exe 名称通用，仅清理本应用 bin/ios 目录下启动的进程
    const base = this._isPackaged
      ? process.resourcesPath || path.join(__dirname, "..")
      : path.join(__dirname, "..")
    const iosDir = path.join(base, "bin", "ios")
    await run("powershell", [
      "-NoProfile",
      "-NonInteractive",
      "-Command",
      buildIosCleanupScript(iosDir),
    ])
    console.log("[backend] 残留进程清理完成")
  }

  // 仅终止后端进程，不改变 _stopping 状态（供崩溃重启失败路径复用，避免污染重试判断）
  async _killProcess() {
    const proc = this._process
    if (!proc) return
    if (process.platform === "win32") {
      // Windows 的 proc.kill 是强杀且只杀后端自身，子进程（ios.exe 等）会变孤儿残留，
      // 占用打包目录导致下次 electron-builder 清理失败；改用 taskkill /T 整树终止
      await new Promise((resolve) => {
        const timeout = setTimeout(resolve, 5000)
        proc.once("exit", () => {
          clearTimeout(timeout)
          resolve()
        })
        execFile("taskkill", ["/PID", String(proc.pid), "/T", "/F"], (err) => {
          if (err && isProcessAlive(proc)) {
            try { proc.kill("SIGKILL") } catch { /* 进程已退出 */ }
          }
        })
      })
    } else {
      proc.kill("SIGTERM")
      await new Promise((resolve) => {
        const timeout = setTimeout(() => {
          // killed 仅表示“已发送过信号”，需用 exitCode/signalCode 判断进程是否仍存活
          if (isProcessAlive(proc)) proc.kill("SIGKILL")
          resolve()
        }, 5000)
        proc.once("exit", () => {
          clearTimeout(timeout)
          resolve()
        })
      })
    }
    if (this._process === proc) this._process = null
  }

  async _handleCrash() {
    // 互斥：重启链进行中时，旧进程的 exit/error 不再触发新的重启链
    if (this._restarting) return
    this._restarting = true
    try {
      while (true) {
        const decision = restartDecision({
          stopping: this._stopping,
          restartCount: this._restartCount,
          maxRestartAttempts: MAX_RESTART_ATTEMPTS,
          restartDelays: RESTART_DELAYS,
        })
        if (decision.action === "stopping") return
        if (decision.action === "give-up") {
          const { dialog } = require("electron")
          dialog.showErrorBox("MSCA 后端异常", "后端进程多次崩溃，请检查日志或手动重启应用。")
          return
        }
        this._restartCount++
        console.log(`[backend] 崩溃重启 (${this._restartCount}/${MAX_RESTART_ATTEMPTS})，等待 ${decision.delay}ms`)
        await new Promise((r) => setTimeout(r, decision.delay))
        if (this._stopping) return
        try {
          await this._spawn()
          await this._waitForHealth()
          this._restartCount = 0
          return
        } catch (e) {
          console.error(`[backend] 重启失败: ${e.message}`)
          // 只杀进程、不置 _stopping，保证剩余重试次数仍然有效
          await this._killProcess()
        }
      }
    } finally {
      this._restarting = false
    }
  }

  _getBackendPath() {
    const isDev = !this._isPackaged
    if (isDev) return process.platform === "win32" ? "uv" : "uv"
    const res = process.resourcesPath || path.join(__dirname, "..")
    const exe = process.platform === "win32" ? "msca-backend.exe" : "msca-backend"
    return path.join(res, "resources", "msca-backend", exe)
  }

  async _spawn() {
    const isDev = !this._isPackaged
    const cmd = this._getBackendPath()
    const portFile = this._portFilePath()
    // 清理残留端口文件，避免健康检查回读到上次运行的旧端口
    try {
      fs.unlinkSync(portFile)
    } catch {
      // 文件不存在时忽略
    }
    let args, opts
    if (isDev) {
      // dev 模式走 __main__.py，统一处理端口文件写入
      args = [
        "run", "python", "__main__.py",
        "--host", "127.0.0.1",
        "--port", String(this._port),
        "--port-file", portFile,
      ]
      opts = { stdio: ["ignore", "pipe", "pipe"], windowsHide: true, cwd: path.join(__dirname, "..", "backend") }
    } else {
      const resPath = process.resourcesPath || path.join(__dirname, "..")
      const backendRuntimeDir = path.join(resPath, "resources", "msca-backend")
      // 打包模式显式指定端口文件路径（Nuitka 产物的默认落点不可靠）；
      // 日志目录与端口文件同样写到 userData，安装目录（Program Files）可能只读
      args = [
        "--port", String(this._port),
        "--port-file", portFile,
        "--log-dir", path.join(path.dirname(portFile), "logs"),
      ]
      opts = {
        cwd: backendRuntimeDir,
        stdio: ["ignore", "pipe", "pipe"],
        windowsHide: true,
        env: {
          ...process.env,
          PATH: `${backendRuntimeDir}${path.delimiter}${process.env.PATH || ""}`,
          MSCA_RESOURCES_PATH: resPath,
        },
      }
    }
    this._generation++
    const proc = spawn(cmd, args, opts)
    this._process = proc
    proc.stdout.on("data", (d) => console.log(`[backend] ${d.toString().trim()}`))
    proc.stderr.on("data", (d) => console.error(`[backend] ${d.toString().trim()}`))
    // error 与 exit 可能先后触发（如 kill 失败），用 settled 确保只处理一次
    let settled = false
    const markGone = () => {
      if (settled) return false
      settled = true
      // 仅在仍指向本进程时置空，避免误清掉重启链中新 spawn 的进程
      if (this._process === proc) this._process = null
      return true
    }
    proc.once("error", (err) => {
      // spawn 失败（如 uv 不在 PATH、exe 缺失）时 exit 不会触发，按一次启动失败处理
      if (!markGone()) return
      console.error(`[backend] 后端进程启动失败: ${err.message}`)
      if (!this._stopping) this._handleCrash()
    })
    proc.once("exit", (code, signal) => {
      if (!markGone()) return
      if (this._stopping) return
      if (code === 0) {
        // 退出码 0 视为正常退出，不重启，但记录日志避免完全静默
        console.warn("[backend] 后端进程已正常退出（退出码 0），不再自动重启")
        return
      }
      console.error(`[backend] 后端进程异常退出 code=${code} signal=${signal}`)
      this._handleCrash()
    })
  }

  _portFilePath() {
    if (this._isPackaged) {
      // 打包模式：resources 目录可能只读（如安装到 Program Files），
      // 端口文件统一写到 userData 目录，通过 --port-file 显式传给后端
      const { app } = require("electron")
      return path.join(app.getPath("userData"), ".backend-port")
    }
    // dev 模式与 backend/__main__.py 默认写入路径一致：项目根目录/.backend-port
    return path.join(__dirname, "..", ".backend-port")
  }

  // --port 仅为“起始端口”，后端可能实际选用其他端口并写入端口文件，
  // 健康检查前回读实际端口，消除 Electron 探测与后端绑定之间的竞态
  _refreshPortFromFile() {
    try {
      const port = parsePortFile(fs.readFileSync(this._portFilePath(), "utf-8"))
      if (port !== null) this._port = port
    } catch {
      // 文件尚未生成时忽略，继续使用探测到的端口
    }
  }

  async _findAvailablePort() {
    for (let i = 0; i < MAX_PORT_ATTEMPTS; i++) {
      const port = DEFAULT_PORT + i
      const ok = await new Promise((resolve) => {
        const s = net.createServer()
        s.once("error", () => resolve(false))
        s.once("listening", () => s.close(() => resolve(true)))
        s.listen(port, "127.0.0.1")
      })
      if (ok) return port
    }
    throw new Error(`端口 ${DEFAULT_PORT}-${DEFAULT_PORT + MAX_PORT_ATTEMPTS - 1} 均被占用`)
  }

  async _findHealthyExistingPort() {
    const candidates = new Set([DEFAULT_PORT])
    try {
      const parsed = parsePortFile(fs.readFileSync(this._portFilePath(), "utf-8"))
      if (parsed !== null) candidates.add(parsed)
    } catch {
      // 端口文件不存在时仅探测默认端口
    }
    for (let i = 1; i < MAX_PORT_ATTEMPTS; i++) {
      candidates.add(DEFAULT_PORT + i)
    }
    for (const port of candidates) {
      if (await this._isBackendHealthy(port)) return port
    }
    return null
  }

  _isBackendHealthy(port) {
    return new Promise((resolve) => {
      let settled = false
      const finish = (value) => {
        if (settled) return
        settled = true
        resolve(value)
      }
      const req = http.get(`http://127.0.0.1:${port}/health`, (res) => {
        let body = ""
        res.setEncoding("utf8")
        res.on("data", (chunk) => {
          body += chunk
          if (body.length > 1024) req.destroy()
        })
        res.on("end", () => {
          if (res.statusCode !== 200) {
            finish(false)
            return
          }
          try {
            finish(JSON.parse(body).status === "ok")
          } catch {
            finish(false)
          }
        })
      })
      req.on("error", () => finish(false))
      req.setTimeout(1000, () => {
        req.destroy()
        finish(false)
      })
    })
  }

  _waitForHealth() {
    // 捕获当前代际，进程更替后旧的轮询链自动失效
    const gen = this._generation
    return new Promise((resolve, reject) => {
      const start = Date.now()
      const check = () => {
        if (gen !== this._generation) {
          reject(new Error("后端进程已更替，取消过期健康检查"))
          return
        }
        if (!this._process) {
          // 进程已退出（含 spawn 失败），快速失败，避免空轮询到超时
          reject(new Error("后端进程已退出"))
          return
        }
        if (Date.now() - start > HEALTH_CHECK_TIMEOUT) {
          reject(new Error("后端健康检查超时"))
          return
        }
        this._refreshPortFromFile()
        // 去重调度：req.destroy() 会再触发 error 事件，避免 timeout 与 error 各调度一次
        let scheduled = false
        const scheduleNext = () => {
          if (scheduled) return
          scheduled = true
          setTimeout(check, HEALTH_CHECK_INTERVAL)
        }
        const req = http.get(`http://127.0.0.1:${this._port}/health`, (res) => {
          if (res.statusCode === 200) {
            console.log(`[backend] 健康检查通过，端口 ${this._port}`)
            resolve()
          } else {
            res.resume()
            scheduleNext()
          }
        })
        req.on("error", scheduleNext)
        // timeout 回调只负责销毁请求，后续调度交由随之触发的 error 事件去重处理
        req.setTimeout(2000, () => req.destroy())
      }
      setTimeout(check, 300)
    })
  }
}

module.exports = BackendManager
