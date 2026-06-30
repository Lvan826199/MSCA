import { defineConfig } from "vite"
import vue from "@vitejs/plugin-vue"
import { resolve } from "path"
import { readFileSync } from "fs"
import { createRequire } from "module"

const require = createRequire(import.meta.url)
const {
  getBackendDevServerConfig,
  getFrontendDevServerConfig,
} = require("../scripts/dev-server-config.cjs")

/**
 * 读取后端端口文件 (.backend-port)，获取后端实际监听端口。
 * 后端启动时自动写入该文件，Vite 启动时读取用于配置 proxy。
 */
function readBackendPort(defaultPort) {
  try {
    const content = readFileSync(resolve(__dirname, "..", ".backend-port"), "utf-8")
    const port = parseInt(content.trim(), 10)
    return Number.isFinite(port) ? port : defaultPort
  } catch {
    return defaultPort
  }
}

export default defineConfig(({ command }) => {
  const backendConfig = getBackendDevServerConfig()
  const backendPort = readBackendPort(backendConfig.port)
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
