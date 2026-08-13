# KeyVault local web UI launcher (Windows)
# Cursor MCP is separate (stdio). This only manages http://127.0.0.1:PORT
# If UI already up: open browser only. Else: start webapp, wait until ready, then open browser.
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

function Show-KvMessage([string]$text, [string]$icon = "Warning") {
  Add-Type -AssemblyName System.Windows.Forms
  [System.Windows.Forms.MessageBox]::Show($text, "KeyVault", "OK", $icon) | Out-Null
}

$python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  Show-KvMessage "Missing .venv. Run scripts\install-windows.ps1 first." "Error"
  exit 1
}

function Import-LocalEnv([string]$envFile) {
  if (-not (Test-Path $envFile)) { return }
  Get-Content $envFile -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim().TrimStart([char]0xFEFF)
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
      $parts = $line.Split("=", 2)
      $name = $parts[0].Trim().TrimStart([char]0xFEFF)
      $value = $parts[1].Trim().Trim('"').Trim("'")
      if ($name) {
        [System.Environment]::SetEnvironmentVariable($name, $value, "Process")
      }
    }
  }
}

Import-LocalEnv (Join-Path $Root "keyvault.local.env")

if (-not $env:KEYVAULT_PATH) {
  $env:KEYVAULT_PATH = Join-Path $env:USERPROFILE "OneDrive\KeyVault\vault.kvault"
}
$port = if ($env:KEYVAULT_UI_PORT) { $env:KEYVAULT_UI_PORT } else { "8799" }
$url = "http://127.0.0.1:$port"

function Test-UiUp {
  try {
    $req = [System.Net.HttpWebRequest]::Create($url)
    $req.Method = "GET"
    $req.Timeout = 1500
    $req.Proxy = $null
    $resp = $req.GetResponse()
    $resp.Close()
    return $true
  } catch {
    return $false
  }
}

function Get-WebappProcesses {
  Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and ($_.CommandLine -match 'keyvault\.webapp') }
}

# Already healthy: only open browser
if (Test-UiUp) {
  Start-Process $url
  exit 0
}

$backups = Join-Path $Root "backups"
if (-not (Test-Path $backups)) {
  New-Item -ItemType Directory -Path $backups | Out-Null
}

# Stale listener / crashed leftover: stop old webapp processes before relaunch
Get-WebappProcesses | ForEach-Object {
  try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch {}
}
Start-Sleep -Milliseconds 400

$outLog = Join-Path $backups "webui-stdout.log"
$errLog = Join-Path $backups "webui-stderr.log"
foreach ($f in @($outLog, $errLog)) {
  if (Test-Path $f) { Remove-Item $f -Force -ErrorAction SilentlyContinue }
}

$proc = Start-Process -FilePath $python `
  -ArgumentList "-m", "keyvault.webapp" `
  -WorkingDirectory "$Root" `
  -WindowStyle Hidden `
  -RedirectStandardOutput $outLog `
  -RedirectStandardError $errLog `
  -PassThru

$ready = $false
$deadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $deadline) {
  Start-Sleep -Milliseconds 500
  if (Test-UiUp) { $ready = $true; break }
  # On Windows, venv may keep a child alive after the parent stub exits.
  if ($proc.HasExited) {
    Start-Sleep -Milliseconds 800
    if (Test-UiUp) { $ready = $true }
    break
  }
}

if ($ready) {
  Start-Process $url
  exit 0
}

$tail = ""
if (Test-Path $errLog) {
  $tail = ((Get-Content $errLog -Tail 20 -ErrorAction SilentlyContinue) -join "`n")
}
if (-not $tail -and (Test-Path $outLog)) {
  $tail = ((Get-Content $outLog -Tail 20 -ErrorAction SilentlyContinue) -join "`n")
}

$reason = if ($proc.HasExited -and -not (Test-UiUp)) {
  "Web UI process exited early (code $($proc.ExitCode))."
} else {
  "Timed out: $url not ready within 30s."
}

$detail = if ($tail) { "`n`n--- log ---`n$tail" } else { "`n`n(No log yet. Check keyvault.local.env and .venv.)" }
Show-KvMessage "$reason`nSee:`n$errLog$detail" "Warning"
exit 2