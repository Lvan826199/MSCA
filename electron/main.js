const { app, BrowserWindow, ipcMain, Menu } = require("electron")
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

function getWindowIconPath() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, "resources", "icon.ico")
  }
  return path.join(__dirname, "..", "resources", "icon.ico")
}

function createApplicationMenu() {
  return Menu.buildFromTemplate([
    {
      label: "文件",
      submenu: [
        { label: "退出", accelerator: "Alt+F4", role: "quit" },
      ],
    },
    {
      label: "编辑",
      submenu: [
        { label: "撤销", accelerator: "Ctrl+Z", role: "undo" },
        { label: "重做", accelerator: "Ctrl+Y", role: "redo" },
        { type: "separator" },
        { label: "剪切", accelerator: "Ctrl+X", role: "cut" },
        { label: "复制", accelerator: "Ctrl+C", role: "copy" },
        { label: "粘贴", accelerator: "Ctrl+V", role: "paste" },
        { type: "separator" },
        { label: "全选", accelerator: "Ctrl+A", role: "selectAll" },
      ],
    },
    {
      label: "视图",
      submenu: [
        { label: "刷新", accelerator: "Ctrl+R", role: "reload" },
        { label: "强制刷新", accelerator: "Ctrl+Shift+R", role: "forceReload" },
        { type: "separator" },
        { label: "开发者工具", accelerator: "Ctrl+Shift+I", role: "toggleDevTools" },
      ],
    },
    {
      label: "窗口",
      submenu: [
        { label: "最小化", accelerator: "Ctrl+M", role: "minimize" },
        { label: "切换全屏", accelerator: "F11", role: "togglefullscreen" },
        { type: "separator" },
        { label: "关闭窗口", accelerator: "Ctrl+W", role: "close" },
      ],
    },
  ])
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
    icon: getWindowIconPath(),
    show: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  win.once("ready-to-show", () => {
    win.show()
    win.focus()
  })

  if (isDev) {
    win.loadURL(getDevServerUrl())
    if (process.env.MSCA_OPEN_DEVTOOLS === "1") {
      win.webContents.openDevTools()
    }
  } else {
    win.loadFile(path.join(__dirname, "../frontend/dist/index.html"))
  }

  return win
}

ipcMain.handle("get-backend-port", () => backendManager.port)
ipcMain.handle("get-backend-status", () => backendManager.getStatus())

app.whenReady().then(async () => {
  if (!hasSingleInstanceLock) return
  Menu.setApplicationMenu(createApplicationMenu())
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
