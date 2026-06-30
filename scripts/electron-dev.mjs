import { spawn } from "node:child_process"
import http from "node:http"
import { createRequire } from "node:module"
import net from "node:net"
import path from "node:path"
import process from "node:process"

const root = process.cwd()
const require = createRequire(import.meta.url)
const {
  buildFrontendDevServerUrl,
  getFrontendDevServerConfig,
} = require("./dev-server-config.cjs")

const frontendConfig = getFrontendDevServerConfig(process.env, root)
const frontendRoot = path.join(root, "frontend")
const viteCli = path.join(frontendRoot, "node_modules", "vite", "bin", "vite.js")
const electronCommand = process.platform === "win32"
  ? path.join(root, "node_modules", "electron", "dist", "electron.exe")
  : path.join(root, "node_modules", ".bin", "electron")

async function portAvailable(port) {
  return await new Promise((resolve) => {
    const server = net.createServer()
    server.once("error", () => resolve(false))
    server.once("listening", () => server.close(() => resolve(true)))
    server.listen(port, frontendConfig.host)
  })
}

async function findAvailablePort(startPort, attempts) {
  for (let offset = 0; offset < attempts; offset++) {
    const port = startPort + offset
    if (await portAvailable(port)) return port
  }
  throw new Error(`Frontend dev ports ${startPort}-${startPort + attempts - 1} are unavailable`)
}

function spawnChild(command, args, options = {}) {
  const child = spawn(command, args, {
    cwd: root,
    stdio: "inherit",
    windowsHide: true,
    ...options,
  })
  child.on("error", (err) => {
    console.error(`[electron-dev] Failed to start ${command}: ${err.message}`)
    shutdown(1)
  })
  return child
}

function waitForUrl(url, timeoutMs = 30_000) {
  const start = Date.now()
  return new Promise((resolve, reject) => {
    const check = () => {
      const req = http.get(url, (res) => {
        res.resume()
        resolve()
      })
      req.on("error", () => {
        if (Date.now() - start > timeoutMs) {
          reject(new Error(`Timed out waiting for frontend dev server: ${url}`))
          return
        }
        setTimeout(check, 500)
      })
      req.setTimeout(2000, () => req.destroy())
    }
    check()
  })
}

let frontendProcess = null
let electronProcess = null
let shuttingDown = false

function shutdown(code = 0) {
  if (shuttingDown) return
  shuttingDown = true
  for (const child of [electronProcess, frontendProcess]) {
    if (child && child.exitCode === null && child.signalCode === null) {
      try {
        if (process.platform === "win32") {
          spawn("taskkill", ["/PID", String(child.pid), "/T", "/F"], {
            stdio: "ignore",
            windowsHide: true,
          })
        } else {
          child.kill()
        }
      } catch {
        // Best-effort shutdown.
      }
    }
  }
  setTimeout(() => process.exit(code), 300)
}

const port = await findAvailablePort(frontendConfig.port, frontendConfig.portSearchAttempts)
const selectedFrontendConfig = { ...frontendConfig, port }
const frontendUrl = buildFrontendDevServerUrl(selectedFrontendConfig)
console.log(`[electron-dev] Frontend dev server: ${frontendUrl}`)

frontendProcess = spawnChild(
  process.execPath,
  [viteCli, "--host", frontendConfig.host, "--port", String(port), "--strictPort"],
  {
    cwd: frontendRoot,
    env: {
      ...process.env,
      MSCA_FRONTEND_HOST: frontendConfig.host,
      MSCA_FRONTEND_PORT: String(port),
    },
  }
)

try {
  await waitForUrl(frontendUrl)
} catch (err) {
  console.error(`[electron-dev] ${err.message}`)
  shutdown(1)
}

electronProcess = spawnChild(electronCommand, ["."], {
  env: {
    ...process.env,
    NODE_ENV: "development",
    MSCA_FRONTEND_HOST: frontendConfig.host,
    MSCA_FRONTEND_PORT: String(port),
    MSCA_FRONTEND_URL: frontendUrl,
  },
})

frontendProcess.on("exit", (code) => {
  if (!shuttingDown) shutdown(code || 0)
})

electronProcess.on("exit", (code) => {
  if (!shuttingDown) shutdown(code || 0)
})

process.on("SIGINT", () => shutdown(0))
process.on("SIGTERM", () => shutdown(0))
