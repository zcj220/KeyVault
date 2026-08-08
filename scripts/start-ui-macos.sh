#!/usr/bin/env bash
# 启动 KeyVault 管理界面（macOS）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/python ]]; then
  echo "未安装，请先运行: ./scripts/install-macos.sh"
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
echo "库路径: ${KEYVAULT_PATH:-未设置}"
echo "打开界面: $URL"
open "$URL" 2>/dev/null || true
exec .venv/bin/python -m keyvault.webapp
