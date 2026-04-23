# MSCA - 多设备移动端投屏控制系统

MSCA（Mobile Screen Control Assistant）是一个跨平台的移动设备投屏与控制工具，支持 Windows 系统（macOS 后续支持），同时提供 Web 端访问能力。系统采用 **Python + Vue + Electron** 统一技术栈，通过分层驱动架构实现对 Android 与 iOS 设备的透明管理与并发控制。

## 核心功能

- **多设备并发管理**：支持同时连接并控制多台移动设备，设备间互不干扰
- **单设备精细操控**：每台设备拥有独立的控制面板，支持精确的点击、滑动、输入等操作
- **多设备同屏监控**：支持单页面同时查看多台设备的实时投屏画面，便于批量监控与管理
- **跨平台支持**：桌面端基于 Electron 构建，支持 Windows（macOS 后续支持）；同时提供 Web 端，无需安装客户端即可使用浏览器访问
- **混合部署**：桌面端内嵌 Python 后端，离线可用；Web 端连接远程后端，支持远程投屏控制
- **本地化部署**：无需数据库，所有数据仅在本地处理，保障数据安全

## 设备支持

| 平台 | 技术方案 | 视频流 | 控制方式 |
| :--- | :--- | :--- | :--- |
| **Android** | 基于 [Scrcpy](https://github.com/Genymobile/scrcpy) 协议，通过 ADB 实现 | H.264 实时视频流 | Scrcpy 控制协议（触控、按键、文本） |
| **iOS ≤15.x** | [Tidevice](https://github.com/alibaba/taobao-iphone-device) + [WebDriverAgent](https://github.com/appium/WebDriverAgent) | MJPEG 截图流 | XCTest 自动化控制 |
| **iOS ≥16.x** | [go-ios](https://github.com/danielpaulus/go-ios) + [WebDriverAgent](https://github.com/appium/WebDriverAgent) | MJPEG 截图流 | XCTest 自动化控制 |

## 技术栈

| 层级 | 技术选型 | 说明 |
| :--- | :--- | :--- |
| **前端** | Vue 3 + Vite + WebCodecs API | 视频解码渲染，WebSocket 实时通信 |
| **桌面端** | Electron | 跨平台桌面应用，主进程管理子进程 |
| **后端** | Python + FastAPI | Web 服务与 WebSocket 服务 |
| **包管理** | uv | Python 依赖管理与虚拟环境 |
| **Android 驱动** | Scrcpy + ADB + adbutils | 屏幕镜像与控制协议 |
| **iOS 驱动** | WebDriverAgent + Tidevice / go-ios | 屏幕流获取与 XCTest 控制 |
| **配置存储** | electron-store / JSON / localStorage | 轻量配置，无数据库 |

## 适用场景

- 应用与游戏的自动化测试
- 多设备批量操作与演示
- 远程设备协助与调试
- 移动应用开发过程中的多机型适配测试

## 快速开始

### 前置依赖

- **Node.js** 18+
- **Python** 3.13+
- **uv** 包管理器
- **ADB**（Android Platform Tools ≥33.0）
- **scrcpy** ≥2.0（桌面端方案）

### 安装与启动

```bash
# 克隆仓库
git clone https://gitee.com/xiaozai-van-liu/MSCA.git
# or
git clone https://github.com/Lvan826199/MSCA.git

cd MSCA

# 前端依赖
npm install

# Python 后端环境（使用 uv）
uv sync

# 如需 iOS 支持：
# uv add tidevice        # iOS ≤15.x
# 下载 go-ios 二进制      # iOS ≥16.x
```

### 开发模式

```bash
# 前端开发
npm run dev              # Vite 开发服务器（Web 端）
npm run electron:dev     # Electron 开发模式

# 后端开发
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 构建打包

```bash
npm run build            # 构建 Vue 前端
npm run electron:build   # 打包 Electron 应用（Windows）
```

## 部署模式

MSCA 采用混合部署架构，前后端解耦，同一套 Vue 代码同时支持两种使用方式：

### 桌面端（离线可用）

双击 `MSCA-Setup.exe` 安装后，Electron 自动启动内嵌的 Python 后端（Nuitka 编译），通过 `127.0.0.1:18000` 本地通信，无需网络。

- 连接模式：自动（auto）/ 仅本地（local）/ 仅远程（remote），可在设置中切换
- 后端崩溃自动重启（最多 3 次），超限弹窗提示

### Web 端（远程访问）

部署 Python 后端到服务器，Vue 静态文件部署到 Nginx，浏览器通过 HTTPS/WSS 连接。

- TLS 由 Nginx 反向代理处理，Python 后端仅监听 HTTP/WS
- 用户需配置远程后端地址

## 项目结构

```
msca/
├── electron/                 # Electron 主进程与预加载脚本
│   ├── main.js              # 主进程入口
│   ├── preload.js           # 预加载脚本
│   ├── scrcpy-manager.js    # Scrcpy 子进程管理模块
│   └── backend-manager.js   # Python 后端进程管理模块
├── frontend/                 # Vue 3 前端应用
│   ├── src/
│   │   ├── components/      # Vue 组件（设备列表、投屏窗口等）
│   │   ├── composables/     # 组合式函数（WebSocket、视频解码）
│   │   └── App.vue
│   └── index.html
├── backend/                  # Python FastAPI 后端
│   ├── app/
│   │   ├── api/             # REST API 路由
│   │   ├── websocket/       # WebSocket 处理
│   │   ├── drivers/         # 设备驱动抽象层
│   │   │   ├── android.py   # AndroidDriver
│   │   │   ├── ios.py       # IOSDriver
│   │   │   └── adapters/    # iOS 适配器 (tidevice, go-ios)
│   │   └── core/            # 设备管理、流分发等核心模块
│   ├── pyproject.toml       # uv 项目配置
│   └── requirements.txt     # 可选依赖锁定文件
├── resources/                # 资源文件（图标、WDA.ipa 等）
├── doc/                      # 项目文档
│   ├── 项目需求及技术栈概览.md
│   ├── 需求拆解.md
│   └── 开发计划.md
└── package.json              # Node.js 项目配置
```

## 文档

- [项目需求及技术栈概览](doc/项目需求及技术栈概览.md) — 完整的技术设计方案
- [需求拆解](doc/需求拆解.md) — 功能模块拆解与优先级
- [开发计划](doc/开发计划.md) — 分阶段开发里程碑

## 参考项目

| 项目 | 用途 | 链接 |
| :--- | :--- | :--- |
| scrcpy | Android 镜像核心 | https://github.com/Genymobile/scrcpy |
| Escrcpy | Electron GUI 参考 | https://github.com/viarotel-org/escrcpy |
| ws-scrcpy | Web 端参考 | https://github.com/NetrisTV/ws-scrcpy |
| uiautodev | Python Web 参考 | https://github.com/codeskyblue/uiautodev |
| Tidevice | iOS ≤15.x 支持 | https://github.com/alibaba/taobao-iphone-device |
| go-ios | iOS ≥16.x 支持 | https://github.com/danielpaulus/go-ios |
| WebDriverAgent | iOS 自动化核心 | https://github.com/appium/WebDriverAgent |

## License

[MIT](LICENSE)
