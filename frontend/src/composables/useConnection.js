/**
 * useConnection — 后端连接管理。
 *
 * 三种场景：
 * - Electron 模式：通过 IPC 获取 BackendManager 分配的端口
 * - Vite dev 模式：backendUrl 为空串，所有请求走 Vite proxy
 * - 生产 Web 模式：使用 window.location.origin
 */

import { ref, readonly } from "vue"
import { useSettings } from "./useSettings.js"
import { normalizeHttpBaseUrl, toWsBaseUrl } from "../utils/connectionUrl.js"

const isElectron = typeof window !== "undefined" && !!window.electronAPI
const isDev = !!import.meta.env?.DEV

const { getConnectionSettings, setConnectionSettings } = useSettings()
const initialConnection = getConnectionSettings()
const mode = ref(initialConnection.mode || (isElectron ? "auto" : "local")) // auto | local | remote
const remoteUrl = ref(normalizeHttpBaseUrl(initialConnection.remoteUrl))
const backendUrl = ref("")
const DEFAULT_LOCAL_BACKEND_URL = "http://127.0.0.1:18000"
const BACKEND_HEALTH_TIMEOUT = 1500

// 模块级初始化 promise，只执行一次
const ready = initBackendUrl()

function buildLocalBackendUrl(port) {
  return `http://127.0.0.1:${port}`
}

function isValidPort(port) {
  return Number.isInteger(port) && port > 0 && port < 65536
}

export async function isBackendHealthy(baseUrl, fetchImpl = globalThis.fetch) {
  if (!baseUrl || typeof fetchImpl !== "function") return false
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), BACKEND_HEALTH_TIMEOUT)
  try {
    const response = await fetchImpl(`${baseUrl.replace(/\/+$/, "")}/health`, {
      cache: "no-store",
      signal: controller.signal,
    })
    if (!response.ok) return false
    const data = await response.json().catch(() => null)
    return data?.status === "ok"
  } catch {
    return false
  } finally {
    clearTimeout(timer)
  }
}

export async function resolveElectronBackendUrl(
  electronAPI,
  { isDevMode = isDev, fetchImpl = globalThis.fetch } = {}
) {
  let status = null
  try {
    if (typeof electronAPI?.getBackendStatus === "function") {
      status = await electronAPI.getBackendStatus()
    }
  } catch {
    status = null
  }

  let port = Number(status?.port)
  if (!isValidPort(port)) {
    try {
      if (typeof electronAPI?.getBackendPort === "function") {
        port = Number(await electronAPI.getBackendPort())
      }
    } catch {
      port = 18000
    }
  }

  const candidateUrl = isValidPort(port) ? buildLocalBackendUrl(port) : DEFAULT_LOCAL_BACKEND_URL
  if (status?.running !== false && await isBackendHealthy(candidateUrl, fetchImpl)) {
    return candidateUrl
  }

  if (isDevMode && await isBackendHealthy(DEFAULT_LOCAL_BACKEND_URL, fetchImpl)) {
    return DEFAULT_LOCAL_BACKEND_URL
  }

  return candidateUrl
}

async function initBackendUrl() {
  if (isElectron) {
    // Electron 模式：通过 IPC 获取后端实际端口
    try {
      backendUrl.value = await resolveElectronBackendUrl(window.electronAPI)
    } catch {
      backendUrl.value = DEFAULT_LOCAL_BACKEND_URL
    }
  } else if (isDev) {
    // Vite dev 模式：空串 → 相对 URL → Vite proxy 转发
    backendUrl.value = ""
  } else if (typeof window !== "undefined") {
    // 生产 Web 模式：后端与前端同源部署
    backendUrl.value = window.location.origin
  } else {
    backendUrl.value = ""
  }
}

export function setMode(newMode) {
  mode.value = newMode
  setConnectionSettings({ mode: newMode })
}

export function setRemoteUrl(url) {
  const normalized = normalizeHttpBaseUrl(url)
  remoteUrl.value = normalized
  setConnectionSettings({ remoteUrl: normalized })
}

export function getConnectionState() {
  return {
    mode: mode.value,
    remoteUrl: remoteUrl.value,
  }
}

/**
 * 获取后端 HTTP 基础 URL。
 * remote 模式返回用户配置的远程地址，其他模式返回动态解析的 backendUrl。
 */
export function getBackendUrl() {
  if (mode.value === "remote" && remoteUrl.value) {
    return remoteUrl.value
  }
  return backendUrl.value
}

/**
 * 将路径转换为 WebSocket URL。
 * 统一处理 Vite proxy（空 backendUrl）和直连（有 backendUrl）两种情况。
 */
export function toWsUrl(path) {
  const base = getBackendUrl()
  if (!base) {
    // Vite dev 模式：用当前页面 host，走 proxy
    const proto = location.protocol === "https:" ? "wss:" : "ws:"
    return `${proto}//${location.host}${path}`
  }
  return toWsBaseUrl(base) + path
}

export function useConnection() {
  return {
    isElectron,
    isDev,
    mode,
    remoteUrl,
    backendUrl: readonly(backendUrl),
    ready,
    setMode,
    setRemoteUrl,
    getBackendUrl,
    toWsUrl,
  }
}
