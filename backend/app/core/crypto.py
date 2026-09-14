"""Server-side credential encryption. Ciphertext never leaves the API process."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.settings import get_settings


class EncryptionUnavailable(Exception):
    """No key material is configured to wrap integration credentials."""


def _fernet_from_material(material: str) -> Fernet:
    raw = material.strip()
    if not raw:
        raise EncryptionUnavailable("Credential encryption is not configured yet.")
    try:
        return Fernet(raw.encode("utf-8"))
    except (ValueError, TypeError):
        digest = hashlib.sha256(raw.encode("utf-8")).digest()
        return Fernet(base64.urlsafe_b64encode(digest))


def credential_key_material() -> str:
    settings = get_settings()
    if settings.credential_encryption_key:
        return settings.credential_encryption_key
    fallback = "|".join(
        part
        for part in (
            settings.gmail_client_secret,
            settings.telegram_bot_token,
            settings.clerk_secret_key,
        )
        if part
    )
    if not fallback:
        raise EncryptionUnavailable("Credential encryption is not configured yet.")
    return fallback


def get_fernet() -> Fernet:
    return _fernet_from_material(credential_key_material())


def encrypt_secret(plaintext: str) -> str:
    return get_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str:
    if not token:
        raise InvalidToken("empty")
    return get_fernet().decrypt(token.encode("ascii")).decode("utf-8")


def encrypt_json(payload: dict[str, Any]) -> str:
    return encrypt_secret(json.dumps(payload, separators=(",", ":"), sort_keys=True))


def decrypt_json(token: str) -> dict[str, Any]:
    data = json.loads(decrypt_secret(token))
    return data if isinstance(data, dict) else {}
