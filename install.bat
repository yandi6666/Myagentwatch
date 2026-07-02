@echo off
chcp 65001 >nul
echo ============================================
echo   MyAgentWatch 安装脚本
echo ============================================
echo.

cd /d "%~dp0"

:: Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.12+
    pause
    exit /b 1
)

:: Show Python version
for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo Python: %%i
echo.

:: Create venv if missing
if not exist ".venv\Scripts\python.exe" (
    echo [1/3] 创建虚拟环境 .venv ...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [错误] 创建虚拟环境失败
        pause
        exit /b 1
    )
) else (
    echo [1/3] 虚拟环境已存在，跳过
)

:: Install dependencies
echo [2/3] 安装依赖 ...
.venv\Scripts\pip.exe install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

:: Init data dir
if not exist "data" mkdir data

echo [3/3] 安装完成！
echo.
echo ============================================
echo   启动命令: install.bat run
echo   或者:   .venv\Scripts\python.exe app.py
echo   地址:   http://127.0.0.1:10000
echo ============================================
echo.

if "%1"=="run" (
    echo 启动 MyAgentWatch ...
    .venv\Scripts\python.exe app.py
)

pause
