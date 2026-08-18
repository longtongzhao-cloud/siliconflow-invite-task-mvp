from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from mvp_app import database as db
from mvp_app import main as main_module
from mvp_app.adapters import AdapterError
from mvp_app.main import app
from mvp_app.site_sms import (
    AliyunDypnsSiteSmsProvider,
    SiteSmsSendResult,
)


WEB_HEADERS = {"X-MVP-Request": "1"}


class FakeAliyunClient:
    def __init__(self, verify_result: str = "PASS"):
        self.verify_result = verify_result
        self.send_request = None
        self.verify_request = None

    def send_sms_verify_code(self, request):
        self.send_request = request
        return SimpleNamespace(
            body=SimpleNamespace(
                code="OK",
                success=True,
                model=SimpleNamespace(biz_id="provider-biz-reference"),
            )
        )

    def check_sms_verify_code(self, request):
        self.verify_request = request
        return SimpleNamespace(
            body=SimpleNamespace(
                code="OK",
                success=True,
                model=SimpleNamespace(verify_result=self.verify_result),
            )
        )


class FakeSiteSmsProvider:
    name = "aliyun-dypns"

    def __init__(self):
        self.sent: list[tuple[str, str]] = []
        self.verified: list[tuple[str, str, str]] = []
        self.fail_send = False

    def send_code(self, phone: str, out_id: str) -> SiteSmsSendResult:
        self.sent.append((phone, out_id))
        if self.fail_send:
            raise AdapterError("SITE_SMS_PROVIDER_UNAVAILABLE", "短信服务不可用", 502)
        return SiteSmsSendResult(provider_reference="provider-biz-reference")

    def verify_code(self, phone: str, code: str, out_id: str) -> bool:
        self.verified.append((phone, code, out_id))
        return code == "654321"


@pytest.fixture()
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "site-sms-test.db"
    db.configure(path)
    db.init_schema()
    return path


@pytest.fixture()
def client(database_path: Path):
    with TestClient(app) as test_client:
        yield test_client


def controlled_aliyun_settings(phone: str = "13900000021"):
    return replace(
        main_module.SETTINGS,
        site_sms_mode="aliyun-dypns",
        development_site_otp=None,
        aliyun_access_key_id="test-access-key-id",
        aliyun_access_key_secret="test-access-key-secret",
        site_sms_sign_name="系统赠送签名",
        site_sms_template_code="100001",
        site_sms_scheme_name="mvp-login",
        site_sms_allowed_phones=(phone,),
    )


def test_aliyun_provider_uses_cloud_generated_code_and_strict_pass() -> None:
    fake_client = FakeAliyunClient()
    provider = AliyunDypnsSiteSmsProvider(
        access_key_id="test-access-key-id",
        access_key_secret="test-access-key-secret",
        sign_name="系统赠送签名",
        template_code="100001",
        scheme_name="mvp-login",
        client=fake_client,
    )

    result = provider.send_code("13900000021", "sms-out-id")

    request = fake_client.send_request
    assert request.phone_number == "13900000021"
    assert request.country_code == "86"
    assert request.out_id == "sms-out-id"
    assert request.scheme_name == "mvp-login"
    assert request.code_length == 6
    assert request.return_verify_code is False
    assert json.loads(request.template_param) == {"code": "##code##", "min": "5"}
    assert result.provider_reference == "provider-biz-reference"

    assert provider.verify_code("13900000021", "654321", "sms-out-id") is True
    assert fake_client.verify_request.country_code == "86"
    assert fake_client.verify_request.out_id == "sms-out-id"

    fake_client.verify_result = "UNKNOWN"
    assert provider.verify_code("13900000021", "000000", "sms-out-id") is False


def test_aliyun_provider_rejects_nonstandard_verify_result() -> None:
    provider = AliyunDypnsSiteSmsProvider(
        access_key_id="test-access-key-id",
        access_key_secret="test-access-key-secret",
        sign_name="系统赠送签名",
        template_code="100001",
        scheme_name="mvp-login",
        client=FakeAliyunClient(verify_result="MAYBE"),
    )

    with pytest.raises(AdapterError) as exc_info:
        provider.verify_code("13900000021", "654321", "sms-out-id")
    assert exc_info.value.code == "SITE_SMS_PROVIDER_INVALID_RESPONSE"


def test_live_site_sms_flow_never_returns_or_stores_sensitive_values(
    client: TestClient,
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    phone = "13900000021"
    provider = FakeSiteSmsProvider()
    monkeypatch.setattr(main_module, "SETTINGS", controlled_aliyun_settings(phone))
    monkeypatch.setattr(main_module, "build_site_sms_provider", lambda _: provider)

    sent = client.post(
        "/api/auth/send-code", headers=WEB_HEADERS, json={"phone": phone}
    )
    assert sent.status_code == 200, sent.text
    assert "debug_code" not in sent.json()
    assert provider.sent[0][0] == phone

    provider.name = "mock"
    provider_changed = client.post(
        "/api/auth/verify",
        headers=WEB_HEADERS,
        json={"phone": phone, "code": "654321"},
    )
    assert provider_changed.status_code == 409
    provider.name = "aliyun-dypns"

    wrong = client.post(
        "/api/auth/verify",
        headers=WEB_HEADERS,
        json={"phone": phone, "code": "000000"},
    )
    assert wrong.status_code == 400

    verified = client.post(
        "/api/auth/verify",
        headers=WEB_HEADERS,
        json={"phone": phone, "code": "654321"},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["user"]["phone"] == "139****0021"

    replay = client.post(
        "/api/auth/verify",
        headers=WEB_HEADERS,
        json={"phone": phone, "code": "654321"},
    )
    assert replay.status_code == 400

    raw_database = database_path.read_bytes()
    assert phone.encode() not in raw_database
    assert b"654321" not in raw_database
    assert b"provider-biz-reference" not in raw_database
    assert b"test-access-key-secret" not in raw_database
    with sqlite3.connect(database_path) as conn:
        status, attempts = conn.execute(
            "SELECT status,verify_attempts FROM site_sms_requests"
        ).fetchone()
    assert status == "VERIFIED"
    assert attempts == 2


def test_site_sms_requires_request_header_and_allowed_phone(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = FakeSiteSmsProvider()
    monkeypatch.setattr(main_module, "SETTINGS", controlled_aliyun_settings())
    monkeypatch.setattr(main_module, "build_site_sms_provider", lambda _: provider)

    no_header = client.post(
        "/api/auth/send-code", json={"phone": "13900000021"}
    )
    other_phone = client.post(
        "/api/auth/send-code",
        headers=WEB_HEADERS,
        json={"phone": "13900000022"},
    )

    assert no_header.status_code == 403
    assert other_phone.status_code == 403
    assert provider.sent == []


def test_site_sms_enforces_cooldown_verify_attempts_and_budget(
    client: TestClient,
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    phone = "13900000021"
    provider = FakeSiteSmsProvider()
    settings = replace(
        controlled_aliyun_settings(phone),
        site_sms_max_sends_per_hour=1,
        site_sms_max_sends_per_day=1,
    )
    monkeypatch.setattr(main_module, "SETTINGS", settings)
    monkeypatch.setattr(main_module, "build_site_sms_provider", lambda _: provider)

    first = client.post(
        "/api/auth/send-code", headers=WEB_HEADERS, json={"phone": phone}
    )
    second = client.post(
        "/api/auth/send-code", headers=WEB_HEADERS, json={"phone": phone}
    )
    assert first.status_code == 200
    assert second.status_code == 429

    for _ in range(5):
        invalid = client.post(
            "/api/auth/verify",
            headers=WEB_HEADERS,
            json={"phone": phone, "code": "000000"},
        )
        assert invalid.status_code == 400
    locked = client.post(
        "/api/auth/verify",
        headers=WEB_HEADERS,
        json={"phone": phone, "code": "654321"},
    )
    assert locked.status_code == 429

    with sqlite3.connect(database_path) as conn:
        conn.execute(
            "UPDATE site_sms_requests SET created_at=?,expires_at=?",
            (db.now_ts() - 90000, db.now_ts() - 1),
        )
        conn.commit()
    db.init_schema()
    with sqlite3.connect(database_path) as conn:
        conn.execute("BEGIN")
        db.sweep(conn)
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM site_sms_requests").fetchone()[0] == 0


def test_failed_provider_send_is_fail_closed_and_counted(
    client: TestClient,
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    phone = "13900000021"
    provider = FakeSiteSmsProvider()
    provider.fail_send = True
    monkeypatch.setattr(main_module, "SETTINGS", controlled_aliyun_settings(phone))
    monkeypatch.setattr(main_module, "build_site_sms_provider", lambda _: provider)

    response = client.post(
        "/api/auth/send-code", headers=WEB_HEADERS, json={"phone": phone}
    )

    assert response.status_code == 502
    assert "debug_code" not in response.text
    assert phone not in response.text
    with sqlite3.connect(database_path) as conn:
        status = conn.execute("SELECT status FROM site_sms_requests").fetchone()[0]
    assert status == "FAILED"
