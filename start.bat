@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title 发票OCR识别工具

rem ===== 配置（一般无需修改）=====
if not defined PORT set "PORT=39417"
set "HOST=127.0.0.1"
if not defined OPEN_BROWSER set "OPEN_BROWSER=1"
if not defined PIP_INDEX_URL set "PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/"
set "DEPS_VERSION=1"
set "VENV_PY=%~dp0.venv\Scripts\python.exe"
set "DEPS_MARKER=%~dp0.venv\deps_installed_v%DEPS_VERSION%.txt"
rem CI 环境下不暂停，失败时直接退出
set "PAUSE_CMD=pause"
if defined CI set "PAUSE_CMD=rem"

echo ==================================================
echo   发票OCR识别工具
echo ==================================================
echo.

if exist "%DEPS_MARKER%" goto run
if exist "%VENV_PY%" goto install

rem ---------- 首次运行：查找 64 位 Python 3.9 ~ 3.13 ----------
set "PYCMD="
for %%V in (3.12 3.11 3.10 3.13 3.9) do (
    if not defined PYCMD (
        py -%%V -c "import struct,sys;sys.exit(0 if struct.calcsize('P')==8 else 1)" >nul 2>nul && set "PYCMD=py -%%V"
    )
)
if not defined PYCMD (
    python -c "import struct,sys;sys.exit(0 if (3,9)<=sys.version_info[:2]<=(3,13) and struct.calcsize('P')==8 else 1)" >nul 2>nul && set "PYCMD=python"
)
if not defined PYCMD goto no_python

echo 使用 Python: %PYCMD%
echo [1/2] 正在创建运行环境...
%PYCMD% -m venv "%~dp0.venv"
if errorlevel 1 goto venv_failed

:install
echo [2/2] 首次运行需要联网下载安装依赖（几百 MB），视网速约需 5~20 分钟，请耐心等待...
echo.
"%VENV_PY%" -m pip install --upgrade pip --default-timeout 100
"%VENV_PY%" -m pip install -r requirements.txt "paddlepaddle==3.1.1" --default-timeout 100
if errorlevel 1 goto pip_failed
echo ok> "%DEPS_MARKER%"
echo.
echo 依赖安装完成，以后双击即可直接启动。
echo.

:run
"%VENV_PY%" -c "import os,sys;sys.exit(0 if os.getcwd().isascii() else 1)"
if errorlevel 1 goto warn_path

:start_server
echo 正在启动服务，加载模型约需 10~30 秒...
echo 启动后会自动打开浏览器；如未自动打开，请手动访问 http://127.0.0.1:%PORT%/fapiao
echo 使用期间请不要关闭本窗口，关闭窗口即退出程序。
echo.
"%VENV_PY%" main.py
echo.
echo 程序已退出。如果上面有报错信息，请截图反馈。
%PAUSE_CMD%
exit /b 0

:no_python
echo [错误] 未找到可用的 Python（需要 64 位 Python 3.9 ~ 3.13）。
echo 即将打开 Python 官网下载页，推荐安装 Python 3.12 的 Windows installer (64-bit)，
echo 安装时务必勾选 "Add python.exe to PATH"，装好后重新双击本文件。
if not defined CI start "" "https://www.python.org/downloads/windows/"
%PAUSE_CMD%
exit /b 1

:venv_failed
echo [错误] 创建运行环境失败，请确认 Python 安装完整后重试。
%PAUSE_CMD%
exit /b 1

:pip_failed
echo.
echo [错误] 依赖安装失败，常见原因：网络不通、磁盘空间不足。
echo 请检查网络后重新双击本文件重试；如仍失败，可删除本目录下的 .venv 文件夹后再试。
%PAUSE_CMD%
exit /b 1

:warn_path
echo [警告] 程序所在路径包含中文等非英文字符：
echo   %CD%
echo PaddleOCR 在这类路径下可能无法加载模型。如果识别时报错，
echo 请把整个文件夹移动到纯英文路径（例如 D:\fapiao-ocr）后再运行。
echo.
goto start_server
