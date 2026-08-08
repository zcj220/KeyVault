# KeyVault 一键安装（Windows）
# 用法（在项目根目录）：
#   powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "==> KeyVault 安装（Windows）" -ForegroundColor Cyan
Write-Host "目录: $Root"

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
  Write-Host "未找到 Python。请先安装 Python 3.10+：https://www.python.org/downloads/" -ForegroundColor Red
  Write-Host "安装时勾选 Add python.exe to PATH"
  exit 1
}

Write-Host "==> 创建虚拟环境 .venv"
if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
  python -m venv .venv
}

Write-Host "==> 安装依赖"
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\pip.exe install -r requirements.txt
& .\.venv\Scripts\pip.exe install -e .

$defaultVault = Join-Path $env:USERPROFILE "OneDrive\KeyVault\vault.kvault"
$envFile = Join-Path $Root "keyvault.local.env"
if (-not (Test-Path $envFile)) {
  Write-Host ""
  Write-Host "请设置主密码（与第一台电脑相同，用来打开加密库）：" -ForegroundColor Yellow
  $secure = Read-Host "主密码" -AsSecureString
  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
  $password = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
  if (-not $password) { throw "主密码不能为空" }

  Write-Host "库文件路径默认: $defaultVault"
  $custom = Read-Host "直接回车用默认，或粘贴新路径"
  $vaultPath = if ($custom) { $custom.Trim() } else { $defaultVault }

  @"
KEYVAULT_PATH=$vaultPath
KEYVAULT_PASSWORD=$password
KEYVAULT_UI_PORT=8799
"@ | Set-Content -Encoding utf8 $envFile

  $dir = Split-Path $vaultPath -Parent
  if (-not (Test-Path $dir)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
  }
  Write-Host "已写入 keyvault.local.env（勿上传 GitHub）"
} else {
  Write-Host "已存在 keyvault.local.env，跳过创建"
}

Write-Host ""
Write-Host "==> 安装完成" -ForegroundColor Green
Write-Host "1) 确认 OneDrive 已登录同一账号，并同步出 KeyVault\vault.kvault"
Write-Host "2) 启动界面:  .\scripts\start-ui.ps1"
Write-Host "3) 浏览器打开后点「接入 Cursor AI」"
Write-Host "4) Cursor → Settings → MCP 重载，看到 keyvault 绿灯即可"
Write-Host ""
Write-Host "手动启动界面命令:"
Write-Host "  .\scripts\start-ui.ps1"
