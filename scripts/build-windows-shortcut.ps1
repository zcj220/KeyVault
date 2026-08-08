# 在桌面创建带自定义图标的 KeyVault 快捷方式（Windows）
# 用法（在项目根目录 PowerShell）:
#   powershell -ExecutionPolicy Bypass -File .\scripts\build-windows-shortcut.ps1
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Ico = Join-Path $Root "assets\AppIcon.ico"
$Vbs = Join-Path $Root "scripts\KeyVault启动.vbs"
$Bat = Join-Path $Root "scripts\KeyVault启动.bat"
$Desktop = [Environment]::GetFolderPath("Desktop")
$LnkPath = Join-Path $Desktop "KeyVault.lnk"

if (-not (Test-Path $Ico)) { throw "缺少图标: $Ico" }
if (-not (Test-Path $Vbs)) { throw "缺少启动脚本: $Vbs" }

$W = New-Object -ComObject WScript.Shell
$Lnk = $W.CreateShortcut($LnkPath)
$Lnk.TargetPath = $Vbs
$Lnk.WorkingDirectory = $Root.Path
$Lnk.WindowStyle = 7
$Lnk.Description = "打开 KeyVault 本机网页（与 Cursor MCP 可同时用）"
$Lnk.IconLocation = "$Ico,0"
$Lnk.Save()

Write-Host "已创建桌面快捷方式: $LnkPath"
Write-Host "图标: $Ico"
Write-Host "也可直接双击: $Bat"
