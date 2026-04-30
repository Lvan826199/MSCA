import { existsSync } from "node:fs"
import http from "node:http"
import path from "node:path"
import { spawn } from "node:child_process"

const root = process.cwd()
const packagedBackendDir = path.join(root, "resources", "msca-backend")
const packagedBackend = path.join(packagedBackendDir, process.platform === "win32" ? "msca-backend.exe" : "msca-backend")
const distBackendDir = path.join(root, "dist", "backend", "msca-backend")
const distBackend = path.join(distBackendDir, process.platform === "win32" ? "msca-backend.exe" : "msca-backend")
const candidates = [distBackend, packagedBackend]
const backendDirCandidates = [distBackendDir, packagedBackendDir]
const requiredResources = [
  { name: "Electron 后端 exe", file: packagedBackend },
  { name: "scrcpy-server", file: path.join(root, "bin", "android", "scrcpy-server") },
  { name: "scrcpy-server.version", file: path.join(root, "bin", "android", "scrcpy-server.version") },
  { name: "bundletool.jar", file: path.join(root, "bin", "android", "bundletool.jar") },
  { name: "go-ios", file: path.join(root, "bin", "ios", process.platform === "win32" ? "ios.exe" : "ios") }
]

for (const resource of requiredResources) {
  if (!existsSync(resource.file)) {
    throw new Error(`${resource.name} 资源不存在: ${resource.file}`)
  }
  console.log(`[verify] 资源存在: ${resource.name}`)
}

const exe = candidates.find((file) => existsSync(file))
const backendRuntimeDir = backendDirCandidates.find((dir) => existsSync(dir))
if (!exe || !backendRuntimeDir) {
  throw new Error("msca-backend.exe 或运行时目录不存在，请先执行 npm run backend:build")
}

const port = 18099
const timeoutMs = 15_000

function request(pathname) {
  return new Promise((resolve, reject) => {
    const req = http.get(`http://127.0.0.1:${port}${pathname}`, (res) => {
      let body = ""
      res.setEncoding("utf8")
      res.on("data", (chunk) => {
        body += chunk
      })
      res.on("end", () => resolve({ status: res.statusCode ?? 0, body }))
    })
    req.on("error", reject)
    req.setTimeout(2_000, () => req.destroy(new Error("request timeout")))
  })
}

console.log(`[verify] 启动 ${exe} (端口 ${port})...`)
const launcher = exe
const launcherArgs = ["--port", String(port)]
const child = spawn(launcher, launcherArgs, {
  cwd: backendRuntimeDir,
  stdio: ["ignore", "pipe", "pipe"],
  windowsHide: true,
  env: {
    ...process.env,
    PATH: `${backendRuntimeDir}${path.delimiter}${process.env.PATH ?? ""}`,
    MSCA_RESOURCES_PATH: root,
  },
})

child.stdout.on("data", (chunk) => process.stdout.write(`[verify:stdout] ${chunk}`))
child.stderr.on("data", (chunk) => process.stderr.write(`[verify:stderr] ${chunk}`))

function stopChild() {
  if (child.exitCode !== null || child.signalCode !== null) {
    return Promise.resolve()
  }

  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      if (child.exitCode === null && child.signalCode === null) {
        child.kill("SIGKILL")
      }
    }, 5_000)

    child.once("exit", () => {
      clearTimeout(timer)
      resolve()
    })
    child.kill("SIGTERM")
  })
}

const cleanup = () => {
  if (child.exitCode === null && child.signalCode === null) {
    child.kill("SIGTERM")
  }
}

process.on("exit", cleanup)
process.on("SIGINT", () => {
  cleanup()
  process.exit(1)
})

const start = Date.now()
let health
while (Date.now() - start < timeoutMs) {
  try {
    health = await request("/health")
    if (health.status === 200) {
      break
    }
  } catch {}
  await new Promise((resolve) => setTimeout(resolve, 1000))
}

if (!health || health.status !== 200) {
  cleanup()
  throw new Error("后端启动超时，健康检查未通过")
}

console.log(`[verify] /health 响应: ${health.body}`)
const devices = await request("/api/devices")
console.log(`[verify] /api/devices 状态码: ${devices.status}`)

await stopChild()

if (devices.status !== 200) {
  throw new Error("API 路由异常")
}

console.log("[verify] 后端打包验证通过")
