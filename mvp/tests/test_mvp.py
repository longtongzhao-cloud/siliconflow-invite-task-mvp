from __future__ import annotations

import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["MVP_ENV"] = "development"
os.environ["MVP_SEED_DEMO"] = "0"
os.environ["MVP_ADMIN_KEY"] = "mvp-admin-demo"
os.environ["MVP_SECRET"] = "test-only-secret-with-more-than-32-bytes"

from mvp_app import database as db  # noqa: E402
from mvp_app import main as main_module  # noqa: E402
from mvp_app.main import app  # noqa: E402


ADMIN_HEADERS = {"X-Admin-Key": "mvp-admin-demo", "X-MVP-Request": "1"}
WEB_HEADERS = {"X-MVP-Request": "1"}


@pytest.fixture()
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "mvp-test.db"
    db.configure(path)
    db.init_schema()
    return path


@pytest.fixture()
def client(database_path: Path):
    with TestClient(app) as test_client:
        yield test_client


def register_worker(client: TestClient, phone: str, alipay: str | None = None) -> None:
    sent = client.post("/api/auth/send-code", json={"phone": phone})
    assert sent.status_code == 200
    verified = client.post("/api/auth/verify", json={"phone": phone, "code": "135790"})
    assert verified.status_code == 200
    if alipay:
        bound = client.put(
            "/api/me/alipay",
            headers=WEB_HEADERS,
            json={"account": alipay, "real_name": "测试用户"},
        )
        assert bound.status_code == 200, bound.text


def create_order(client: TestClient, tid: str, sku: str = "SF_INVITE_1", mode: str = "mock") -> dict:
    response = client.post(
        "/api/admin/orders",
        headers=ADMIN_HEADERS,
        json={"taobao_tid": tid, "outer_sku_id": sku, "quantity": 1, "silicon_mode": mode},
    )
    assert response.status_code == 200, response.text
    return response.json()


def activate_manual(client: TestClient, order: dict, code: str = "ABCD1234") -> None:
    response = client.post(
        f"{order['customer_url']}/manual-invitation".replace("/o/", "/api/customer/"),
        json={"invitation": code, "consent": True},
    )
    assert response.status_code == 200, response.text


def test_full_proxy_login_claim_reward_and_payout(client: TestClient, database_path: Path) -> None:
    order = create_order(client, "T-FULL-001", "SF_INVITE_1", "mock")
    customer_api = order["customer_url"].replace("/o/", "/api/customer/")

    sent = client.post(f"{customer_api}/silicon/send-code", json={"phone": "13800000001"})
    assert sent.status_code == 200
    assert sent.json()["debug_code"] == "246810"

    logged_in = client.post(
        f"{customer_api}/silicon/login",
        json={"phone": "13800000001", "otp": "246810", "consent": True},
    )
    assert logged_in.status_code == 200, logged_in.text
    payload = logged_in.json()
    assert len(payload["invitation_code"]) == 8
    assert payload["status"] == "ACTIVE"
    assert payload["session_expires_at"] <= payload["expires_at"]

    raw_db = database_path.read_bytes()
    assert b"246810" not in raw_db
    assert b"mock_sf_session_" not in raw_db
    assert b"13800000001" not in raw_db

    register_worker(client, "13900000001", "13900000001")
    slug = order["task_url"].split("/t/", 1)[1]
    claim = client.post(f"/api/tasks/{slug}/claim", headers=WEB_HEADERS)
    assert claim.status_code == 200
    assignment_id = claim.json()["assignment"]["id"]
    duplicate = client.post(f"/api/tasks/{slug}/claim", headers=WEB_HEADERS)
    assert duplicate.status_code == 200
    assert duplicate.json()["idempotent"] is True
    assert duplicate.json()["assignment"]["id"] == assignment_id

    assert client.post(f"/api/assignments/{assignment_id}/mock-register", headers=WEB_HEADERS).status_code == 200
    verified = client.post(f"/api/assignments/{assignment_id}/mock-verify", headers=WEB_HEADERS)
    assert verified.status_code == 200, verified.text
    reward_id = verified.json()["reward"]["id"]
    assert verified.json()["assignment"]["status"] == "PAYOUT_PENDING"

    paid = client.post(
        f"/api/admin/rewards/{reward_id}/pay",
        headers=ADMIN_HEADERS,
        json={"payout_reference": "ALI-TX-0001"},
    )
    assert paid.status_code == 200
    assert paid.json()["reward"]["status"] == "PAID"
    duplicate_paid = client.post(
        f"/api/admin/rewards/{reward_id}/pay",
        headers=ADMIN_HEADERS,
        json={"payout_reference": "ALI-TX-0001"},
    )
    assert duplicate_paid.status_code == 200
    assert duplicate_paid.json()["idempotent"] is True
    raw_db = database_path.read_bytes()
    assert b"13900000001" not in raw_db
    assert b"ALI-TX-0001" in raw_db


@pytest.mark.parametrize(
    ("sku", "expected"),
    [("SF_INVITE_1", 1), ("SF_INVITE_5", 5), ("SF_INVITE_10", 10)],
)
def test_sku_mapping(client: TestClient, sku: str, expected: int) -> None:
    order = create_order(client, f"T-SKU-{expected}", sku, "manual")
    assert order["target"] == expected


def test_claim_requires_login_and_alipay(client: TestClient) -> None:
    order = create_order(client, "T-AUTH-001", mode="manual")
    activate_manual(client, order)
    slug = order["task_url"].split("/t/", 1)[1]
    assert client.post(f"/api/tasks/{slug}/claim", headers=WEB_HEADERS).status_code == 401
    register_worker(client, "13900000002")
    response = client.post(f"/api/tasks/{slug}/claim", headers=WEB_HEADERS)
    assert response.status_code == 409
    assert "支付宝" in response.text


@pytest.mark.parametrize(
    ("sku", "expected"),
    [("SF_INVITE_1", 1), ("SF_INVITE_5", 5), ("SF_INVITE_10", 10)],
)
def test_concurrent_claims_never_exceed_n(
    client: TestClient, database_path: Path, sku: str, expected: int
) -> None:
    order = create_order(client, f"T-CONCURRENT-{expected}", sku=sku, mode="manual")
    activate_manual(client, order)
    slug = order["task_url"].split("/t/", 1)[1]
    clients: list[TestClient] = []
    try:
        for index in range(12):
            worker = TestClient(app)
            register_worker(worker, f"1370000{index:04d}", f"pay{index:04d}@example.com")
            clients.append(worker)

        def claim(worker: TestClient) -> int:
            return worker.post(f"/api/tasks/{slug}/claim", headers=WEB_HEADERS).status_code

        with ThreadPoolExecutor(max_workers=12) as pool:
            statuses = list(pool.map(claim, clients))
        assert statuses.count(200) == expected
        assert statuses.count(409) == 12 - expected
        with sqlite3.connect(database_path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM assignments WHERE status='ACTIVE'").fetchone()[0] == expected
    finally:
        for worker in clients:
            worker.close()


def test_late_completion_gets_reward_only_when_capacity_free(client: TestClient, database_path: Path) -> None:
    order = create_order(client, "T-LATE-001", mode="manual")
    activate_manual(client, order)
    slug = order["task_url"].split("/t/", 1)[1]
    register_worker(client, "13900000003", "late1@example.com")
    assignment = client.post(f"/api/tasks/{slug}/claim", headers=WEB_HEADERS).json()["assignment"]
    with sqlite3.connect(database_path) as conn:
        conn.execute("UPDATE assignments SET reservation_expires_at=? WHERE id=?", (db.now_ts() - 1, assignment["id"]))
        conn.commit()
    completed = client.post(f"/api/assignments/{assignment['id']}/mock-verify", headers=WEB_HEADERS)
    assert completed.status_code == 200
    assert completed.json()["assignment"]["status"] == "PAYOUT_PENDING"


def test_late_completion_cannot_displace_active_claim(client: TestClient, database_path: Path) -> None:
    order = create_order(client, "T-LATE-002", mode="manual")
    activate_manual(client, order)
    slug = order["task_url"].split("/t/", 1)[1]
    first = TestClient(app)
    second = TestClient(app)
    try:
        register_worker(first, "13900000004", "late2@example.com")
        old = first.post(f"/api/tasks/{slug}/claim", headers=WEB_HEADERS).json()["assignment"]
        with sqlite3.connect(database_path) as conn:
            conn.execute("UPDATE assignments SET reservation_expires_at=? WHERE id=?", (db.now_ts() - 1, old["id"]))
            conn.commit()
        register_worker(second, "13900000005", "fresh@example.com")
        fresh = second.post(f"/api/tasks/{slug}/claim", headers=WEB_HEADERS)
        assert fresh.status_code == 200
        late = first.post(f"/api/assignments/{old['id']}/mock-verify", headers=WEB_HEADERS)
        assert late.status_code == 200
        assert late.json()["assignment"]["status"] == "VERIFIED_NO_REWARD"
        assert late.json()["reward"] is None
    finally:
        first.close()
        second.close()


def test_order_expiry_blocks_late_reward(client: TestClient, database_path: Path) -> None:
    order = create_order(client, "T-EXPIRE-001", mode="manual")
    activate_manual(client, order)
    slug = order["task_url"].split("/t/", 1)[1]
    register_worker(client, "13900000006", "expired@example.com")
    assignment = client.post(f"/api/tasks/{slug}/claim", headers=WEB_HEADERS).json()["assignment"]
    with sqlite3.connect(database_path) as conn:
        conn.execute("UPDATE orders SET expires_at=? WHERE id=?", (db.now_ts() - 1, order["id"]))
        conn.commit()
    response = client.post(f"/api/assignments/{assignment['id']}/mock-verify", headers=WEB_HEADERS)
    assert response.status_code == 200
    assert response.json()["assignment"]["status"] == "ORDER_EXPIRED"
    assert response.json()["reward"] is None


def test_fifteen_minute_reminder_is_idempotent(client: TestClient, database_path: Path) -> None:
    order = create_order(client, "T-REMINDER-001", mode="manual")
    activate_manual(client, order)
    slug = order["task_url"].split("/t/", 1)[1]
    register_worker(client, "13900000007", "reminder@example.com")
    assignment = client.post(f"/api/tasks/{slug}/claim", headers=WEB_HEADERS).json()["assignment"]
    current = db.now_ts()
    with sqlite3.connect(database_path) as conn:
        conn.execute(
            "UPDATE assignments SET claimed_at=?, reservation_expires_at=? WHERE id=?",
            (current - 901, current + 899, assignment["id"]),
        )
        conn.commit()
    assert client.get("/api/me/notifications").status_code == 200
    assert client.get("/api/me/notifications").status_code == 200
    with sqlite3.connect(database_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE dedupe_key=?",
            (f"{assignment['id']}:reminder-15m",),
        ).fetchone()[0]
    assert count == 1


def test_live_disabled_adapter_fails_closed(client: TestClient) -> None:
    order = create_order(client, "T-DISABLED-001", mode="live-disabled")
    endpoint = order["customer_url"].replace("/o/", "/api/customer/") + "/silicon/send-code"
    response = client.post(endpoint, json={"phone": "13800000009"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "POLICY_DISABLED"


def test_disabled_site_sms_fails_closed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        main_module,
        "SETTINGS",
        replace(
            main_module.SETTINGS,
            site_sms_mode="disabled",
            development_site_otp=None,
        ),
    )

    sent = client.post("/api/auth/send-code", json={"phone": "13900000010"})
    verified = client.post(
        "/api/auth/verify",
        json={"phone": "13900000010", "code": "135790"},
    )

    assert sent.status_code == 503
    assert sent.json()["error"]["code"] == "SITE_SMS_DISABLED"
    assert verified.status_code == 503
    assert verified.json()["error"]["code"] == "SITE_SMS_DISABLED"


def test_expired_silicon_session_is_deleted(client: TestClient, database_path: Path) -> None:
    order = create_order(client, "T-SESSION-CLEANUP", mode="mock")
    customer_api = order["customer_url"].replace("/o/", "/api/customer/")
    response = client.post(
        f"{customer_api}/silicon/login",
        json={"phone": "13800000008", "otp": "246810", "consent": True},
    )
    assert response.status_code == 200
    with sqlite3.connect(database_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM silicon_sessions").fetchone()[0] == 1
        conn.execute("UPDATE silicon_sessions SET expires_at=?", (db.now_ts() - 1,))
        conn.commit()
    assert client.get("/api/tasks").status_code == 200
    with sqlite3.connect(database_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM silicon_sessions").fetchone()[0] == 0


def test_taobao_mock_payment_is_idempotent_and_refund_closes_order(client: TestClient) -> None:
    event = {
        "event_id": "TB-EVENT-001",
        "topic": "PAYMENT_SUCCEEDED",
        "taobao_tid": "TB-TID-001",
        "outer_sku_id": "SF_INVITE_5",
        "quantity": 2,
    }
    paid = client.post("/api/dev/taobao/events", headers=ADMIN_HEADERS, json=event)
    assert paid.status_code == 200, paid.text
    assert paid.json()["order"]["target"] == 10
    assert paid.json()["delivery_mode"] == "MANUAL_REQUIRED"
    repeated = client.post("/api/dev/taobao/events", headers=ADMIN_HEADERS, json=event)
    assert repeated.status_code == 200
    assert repeated.json()["idempotent"] is True

    refunded = client.post(
        "/api/dev/taobao/events",
        headers=ADMIN_HEADERS,
        json={
            "event_id": "TB-EVENT-002",
            "topic": "ORDER_REFUNDED",
            "taobao_tid": "TB-TID-001",
            "quantity": 1,
        },
    )
    assert refunded.status_code == 200
    assert refunded.json()["order"]["status"] == "REFUNDED"


def test_taobao_production_webhook_fails_closed(client: TestClient) -> None:
    response = client.post("/api/integrations/taobao/webhook", json={})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "TAOBAO_INTEGRATION_DISABLED"
