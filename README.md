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
| **Android 驱动** | Scrcpy + ADB + adbutils | Python 后端推送并管理内置 scrcpy-server，实现屏幕镜像与控制协议 |
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
- **内置 scrcpy-server**（位于 `bin/android/scrcpy-server`，由 Python 后端推送并管理）

### 安装与启动

```bash
# 克隆仓库
git clone https://gitee.com/xiaozai-van-liu/MSCA.git
# or
git clone https://github.com/Lvan826199/MSCA.git

cd MSCA

# 安装所有依赖（一键完成）
npm install && cd frontend && npm install && cd ../backend && uv sync && cd ..
```

### 一键启动（桌面端开发模式）

```bash
npm run electron:dev
```

该命令会自动完成以下操作，无需手动干预：
1. 启动 Vite 前端开发服务器（localhost:5173）
2. 启动 Python 后端服务（从 18000 起自动探测可用端口，实际端口写入 `.backend-port`）
3. 等待前端就绪后打开 Electron 桌面窗口

### 仅启动 Web 前端

```bash
npm run dev
```

浏览器访问 http://localhost:5173（需要单独启动后端服务）。

### 构建打包

```bash
# 仅构建前端
npm run build

# 编译后端为独立可执行文件（Nuitka）
npm run backend:build

# 验证后端编译产物是否正常运行
npm run backend:verify

# 完整打包（前端构建 + 后端编译 + Electron 打包）
npm run electron:build
```

### 命令速查

| 命令 | 说明 |
| :--- | :--- |
| `npm run electron:dev` | 一键启动桌面端开发模式（推荐） |
| `npm run dev` | 仅启动前端开发服务器 |
| `npm run build` | 构建 Vue 前端 |
| `npm run backend:build` | Nuitka 编译后端为 exe |
| `npm run backend:verify` | 验证后端 exe 是否正常运行 |
| `npm run electron:build` | 完整打包（前端 + 后端 + Electron），输出 `dist/electron/MSCA Setup 0.1.0.exe` |

## 部署模式

MSCA 采用混合部署架构，前后端解耦，同一套 Vue 代码同时支持两种使用方式：

### 桌面端（离线可用）

双击 `MSCA Setup 0.1.0.exe` 安装后，Electron 自动启动内嵌的 Python 后端（Nuitka 编译），从 18000 起自动探测本地端口，实际端口写入 `.backend-port`，无需网络。

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

## 发布与验证清单

发布前建议按顺序执行以下验证：

1. `npm run build`：验证 Vue 前端可正常构建。
2. `npm run backend:verify`：验证 Nuitka 后端 standalone 产物可启动，并通过 `/health` 与 `/api/devices` 检查。
3. `npm run electron:build`：生成 Windows 安装包与免安装目录。
4. 安装 `dist/electron/MSCA Setup 0.1.0.exe` 后启动应用，确认内嵌后端自动拉起、设备列表正常。
5. 连接 Android 与 iOS 设备，分别验证投屏启动、控制操作、停止投屏与资源释放。

## iOS WDA 排障速查

| 场景 | 前端/日志提示 | 处理方式 |
| :--- | :--- | :--- |
| WDA 签名过期或无效 | `WDA 签名无效或已过期` | 使用有效开发者证书重新签名并安装 WDA；免费账号通常 7 天后需重新签名 |
| 设备未信任电脑 | `iOS 设备未信任电脑或配对凭证不可用` | 解锁设备，点击“信任此电脑”；必要时重新插拔 USB 或删除 `selfIdentity.plist` 后重新信任 |
| WDA/MJPEG 本地端口占用 | `本地 WDA 或 MJPEG 端口被占用` | 关闭残留的 MSCA、tidevice、ios.exe 或占用 8100/8101/8110 等端口的进程后重试 |
| WDA Bundle ID 不匹配 | `未找到可启动的 WDA Runner 应用或 Bundle ID 不匹配` | 检查 `backend/config/wda_config.json` 的 `wda_bundle_id` 或 `wda_bundle_id_pattern`，确认设备已安装签名后的 WDA |
| go-ios tunnel 启动失败 | `go-ios tunnel 启动失败` | iOS 17+ 以管理员身份运行 `scripts/ios-tunnel.bat`，或手动执行 `ios tunnel start` 后重试 |
| WDA session/control 失败 | `WDA 服务已连接但 session 或控制接口不可用` | 重启设备上的 WDA Runner，确认 `/status` 正常，再重新启动投屏 |

## iOS 手势封装决策

当前不引入 `python-wda`、W3C Actions 或 Airtest 作为主链路依赖。推荐继续维护现有 WDA REST 最小实现，并通过错误分类、日志与操作手册降低排障成本；仅当真实设备手势兼容性继续不足或 REST 维护成本显著上升时，再评估引入第三方封装。

## 文档

- [项目需求及技术栈概览](doc/项目需求及技术栈概览.md) — 完整的技术设计方案
- [需求拆解](doc/需求拆解.md) — 功能模块拆解与优先级
- [开发计划](doc/开发计划.md) — 分阶段开发里程碑
- [CLAUDE.md](CLAUDE.md) — AI 开发指令与强制验证流程
- [AI 操作步骤记录](memory/ai_step.md) — 历次开发操作记录与验证结果

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
