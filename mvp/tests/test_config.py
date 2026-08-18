from __future__ import annotations

import pytest

from mvp_app.config import (
    DEVELOPMENT_ADMIN_KEY,
    DEVELOPMENT_SECRET,
    ConfigurationError,
    load_settings,
)


def production_environment(**overrides: str) -> dict[str, str]:
    values = {
        "MVP_ENV": "production",
        "MVP_SECRET": "production-secret-material-is-at-least-32-bytes",
        "MVP_ADMIN_KEY": "production-admin-key",
        "MVP_ALLOWED_HOSTS": "tasks.example.com,127.0.0.1,localhost",
        "MVP_SILICON_MODE": "live-disabled",
        "MVP_SITE_SMS_MODE": "disabled",
        "MVP_SEED_DEMO": "0",
    }
    values.update(overrides)
    return values


def test_development_defaults_are_explicit() -> None:
    settings = load_settings({})

    assert settings.is_development is True
    assert settings.secret == DEVELOPMENT_SECRET
    assert settings.admin_key == DEVELOPMENT_ADMIN_KEY
    assert settings.allowed_hosts == ("localhost", "127.0.0.1", "testserver")
    assert settings.cookie_secure is False
    assert settings.silicon_mode == "mock"
    assert settings.site_sms_mode == "mock"
    assert settings.remote_browser_mode == "disabled"
    assert settings.development_site_otp == "135790"
    assert settings.aliyun_access_key_id is None
    assert settings.aliyun_access_key_secret is None
    assert settings.site_sms_allowed_phones == ()
    assert settings.site_sms_max_sends_per_hour == 20
    assert settings.site_sms_max_sends_per_day == 50
    assert settings.seed_demo is True


def test_production_accepts_only_explicit_non_demo_configuration() -> None:
    settings = load_settings(production_environment())

    assert settings.is_development is False
    assert settings.allowed_hosts == ("tasks.example.com", "127.0.0.1", "localhost")
    assert settings.cookie_secure is True
    assert settings.silicon_mode == "live-disabled"
    assert settings.site_sms_mode == "disabled"
    assert settings.development_site_otp is None
    assert settings.seed_demo is False


def test_aliyun_sms_requires_complete_controlled_acceptance_configuration() -> None:
    settings = load_settings(
        production_environment(
            MVP_SITE_SMS_MODE="aliyun-dypns",
            ALIBABA_CLOUD_ACCESS_KEY_ID="test-access-key-id",
            ALIBABA_CLOUD_ACCESS_KEY_SECRET="test-access-key-secret",
            MVP_SITE_SMS_SIGN_NAME="系统赠送签名",
            MVP_SITE_SMS_TEMPLATE_CODE="100001",
            MVP_SITE_SMS_SCHEME_NAME="mvp-login",
            MVP_SITE_SMS_ALLOWED_PHONES="+86 13900000001,13800000001",
        )
    )

    assert settings.site_sms_mode == "aliyun-dypns"
    assert settings.site_sms_template_code == "100001"
    assert settings.site_sms_allowed_phones == ("13900000001", "13800000001")
    assert "test-access-key-secret" not in repr(settings)


@pytest.mark.parametrize(
    ("overrides", "expected_message"),
    [
        ({"MVP_SECRET": ""}, "MVP_SECRET"),
        ({"MVP_SECRET": "short"}, "MVP_SECRET"),
        ({"MVP_SECRET": DEVELOPMENT_SECRET}, "MVP_SECRET"),
        ({"MVP_SECRET": "replace-with-at-least-32-random-bytes"}, "MVP_SECRET"),
        ({"MVP_ADMIN_KEY": ""}, "MVP_ADMIN_KEY"),
        ({"MVP_ADMIN_KEY": "short"}, "MVP_ADMIN_KEY"),
        ({"MVP_ADMIN_KEY": DEVELOPMENT_ADMIN_KEY}, "MVP_ADMIN_KEY"),
        (
            {"MVP_ADMIN_KEY": "replace-with-at-least-16-random-characters"},
            "MVP_ADMIN_KEY",
        ),
        ({"MVP_SILICON_MODE": "mock"}, "mock SiliconFlow"),
        ({"MVP_ALLOWED_HOSTS": ""}, "MVP_ALLOWED_HOSTS"),
        ({"MVP_ALLOWED_HOSTS": "*"}, "MVP_ALLOWED_HOSTS"),
        ({"MVP_COOKIE_SECURE": "0"}, "secure cookies"),
        ({"MVP_SITE_SMS_MODE": "mock"}, "mock site SMS"),
        ({"MVP_SEED_DEMO": "1"}, "seed demo"),
    ],
)
def test_production_rejects_unsafe_configuration(
    overrides: dict[str, str], expected_message: str
) -> None:
    with pytest.raises(ConfigurationError, match=expected_message):
        load_settings(production_environment(**overrides))


@pytest.mark.parametrize(
    ("values", "expected_message"),
    [
        ({"MVP_ENV": "staging"}, "MVP_ENV"),
        ({"MVP_SILICON_MODE": "live"}, "MVP_SILICON_MODE"),
        ({"MVP_SITE_SMS_MODE": "console"}, "MVP_SITE_SMS_MODE"),
        ({"MVP_REMOTE_BROWSER_MODE": "external"}, "MVP_REMOTE_BROWSER_MODE"),
        ({"MVP_ALLOWED_HOSTS": "https://example.com"}, "MVP_ALLOWED_HOSTS"),
        ({"MVP_ALLOWED_HOSTS": "bad..example.com"}, "MVP_ALLOWED_HOSTS"),
        ({"MVP_COOKIE_SECURE": "sometimes"}, "MVP_COOKIE_SECURE"),
        ({"MVP_SEED_DEMO": "sometimes"}, "MVP_SEED_DEMO"),
        ({"MVP_DEV_SITE_OTP": "12345"}, "MVP_DEV_SITE_OTP"),
        ({"MVP_SITE_SMS_MAX_SENDS_PER_HOUR": "0"}, "MVP_SITE_SMS_MAX_SENDS_PER_HOUR"),
        ({"MVP_SITE_SMS_MAX_SENDS_PER_DAY": "not-a-number"}, "MVP_SITE_SMS_MAX_SENDS_PER_DAY"),
        (
            {
                "MVP_SITE_SMS_MAX_SENDS_PER_HOUR": "20",
                "MVP_SITE_SMS_MAX_SENDS_PER_DAY": "10",
            },
            "cannot be lower",
        ),
        ({"MVP_SITE_SMS_ALLOWED_PHONES": "123"}, "MVP_SITE_SMS_ALLOWED_PHONES"),
    ],
)
def test_invalid_values_are_rejected(values: dict[str, str], expected_message: str) -> None:
    with pytest.raises(ConfigurationError, match=expected_message):
        load_settings(values)


@pytest.mark.parametrize(
    "missing_name",
    [
        "ALIBABA_CLOUD_ACCESS_KEY_ID",
        "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
        "MVP_SITE_SMS_SIGN_NAME",
        "MVP_SITE_SMS_TEMPLATE_CODE",
        "MVP_SITE_SMS_SCHEME_NAME",
        "MVP_SITE_SMS_ALLOWED_PHONES",
    ],
)
def test_aliyun_sms_rejects_missing_required_settings(missing_name: str) -> None:
    values = production_environment(
        MVP_SITE_SMS_MODE="aliyun-dypns",
        ALIBABA_CLOUD_ACCESS_KEY_ID="test-access-key-id",
        ALIBABA_CLOUD_ACCESS_KEY_SECRET="test-access-key-secret",
        MVP_SITE_SMS_SIGN_NAME="系统赠送签名",
        MVP_SITE_SMS_TEMPLATE_CODE="100001",
        MVP_SITE_SMS_SCHEME_NAME="mvp-login",
        MVP_SITE_SMS_ALLOWED_PHONES="13900000001",
    )
    values.pop(missing_name)

    with pytest.raises(ConfigurationError):
        load_settings(values)
