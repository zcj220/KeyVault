@echo off
REM KeyVault 双击启动器（Windows）
cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
  echo 还没安装依赖。请先运行: scripts\install-windows.ps1
  pause
  exit /b 1
)

if exist "keyvault.local.env" (
  for /f "usebackq tokens=1,* delims==" %%A in ("keyvault.local.env") do (
    if not "%%A"=="" if not "%%A:~0,1%"=="#" set "%%A=%%B"
  )
)

if "%KEYVAULT_UI_PORT%"=="" set KEYVAULT_UI_PORT=8799
set URL=http://127.0.0.1:%KEYVAULT_UI_PORT%

curl -sf "%URL%" >nul 2>&1
if errorlevel 1 (
  start "" /B ".venv\Scripts\python.exe" -m keyvault.webapp
  timeout /t 2 /nobreak >nul
)

start "" "%URL%"
