/**
 * useSettings — 统一设置读写接口。
 *
 * 自动检测环境：
 * - Electron 桌面端：使用 electron-store（通过 IPC）
 * - Web 端：使用 localStorage
 *
 * 所有设置项都有默认值，首次使用无需初始化。
 */

import { ref, watch } from "vue"

const STORAGE_KEY = "msca-settings"

// 默认设置
const DEFAULTS = {
  // 投屏参数
  mirror: {
    maxFps: 30,
    bitrate: 8_000_000,
    maxSize: 0, // 0 = 不限制
  },
  // 布局偏好
  layout: {
    gridColumns: 0, // 0 = 自动
  },
  // 连接模式
  connection: {
    mode: "auto", // auto | local | remote
    remoteUrl: "",
  },
}

const isElectron = typeof window !== "undefined" && !!window.electronAPI

// 单例状态
let _settings = null
let _initialized = false

function loadSettings() {
  if (_settings) return _settings

  let stored = null
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) stored = JSON.parse(raw)
  } catch {
    /* ignore */
  }

  // 深度合并默认值
  _settings = deepMerge(structuredClone(DEFAULTS), stored || {})
  _initialized = true
  return _settings
}

function saveSettings(settings) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
  } catch {
    /* ignore */
  }
}

function deepMerge(target, source) {
  for (const key of Object.keys(source)) {
    if (
      source[key] &&
      typeof source[key] === "object" &&
      !Array.isArray(source[key]) &&
      target[key] &&
      typeof target[key] === "object"
    ) {
      deepMerge(target[key], source[key])
    } else {
      target[key] = source[key]
    }
  }
  return target
}

// 响应式设置对象
const settings = ref(loadSettings())

// 自动持久化
watch(settings, (val) => saveSettings(val), { deep: true })

export function useSettings() {
  return {
    settings,

    // 投屏参数快捷访问
    getMirrorOptions() {
      return { ...settings.value.mirror }
    },

    setMirrorOptions(opts) {
      Object.assign(settings.value.mirror, opts)
    },

    // 布局偏好
    getGridColumns() {
      return settings.value.layout.gridColumns
    },

    setGridColumns(cols) {
      settings.value.layout.gridColumns = cols
    },

    // 重置为默认值
    resetToDefaults() {
      settings.value = structuredClone(DEFAULTS)
    },
  }
}
