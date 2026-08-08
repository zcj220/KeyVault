from __future__ import annotations

import os
from pathlib import Path


DEFAULT_VAULT_DIR = Path.home() / ".keyvault"
DEFAULT_VAULT_PATH = DEFAULT_VAULT_DIR / "vault.kvault"
ENV_VAULT_PATH = "KEYVAULT_PATH"
ENV_MASTER_PASSWORD = "KEYVAULT_PASSWORD"


def get_vault_path() -> Path:
    raw = os.environ.get(ENV_VAULT_PATH, "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return DEFAULT_VAULT_PATH


def get_master_password() -> str | None:
    value = os.environ.get(ENV_MASTER_PASSWORD)
    if value is None:
        return None
    value = value.strip()
    return value or None
