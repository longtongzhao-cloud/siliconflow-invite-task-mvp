from __future__ import annotations

import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .adapters import SKU_PEOPLE
from .security import random_token, token_hash


_db_path = Path(os.getenv("MVP_DB_PATH", Path(__file__).resolve().parents[1] / "data" / "mvp.db"))


def configure(path: str | Path) -> None:
    global _db_path
    _db_path = Path(path)


def now_ts() -> int:
    return int(time.time())


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


@contextmanager
def connect(immediate: bool = False) -> Iterator[sqlite3.Connection]:
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_db_path, timeout=10, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema() -> None:
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_db_path, timeout=10)
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;
        PRAGMA journal_mode = WAL;
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            phone_hmac TEXT NOT NULL UNIQUE,
            phone_mask TEXT NOT NULL,
            alipay_cipher TEXT,
            alipay_hmac TEXT UNIQUE,
            alipay_mask TEXT,
            alipay_name_cipher TEXT,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS site_otps (
            id TEXT PRIMARY KEY,
            phone_hmac TEXT NOT NULL,
            phone_mask TEXT NOT NULL,
            code_hmac TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            consumed_at INTEGER,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_site_otps_phone ON site_otps(phone_hmac, created_at DESC);
        CREATE TABLE IF NOT EXISTS site_sms_requests (
            id TEXT PRIMARY KEY,
            phone_hmac TEXT NOT NULL,
            phone_mask TEXT NOT NULL,
            provider TEXT NOT NULL,
            provider_out_id TEXT NOT NULL UNIQUE,
            provider_reference_hmac TEXT,
            status TEXT NOT NULL,
            verify_attempts INTEGER NOT NULL DEFAULT 0,
            expires_at INTEGER NOT NULL,
            verified_at INTEGER,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_site_sms_requests_phone
            ON site_sms_requests(phone_hmac, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_site_sms_requests_created
            ON site_sms_requests(created_at DESC);
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            taobao_tid TEXT NOT NULL UNIQUE,
            outer_sku_id TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            target_n INTEGER NOT NULL CHECK(target_n > 0),
            status TEXT NOT NULL,
            paid_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            customer_token_hash TEXT NOT NULL UNIQUE,
            public_slug TEXT NOT NULL UNIQUE,
            invitation_code TEXT,
            invitation_url TEXT,
            invitation_source TEXT,
            silicon_mode TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS consents (
            id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL REFERENCES orders(id),
            actor_ref TEXT NOT NULL,
            scope TEXT NOT NULL,
            accepted_at INTEGER NOT NULL,
            revoked_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS silicon_sessions (
            id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL REFERENCES orders(id),
            actor_ref TEXT NOT NULL,
            consent_id TEXT NOT NULL REFERENCES consents(id),
            token_cipher TEXT NOT NULL,
            upstream_user_key TEXT,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            revoked_at INTEGER,
            CHECK(expires_at <= created_at + 86400)
        );
        CREATE TABLE IF NOT EXISTS assignments (
            id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL REFERENCES orders(id),
            user_id TEXT NOT NULL REFERENCES users(id),
            status TEXT NOT NULL,
            claimed_at INTEGER NOT NULL,
            reservation_expires_at INTEGER NOT NULL,
            registered_at INTEGER,
            verified_at INTEGER,
            upstream_user_key TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            UNIQUE(order_id, user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_assignments_order_status ON assignments(order_id, status);
        CREATE TABLE IF NOT EXISTS assignment_upstream_claims (
            assignment_id TEXT PRIMARY KEY REFERENCES assignments(id),
            account_id_cipher TEXT NOT NULL,
            upstream_user_key TEXT NOT NULL,
            account_id_mask TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('PENDING','CONFIRMED','REJECTED')),
            submitted_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            reviewed_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS silicon_browser_handoffs (
            id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL REFERENCES orders(id),
            consent_id TEXT REFERENCES consents(id),
            actor_ref TEXT,
            state TEXT NOT NULL CHECK(state IN (
                'STARTING','AWAITING_USER','PROCESSING','COMPLETED',
                'FAILED','CANCELLED','EXPIRED'
            )),
            provider_session_ref TEXT,
            viewer_token_hash TEXT,
            viewer_token_used_at INTEGER,
            failure_code TEXT,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            terminal_at INTEGER,
            CHECK(expires_at <= created_at + 300)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_handoff_active_order
        ON silicon_browser_handoffs(order_id)
        WHERE state IN ('STARTING','AWAITING_USER','PROCESSING');
        CREATE TABLE IF NOT EXISTS rewards (
            id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL REFERENCES orders(id),
            assignment_id TEXT NOT NULL UNIQUE REFERENCES assignments(id),
            user_id TEXT NOT NULL REFERENCES users(id),
            upstream_user_key TEXT NOT NULL UNIQUE,
            amount_cents INTEGER NOT NULL CHECK(amount_cents = 500),
            status TEXT NOT NULL,
            alipay_snapshot_cipher TEXT NOT NULL,
            payout_reference TEXT UNIQUE,
            created_at INTEGER NOT NULL,
            paid_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            kind TEXT NOT NULL,
            message TEXT NOT NULL,
            dedupe_key TEXT NOT NULL UNIQUE,
            created_at INTEGER NOT NULL,
            read_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS audit_events (
            id TEXT PRIMARY KEY,
            actor_type TEXT NOT NULL,
            actor_id TEXT,
            action TEXT NOT NULL,
            object_type TEXT NOT NULL,
            object_id TEXT,
            metadata_json TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS taobao_events (
            event_id TEXT PRIMARY KEY,
            topic TEXT NOT NULL,
            taobao_tid TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


LOCKED_STATUSES = ("VERIFIED_LOCKED", "PAYOUT_PENDING", "PAYOUT_RETRY", "PAID")


def sweep(conn: sqlite3.Connection, now: int | None = None) -> None:
    current = now or now_ts()
    conn.execute(
        """
        UPDATE silicon_browser_handoffs
        SET state='EXPIRED',terminal_at=?,failure_code='HANDOFF_TIMEOUT'
        WHERE state IN ('STARTING','AWAITING_USER','PROCESSING') AND expires_at<=?
        """,
        (current, current),
    )
    reminders = conn.execute(
        """
        SELECT a.id, a.user_id
        FROM assignments a JOIN orders o ON o.id = a.order_id
        WHERE a.status = 'ACTIVE'
          AND a.claimed_at + 900 <= ?
          AND a.reservation_expires_at > ?
          AND o.expires_at > ?
        """,
        (current, current, current),
    ).fetchall()
    for row in reminders:
        conn.execute(
            """
            INSERT OR IGNORE INTO notifications(id,user_id,kind,message,dedupe_key,created_at)
            VALUES(?,?,?,?,?,?)
            """,
            (
                new_id("note"), row["user_id"], "REMINDER_15M",
                "任务已进行 15 分钟，请在保护期内完成注册和实名认证。",
                f"{row['id']}:reminder-15m", current,
            ),
        )

    expired = conn.execute(
        """
        SELECT a.id, a.user_id, o.expires_at AS order_expires_at
        FROM assignments a JOIN orders o ON o.id = a.order_id
        WHERE a.status = 'ACTIVE'
          AND (a.reservation_expires_at <= ? OR o.expires_at <= ?)
        """,
        (current, current),
    ).fetchall()
    for row in expired:
        next_status = "ORDER_EXPIRED" if row["order_expires_at"] <= current else "EXPIRED"
        conn.execute(
            "UPDATE assignments SET status=?, updated_at=? WHERE id=? AND status='ACTIVE'",
            (next_status, current, row["id"]),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO notifications(id,user_id,kind,message,dedupe_key,created_at)
            VALUES(?,?,?,?,?,?)
            """,
            (
                new_id("note"), row["user_id"], next_status,
                "订单已结束。" if next_status == "ORDER_EXPIRED" else "30 分钟保护期已结束，订单未满时仍可补做。",
                f"{row['id']}:{next_status.lower()}", current,
            ),
        )

    conn.execute(
        "UPDATE orders SET status='CLOSED', updated_at=? WHERE expires_at<=? AND status IN ('ACTIVE','AWAITING_INVITE')",
        (current, current),
    )
    conn.execute(
        """
        UPDATE silicon_browser_handoffs
        SET state='CANCELLED',terminal_at=?,failure_code='ORDER_ENDED'
        WHERE state IN ('STARTING','AWAITING_USER','PROCESSING')
          AND order_id IN (SELECT id FROM orders WHERE status IN ('CLOSED','REFUNDED'))
        """,
        (current,),
    )
    conn.execute(
        """
        DELETE FROM silicon_sessions
        WHERE expires_at<=? OR revoked_at IS NOT NULL
           OR order_id IN (SELECT id FROM orders WHERE status IN ('CLOSED','REFUNDED'))
        """,
        (current,),
    )
    conn.execute("DELETE FROM site_otps WHERE created_at<=?", (current - 86400,))
    conn.execute("DELETE FROM site_sms_requests WHERE created_at<=?", (current - 86400,))


def metrics(conn: sqlite3.Connection, order_id: str, now: int | None = None) -> dict[str, int]:
    current = now or now_ts()
    row = conn.execute(
        """
        SELECT
          SUM(CASE WHEN status='ACTIVE' AND reservation_expires_at>? THEN 1 ELSE 0 END) AS active,
          SUM(CASE WHEN registered_at IS NOT NULL THEN 1 ELSE 0 END) AS registered,
          SUM(CASE WHEN status IN ('VERIFIED_LOCKED','PAYOUT_PENDING','PAYOUT_RETRY','PAID') THEN 1 ELSE 0 END) AS locked,
          SUM(CASE WHEN status='PAID' THEN 1 ELSE 0 END) AS paid
        FROM assignments WHERE order_id=?
        """,
        (current, order_id),
    ).fetchone()
    return {
        "active": int(row["active"] or 0),
        "registered": int(row["registered"] or 0),
        "locked": int(row["locked"] or 0),
        "paid": int(row["paid"] or 0),
    }


def seed_demo_orders(mode: str = "mock") -> None:
    current = now_ts()
    with connect(immediate=True) as conn:
        for sku, count in SKU_PEOPLE.items():
            tid = f"DEMO-{count}-PERSON"
            exists = conn.execute("SELECT 1 FROM orders WHERE taobao_tid=?", (tid,)).fetchone()
            if exists:
                continue
            raw_customer = random_token(32)
            code = f"D{count:07d}"[-8:]
            conn.execute(
                """
                INSERT INTO orders(
                    id,taobao_tid,outer_sku_id,quantity,target_n,status,paid_at,expires_at,
                    customer_token_hash,public_slug,invitation_code,invitation_url,invitation_source,
                    silicon_mode,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    new_id("ord"), tid, sku, 1, count, "ACTIVE", current,
                    current + 24 * 3600, token_hash(raw_customer), random_token(18), code,
                    f"https://cloud.siliconflow.cn/i/{code}", "MOCK_SEED", mode, current, current,
                ),
            )
