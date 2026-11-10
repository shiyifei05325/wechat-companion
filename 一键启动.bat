@echo off
cd /d "%~dp0"
echo ============================================
echo    微信虚拟伴侣 · 一键启动
echo ============================================
echo.
set "PYEXE=python"
if exist "C:\Python313\python.exe" set "PYEXE=C:\Python313\python.exe"
echo 正在检测运行环境（Python / 依赖 / 微信）...
"%PYEXE%" --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo [错误] 未检测到 Python，请先安装 Python 3.9 或更高版本。
    echo        安装时请勾选 Add Python to PATH。
    echo        下载地址：https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)
"%PYEXE%" launcher.py
echo.
pause