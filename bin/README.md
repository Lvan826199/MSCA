# MSCA 外部二进制工具

MSCA 运行需要以下外部二进制工具，统一放置在本目录下，并在 Electron 打包时通过 `extraResources` 内嵌到应用资源目录。

---

## 目录结构

```
bin/
├── README.md
├── android/
│   ├── scrcpy-server      # scrcpy-server v3.3.4，Android 投屏核心
│   └── bundletool.jar     # AAB 安装支持（如需）
└── ios/
    └── ios.exe            # go-ios（Windows），iOS ≥16.x 设备管理
```

---

## 1. Android ADB（必需）

ADB（Android Debug Bridge）是 Android 设备连接的基础工具，默认使用系统 PATH 中的 ADB；如后续需要内嵌 ADB，可放入 `bin/android/` 并同步后端路径解析逻辑。

### 安装方式

**方式一：Android SDK Platform Tools（推荐）**
- 下载 Android Platform Tools
- Windows：解压后将目录加入系统 PATH
- Linux/macOS：解压后将 `adb` 放入 PATH

**方式二：通过包管理器**
```bash
# macOS
brew install android-platform-tools

# Ubuntu/Debian
sudo apt install android-tools-adb

# Windows (scoop)
scoop install adb
```

### 验证安装
```bash
adb version
# 输出类似：Android Debug Bridge version 1.0.41
```

### 常见问题
- Windows 需要安装 USB 驱动（通用 ADB 驱动或设备厂商驱动）
- 设备需开启「开发者选项」→「USB 调试」
- 首次连接需在设备上确认「允许 USB 调试」

---

## 2. scrcpy-server（Android 投屏）

scrcpy-server 是运行在 Android 设备上的 Java 程序，负责屏幕捕获和事件注入。MSCA 由 Python 后端 `ScrcpyServerManager` 推送并启动 `bin/android/scrcpy-server`，桌面端和 Web 端共用同一套后端逻辑。

### 当前版本
- `bin/android/scrcpy-server` — scrcpy-server v3.3.4

### 获取方式

**方式一：从 Release 提取**
1. 下载 scrcpy 对应版本压缩包（如 `scrcpy-win64-v3.3.4.zip`）
2. 解压后找到 `scrcpy-server` 文件
3. 复制到 `bin/android/scrcpy-server`

**方式二：从源码构建**
参见 `doc/scrcpy-server构建指南.md`。

### 版本说明
- 当前后端协议解析与 scrcpy-server v3.3.4 对齐
- 更换 scrcpy-server 版本后需回归验证 Android 投屏、触控、文本输入、滚动与旋转

---

## 3. go-ios（iOS ≥16.x 设备管理）

go-ios 是跨平台的 iOS 设备管理工具，MSCA 用于 iOS ≥16.x 设备发现、WDA 管理与 tunnel 能力。

### 当前版本
- `bin/ios/ios.exe` — Windows 版本

### 获取方式
1. 下载 go-ios 对应平台版本
2. Windows 放置为 `bin/ios/ios.exe`
3. Linux/macOS 放置为 `bin/ios/ios` 并添加可执行权限（后续跨平台支持时启用）

### iOS 17+ 特殊要求
部分 iOS 17+ 场景需要先启动隧道：
```bash
# Windows（管理员终端）
bin\ios\ios.exe tunnel start

# macOS/Linux（后续跨平台支持）
sudo bin/ios/ios tunnel start
```

### 验证安装
```bash
bin/ios/ios.exe list
# 应输出连接的 iOS 设备列表（JSON 格式）
```

---

## 4. tidevice（iOS ≤15.x 设备管理）

tidevice 是 Python 包，通过后端 uv 环境安装，不需要放在 `bin/` 目录。

```bash
cd backend
uv sync
```

### 验证安装
```bash
cd backend
uv run tidevice list
# 应输出连接的 iOS 设备列表
```

---

## 5. 环境检查清单

启动前确认以下工具可用：

| 工具 | 检查命令 | 必需 | 说明 |
|------|----------|------|------|
| ADB | `adb version` | Android 必需 | 系统 PATH 中 |
| scrcpy-server | 文件存在检查 | Android 投屏必需 | `bin/android/scrcpy-server` |
| go-ios | `bin/ios/ios.exe version` | iOS ≥16.x 需要 | Electron 打包时内嵌 |
| tidevice | `cd backend && uv run tidevice version` | iOS ≤15.x 需要 | uv 环境安装 |
| Python | `python --version` ≥ 3.13 | 开发/源码运行需要 | |

---

## 6. 打包资源说明

`package.json` 的 electron-builder `extraResources` 会将以下目录内嵌到 Electron 应用：

- `bin/android/` → `process.resourcesPath/bin/android/`
- `bin/ios/` → `process.resourcesPath/bin/ios/`
- `resources/` → `process.resourcesPath/resources/`

生产环境后端通过 `MSCA_RESOURCES_PATH` 定位这些资源。更新本目录文件后，需要执行 `npm run backend:verify` 与 `npm run electron:build` 验证资源路径。
