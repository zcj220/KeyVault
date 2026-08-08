#!/bin/bash
# KeyVault 双击启动器（macOS）— 无自定义图标时可用；推荐用项目根目录 KeyVault.app
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "$ROOT/scripts/launch-ui.sh"
