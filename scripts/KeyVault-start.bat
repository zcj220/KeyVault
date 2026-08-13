@echo off
REM Thin wrapper: prefer PowerShell launcher (encoding-safe)
cd /d "%~dp0\.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0KeyVault-start.ps1"
exit /b %ERRORLEVEL%
