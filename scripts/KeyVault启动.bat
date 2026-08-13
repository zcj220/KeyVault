@echo off
REM Thin wrapper: prefer PowerShell launcher (encoding-safe)
REM 旧版 KeyVault启动.bat 也走同一套逻辑，避免双击旧文件又用弱启动流程
cd /d "%~dp0\.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0KeyVault-start.ps1"
exit /b %ERRORLEVEL%
