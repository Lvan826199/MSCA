const { app, BrowserWindow, ipcMain } = require("electron")
const path = require("path")
const BackendManager = require("./backend-manager")

const isDev = !app.isPackaged
const backendManager = new BackendManager(app.isPackaged)

function getDevServerUrl() {
  if (process.env.MSCA_FRONTEND_URL) {
    return process.env.MSCA_FRONTEND_URL
  }
  const {
    buildFrontendDevServerUrl,
    getFrontendDevServerConfig,
  } = require("../scripts/dev-server-config.cjs")
  return buildFrontendDevServerUrl(getFrontendDevServerConfig(process.env, path.join(__dirname, "..")))
}

// 单实例锁：双开会导致启动时的残留进程清理误杀另一实例的后端
const hasSingleInstanceLock = app.requestSingleInstanceLock()
if (!hasSingleInstanceLock) {
  app.quit()
}
app.on("second-instance", () => {
  const win = BrowserWindow.getAllWindows()[0]
  if (win) {
    if (win.isMinimized()) win.restore()
    win.focus()
  }
})

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 960,
    minHeight: 600,
    title: "MSCA - 多设备投屏控制",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  if (isDev) {
    win.loadURL(getDevServerUrl())
    win.webContents.openDevTools()
  } else {
    win.loadFile(path.join(__dirname, "../frontend/dist/index.html"))
  }

  return win
}

ipcMain.handle("get-backend-port", () => backendManager.port)
ipcMain.handle("get-backend-status", () => backendManager.getStatus())

app.whenReady().then(async () => {
  if (!hasSingleInstanceLock) return
  try {
    await backendManager.start()
    console.log(`[main] 后端已启动，端口 ${backendManager.port}`)
  } catch (err) {
    console.error("[main] 后端启动失败:", err.message)
  }

  createWindow()

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })
})

// Electron 不会等待监听器中的 Promise，需阻止默认退出并在后端停止后手动退出
let quitting = false
app.on("before-quit", (event) => {
  if (quitting) return
  event.preventDefault()
  quitting = true
  backendManager.stop().finally(() => app.exit(0))
})

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit()
  }
})
