#!/usr/bin/env bash
# KeyVault 一键安装（macOS）
# 用法：
#   cd KeyVault
#   chmod +x scripts/install-macos.sh scripts/start-ui-macos.sh
#   ./scripts/install-macos.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> KeyVault 安装（macOS）"
echo "目录: $ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 python3。请先安装："
  echo "  brew install python@3.12"
  echo "或从 https://www.python.org/downloads/ 安装"
  exit 1
fi

echo "==> 创建虚拟环境 .venv"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi

echo "==> 安装依赖"
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .

# 常见 OneDrive for Mac 路径
DEFAULT_VAULT=""
for cand in \
  "$HOME/OneDrive/KeyVault/vault.kvault" \
  "$HOME/Library/CloudStorage/OneDrive-Personal/KeyVault/vault.kvault" \
  "$HOME/Library/CloudStorage/OneDrive-商业*/KeyVault/vault.kvault"
do
  # 允许通配
  for p in $cand; do
    if [[ -e "$(dirname "$p")" || -f "$p" ]]; then
      DEFAULT_VAULT="$p"
      break 2
    fi
  done
done
if [[ -z "$DEFAULT_VAULT" ]]; then
  DEFAULT_VAULT="$HOME/OneDrive/KeyVault/vault.kvault"
fi

ENV_FILE="$ROOT/keyvault.local.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo ""
  echo "请设置主密码（与第一台电脑相同）："
  read -r -s -p "主密码: " PASSWORD
  echo ""
  if [[ -z "$PASSWORD" ]]; then
    echo "主密码不能为空"
    exit 1
  fi
  echo "库文件路径默认: $DEFAULT_VAULT"
  read -r -p "直接回车用默认，或粘贴新路径: " CUSTOM
  VAULT_PATH="${CUSTOM:-$DEFAULT_VAULT}"
  mkdir -p "$(dirname "$VAULT_PATH")"
  cat > "$ENV_FILE" <<EOF
KEYVAULT_PATH=$VAULT_PATH
KEYVAULT_PASSWORD=$PASSWORD
KEYVAULT_UI_PORT=8799
EOF
  echo "已写入 keyvault.local.env（勿上传 GitHub）"
else
  echo "已存在 keyvault.local.env，跳过创建"
fi

echo ""
echo "==> 安装完成"
echo "1) Mac 安装 OneDrive，登录与 Windows 同一微软账号，等 KeyVault/vault.kvault 同步下来"
echo "2) 启动界面: ./scripts/start-ui-macos.sh"
echo "3) 浏览器打开后点「接入 Cursor AI」"
echo "4) Cursor → Settings → MCP 重载，看到 keyvault 绿灯即可"
