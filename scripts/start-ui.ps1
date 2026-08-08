# 启动 KeyVault 本地管理界面（仅本机 127.0.0.1）
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
  Write-Host "未找到虚拟环境，正在创建..."
  python -m venv .venv
  .\.venv\Scripts\pip.exe install -r requirements.txt
  .\.venv\Scripts\pip.exe install -e .
}

# 加载本地配置（若存在）
$envFile = ".\keyvault.local.env"
if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
      $parts = $line.Split("=", 2)
      [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim())
    }
  }
}

if (-not $env:KEYVAULT_PATH) {
  $env:KEYVAULT_PATH = Join-Path $env:USERPROFILE "OneDrive\KeyVault\vault.kvault"
}

$port = if ($env:KEYVAULT_UI_PORT) { $env:KEYVAULT_UI_PORT } else { "8799" }
$url = "http://127.0.0.1:$port"

Write-Host "库路径: $env:KEYVAULT_PATH"
Write-Host "打开界面: $url"
Start-Process $url
& .\.venv\Scripts\python.exe -m keyvault.webapp
