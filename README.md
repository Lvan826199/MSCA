# MSCA - 多设备移动端投屏控制系统

MSCAMSCA（Mobile Screen Control Assistant）是一个跨平台的移动设备投屏与控制工具，支持 Windows 和 macOS 系统，同时提供 Web 端访问能力。**当前专注于 Android 设备**，未来规划扩展 iOS 设备支持。

## 核心功能

- **多设备并发管理**：支持同时连接并控制多台移动设备，设备间互不干扰
- **单设备精细操控**：每台设备拥有独立的控制面板，支持精确的点击、滑动、输入等操作
- **多设备同屏监控**：支持单页面同时查看多台设备的实时投屏画面，便于批量监控与管理
- **跨平台支持**：桌面端基于 Electron 构建，原生支持 Windows 和 macOS；同时提供 Web 端，无需安装客户端即可使用浏览器访问
- **本地化部署**：无需数据库，所有数据仅在本地处理，保障数据安全

## 设备支持规划

| 平台 | 当前状态 | 技术方案 | 实现难度 |
| :--- | :---: | :--- | :---: |
| **Android** | ✅ 已规划 | 基于 Scrcpy 协议，通过 ADB 实现高效 H.264 视频流传输与控制 | ⭐⭐ |
| **iOS** | 🔮 未来扩展 | 基于 [WebDriverAgent](https://github.com/appium/WebDriverAgent) + [usbmuxd](https://github.com/libimobiledevice/usbmuxd) 实现屏幕镜像与 XCTest 自动化控制 | ⭐⭐⭐⭐ |

> **说明**：iOS 控屏因系统封闭性，实现难度和限制均高于 Android。当前版本专注于 Android 设备支持，iOS 支持将在后续版本中评估与实现。

## 技术栈

- **前端**：Vue 3 + Vite + WebCodecs API
- **桌面端**：Electron
- **后端**：Python + FastAPI + adbutils
- **核心协议**：
  - Android：基于 [Scrcpy](https://github.com/Genymobile/scrcpy) 实现 H.264 视频流传输与控制
  - iOS（未来）：基于 [WebDriverAgent](https://github.com/appium/WebDriverAgent) 实现 XCTest 自动化与 MJPEG/H.264 视频流

## 适用场景

- 应用与游戏的自动化测试
- 多设备批量操作与演示
- 远程设备协助与调试
- 移动应用开发过程中的多机型适配测试

## 快速开始

```bash
# 克隆仓库
git clone https://gitee.com/xiaozai-van-liu/MSCA

# or
git clone https://github.com/Lvan826199/MSCA

cd MSCA

# 安装依赖
npm install
pip install -r requirements.txt

# 启动开发环境
npm run dev