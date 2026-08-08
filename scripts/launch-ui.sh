#!/bin/bash
# KeyVault 启动核心逻辑（供 .command / .app 共用）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/python ]]; then
  osascript -e 'display dialog "还没安装依赖。请先在终端运行：\n\ncd '"$ROOT"'\n./scripts/install-macos.sh" buttons {"好"} default button 1 with title "KeyVault"'
  exit 1
fi

if [[ -f keyvault.local.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source keyvault.local.env
  set +a
fi

PORT="${KEYVAULT_UI_PORT:-8799}"
URL="http://127.0.0.1:${PORT}"
LOG="$ROOT/backups/ui.log"
mkdir -p "$ROOT/backups"

already_up=0
if curl -sf "$URL" >/dev/null 2>&1; then
  already_up=1
elif lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  already_up=1
fi

if [[ "$already_up" -eq 0 ]]; then
  nohup .venv/bin/python -m keyvault.webapp >>"$LOG" 2>&1 &
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if curl -sf "$URL" >/dev/null 2>&1; then
      break
    fi
    sleep 0.3
  done
fi

open "$URL"
