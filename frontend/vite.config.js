import { defineConfig } from "vite"
import vue from "@vitejs/plugin-vue"
import { resolve } from "path"
import { readFileSync } from "fs"

/**
 * 读取后端端口文件 (.backend-port)，获取后端实际监听端口。
 * 后端启动时自动写入该文件，Vite 启动时读取用于配置 proxy。
 */
function readBackendPort() {
  try {
    const content = readFileSync(resolve(__dirname, "..", ".backend-port"), "utf-8")
    const port = parseInt(content.trim(), 10)
    return Number.isFinite(port) ? port : 18000
  } catch {
    return 18000
  }
}

export default defineConfig(() => {
  const backendPort = readBackendPort()
  console.log(`[vite] 后端 proxy 目标端口: ${backendPort}`)

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        "@": resolve(__dirname, "src"),
      },
    },
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: `http://127.0.0.1:${backendPort}`,
          changeOrigin: true,
        },
        "/ws": {
          target: `ws://127.0.0.1:${backendPort}`,
          ws: true,
        },
        "/health": {
          target: `http://127.0.0.1:${backendPort}`,
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: "dist",
    },
  }
})
