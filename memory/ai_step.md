# AI 操作步骤记录

> **强制规则**：每次 AI 完成开发任务后，必须将本次操作行为和执行结果写入本文档。本文档作为持久化操作记录，供后续会话参考。

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
