const { spawn } = require("child_process")
const path = require("path")
const http = require("http")
const net = require("net")

const DEFAULT_PORT = 18000
const MAX_PORT_ATTEMPTS = 3
const HEALTH_CHECK_INTERVAL = 500
const HEALTH_CHECK_TIMEOUT = 15000
const MAX_RESTART_ATTEMPTS = 3
const RESTART_DELAYS = [0, 3000, 5000]

class BackendManager {
  constructor() {
    this._process = null
    this._port = DEFAULT_PORT
    this._restartCount = 0
    this._stopping = false
  }

  get port() {
    return this._port
  }

  get isRunning() {
    return this._process !== null && !this._process.killed
  }

  async start() {
    this._stopping = false
    this._port = await this._findAvailablePort()
    await this._spawn()
    await this._waitForHealth()
    return this._port
  }

  async stop() {
    this._stopping = true
    if (!this._process) return
    const proc = this._process
    proc.kill("SIGTERM")
    await new Promise((resolve) => {
      const timeout = setTimeout(() => {
        if (!proc.killed) proc.kill("SIGKILL")
        resolve()
      }, 5000)
      proc.once("exit", () => {
        clearTimeout(timeout)
        resolve()
      })
    })
    this._process = null
  }

  async _handleCrash() {
    if (this._restartCount >= MAX_RESTART_ATTEMPTS) {
      const { dialog } = require("electron")
      dialog.showErrorBox("MSCA 后端异常", "后端进程多次崩溃，请检查日志或手动重启应用。")
      return
    }
    const delay = RESTART_DELAYS[this._restartCount] || 5000
    this._restartCount++
    console.log(`[backend] 崩溃重启 (${this._restartCount}/${MAX_RESTART_ATTEMPTS})，等待 ${delay}ms`)
    await new Promise((r) => setTimeout(r, delay))
    if (!this._stopping) {
      try {
        await this._spawn()
        await this._waitForHealth()
        this._restartCount = 0
      } catch {
        this._handleCrash()
      }
    }
  }

  _getBackendPath() {
    const isDev = process.env.NODE_ENV !== "production"
    if (isDev) return process.platform === "win32" ? "uv" : "uv"
    const res = process.resourcesPath || path.join(__dirname, "..")
    const exe = process.platform === "win32" ? "msca-backend.exe" : "msca-backend"
    return path.join(res, "resources", exe)
  }

  async _spawn() {
    const isDev = process.env.NODE_ENV !== "production"
    const cmd = this._getBackendPath()
    let args, opts
    if (isDev) {
      // dev 模式走 __main__.py，统一处理端口文件写入
      args = ["run", "python", "__main__.py", "--host", "127.0.0.1", "--port", String(this._port)]
      opts = { stdio: ["ignore", "pipe", "pipe"], windowsHide: true, cwd: path.join(__dirname, "..", "backend") }
    } else {
      const resPath = process.resourcesPath || path.join(__dirname, "..")
      args = ["--port", String(this._port)]
      opts = {
        stdio: ["ignore", "pipe", "pipe"],
        windowsHide: true,
        env: {
          ...process.env,
          MSCA_RESOURCES_PATH: resPath,
        },
      }
    }
    this._process = spawn(cmd, args, opts)
    this._process.stdout.on("data", (d) => console.log(`[backend] ${d.toString().trim()}`))
    this._process.stderr.on("data", (d) => console.error(`[backend] ${d.toString().trim()}`))
    this._process.once("exit", (code) => {
      this._process = null
      if (!this._stopping && code !== 0) this._handleCrash()
    })
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

  _waitForHealth() {
    return new Promise((resolve, reject) => {
      const start = Date.now()
      const check = () => {
        if (Date.now() - start > HEALTH_CHECK_TIMEOUT) {
          reject(new Error("后端健康检查超时"))
          return
        }
        const req = http.get(`http://127.0.0.1:${this._port}/health`, (res) => {
          if (res.statusCode === 200) {
            console.log(`[backend] 健康检查通过，端口 ${this._port}`)
            resolve()
          } else {
            setTimeout(check, HEALTH_CHECK_INTERVAL)
          }
        })
        req.on("error", () => setTimeout(check, HEALTH_CHECK_INTERVAL))
        req.setTimeout(2000, () => {
          req.destroy()
          setTimeout(check, HEALTH_CHECK_INTERVAL)
        })
      }
      setTimeout(check, 300)
    })
  }
}

module.exports = BackendManager
