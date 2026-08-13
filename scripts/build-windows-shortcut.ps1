# Create desktop shortcut for KeyVault (Windows)
# Usage from repo root:
#   powershell -ExecutionPolicy Bypass -File .\scripts\build-windows-shortcut.ps1
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Ico = Join-Path $Root "assets\AppIcon.ico"
$Vbs = Join-Path $Root "scripts\KeyVault-start.vbs"
$Bat = Join-Path $Root "scripts\KeyVault-start.bat"
$Desktop = [Environment]::GetFolderPath("Desktop")
$LnkPath = Join-Path $Desktop "KeyVault.lnk"

if (-not (Test-Path $Ico)) { throw "Missing icon: $Ico" }
if (-not (Test-Path $Vbs)) { throw "Missing launcher: $Vbs" }

$W = New-Object -ComObject WScript.Shell
$Lnk = $W.CreateShortcut($LnkPath)
$Lnk.TargetPath = "$Vbs"
$Lnk.WorkingDirectory = "$($Root.Path)"
$Lnk.WindowStyle = 7
$Lnk.Description = "Open KeyVault local web UI (works alongside Cursor MCP)"
$Lnk.IconLocation = ($Ico + ",0")
$Lnk.Save()

Write-Host "Desktop shortcut created: $LnkPath"
Write-Host "Icon: $Ico"
Write-Host "You can also double-click: $Bat"
