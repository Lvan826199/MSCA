@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

:: ============================================================
:: ios-tunnel.bat — 以管理员权限启动 go-ios tunnel（iOS 17+ 必需）
::
:: 使用方式：双击运行，或在命令行执行 scripts\ios-tunnel.bat
:: 如果当前不是管理员，会自动弹出 UAC 提权窗口
:: ============================================================

:: 检测是否已是管理员
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] 当前非管理员，正在请求管理员权限...
    powershell -Command "Start-Process -Verb RunAs -FilePath '%~f0' -WorkingDirectory '%~dp0'"
    exit /b
)

echo ============================================================
echo   go-ios tunnel 启动脚本（管理员模式）
echo ============================================================
echo.

set "ENABLE_GO_IOS_AGENT=1"

:: 查找 ios.exe
set "IOS_BIN="

:: 1. 项目 bin 目录
if exist "%~dp0..\bin\ios\ios.exe" (
    set "IOS_BIN=%~dp0..\bin\ios\ios.exe"
    goto :found
)

:: 2. 系统 PATH
where ios.exe >nul 2>&1
if %errorlevel% equ 0 (
    for /f "delims=" %%i in ('where ios.exe') do set "IOS_BIN=%%i"
    goto :found
)

:: 3. 未找到
echo [ERROR] 未找到 ios.exe
echo 请确保 go-ios 已安装并在 PATH 中，或放置在项目 bin\ios\ 目录下
echo 下载地址: https://github.com/danielpaulus/go-ios/releases
pause
exit /b 1

:found
echo [INFO] 使用: %IOS_BIN%

:: ── wintun.dll 检查（内核 tunnel 必需；go-ios 搜索 exe 同目录与 System32） ──
for %%a in ("%IOS_BIN%") do set "IOS_DIR=%%~dpa"
if exist "%IOS_DIR%wintun.dll" goto :wintun_ok
if exist "%SystemRoot%\System32\wintun.dll" goto :wintun_ok
if exist "%~dp0..\bin\ios\wintun.dll" (
    echo [INFO] 复制内置 wintun.dll 到 System32...
    copy /y "%~dp0..\bin\ios\wintun.dll" "%SystemRoot%\System32\wintun.dll" >nul
    if !errorlevel! equ 0 goto :wintun_ok
)
echo [WARN] 未找到 wintun.dll，内核 tunnel 可能启动失败
echo [WARN] 请从 https://www.wintun.net/ 下载，将 wintun.dll 放到 ios.exe 同目录或 C:\Windows\System32
:wintun_ok

echo [INFO] 启动 tunnel...
echo.

"%IOS_BIN%" tunnel start

echo.
echo [INFO] tunnel 已退出
pause
