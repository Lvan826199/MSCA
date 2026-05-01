const { app, BrowserWindow, ipcMain } = require("electron")
const path = require("path")
const BackendManager = require("./backend-manager")

const isDev = !app.isPackaged
const backendManager = new BackendManager(app.isPackaged)

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
    win.loadURL("http://localhost:5173")
    win.webContents.openDevTools()
  } else {
    win.loadFile(path.join(__dirname, "../frontend/dist/index.html"))
  }

  return win
}

ipcMain.handle("get-backend-port", () => backendManager.port)

app.whenReady().then(async () => {
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

app.on("before-quit", async () => {
  await backendManager.stop()
})

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit()
  }
})
