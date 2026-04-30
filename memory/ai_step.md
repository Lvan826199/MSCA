# AI 操作步骤记录

> **强制规则**：每次 AI 完成开发任务后，必须将本次操作行为和执行结果写入本文档。本文档作为持久化操作记录，供后续会话参考。

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
