const { contextBridge, ipcRenderer } = require("electron")

contextBridge.exposeInMainWorld("electronAPI", {
  isElectron: true,
  platform: process.platform,
  getBackendPort: () => ipcRenderer.invoke("get-backend-port"),
  getBackendStatus: () => ipcRenderer.invoke("get-backend-status"),
})
