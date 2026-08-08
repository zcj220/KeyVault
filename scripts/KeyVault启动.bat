@echo off
REM KeyVault 双击启动器（Windows）
REM MCP（Cursor）与网页界面是两套进程：可同时开，不会抢端口。
REM 若网页已在跑，只会再打开浏览器，不会重复起服务。
cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
  echo 还没安装依赖。请先运行: scripts\install-windows.ps1
  pause
  exit /b 1
)

REM 加载 keyvault.local.env（去掉引号）
if exist "keyvault.local.env" (
  for /f "usebackq eol=# tokens=1,* delims==" %%A in ("keyvault.local.env") do (
    if not "%%A"=="" (
      set "_k=%%A"
      set "_v=%%B"
      call :setenv
    )
  )
)

if "%KEYVAULT_UI_PORT%"=="" set "KEYVAULT_UI_PORT=8799"
set "URL=http://127.0.0.1:%KEYVAULT_UI_PORT%"

curl -sf "%URL%" >nul 2>&1
if errorlevel 1 (
  if not exist "backups" mkdir "backups"
  start "KeyVault-UI" /MIN ".venv\Scripts\python.exe" -m keyvault.webapp
  set /a _i=0
  :waitloop
  timeout /t 1 /nobreak >nul
  curl -sf "%URL%" >nul 2>&1
  if not errorlevel 1 goto openbrowser
  set /a _i+=1
  if %_i% LSS 10 goto waitloop
)

:openbrowser
start "" "%URL%"
exit /b 0

:setenv
REM trim and strip quotes from value
set "_v=%_v:"=%"
set "%_k%=%_v%"
set "_k="
set "_v="
exit /b 0
