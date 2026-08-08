from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

KDF_ITERATIONS = 390_000
SALT_SIZE = 16
FILE_MAGIC = b"KVAULT1\n"


class VaultCryptoError(Exception):
    pass


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=KDF_ITERATIONS,
    )
    raw = kdf.derive(password.encode("utf-8"))
    return base64.urlsafe_b64encode(raw)


def encrypt_payload(password: str, payload: dict[str, Any]) -> bytes:
    salt = os.urandom(SALT_SIZE)
    key = _derive_key(password, salt)
    token = Fernet(key).encrypt(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    # 校验指纹：用于快速发现密码错误（仍依赖 Fernet 校验）
    check = hashlib.sha256(password.encode("utf-8") + salt).digest()[:8]
    return FILE_MAGIC + salt + check + token


def decrypt_payload(password: str, blob: bytes) -> dict[str, Any]:
    if not blob.startswith(FILE_MAGIC):
        raise VaultCryptoError("不是有效的密钥库文件（格式不对）")
    body = blob[len(FILE_MAGIC) :]
    if len(body) < SALT_SIZE + 8 + 16:
        raise VaultCryptoError("密钥库文件损坏或过短")
    salt = body[:SALT_SIZE]
    check = body[SALT_SIZE : SALT_SIZE + 8]
    token = body[SALT_SIZE + 8 :]
    expected = hashlib.sha256(password.encode("utf-8") + salt).digest()[:8]
    if not hmac.compare_digest(check, expected):
        raise VaultCryptoError("主密码错误")
    key = _derive_key(password, salt)
    try:
        raw = Fernet(key).decrypt(token)
    except InvalidToken as exc:
        raise VaultCryptoError("解密失败，主密码可能错误或文件已损坏") from exc
    return json.loads(raw.decode("utf-8"))
