from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import SETTINGS


def _secret() -> bytes:
    return SETTINGS.secret.encode("utf-8")


def _key(purpose: str) -> bytes:
    return hashlib.sha256(_secret() + b":" + purpose.encode("ascii")).digest()


def hmac_hex(value: str, purpose: str) -> str:
    return hmac.new(_key(purpose), value.encode("utf-8"), hashlib.sha256).hexdigest()


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def random_token(size: int = 32) -> str:
    return secrets.token_urlsafe(size)


def encrypt_text(value: str, aad: str) -> str:
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(_key("field-encryption")).encrypt(
        nonce, value.encode("utf-8"), aad.encode("utf-8")
    )
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_text(value: str, aad: str) -> str:
    raw = base64.urlsafe_b64decode(value.encode("ascii"))
    plaintext = AESGCM(_key("field-encryption")).decrypt(
        raw[:12], raw[12:], aad.encode("utf-8")
    )
    return plaintext.decode("utf-8")


def sign_session(user_id: str, ttl_seconds: int = 7 * 24 * 3600) -> str:
    payload = {
        "sub": user_id,
        "exp": int(time.time()) + ttl_seconds,
        "nonce": secrets.token_hex(8),
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    signature = hmac.new(_key("site-session"), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def verify_session(value: str | None) -> dict[str, Any] | None:
    if not value or "." not in value:
        return None
    encoded, supplied = value.rsplit(".", 1)
    expected = hmac.new(_key("site-session"), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(supplied, expected):
        return None
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        if int(payload["exp"]) <= int(time.time()):
            return None
        return payload
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def mask_phone(phone: str) -> str:
    return f"{phone[:3]}****{phone[-4:]}"


def mask_alipay(account: str) -> str:
    if "@" in account:
        left, right = account.split("@", 1)
        return f"{left[:2]}***@{right}"
    if len(account) <= 5:
        return "***"
    return f"{account[:3]}***{account[-3:]}"
