#!/usr/bin/env python3
"""Local cryptographic and lifecycle validation using synthetic secrets only."""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


MAX_TTL = timedelta(hours=24)


@dataclass(frozen=True)
class Context:
    provider: str
    user_id: str
    order_id: str
    record_id: str
    expires_at: datetime
    key_version: str = "test-v1"

    def aad(self) -> bytes:
        normalized = {
            "expires_at": self.expires_at.astimezone(timezone.utc).isoformat(),
            "key_version": self.key_version,
            "order_id": self.order_id,
            "provider": self.provider,
            "record_id": self.record_id,
            "user_id": self.user_id,
        }
        return json.dumps(normalized, separators=(",", ":"), sort_keys=True).encode()


class SyntheticSessionVault:
    def __init__(self, key: bytes) -> None:
        self._cipher = AESGCM(key)
        self._revoked: set[str] = set()

    def encrypt(self, plaintext: bytes, context: Context, created_at: datetime) -> dict[str, str]:
        if context.expires_at <= created_at:
            raise ValueError("expiry must be in the future")
        if context.expires_at - created_at > MAX_TTL:
            raise ValueError("TTL exceeds 24 hours")
        nonce = os.urandom(12)
        ciphertext = self._cipher.encrypt(nonce, plaintext, context.aad())
        return {
            "ciphertext": base64.b64encode(ciphertext).decode(),
            "nonce": base64.b64encode(nonce).decode(),
            "key_version": context.key_version,
        }

    def decrypt(self, envelope: dict[str, str], context: Context, now: datetime) -> bytes:
        if context.record_id in self._revoked:
            raise PermissionError("session revoked")
        if now >= context.expires_at:
            raise PermissionError("session expired")
        return self._cipher.decrypt(
            base64.b64decode(envelope["nonce"]),
            base64.b64decode(envelope["ciphertext"]),
            context.aad(),
        )

    def revoke(self, record_id: str) -> None:
        self._revoked.add(record_id)


def expect_failure(name: str, exception_types: tuple[type[BaseException], ...], action) -> dict[str, object]:
    try:
        action()
    except exception_types:
        return {"scenario": name, "passed": True}
    raise AssertionError(f"{name}: expected failure")


def main() -> None:
    now = datetime(2026, 8, 14, tzinfo=timezone.utc)
    context = Context("siliconflow", "user-a", "order-a", "record-a", now + timedelta(hours=24))
    vault = SyntheticSessionVault(AESGCM.generate_key(bit_length=256))
    synthetic_token = b"synthetic-session-token-not-a-real-secret"
    envelope = vault.encrypt(synthetic_token, context, now)

    results: list[dict[str, object]] = []
    serialized = json.dumps(envelope, sort_keys=True).encode()
    results.append(
        {
            "scenario": "plaintext-not-present-in-envelope",
            "passed": synthetic_token not in serialized,
        }
    )
    results.append(
        {
            "scenario": "valid-context-round-trip",
            "passed": vault.decrypt(envelope, context, now + timedelta(minutes=1)) == synthetic_token,
        }
    )

    wrong_order = Context("siliconflow", "user-a", "order-b", "record-a", context.expires_at)
    results.append(
        expect_failure(
            "cross-order-envelope-rejected",
            (InvalidTag,),
            lambda: vault.decrypt(envelope, wrong_order, now + timedelta(minutes=1)),
        )
    )

    wrong_user = Context("siliconflow", "user-b", "order-a", "record-a", context.expires_at)
    results.append(
        expect_failure(
            "cross-user-envelope-rejected",
            (InvalidTag,),
            lambda: vault.decrypt(envelope, wrong_user, now + timedelta(minutes=1)),
        )
    )

    tampered = dict(envelope)
    tampered_bytes = bytearray(base64.b64decode(tampered["ciphertext"]))
    tampered_bytes[0] ^= 1
    tampered["ciphertext"] = base64.b64encode(tampered_bytes).decode()
    results.append(
        expect_failure(
            "tampered-ciphertext-rejected",
            (InvalidTag,),
            lambda: vault.decrypt(tampered, context, now + timedelta(minutes=1)),
        )
    )

    results.append(
        expect_failure(
            "expired-session-rejected",
            (PermissionError,),
            lambda: vault.decrypt(envelope, context, context.expires_at),
        )
    )

    too_long = Context("siliconflow", "user-a", "order-a", "record-long", now + timedelta(hours=24, seconds=1))
    results.append(
        expect_failure(
            "ttl-over-24-hours-rejected",
            (ValueError,),
            lambda: vault.encrypt(synthetic_token, too_long, now),
        )
    )

    vault.revoke(context.record_id)
    results.append(
        expect_failure(
            "revoked-session-rejected",
            (PermissionError,),
            lambda: vault.decrypt(envelope, context, now + timedelta(minutes=2)),
        )
    )

    if not all(bool(result["passed"]) for result in results):
        raise AssertionError("one or more session-security scenarios failed")

    output_directory = Path(__file__).resolve().parent / "evidence"
    output_directory.mkdir(parents=True, exist_ok=True)
    output_path = output_directory / "session-security-tests.json"
    output_path.write_text(
        json.dumps(
            {
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "usesSyntheticSecretsOnly": True,
                "passed": True,
                "scenarios": results,
            },
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"All {len(results)} session-security scenarios passed: {output_path}")


if __name__ == "__main__":
    main()

