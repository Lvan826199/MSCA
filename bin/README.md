# Agent 外部依赖（二进制工具）

Agent 运行需要以下外部二进制工具，放置在本目录下。

---

## 目录结构

```
device_agent/bin/
├── README.md              # 本文件
├── android/
│   └── scrcpy-server      # scrcpy-server v3.x，Android 投屏核心
└── ios/
    └── ios.exe            # go-ios（Windows），iOS 17+ 设备管理
```

---

## 1. Android ADB（必需）

ADB（Android Debug Bridge）是 Android 设备连接的基础工具，**不放在 bin/ 目录下**，需要系统全局安装。

### 安装方式

**方式一：Android SDK Platform Tools（推荐）**
- 下载地址：https://developer.android.com/tools/releases/platform-tools
- Windows：解压后将目录加入系统 PATH
- Linux/macOS：解压后 `sudo cp adb /usr/local/bin/`

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

scrcpy-server 是运行在 Android 设备上的 Java 程序，负责屏幕捕获和事件注入。

### 当前版本
- `device_agent/bin/android/scrcpy-server` — 用户维护的版本（v3.x）

### 获取方式

**方式一：从 Release 提取**
1. 访问 https://github.com/Genymobile/scrcpy/releases
2. 下载对应平台压缩包（如 `scrcpy-win64-v3.3.4.zip`）
3. 解压后找到 `scrcpy-server` 文件
4. 复制到 `device_agent/bin/android/scrcpy-server`

**方式二：从源码构建**
参见 `doc/scrcpy-server构建指南.md`

### 版本说明
- `device_agent/bin/android/scrcpy-server` 为用户维护的 v3.x 版本
- 当前 `device_agent/libs/scrcpy/` 代码协议兼容 scrcpy-server **v1.20**，使用 v3.x server 需升级协议
- 升级计划见 `device_agent/libs/scrcpy/ANALYSIS.md`

---

## 3. go-ios（iOS 17+ 设备管理）

go-ios 是跨平台的 iOS 设备管理工具，用于 iOS 17+ 设备。

### 当前版本
- `device_agent/bin/ios/ios.exe` — Windows 版本

### 获取方式
1. 访问 https://github.com/danielpaulus/go-ios/releases
2. 下载对应平台版本：
   - Windows: `ios.exe`
   - Linux: `ios`（需 chmod +x）
   - macOS: `ios`（需 chmod +x）
3. 放到 `device_agent/bin/ios/` 目录

### iOS 17+ 特殊要求
iOS 17 及以上版本需要先启动隧道守护进程：
```bash
# 需要管理员/root 权限
sudo device_agent/bin/ios/ios tunnel start

# Windows（管理员 CMD）
agent\bin\ios\ios.exe tunnel start
```

### 验证安装
```bash
device_agent/bin/ios/ios list
# 应输出连接的 iOS 设备列表（JSON 格式）
```

---

## 4. tidevice（iOS ≤16 设备管理）

tidevice 是 Python 包，通过 pip 安装，**不需要放在 bin/ 目录**。

```bash
# 在 agent 虚拟环境中安装（已包含在 pyproject.toml）
cd agent
uv sync
```

### 验证安装
```bash
tidevice list
# 应输出连接的 iOS 设备列表
```

---

## 5. 环境检查清单

Agent 启动前，确认以下工具可用：

| 工具 | 检查命令 | 必需 | 说明 |
|------|----------|------|------|
| ADB | `adb version` | ✅ Android 必需 | 系统 PATH 中 |
| scrcpy-server | 文件存在检查 | ✅ Android 投屏 | `device_agent/bin/android/scrcpy-server` |
| go-ios | `device_agent/bin/ios/ios version` | iOS 17+ 需要 | |
| tidevice | `tidevice version` | iOS ≤16 需要 | pip 安装 |
| Python | `python --version` ≥ 3.10 | ✅ | |
