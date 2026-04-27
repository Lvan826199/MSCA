# CLAUDE.md



> **您必须严格遵守本文档。**
>
> 始终使用简体中文回复用户,包括你的thinking过程也使用简体中文
>
> 请勿跳过任何步骤
>
> 请勿对未明确说明的要求进行假设
>
> 任何不确定之处必须在继续之前向用户确认

## 项目文档索引

| 文档 | 说明 |
| :--- | :--- |
| [项目需求及技术栈概览](doc/项目需求及技术栈概览.md) | 完整的技术设计方案，包含架构、协议、各平台详细设计 |
| [需求拆解](doc/需求拆解.md) | 功能模块拆解，含 13 个模块的子任务与验收标准 |
| [开发计划](doc/开发计划.md) | 四阶段开发里程碑，含技术验证清单与风险应对 |
| [下一步计划](doc/下一步计划.md) | 当前阶段具体开发任务（M2→M3→M4），含文件级实施细节 |
| [操作手册](doc/操作手册.md) | 开发环境搭建、设备连接、平台启动操作流程 |

## 项目概述

本项目为 MSCA（Mobile Screen Control Assistant），一个跨平台的多设备移动端投屏控制系统，支持 Android 与 iOS 设备的屏幕实时投射与反向控制。

核心功能包括：

- 多设备并发投屏与独立控制
- 单页面同时查看多台设备画面
- Android 基于 Scrcpy 协议实现高效 H.264 视频流传输与控制
- iOS 基于 WebDriverAgent + Tidevice/go-ios 实现屏幕投射与 XCTest 控制

## 技术栈

| 层级             | 技术选型                             | 说明                             |
| :--------------- | :----------------------------------- | :------------------------------- |
| **前端**         | Vue 3 + Vite + WebCodecs API         | 视频解码渲染，WebSocket 实时通信 |
| **桌面端**       | Electron                             | 跨平台桌面应用，主进程管理子进程 |
| **后端**         | Python + FastAPI                     | Web 服务与 WebSocket 服务        |
| **包管理**       | uv                                   | Python 依赖管理与虚拟环境        |
| **Android 驱动** | Scrcpy + ADB + adbutils              | 屏幕镜像与控制协议               |
| **iOS 驱动**     | WebDriverAgent + Tidevice / go-ios   | 屏幕流获取与 XCTest 控制         |
| **配置存储**     | electron-store / JSON / localStorage | 轻量配置，无数据库               |

## 项目结构

```
msca/
├── electron/                 # Electron 主进程与预加载脚本
│   ├── main.js              # 主进程入口
│   ├── preload.js           # 预加载脚本
│   ├── scrcpy-manager.js    # Scrcpy 子进程管理模块
│   └── backend-manager.js   # Python 后端进程管理模块（BackendManager）
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
└── package.json              # Node.js 项目配置
```

## 开发环境搭建

### 前置依赖

- **Node.js** 18+
- **Python** 3.13+
- **uv** 包管理器
- **ADB**（Android Platform Tools）
- **scrcpy** 可执行文件（桌面端方案）
- **Tidevice**（iOS ≤15.x 支持）：`uv add tidevice`
- **go-ios**（iOS ≥16.x 支持）：从 [releases](https://github.com/danielpaulus/go-ios/releases) 下载二进制

### 初始化步骤

```bash
# 克隆仓库
git git clone https://gitee.com/xiaozai-van-liu/MSCA.git
cd MSCA

# 前端依赖
npm install

# Python 后端环境（使用 uv）
cd backend
uv venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
uv pip install fastapi uvicorn adbutils websockets
# 如需 iOS 支持：
uv pip install tidevice
```

## 常用命令

### 前端开发

```bash
npm run dev          # 启动 Vite 开发服务器（Web 端）
npm run electron:dev # 启动 Electron 开发模式
```

### 后端开发

```bash
# 推荐方式（自动找端口，写 .backend-port）
npm run dev:backend

# 或手动指定端口
cd backend
uv run python __main__.py --port 19000
```

### 打包构建

```bash
npm run build            # 构建 Vue 前端
npm run backend:build    # Nuitka 编译后端为 exe
npm run backend:verify   # 验证后端 exe 是否正常运行
npm run electron:build   # 完整打包（前端 + 后端 + Electron）
```

### 依赖管理（uv）

```bash
# 安装所有依赖
uv sync

# 安装开发依赖
uv sync --dev

# 添加依赖
uv add <package>
uv add --dev <package>
```

## UI 设计规范

本项目 UI 设计遵循 **ui-ux-pro-max** Skill 所定义的现代桌面应用设计语言，确保界面专业、一致且易用。

- **设计系统**：参考 ui-ux-pro-max 提供的组件库、间距体系、色彩方案与字体规范。
- **核心原则**：清晰的信息层级、高效的操作路径、统一的视觉反馈。
- **适用场景**：设备列表卡片、投屏窗口布局、控制面板按钮、设置界面等所有前端界面。

在进行 UI 设计或前端组件开发时，应优先调用 **ui-ux-pro-max** Skill 获取具体的设计指南与组件规范。

## 核心架构要点

### 设备驱动抽象层

所有设备驱动继承 `AbstractDeviceDriver`，统一接口：

```python
class AbstractDeviceDriver(ABC):
    async def start_mirroring(self, options: MirrorOptions) -> str: ...
    async def stop_mirroring(self) -> None: ...
    async def send_event(self, event: ControlEvent) -> bool: ...
    async def get_screenshot(self) -> bytes: ...
```

- **AndroidDriver**：桌面端通过 Electron 子进程启动 scrcpy；Web 端通过 Python 代理 scrcpy 协议。
- **IOSDriver**：封装 TideviceAdapter / GoIOSAdapter，管理 WDA 服务与 MJPEG 流。

### 多设备并发

- 桌面端：每个设备独立 scrcpy 子进程。
- Web 端：每个设备独立 WebSocket 连接与驱动实例。
- iOS 端口分配：以 8100 为基础，每设备递增 10。

### 通信协议

- **设备管理**：HTTP REST / WebSocket 推送
- **视频流**：WebSocket 二进制帧（Android H.264，iOS MJPEG JPEG）
- **控制指令**：WebSocket JSON（点击、滑动、按键等）

## 打包部署架构

### 混合部署模式

MSCA 采用混合部署架构，前后端解耦，同一套 Vue 代码无需修改即可同时用于桌面端和 Web 端：

- **桌面端**：Electron 主进程自动启动内嵌的 Python 后端（Nuitka 编译产物），通过 `127.0.0.1:18000` 本地通信，完全离线可用。
- **Web 端**：部署公共后端服务（用户自有服务器），浏览器通过 HTTPS/WSS 连接远程后端。Web 端 TLS 由 Nginx 反向代理处理。

### 后端打包

- **工具**：Nuitka（Python → C 编译，生成独立可执行文件 msca-backend.exe）
- **目标平台**：当前仅 Windows，macOS 支持延后
- **体积**：不设硬性限制，以功能完整为优先
- **健康检查**：`GET /health` 端点，返回 200 表示服务就绪

### BackendManager（Electron 主进程模块）

负责本地后端进程的完整生命周期管理：
- 应用启动时 spawn 后端子进程，轮询 `/health` 确认就绪
- 崩溃自动重启：最多 3 次，间隔递增（立即 → 3s → 5s），超限弹窗提示用户
- 应用退出时优雅关闭后端进程

### 前端连接模式

| 模式 | 说明 | 适用场景 |
| :--- | :--- | :--- |
| **自动（auto）** | 桌面端默认，优先连接本地后端，失败提示配置远程 | 桌面端日常使用 |
| **仅本地（local）** | 仅连接 `ws://127.0.0.1:18000` | 离线环境 |
| **仅远程（remote）** | 连接用户配置的远程后端地址（WSS） | Web 端、远程控制 |

- 桌面端通过 `window.electronAPI` 判断环境，默认 auto 模式。
- Web 端仅 remote 模式，需配置远程后端地址。

### 端口管理策略

| 端口号 | 用途 | 处理方式 |
| :--- | :--- | :--- |
| **18000** | 默认本地后端起始端口 | 自动探测可用端口（18000→18001→...），实际端口写入 `.backend-port` 文件 |
| **8100~** | iOS WDA 端口转发 | 每设备递增 10（8100、8110、8120），由后端管理 |

### 构建产物

| 产物 | 说明 |
| :--- | :--- |
| **MSCA-Setup.exe** | Electron 应用 + Vue 前端 + msca-backend.exe + scrcpy 二进制 |
| **msca-web/** | Vue 静态文件，部署至 Nginx 等 Web 服务器 |
| **msca-backend.exe** | Nuitka 编译的 Python 后端，桌面端内嵌 / Web 端独立部署 |

## 重要注意事项

- **无需数据库**：所有设备状态为临时数据，配置使用 `electron-store`（桌面端）或 `localStorage`（Web 端）。
- **iOS 配对凭证**：首次连接 iOS 设备时自动生成 `backend/selfIdentity.plist`，包含配对密钥，已加入 `.gitignore`，禁止提交到远程仓库。
- **iOS WDA 签名**：WebDriverAgent 需使用有效开发者证书签名，否则 7 天过期。
- **iOS 版本适配**：iOS ≤15.x 使用 Tidevice，≥16.x 使用 go-ios，未知版本自动探测回退。
- **视频解码**：Web 端优先使用 WebCodecs API 硬件解码 H.264，降级方案为 MSE。

## 参考资源

| 项目           | 用途              | 链接                                            |
| :------------- | :---------------- | :---------------------------------------------- |
| scrcpy         | Android 镜像核心  | https://github.com/Genymobile/scrcpy            |
| Escrcpy        | Electron GUI 参考 | https://github.com/viarotel-org/escrcpy         |
| ws-scrcpy      | Web 端参考        | https://github.com/NetrisTV/ws-scrcpy           |
| uiautodev      | Python Web 参考   | https://github.com/codeskyblue/uiautodev        |
| Tidevice       | iOS 低版本支持    | https://github.com/alibaba/taobao-iphone-device |
| go-ios         | iOS 高版本支持    | https://github.com/danielpaulus/go-ios          |
| WebDriverAgent | iOS 自动化核心    | https://github.com/appium/WebDriverAgent        |

## 开发阶段建议

1. **第一阶段**：实现 Android 桌面端投屏（基于 Escrcpy 架构），验证 Electron 子进程管理。
2. **第二阶段**：实现 Android Web 端投屏（基于 ws-scrcpy/uiautodev 思路），完善 Python 后端与 WebSocket 流。
3. **第三阶段**：实现 iOS 低版本支持（TideviceAdapter），完成基础投屏控制。
4. **第四阶段**：实现 iOS 高版本支持（GoIOSAdapter），完成混合部署架构打包（Nuitka 后端编译 + Electron 打包，当前仅 Windows）。

## 开发完成验证清单（必须执行）

每次开发完成后，必须按以下顺序执行验证步骤，确保项目可正常运行：

### 1. 前端构建验证
```bash
npm run build
```
**预期结果**：构建成功，生成 `frontend/dist/` 目录，无报错。

### 2. 后端健康检查
```bash
npm run dev:backend
```
另开终端执行（端口号从 `.backend-port` 文件读取）：
```bash
curl http://127.0.0.1:$(cat .backend-port)/health
```
**预期结果**：返回 `{"status":"ok"}`，后端服务正常启动。

### 3. 后端编译与验证（发布前必选）
```bash
# 编译后端为独立可执行文件
npm run backend:build

# 验证编译产物是否正常运行
npm run backend:verify
```
**预期结果**：`backend:verify` 输出 `✅ 后端打包验证通过！`。

### 4. Electron 打包验证（可选，耗时较长）
```bash
npm run electron:build
```
**预期结果**：生成 `dist-electron/` 目录，包含安装包或可执行文件。

**注意**：
- 如遇 Electron 下载超时，项目已配置国内镜像（`.npmrc` 与 `package.json`），无需手动处理。
- 验证步骤 1 和 2 为必选项，步骤 3 在发布前执行，步骤 4 可在最终发布时执行。
- 所有验证通过后方可提交代码或发起 PR。

## Code Review 方案

为确保代码质量、一致性与可维护性，本项目建立以下代码审查流程与规范。

**重要**：Code Review 过程中须遵循 **code-review** Skill 所规定的审查标准、流程与最佳实践。该 Skill 定义了详细的审查要点、检查清单与反馈规范，所有代码提交前均需通过基于该 Skill 的审查流程。

### 1. 自动化静态检查

#### 前端（Vue 3 + JavaScript/TypeScript）

| 工具          | 用途                               | 配置文件        |
| :------------ | :--------------------------------- | :-------------- |
| **ESLint**    | JavaScript/TypeScript 代码规范检查 | `.eslintrc.cjs` |
| **Prettier**  | 代码格式化                         | `.prettierrc`   |
| **Stylelint** | CSS/SCSS 样式规范（可选）          | `.stylelintrc`  |

**建议 ESLint 规则集**：
- `eslint:recommended`
- `plugin:vue/vue3-recommended`
- `@vue/eslint-config-prettier`

**命令集成**：
```json
"scripts": {
  "lint": "eslint . --ext .vue,.js,.ts --fix",
  "format": "prettier --write ."
}
```

#### 后端（Python）

| 工具     | 用途                                            | 配置文件         |
| :------- | :---------------------------------------------- | :--------------- |
| **Ruff** | 快速 Linter 与 Formatter（替代 Flake8 + Black） | `pyproject.toml` |
| **mypy** | 静态类型检查（如使用类型注解）                  | `mypy.ini`       |

**Ruff 配置示例（pyproject.toml）**：
```toml
[tool.ruff]
line-length = 100
select = ["E", "F", "I", "N", "W", "UP", "B", "C4"]
ignore = ["E501"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

**命令**：
```bash
uv run ruff check .        # 代码检查
uv run ruff format .       # 代码格式化
uv run mypy backend/       # 类型检查（若启用）
```

#### Electron 主进程

- 主进程代码亦纳入前端 ESLint 检查范围。
- 建议增加针对 Node.js 环境的规则（`env: { node: true }`）。

### 2. Code Review 流程

#### 分支策略
- `main`：稳定生产分支，仅接受通过 PR 合并。
- `develop`：开发主线，功能分支从此拉取。
- `feature/xxx`：功能分支，完成后向 `develop` 发起 PR。
- `fix/xxx`：缺陷修复分支。

#### PR 提交前自检清单

| 检查项               | 说明                                                   |
| :------------------- | :----------------------------------------------------- |
| ✅ 本地构建通过       | `npm run build` 与后端无语法错误                       |
| ✅ 自动化检查通过     | ESLint、Prettier、Ruff 无报错                          |
| ✅ 新增功能有测试覆盖 | 核心逻辑需补充单元测试（见下节）                       |
| ✅ 文档同步更新       | 接口变更需更新 API 注释或相关文档                      |
| ✅ Commit 信息规范    | 遵循 Conventional Commits（如 `feat: add iOS driver`） |

#### Code Review 要点

**通用要点**：
- 代码可读性与命名规范
- 错误处理是否完善（如网络中断、设备断开）
- 资源释放（子进程、端口转发、WebSocket 连接）是否正确
- 并发安全性（多设备同时操作时的竞态条件）

**前端专项要点**：
- WebSocket 重连机制与心跳保活
- 视频解码性能（避免主线程阻塞，合理使用 WebCodecs）
- 组件拆分与复用性
- 内存泄漏防范（事件监听器、定时器清理）

**后端专项要点**：
- FastAPI 路由的异步支持（`async def` 与阻塞 I/O 处理）
- WebSocket 连接生命周期管理（`try/finally` 清理资源）
- ADB / usbmuxd 子进程的优雅终止
- 流数据处理时的背压控制（防止内存暴涨）

**Electron 专项要点**：
- 主进程与渲染进程 IPC 通信安全性（`contextBridge` 暴露方法）
- 子进程崩溃后的恢复机制
- 跨平台兼容性（Windows 与 macOS 路径、进程信号差异）

## Git 操作
```bash
# 安装 pre-commit 钩子
uv run pre-commit install

# 提交代码（会自动触发 pre-commit）
git add .
git commit -m "描述"

# 跳过 pre-commit（不推荐）
git commit --no-verify -m "描述"
```
#### Git 提交信息规范（必须）

- 提交信息必须使用 Conventional Commits：`type(scope): subject`
- 允许的 `type`：`feat`、`fix`、`docs`、`refactor`、`test`、`chore`
- 禁止使用无法表达变更性质的模糊前缀（如 `update`、`misc`、`todo`）
- `subject` 要能直接体现本次提交的主要意图（功能新增、缺陷修复、文档调整等）
- 示例：
  - `feat(order): 新增订单价格自动匹配回退逻辑`
  - `fix(api): 修复订单保存时重量整数校验错误`
  - `docs(skill): 统一项目手册技能分流与开场话术`