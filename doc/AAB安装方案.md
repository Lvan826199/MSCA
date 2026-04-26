# AAB (Android App Bundle) 安装方案

## 概述

MSCA 支持通过 Google 官方的 `bundletool` 工具将 `.aab` 文件转换并安装到 Android 设备。

AAB 是 Google Play 的标准发布格式，不能直接安装到设备。安装流程为：
1. `bundletool build-apks` — 根据连接设备的配置，将 AAB 转换为设备专属的 APKS
2. `bundletool install-apks` — 将生成的 APKS 安装到设备

## 你需要准备的内容

### 1. bundletool.jar

- 下载地址：https://github.com/niclas-niclas/bundletool/releases
- 下载最新版本的 `bundletool-all-x.x.x.jar`
- 重命名为 `bundletool.jar`
- 放置到项目目录：`bin/android/bundletool.jar`

### 2. Java 运行时 (JRE/JDK 11+)

bundletool 是 Java 程序，需要 Java 11 或更高版本。

- 下载地址：https://adoptium.net/ （推荐 Eclipse Temurin）
- 安装后确保 `java` 命令在系统 PATH 中可用
- 验证：`java -version` 应输出 11+ 版本号

## 目录结构

```
bin/
└── android/
    ├── scrcpy-server          # 已有
    ├── scrcpy-server.version  # 已有
    └── bundletool.jar         # ← 新增，你需要放置到这里
```

## 查找优先级

程序按以下顺序查找 `bundletool.jar`：

1. `bin/android/bundletool.jar`（项目内置，推荐）
2. 环境变量 `BUNDLETOOL_PATH` 指向的文件路径

## 使用方式

放置好 `bundletool.jar` 后，在设备卡片点击"安装应用"时即可选择 `.aab` 文件，后端会自动调用 bundletool 完成转换和安装。

## 注意事项

- AAB 转换过程会根据连接设备的 ABI、屏幕密度、语言等生成专属 APK，因此必须在设备连接状态下操作
- 转换过程可能需要 10-30 秒，取决于 AAB 大小
- 如果 AAB 使用了 Play App Signing，需要提供签名密钥（当前实现使用 debug 签名，适用于开发/测试场景）
- 生产签名的 AAB 如需安装，可能需要额外的 `--ks`（keystore）参数，后续可按需扩展
