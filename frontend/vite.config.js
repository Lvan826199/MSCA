import { defineConfig } from "vite"
import vue from "@vitejs/plugin-vue"
import { resolve } from "path"
import { readFileSync } from "fs"
import { createRequire } from "module"
import http from "http"

const require = createRequire(import.meta.url)
const {
  getBackendDevServerConfig,
  getFrontendDevServerConfig,
} = require("../scripts/dev-server-config.cjs")

/**
 * 读取后端端口文件 (.backend-port)，获取后端实际监听端口。
 * 后端启动时自动写入该文件，Vite 启动时读取用于配置 proxy。
 */
function probeBackendHealth(host, port) {
  return new Promise((resolveProbe) => {
    let settled = false
    const finish = (value) => {
      if (settled) return
      settled = true
      resolveProbe(value)
    }
    const req = http.get(`http://${host}:${port}/health`, (res) => {
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
    req.setTimeout(300, () => {
      req.destroy()
      finish(false)
    })
  })
}

async function readBackendPort(host, defaultPort) {
  if (await probeBackendHealth(host, defaultPort)) return defaultPort

  try {
    const content = readFileSync(resolve(__dirname, "..", ".backend-port"), "utf-8")
    const port = parseInt(content.trim(), 10)
    if (Number.isFinite(port) && await probeBackendHealth(host, port)) {
      return port
    }
  } catch {
    // 端口文件不存在或不可读时回落默认端口
  }
  return defaultPort
}

export default defineConfig(async ({ command }) => {
  const backendConfig = getBackendDevServerConfig()
  const backendPort = await readBackendPort(backendConfig.host, backendConfig.port)
  const frontendConfig = getFrontendDevServerConfig()
  if (command === "serve") {
    console.log(`[vite] 前端开发服务: http://${frontendConfig.host}:${frontendConfig.port}`)
  }
  console.log(`[vite] 后端 proxy 目标端口: ${backendPort}`)

  return {
    base: "./",
    plugins: [vue()],
    resolve: {
      alias: {
        "@": resolve(__dirname, "src"),
      },
    },
    server: {
      host: frontendConfig.host,
      port: frontendConfig.port,
      strictPort: Boolean(process.env.MSCA_FRONTEND_PORT),
      proxy: {
        "/api": {
          target: `http://${backendConfig.host}:${backendPort}`,
          changeOrigin: true,
        },
        "/ws": {
          target: `ws://${backendConfig.host}:${backendPort}`,
          ws: true,
        },
        "/health": {
          target: `http://${backendConfig.host}:${backendPort}`,
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: "dist",
      rollupOptions: {
        output: {
          manualChunks(id) {
            const normalized = id.replace(/\\/g, "/")
            if (normalized.includes("/node_modules/")) {
              if (
                normalized.includes("/node_modules/element-plus/") ||
                normalized.includes("/node_modules/@element-plus/") ||
                normalized.includes("/node_modules/@popperjs/")
              ) {
                return "vendor-element-plus"
              }
              if (
                normalized.includes("/node_modules/vue/") ||
                normalized.includes("/node_modules/vue-router/") ||
                normalized.includes("/node_modules/@vue/")
              ) {
                return "vendor-vue"
              }
              return "vendor"
            }
            if (normalized.includes("/src/composables/useVideoDecoder.js")) {
              return "decoder-video"
            }
          },
        },
      },
    },
  }
})
