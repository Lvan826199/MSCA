# MSCA 打包构建指南

## 目录结构

```
dist/
├── README.md          # 本文件
├── backend/           # Python 后端编译产物
│   └── msca-backend/     # Nuitka standalone 运行时目录
│       └── msca-backend.exe
├── web/               # Vue 前端静态文件（Web 部署用）
│   ├── index.html
│   └── assets/
└── electron/          # Electron 桌面端安装包
    ├── MSCA Setup 0.1.0.exe
    └── win-unpacked/
        └── MSCA.exe
```

## 构建命令

### 1. 前端构建（Web 静态文件）

```bash
npm run build:web
```

产物输出到 `dist/web/`，可直接部署到 Nginx 等 Web 服务器。

### 2. 后端编译（Nuitka → 独立 exe）

```bash
npm run backend:build
```

产物输出到 `dist/backend/msca-backend/` standalone 运行时目录，同时复制到 `resources/msca-backend/` 供 Electron 打包使用。

验证编译产物：

```bash
npm run backend:verify
```

### 3. Electron 桌面端打包

```bash
npm run electron:build
```

该命令会依次执行前端构建、后端编译、Electron 打包，最终产物在 `dist/electron/`。

### 4. 清理所有构建产物

```bash
npm run dist:clean
```

## 部署说明

### 桌面端

直接运行 `dist/electron/MSCA Setup 0.1.0.exe` 安装，或运行 `dist/electron/win-unpacked/MSCA.exe` 做免安装验证。应用内嵌后端，无需额外配置。

安装后建议按以下顺序做发布验证：

1. 首次启动应用，确认内嵌后端自动拉起且左下角连接状态为“已连接”。
2. 连接 Android/iOS 设备，确认设备列表正常刷新。
3. 分别启动 Android 与 iOS 投屏，确认画面可见、停止后返回设备列表且后端健康检查仍为 `ok`。
4. 如 iOS 投屏失败，优先按下方 WDA 排障清单处理签名、信任、端口和 tunnel 问题。

### Web 端

1. 将 `dist/web/` 部署到 Web 服务器（如 Nginx）
2. 独立部署 `dist/backend/msca-backend.exe`（或用 Python 源码运行）
3. 配置前端连接远程后端地址

Nginx 参考配置（示例以后端监听 `18000` 为例，如使用其他端口需同步修改 `proxy_pass`）：

```nginx
server {
    listen 443 ssl;
    server_name msca.example.com;

    # 前端静态文件
    location / {
        root /path/to/dist/web;
        try_files $uri $uri/ /index.html;
    }

    # 后端 API 代理
    location /api/ {
        proxy_pass http://127.0.0.1:18000;
    }

    # WebSocket 代理
    location /ws/ {
        proxy_pass http://127.0.0.1:18000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

### 后端独立运行

```bash
# 编译版
./msca-backend.exe --port 18000

# 源码版
cd backend
uv run python __main__.py --port 18000
```

## iOS WDA 排障清单

| 场景 | 常见提示 | 处理方式 |
|------|----------|----------|
| WDA 签名过期或无效 | `WDA 签名无效或已过期` | 使用有效开发者证书重新签名并安装 WDA；免费开发者账号通常 7 天后需重新签名 |
| 设备未信任电脑 | `iOS 设备未信任电脑或配对凭证不可用` | 解锁设备并点击“信任此电脑”，必要时重新插拔 USB 或删除 `selfIdentity.plist` 后重新信任 |
| 本地端口占用 | `本地 WDA 或 MJPEG 端口被占用` | 关闭残留的 MSCA、tidevice、ios.exe，或释放 8100/8101/8110 等端口后重试 |
| WDA Bundle ID 不匹配 | `未找到可启动的 WDA Runner 应用或 Bundle ID 不匹配` | 确认设备已安装签名后的 WDA，并检查 `backend/config/wda_config.json` 的 `wda_bundle_id` 或 `wda_bundle_id_pattern` |
| go-ios tunnel 失败 | `go-ios tunnel 启动失败` | iOS 17+ 以管理员身份运行 `scripts/ios-tunnel.bat`，或手动执行 `ios tunnel start` 后重试 |
| WDA session/control 失败 | `WDA 服务已连接但 session 或控制接口不可用` | 重启设备上的 WDA Runner，确认 `/status` 正常后重新启动投屏 |

## iOS 手势封装决策

当前不引入 `python-wda`、W3C Actions 或 Airtest 作为主链路依赖。发布前继续维护现有 WDA REST 最小实现，并通过后端错误分类、前端提示和本排障清单降低定位成本；仅当真实设备手势兼容性仍持续不足或 REST 维护成本明显上升时，再评估第三方封装。

## 前置依赖

| 依赖 | 用途 | 安装方式 |
|------|------|----------|
| Node.js 18+ | 前端构建 | nodejs.org |
| Python 3.13+ | 后端运行 | python.org |
| uv | Python 包管理 | `pip install uv` |
| Nuitka | 后端编译 | `uv add --dev nuitka`（自动安装） |
| ADB | Android 设备连接 | Android Platform Tools |
| scrcpy-server | Android 投屏 | 已内置于 `bin/android/` |
| go-ios | iOS ≥16.x 支持 | 已内置于 `bin/ios/` |
| tidevice | iOS ≤15.x 支持 | `uv add tidevice` |
