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
    assert settings.silicon_mode == "mock"
    assert settings.site_sms_mode == "mock"
    assert settings.development_site_otp == "135790"
    assert settings.seed_demo is True


def test_production_accepts_only_explicit_non_demo_configuration() -> None:
    settings = load_settings(production_environment())

    assert settings.is_development is False
    assert settings.silicon_mode == "live-disabled"
    assert settings.site_sms_mode == "disabled"
    assert settings.development_site_otp is None
    assert settings.seed_demo is False


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
        ({"MVP_SEED_DEMO": "sometimes"}, "MVP_SEED_DEMO"),
        ({"MVP_DEV_SITE_OTP": "12345"}, "MVP_DEV_SITE_OTP"),
    ],
)
def test_invalid_values_are_rejected(values: dict[str, str], expected_message: str) -> None:
    with pytest.raises(ConfigurationError, match=expected_message):
        load_settings(values)
