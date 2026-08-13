from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL_ENV = ROOT / "keyvault.local.env"
DEFAULT_VAULT = Path.home() / "OneDrive" / "KeyVault" / "vault.kvault"


def load_local_env() -> dict[str, str]:
    data: dict[str, str] = {}
    if not LOCAL_ENV.is_file():
        return data
    # utf-8-sig strips a leading BOM; also strip BOM from individual keys/lines
    for line in LOCAL_ENV.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip().lstrip("\ufeff").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lstrip("\ufeff")
        if not key:
            continue
        data[key] = value.strip().strip('"').strip("'")
    return data


def apply_local_env() -> None:
    for key, value in load_local_env().items():
        if key and value and key not in os.environ:
            os.environ[key] = value


def save_local_env(updates: dict[str, str]) -> None:
    current = load_local_env()
    current.update({k: v for k, v in updates.items() if v is not None})
    # Drop accidental BOM-prefixed duplicate keys
    current = {
        k.lstrip("\ufeff"): v
        for k, v in current.items()
        if k and k.lstrip("\ufeff")
    }
    lines = ["# KeyVault 本地配置（不要提交到 Git）"]
    for key in ("KEYVAULT_PATH", "KEYVAULT_PASSWORD", "KEYVAULT_UI_PORT"):
        if key in current and current[key]:
            lines.append(f"{key}={current[key]}")
    for key, value in current.items():
        if key in {"KEYVAULT_PATH", "KEYVAULT_PASSWORD", "KEYVAULT_UI_PORT"}:
            continue
        if value:
            lines.append(f"{key}={value}")
    LOCAL_ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")


def preferred_vault_path() -> Path:
    apply_local_env()
    raw = os.environ.get("KEYVAULT_PATH", "").strip()
    if raw:
        return Path(raw).expanduser()
    # 优先坚果云常见路径，其次 OneDrive
    candidates = [
        Path.home() / "坚果云" / "KeyVault" / "vault.kvault",
        Path.home() / "Nutstore" / "KeyVault" / "vault.kvault",
        Path.home() / "Nutstore Cloud" / "KeyVault" / "vault.kvault",
        DEFAULT_VAULT,
    ]
    for path in candidates:
        if path.parent.is_dir():
            return path
    return DEFAULT_VAULT
