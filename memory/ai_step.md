# AI 操作步骤记录

> **强制规则**：每次 AI 完成开发任务后，必须将本次操作行为和执行结果写入本文档。本文档作为持久化操作记录，供后续会话参考。

---

## 2026-05-01 — Electron 打包产物启动修复 + 内嵌后端验证

### 触发背景

打包后的 `dist/electron/win-unpacked/MSCA.exe` 启动日志显示后端健康检查超时，并错误尝试加载 `http://localhost:5173/`。用户确认此前 Web 端校验可正常投屏，要求继续任务；若再次失败先记录，并优先完成全部开发任务。

### 操作摘要

| 类别 | 操作 | 涉及文件 |
|:---|:---|:---|
| Electron 模式识别 | 主进程改用 `app.isPackaged` 判断开发/打包模式，避免打包产物误连 Vite 开发服务 | `electron/main.js` |
| 后端启动模式 | `BackendManager` 接收 `isPackaged` 参数，生产模式启动内嵌 `msca-backend.exe`，不再依赖 `NODE_ENV` | `electron/backend-manager.js` |
| 打包验证 | 重新执行完整 Electron 打包，生成安装包与 unpacked 可执行文件 | `package.json`, `dist/electron/*` |
| 运行验证 | 启动 `dist/electron/win-unpacked/MSCA.exe`，验证内嵌后端 `/health` 与 `/api/devices` | Electron 打包产物 |
| iOS 15.1 记录 | 使用打包产物内嵌后端启动 iOS 15.1 投屏接口，返回 started，并随后停止会话 | 后端运行时 |

### 关键代码变更

- `electron/main.js`：`isDev` 从 `process.env.NODE_ENV !== "production"` 改为 `!app.isPackaged`。
- `electron/main.js`：创建 `BackendManager(app.isPackaged)`，将打包状态传入后端管理器。
- `electron/backend-manager.js`：构造函数新增 `isPackaged` 参数，并在 `_getBackendPath()` / `_spawn()` 中使用 `!this._isPackaged` 判断开发模式。

### 验证步骤（已执行）

1. **Electron 打包验证**：`npm run electron:build` → 通过，重新生成 `dist/electron/MSCA Setup 0.1.0.exe` 与 `dist/electron/win-unpacked/MSCA.exe`。
2. **打包产物启动验证**：启动 `dist/electron/win-unpacked/MSCA.exe` → 日志显示内嵌后端在 `127.0.0.1:18000` 启动，主进程输出“后端已启动，端口 18000”。
3. **内嵌后端健康检查**：`GET http://127.0.0.1:18000/health` → `{"status":"ok"}`。
4. **设备接口验证**：`GET http://127.0.0.1:18000/api/devices` → 200，返回 Android 与 iOS 设备列表。
5. **iOS 15.1 投屏接口记录**：`POST /api/mirror/00008101-001859DE1E38001E/start` → `{"status":"started","device_id":"00008101-001859DE1E38001E","width":428,"height":926}`；随后执行 stop → `{"status":"stopped"}`。

### 后续注意

- 本轮验证确认打包产物不再尝试加载 `http://localhost:5173/`，内嵌后端可正常启动。
- iOS 15.1 本次通过接口启动投屏，仍建议在桌面 UI 中回归点击、拖拽、滑动、长按与按键控制表现。

### 最终提交 hash

- `8b986c1` fix(electron): 修复打包产物启动模式识别

---

## 2026-04-30 — iOS 15.1 控屏稳定性增强 + 完整发布验证 + Electron 打包通过

### 触发背景

用户要求继续完善 iOS 真机投屏 / 控制稳定性，明确 iOS 15.1 当前仍无法控屏；同时要求执行完整发布验证（`npm run build`、`npm run dev:backend`、`npm run backend:verify`）和 Electron 打包验证（`npm run electron:build`），并继续排查现有 bug。

### 操作摘要

| 类别 | 操作 | 涉及文件 |
|:---|:---|:---|
| iOS 控制可观测性 | WDA 控制请求统一检查 HTTP 状态码与响应体，失败返回 `False` 并记录日志 | `backend/app/drivers/ios.py` |
| iOS 控制反馈 | 控制 WebSocket 检查 `send_event()` 返回值，失败时向前端返回错误 | `backend/app/websocket/control.py` |
| iOS 点击兼容 | 鼠标简单点击最终发送 `tap` 指令，后端映射到 WDA `/wda/tap/0`；拖动仍走 down/move/up | `frontend/src/composables/useDeviceControl.js`, `backend/app/websocket/control.py` |
| iOS 坐标修复 | Canvas 坐标换算扣除 `object-fit: contain` 黑边，并将坐标限制到 `0..width-1/height-1` | `frontend/src/composables/useDeviceControl.js` |
| iOS 尺寸修复 | 启动时优先读取 WDA screenshot JPEG 尺寸，降低 WDA point 与 MJPEG pixel 不一致导致的触控偏移 | `backend/app/drivers/ios.py` |
| iOS 版本选择 | go-ios 扫描补齐 tidevice 缺失的版本；版本未知时优先 tidevice，避免 iOS 15.x 误走 go-ios | `backend/app/core/device_manager.py` |
| WDA 端口配置 | tidevice/go-ios 端口转发读取 `wda_port_on_device`，不再硬编码设备端 8100 | `backend/app/drivers/adapters/tidevice_adapter.py`, `backend/app/drivers/adapters/goios_adapter.py` |
| 前端提示 | 投屏面板展示控制 WebSocket 返回的控制错误 | `frontend/src/components/DeviceMirrorPanel.vue` |
| 打包修复 | electron-builder 二进制依赖使用国内镜像，Windows 非管理员环境关闭 `signAndEditExecutable` 避免 winCodeSign 符号链接权限失败 | `package.json` |
| 文档同步 | 更新 M13 进度、Electron 打包说明和未知版本 iOS 适配说明 | `README.md`, `CLAUDE.md`, `doc/下一步计划.md` |

### 关键代码变更

**iOS 15.1 控屏链路增强：**
- `IOSDriver._post_wda()` 统一封装 WDA POST 请求，记录非 2xx 状态码和响应体前 500 字符。
- 控制 WebSocket 不再吞掉 WDA 控制失败，前端可看到如“iOS 点击失败 / iOS 触控动作失败”等提示。
- 简单鼠标点击改用 WDA tap endpoint，降低 iOS 15.1 对 `/wda/touch/down|up` 连续触控 endpoint 不兼容的风险。
- 拖动/滑动仍保留完整 `down → move → up` 序列。
- iOS 屏幕尺寸优先采用 screenshot JPEG 实际尺寸，坐标转换扣除 contain 黑边并避免边界坐标等于宽高。

**iOS 适配器选择修复：**
- tidevice 扫描到设备但版本为空时，允许 go-ios 同 UDID 结果补齐版本。
- 如果最终版本仍未知，优先使用 tidevice，避免 iOS 15.1 误走 go-ios tunnel/runwda 路径。

**Electron 打包修复：**
- 第一次 `electron:build` 失败：`winCodeSign-2.6.0.7z` 从 GitHub 下载超时。
- 增加 `ELECTRON_BUILDER_BINARIES_MIRROR=https://npmmirror.com/mirrors/electron-builder-binaries/` 后，下载问题解决。
- 第二次失败：Windows 当前权限无法创建 `winCodeSign` 包内 darwin 符号链接。
- 设置 `build.win.signAndEditExecutable=false` 后，非管理员环境打包通过。

### 验证步骤（已执行）

1. **Python 修改语法检查**：`python -m py_compile backend/app/drivers/ios.py backend/app/websocket/control.py backend/app/core/device_manager.py backend/app/drivers/adapters/tidevice_adapter.py backend/app/drivers/adapters/goios_adapter.py` → 通过。
2. **前端构建**：`npm run build` → 1028 modules transformed，构建成功。
3. **后端健康检查**：`npm run dev:backend` + 读取 `.backend-port` 请求 `/health` → `{"status":"ok"}`。
4. **后端编译与验证**：`npm run backend:build && npm run backend:verify` → `/health` 返回 `{"status":"ok"}`，`/api/devices` 返回 200，`后端打包验证通过`。
5. **Electron 打包验证**：`npm run electron:build` → 通过，生成：
   - `dist/electron/MSCA Setup 0.1.0.exe`
   - `dist/electron/win-unpacked/MSCA.exe`
6. **Electron 资源检查**：确认打包目录包含：
   - `dist/electron/win-unpacked/resources/bin/android/scrcpy-server`
   - `dist/electron/win-unpacked/resources/bin/android/bundletool.jar`
   - `dist/electron/win-unpacked/resources/bin/ios/ios.exe`
   - `dist/electron/win-unpacked/resources/resources/msca-backend/msca-backend.exe`

### 待后续执行

- 在真实 iOS 15.1 设备上回归点击、拖拽、滑动、长按、Home/锁屏/音量键控制表现。
- 安装 `dist/electron/MSCA Setup 0.1.0.exe` 后做端到端启动验证：内嵌后端自动启动、设备列表、Android/iOS 投屏和控制链路。
- 如果 iOS 15.1 仍无法控屏，优先查看后端 WDA HTTP 状态码/响应体日志，判断是 endpoint 不支持、session 缺失、坐标系不匹配还是 WDA 签名/权限问题。

### 最终提交 hash

- 当前尚未提交，本轮变更待用户确认后提交。

---

## 2026-04-30 — 文档同步 + 代码审查与 M13 后端打包验证

### 触发背景

用户要求同步所有文档，校验当前项目所有代码，执行 code review 与 UI/交互易用性分析，并根据文档继续下一步开发任务直到完成后提交本地仓库。

### 操作摘要

| 类别 | 操作 | 涉及文件 |
|:---|:---|:---|
| 文档同步 | 统一当前架构说明，移除旧 Electron 直连 scrcpy GUI 表述，补充 M13 打包验证状态 | `README.md`, `CLAUDE.md`, `doc/*.md`, `bin/README.md`, `dist/README.md` |
| 代码审查 | 审查后端资源路径、Electron 后端启动、前端连接与设备状态展示 | `backend/app/`, `electron/backend-manager.js`, `frontend/src/` |
| 易用性分析 | 梳理设备列表、连接状态、投屏页面、同步模式、移动端适配等 UI/交互改进点 | `frontend/src/views/*`, `frontend/src/components/*` |
| Android 资源路径 | `bundletool.jar` 与 `aab_keys` 支持 `MSCA_RESOURCES_PATH/bin/android` | `backend/app/drivers/android.py` |
| 后端构建 | Nuitka 改为 standalone 目录产物，自动同意依赖下载，复制完整运行时目录 | `scripts/build-backend.mjs` |
| 后端验证 | 验证脚本检查 Electron 资源、从 runtime 目录启动 exe、传入 `MSCA_RESOURCES_PATH` 并等待进程退出 | `scripts/verify-backend.mjs` |
| Electron 启动 | 生产模式后端路径改为 `resources/msca-backend/msca-backend.exe`，并设置 cwd/PATH 到 runtime 目录 | `electron/backend-manager.js` |

### 关键代码变更

**M13 standalone 后端运行时修复：**
- 不再把 Nuitka standalone exe 单独复制到 `dist/backend/msca-backend.exe` 运行。
- 完整复制 `.dist` 运行时目录到 `dist/backend/msca-backend/` 与 `resources/msca-backend/`。
- `backend:verify` 优先启动 `dist/backend/msca-backend/msca-backend.exe`，避免缺少 `python313.dll` 或运行路径错误。
- Electron 生产路径同步指向 `resources/msca-backend/msca-backend.exe`，并将 runtime 目录加入 `PATH`。

**资源验证增强：**
- 校验 `resources/msca-backend/msca-backend.exe`。
- 校验 `bin/android/scrcpy-server`、`scrcpy-server.version`、`bundletool.jar`。
- 校验 `bin/ios/ios.exe`。
- 后端启动时设置 `MSCA_RESOURCES_PATH`，模拟 Electron 生产资源路径。

### 验证步骤（已执行）

1. **脚本语法检查**：`node --check scripts/build-backend.mjs` → 通过。
2. **脚本语法检查**：`node --check scripts/verify-backend.mjs` → 通过。
3. **脚本语法检查**：`node --check electron/backend-manager.js` → 通过。
4. **后端打包构建**：`npm run backend:build` → Nuitka standalone 构建成功，产物位于 `dist/backend/msca-backend/msca-backend.exe`。
5. **后端打包验证**：`npm run backend:verify` → `/health` 返回 `{"status":"ok"}`，`/api/devices` 返回 200，验证通过。
6. **前端构建**：`npm run build` → 1028 modules transformed，构建成功。
7. **后端语法检查**：`uv run --project backend python -m py_compile backend/app/drivers/android.py backend/app/core/device_manager.py backend/app/scrcpy/server_manager.py` → 通过。
8. **后端导入测试**：`uv run --project backend python -c "import sys; sys.path.insert(0, 'backend'); from app.main import app; from app.drivers.android import AndroidDriver; print('Import OK')"` → `Import OK`。

### 待后续执行

- 最终发布前执行 `npm run electron:build`，验证安装包端到端启动内嵌后端。
- 根据本轮 UI/交互分析继续优化设备列表加载/错误态、连接模式设置、同步模式风险提示与窄屏投屏布局。
- 在真实 Android/iOS 设备上回归资源路径、AAB 安装、投屏和控制链路。

---

## 2026-04-30 — 开发计划同步 + iOS 触控序列与不可用状态

### 触发背景

用户要求结合开发计划、第三方项目调研报告与 `memory/ai_step.md`，先更新开发计划，再按推荐建议继续下一步开发任务并提交到本地仓库。

### 操作摘要

| 类别 | 操作 | 涉及文件 |
|:---|:---|:---|
| 文档更新 | 重写并同步当前开发进度：M1~M12 完成、M13 剩余 Electron 打包验证、P0 稳定性任务 | `doc/开发计划.md` |
| 文档更新 | 纳入第三方调研落地策略：Liuma-agent、pymobiledevice3、Airtest、mwj-autotest-vue3 | `doc/开发计划.md` |
| iOS 控制 | `IOSDriver.send_event()` 新增 `touch` 动作，映射 WDA `/wda/touch/down|move|up` | `backend/app/drivers/ios.py` |
| iOS 控制 | `_handle_ios_command()` 改为完整转发前端 down/move/up，不再将 down 简化为 tap | `backend/app/websocket/control.py` |
| 设备状态 | 新增 iOS 连续投屏失败计数，达到 3 次后标记 `unavailable` 并推送设备列表 | `backend/app/core/device_manager.py` |
| API 处理 | 投屏启动成功清空失败计数，启动失败累计失败计数 | `backend/app/api/mirror.py` |
| 数据模型 | 设备状态注释新增 `unavailable` | `backend/app/models/device.py` |
| 前端提示 | 设备卡片展示 `不可用` 状态和“当前设备无法连接，请联系管理员处理”提示 | `frontend/src/components/DeviceCard.vue` |

### 关键代码变更

**iOS 触控序列修复：**
- 前端已有 down→move→up 发送逻辑，本次修复后端 iOS 分支吞掉 move/up 的问题。
- `ControlEvent("touch", {"action": action, "x": x, "y": y})` 直接映射到 WDA touch endpoint。
- 支持 `down`、`move`、`up` 三类动作，拖拽/滑动不再退化为单次 tap。

**iOS 不可用状态：**
- `DeviceManager` 增加 `_ios_failure_counts` 与 `_ios_unavailable`。
- 连续 3 次 iOS 投屏启动失败后，将设备状态改为 `unavailable`。
- 投屏启动成功后清理失败计数并恢复 `online`。
- 前端设备卡片禁用投屏/安装按钮，并展示管理员处理提示。

### 验证步骤（已执行）

1. **前端构建**：`npm run build` → 1028 modules transformed，构建成功。
2. **后端语法检查**：`uv run python -m compileall backend/app` → 通过。
3. **后端导入测试**：`uv run --project backend python -c "from backend.app.main import app; print('Import OK')"` → `Import OK`。
4. **后端 /health 实测**：`npm run dev:backend` + 读取 `.backend-port` 请求 `/health` → `{"status":"ok"}`。
5. **说明**：曾用根目录 uv 环境执行导入测试，因根 `pyproject.toml` 未包含 `aiohttp` 失败；改用 `--project backend` 后通过。

### 待后续执行

- 在真实 iOS 15.1 设备上验证拖拽、滑动、长按触控表现。
- 执行 M13 Electron 安装包端到端验证：`npm run electron:build`。
- 继续评估是否引入 `python-wda` 统一 WDA HTTP 封装。

---

## 2026-04-29 — Bug 修复: 侧边栏样式 + 设备名称 + iOS 重复投屏

### 触发背景

用户反馈 5 个问题：侧边栏白色背景、添加投屏设备名称显示为 ID、iOS 15.1 停投再投报 cert_reqs 错误；要求分析 iOS 控屏方案和低版本提示方案。

### 操作摘要

| 类别 | 操作 | 涉及文件 |
|:---|:---|:---|
| Bug 修复 | 侧边栏 `el-menu` 覆盖 CSS 变量 (`--el-menu-bg-color` 等 4 个) 解决白色背景 | `frontend/src/App.vue` |
| Bug 修复 | 添加投屏弹窗新增 `getDeviceLabel()` 优先展示 `别名(型号)` 格式 | `frontend/src/views/MirrorView.vue` |
| Bug 修复 | `_kill_process` → `_kill_process_tree` (Windows `taskkill /T` 杀进程树) | `backend/app/drivers/adapters/tidevice_adapter.py` |
| Bug 修复 | 新增 `_cleanup_orphan_tidevice()` 按 UDID 清理残留进程 | 同上 |
| Bug 修复 | `start_wda()` 添加一次自动重试 + 间隔清理机制 | 同上 |
| 分析 | iOS 15.1 控屏方案分析（对比 csmobileagent → 定位 touch move 未处理） | 未写代码 |
| 分析 | iOS 低版本无法连接提示方案规划（新增 `unavailable` 状态） | 未写代码 |

### 关键代码变更

**tidevice_adapter.py 进程清理改进：**
- `_kill_process_tree()`: 使用 `taskkill /F /T /PID` 终止整个进程树（替代单一 `proc.terminate()`）
- `_cleanup_orphan_tidevice()`: 通过 `wmic process where "commandline like '%UDID%'"` 匹配并强制终止残留进程
- `stop_wda()`: 清理后额外等待 0.3s 确保资源释放
- `start_wda()`: 首次 wdaproxy 启动失败 → `stop_wda` 彻底清理 → 等待 1s → 重试 1 次

### iOS 控屏问题根因分析

`control.py:_handle_ios_command()` 中 touch 处理仅响应 `action="down"`（转 tap），`move` 和 `up` 被忽略。前端发送的 down→move→up 触摸序列在 iOS 侧退化为单次 tap，拖拽/滑动手势失效。建议方案：
1. iOS 驱动新增基于 WDA `/wda/touch/down|move|up` API 的触控方法
2. 缓存 touch 状态实现完整手势序列
3. 可选引入 `python-wda` 库，再调研一下`https://github.com/doronz88/pymobiledevice3` ，看下是否有可以借鉴使用的地方，
4. 继续调研`https://github.com/AirtestProject/Airtest` ，这个项目，我们计划里面能用到，该项目有适合的地方可以借鉴过来
5. 上面两个github项目我已经下载到了E:\Y_pythonProject\csmobileagent目录下，你直接本地探索
### 验证步骤（已执行）

1. **前端构建**：`npm run build` → 1028 modules, 2.53s, 构建成功
2. **后端代码语法**：手动审查通过，无语法错误

### 待后续执行

- 后端 /health 启动测试
- iOS 控屏方案代码实现（等待用户指令）
- iOS 低版本 `unavailable` 状态实现（等待用户指令）

---

## 2026-04-29 — 后端导入修复 & 前端树摇与懒加载

### 触发背景

后端 `main.py` 导入飘红（绝对导入 `from app.xxx` 在 `uvicorn.run("app.main:app")` 模式下不可靠），前端大包体积过大需按需加载。

### 操作摘要

| 类别 | 操作 | 涉及文件 |
|:---|:---|:---|
| 后端导入修复 | 15 个 Python 文件绝对导入 (`from app.xxx`) → 相对导入 (`from .xxx` / `from ..xxx`) | `backend/app/` 下所有 .py |
| 后端代码清理 | 删除未使用导入、logging 改用 %-格式化、类型标注现代化 | `ios.py`, `install.py`, `base.py` 等 |
| 前端 Element Plus 树摇 | 移除全量 `app.use(ElementPlus)`，改为 `plugins/element-plus.js` 按需导入 23 个组件 + 独立 CSS | `main.js`, 新增 `plugins/element-plus.js` |
| 前端懒加载 | `DeviceMirrorPanel`、`DeviceControlBar`、`useVideoDecoder` 改为 `defineAsyncComponent` / 动态 `import()` | `MirrorView.vue`, `DeviceMirrorPanel.vue` |
| 前端死代码清理 | 删除未使用的 `useMjpegDecoder.js` (75 行) | 1 个文件 |
| 前端手动分包 | `vite.config.js` manualChunks: vendor-element-plus, vendor-vue (含 @vue/*), decoder-video | `vite.config.js` |
| 构建脚本 | 新增 `build-backend.mjs`, `build-web.mjs`, `clean-dist.mjs`, `verify-backend.mjs` | 4 个文件 |

### 验证步骤（已执行）

1. **后端导入测试**：`uv run --project backend python -c "from backend.app.main import app; print('Import OK')"` → 通过
2. **后端 /health 实测**：`curl http://127.0.0.1:18002/health` → `{"status":"ok"}`
3. **后端 API 实测**：`/api/devices` 返回 9 台设备，`/api/devices/refresh` POST 正常
4. **前端构建测试**：`npm run build` → 1028 modules, 构建成功
5. **Git 提交**：`376efd7` refactor: 后端绝对导入转相对导入 + 前端 Element Plus 树摇与懒加载

### 构建产物体积 (gzip)

| Chunk | JS | 说明 |
|:---|---:|:---|
| vendor-element-plus | 72KB | Element Plus 组件 |
| vendor-vue | 42KB | Vue 3 完整运行时 + Router + @vue/* |
| vendor | 21KB | 其他第三方依赖 |
| decoder-video | 2KB | 视频解码器（懒加载） |
| DeviceMirrorPanel | 4KB | 投屏面板（懒加载） |
| 其他页面/组件 | ~10KB | MirrorView, HomeView 等 |
| **首屏总计** | **~151KB** | |

### 后续必须执行的验证流程

每次开发完成后，必须按以下顺序执行：

```bash
# 1. 前端构建
npm run build

# 2. 后端启动 + 健康检查
npm run dev:backend
# 另开终端
curl http://127.0.0.1:$(cat .backend-port)/health
# 期望: {"status":"ok"}

# 3. 提交代码
git add <files>
git commit -m "type(scope): subject"
```
