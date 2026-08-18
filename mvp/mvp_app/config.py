from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field


DEVELOPMENT_SECRET = "local-mvp-secret-change-before-production"
DEVELOPMENT_ADMIN_KEY = "mvp-admin-demo"
DEVELOPMENT_SITE_OTP = "135790"
PLACEHOLDER_PREFIX = "replace-with-"
HOST_PATTERN = re.compile(
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*"
)


class ConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    environment: str
    secret: str
    admin_key: str
    allowed_hosts: tuple[str, ...]
    cookie_secure: bool
    silicon_mode: str
    site_sms_mode: str
    remote_browser_mode: str
    development_site_otp: str | None
    aliyun_access_key_id: str | None = field(repr=False)
    aliyun_access_key_secret: str | None = field(repr=False)
    site_sms_sign_name: str | None
    site_sms_template_code: str | None
    site_sms_scheme_name: str | None
    site_sms_allowed_phones: tuple[str, ...] = field(repr=False)
    site_sms_max_sends_per_hour: int
    site_sms_max_sends_per_day: int
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


def _parse_bounded_int(value: str, name: str, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if not minimum <= parsed <= maximum:
        raise ConfigurationError(f"{name} must be between {minimum} and {maximum}")
    return parsed


def _optional(values: Mapping[str, str], name: str) -> str | None:
    value = values.get(name, "").strip()
    return value or None


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    values = os.environ if environ is None else environ
    environment = values.get("MVP_ENV", "development").strip().lower()
    if environment not in {"development", "production"}:
        raise ConfigurationError("MVP_ENV must be development or production")

    is_development = environment == "development"
    default_hosts = "localhost,127.0.0.1,testserver" if is_development else ""
    allowed_hosts = tuple(
        dict.fromkeys(
            host.strip().lower()
            for host in values.get("MVP_ALLOWED_HOSTS", default_hosts).split(",")
            if host.strip()
        )
    )
    if not allowed_hosts:
        raise ConfigurationError("MVP_ALLOWED_HOSTS must contain at least one host")
    if any(
        host == "*"
        or "://" in host
        or "/" in host
        or ":" in host
        or len(host) > 253
        or not HOST_PATTERN.fullmatch(host)
        for host in allowed_hosts
    ):
        raise ConfigurationError("MVP_ALLOWED_HOSTS contains an invalid or unsafe host")
    cookie_secure = _parse_bool(
        values.get("MVP_COOKIE_SECURE", "0" if is_development else "1"),
        "MVP_COOKIE_SECURE",
    )
    silicon_mode = values.get(
        "MVP_SILICON_MODE", "mock" if is_development else "live-disabled"
    ).strip().lower()
    if silicon_mode not in {"mock", "manual", "live-disabled"}:
        raise ConfigurationError("MVP_SILICON_MODE is invalid")

    site_sms_mode = values.get(
        "MVP_SITE_SMS_MODE", "mock" if is_development else "disabled"
    ).strip().lower()
    if site_sms_mode not in {"mock", "aliyun-dypns", "disabled"}:
        raise ConfigurationError(
            "MVP_SITE_SMS_MODE must be mock, aliyun-dypns, or disabled"
        )

    remote_browser_mode = values.get("MVP_REMOTE_BROWSER_MODE", "disabled").strip().lower()
    if remote_browser_mode != "disabled":
        raise ConfigurationError(
            "MVP_REMOTE_BROWSER_MODE must remain disabled until a trusted gateway is configured"
        )

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

    aliyun_access_key_id = _optional(values, "ALIBABA_CLOUD_ACCESS_KEY_ID")
    aliyun_access_key_secret = _optional(values, "ALIBABA_CLOUD_ACCESS_KEY_SECRET")
    site_sms_sign_name = _optional(values, "MVP_SITE_SMS_SIGN_NAME")
    site_sms_template_code = _optional(values, "MVP_SITE_SMS_TEMPLATE_CODE")
    site_sms_scheme_name = _optional(values, "MVP_SITE_SMS_SCHEME_NAME")
    allowed_phone_values = tuple(
        dict.fromkeys(
            re.sub(r"[ +()-]", "", phone)
            for phone in values.get("MVP_SITE_SMS_ALLOWED_PHONES", "").split(",")
            if phone.strip()
        )
    )
    site_sms_allowed_phones = tuple(
        phone[2:] if phone.startswith("86") and len(phone) == 13 else phone
        for phone in allowed_phone_values
    )
    if any(not re.fullmatch(r"1[3-9]\d{9}", phone) for phone in site_sms_allowed_phones):
        raise ConfigurationError("MVP_SITE_SMS_ALLOWED_PHONES contains an invalid phone")
    if len(site_sms_allowed_phones) > 5:
        raise ConfigurationError("MVP_SITE_SMS_ALLOWED_PHONES supports at most 5 phones")
    site_sms_max_sends_per_hour = _parse_bounded_int(
        values.get("MVP_SITE_SMS_MAX_SENDS_PER_HOUR", "20"),
        "MVP_SITE_SMS_MAX_SENDS_PER_HOUR",
        1,
        1000,
    )
    site_sms_max_sends_per_day = _parse_bounded_int(
        values.get("MVP_SITE_SMS_MAX_SENDS_PER_DAY", "50"),
        "MVP_SITE_SMS_MAX_SENDS_PER_DAY",
        1,
        10000,
    )
    if site_sms_max_sends_per_day < site_sms_max_sends_per_hour:
        raise ConfigurationError(
            "MVP_SITE_SMS_MAX_SENDS_PER_DAY cannot be lower than the hourly limit"
        )
    if site_sms_mode == "aliyun-dypns":
        required_aliyun_values = {
            "ALIBABA_CLOUD_ACCESS_KEY_ID": aliyun_access_key_id,
            "ALIBABA_CLOUD_ACCESS_KEY_SECRET": aliyun_access_key_secret,
            "MVP_SITE_SMS_SIGN_NAME": site_sms_sign_name,
            "MVP_SITE_SMS_TEMPLATE_CODE": site_sms_template_code,
            "MVP_SITE_SMS_SCHEME_NAME": site_sms_scheme_name,
        }
        missing = [name for name, value in required_aliyun_values.items() if not value]
        if missing:
            raise ConfigurationError(
                f"aliyun-dypns requires {', '.join(missing)}"
            )
        if any(value.startswith(PLACEHOLDER_PREFIX) for value in required_aliyun_values.values()):
            raise ConfigurationError("aliyun-dypns settings cannot use placeholder values")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", site_sms_template_code or ""):
            raise ConfigurationError("MVP_SITE_SMS_TEMPLATE_CODE is invalid")
        if not 1 <= len(site_sms_scheme_name or "") <= 20:
            raise ConfigurationError("MVP_SITE_SMS_SCHEME_NAME must contain 1 to 20 characters")
        if not site_sms_allowed_phones:
            raise ConfigurationError(
                "aliyun-dypns requires MVP_SITE_SMS_ALLOWED_PHONES during controlled acceptance"
            )

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
        if not cookie_secure:
            raise ConfigurationError("production cannot disable secure cookies")

    return Settings(
        environment=environment,
        secret=secret,
        admin_key=admin_key,
        allowed_hosts=allowed_hosts,
        cookie_secure=cookie_secure,
        silicon_mode=silicon_mode,
        site_sms_mode=site_sms_mode,
        remote_browser_mode=remote_browser_mode,
        development_site_otp=development_site_otp,
        aliyun_access_key_id=aliyun_access_key_id,
        aliyun_access_key_secret=aliyun_access_key_secret,
        site_sms_sign_name=site_sms_sign_name,
        site_sms_template_code=site_sms_template_code,
        site_sms_scheme_name=site_sms_scheme_name,
        site_sms_allowed_phones=site_sms_allowed_phones,
        site_sms_max_sends_per_hour=site_sms_max_sends_per_hour,
        site_sms_max_sends_per_day=site_sms_max_sends_per_day,
        seed_demo=seed_demo,
    )


SETTINGS = load_settings()
