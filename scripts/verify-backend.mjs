import { existsSync } from "node:fs"
import http from "node:http"
import path from "node:path"
import { spawn } from "node:child_process"

const root = process.cwd()
const candidates = [
  path.join(root, "dist", "backend", "msca-backend.exe"),
  path.join(root, "resources", "msca-backend.exe")
]

const exe = candidates.find((file) => existsSync(file))
if (!exe) {
  throw new Error("msca-backend.exe 不存在，请先执行 npm run backend:build")
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
const child = spawn(exe, ["--port", String(port)], {
  stdio: ["ignore", "pipe", "pipe"],
  windowsHide: true
})

child.stdout.on("data", (chunk) => process.stdout.write(`[verify:stdout] ${chunk}`))
child.stderr.on("data", (chunk) => process.stderr.write(`[verify:stderr] ${chunk}`))

const cleanup = () => {
  if (!child.killed) {
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

cleanup()

if (devices.status !== 200) {
  throw new Error("API 路由异常")
}

console.log("[verify] 后端打包验证通过")
