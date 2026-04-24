import { ref } from "vue"

const isElectron = typeof window !== "undefined" && !!window.electronAPI

const mode = ref(isElectron ? "auto" : "remote") // auto | local | remote
const remoteUrl = ref("")
const localUrl = "http://127.0.0.1:18000"

function setMode(newMode) {
  mode.value = newMode
}

function setRemoteUrl(url) {
  remoteUrl.value = url
}

function getBackendUrl() {
  if (mode.value === "local") return localUrl
  if (mode.value === "remote") return remoteUrl.value || localUrl
  // auto: 桌面端优先本地
  return localUrl
}

export function useConnection() {
  return {
    isElectron,
    mode,
    remoteUrl,
    setMode,
    setRemoteUrl,
    getBackendUrl,
  }
}
