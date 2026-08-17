from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass


DEVELOPMENT_SECRET = "local-mvp-secret-change-before-production"
DEVELOPMENT_ADMIN_KEY = "mvp-admin-demo"
DEVELOPMENT_SITE_OTP = "135790"
PLACEHOLDER_PREFIX = "replace-with-"


class ConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    environment: str
    secret: str
    admin_key: str
    silicon_mode: str
    site_sms_mode: str
    development_site_otp: str | None
    seed_demo: bool

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


def _parse_bool(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} must be a boolean value")


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    values = os.environ if environ is None else environ
    environment = values.get("MVP_ENV", "development").strip().lower()
    if environment not in {"development", "production"}:
        raise ConfigurationError("MVP_ENV must be development or production")

    is_development = environment == "development"
    silicon_mode = values.get(
        "MVP_SILICON_MODE", "mock" if is_development else "live-disabled"
    ).strip().lower()
    if silicon_mode not in {"mock", "manual", "live-disabled"}:
        raise ConfigurationError("MVP_SILICON_MODE is invalid")

    site_sms_mode = values.get(
        "MVP_SITE_SMS_MODE", "mock" if is_development else "disabled"
    ).strip().lower()
    if site_sms_mode not in {"mock", "disabled"}:
        raise ConfigurationError("MVP_SITE_SMS_MODE must be mock or disabled")

    secret = values.get("MVP_SECRET", DEVELOPMENT_SECRET if is_development else "")
    admin_key = values.get(
        "MVP_ADMIN_KEY", DEVELOPMENT_ADMIN_KEY if is_development else ""
    )
    seed_demo = _parse_bool(
        values.get("MVP_SEED_DEMO", "1" if is_development else "0"),
        "MVP_SEED_DEMO",
    )

    development_site_otp: str | None = None
    if site_sms_mode == "mock":
        development_site_otp = values.get("MVP_DEV_SITE_OTP", DEVELOPMENT_SITE_OTP)
        if not re.fullmatch(r"\d{6}", development_site_otp):
            raise ConfigurationError("MVP_DEV_SITE_OTP must contain exactly 6 digits")

    if not is_development:
        if (
            not secret.strip()
            or secret == DEVELOPMENT_SECRET
            or secret.startswith(PLACEHOLDER_PREFIX)
            or len(secret.encode("utf-8")) < 32
        ):
            raise ConfigurationError("production MVP_SECRET must contain at least 32 bytes")
        if (
            not admin_key.strip()
            or admin_key == DEVELOPMENT_ADMIN_KEY
            or admin_key.startswith(PLACEHOLDER_PREFIX)
            or len(admin_key) < 16
        ):
            raise ConfigurationError(
                "production MVP_ADMIN_KEY must contain at least 16 characters"
            )
        if silicon_mode == "mock":
            raise ConfigurationError("production cannot use the mock SiliconFlow adapter")
        if site_sms_mode == "mock":
            raise ConfigurationError("production cannot use the mock site SMS provider")
        if seed_demo:
            raise ConfigurationError("production cannot seed demo data")

    return Settings(
        environment=environment,
        secret=secret,
        admin_key=admin_key,
        silicon_mode=silicon_mode,
        site_sms_mode=site_sms_mode,
        development_site_otp=development_site_otp,
        seed_demo=seed_demo,
    )


SETTINGS = load_settings()
