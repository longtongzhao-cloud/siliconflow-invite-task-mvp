from __future__ import annotations

import hmac
import json
import re
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import database as db
from .adapters import AdapterError, adapter_result, get_silicon_adapter, parse_invitation, target_people
from .browser_handoff import get_browser_handoff_broker
from .config import SETTINGS
from .security import (
    decrypt_text,
    encrypt_text,
    hmac_hex,
    mask_alipay,
    mask_phone,
    random_token,
    sign_session,
    token_hash,
    verify_session,
)


BASE_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = BASE_DIR / "static"
ENV = SETTINGS.environment
DEFAULT_SILICON_MODE = SETTINGS.silicon_mode


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_schema()
    if SETTINGS.is_development and SETTINGS.seed_demo:
        db.seed_demo_orders(DEFAULT_SILICON_MODE)
    yield


app = FastAPI(
    title="邀新任务台 MVP",
    docs_url="/api/docs" if SETTINGS.is_development else None,
    lifespan=lifespan,
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=list(SETTINGS.allowed_hosts),
)
app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


class PhoneRequest(BaseModel):
    phone: str


class PhoneVerify(BaseModel):
    phone: str
    code: str


class AlipayBind(BaseModel):
    account: str = Field(min_length=5, max_length=100)
    real_name: str = Field(min_length=2, max_length=30)


class OrderCreate(BaseModel):
    taobao_tid: str = Field(min_length=4, max_length=64)
    outer_sku_id: str
    quantity: int = Field(ge=1, le=100)
    silicon_mode: str | None = None


class SiliconLogin(BaseModel):
    phone: str
    otp: str
    consent: bool


class ManualInvite(BaseModel):
    invitation: str
    consent: bool


class BrowserHandoffStart(BaseModel):
    consent: bool


class SiliconAccountClaim(BaseModel):
    account_id: str = Field(min_length=3, max_length=128)


class ManualVerify(BaseModel):
    upstream_account_id: str = Field(min_length=3, max_length=128)
    valid_authentication: bool = True


class PayoutInput(BaseModel):
    payout_reference: str = Field(min_length=4, max_length=100)


class TaobaoMockEvent(BaseModel):
    event_id: str = Field(min_length=4, max_length=100)
    topic: str
    taobao_tid: str = Field(min_length=4, max_length=64)
    outer_sku_id: str | None = None
    quantity: int = Field(default=1, ge=1, le=100)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    return response


@app.exception_handler(AdapterError)
async def adapter_error_handler(_: Request, exc: AdapterError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.safe_message}},
    )


def normalize_phone(value: str) -> str:
    phone = re.sub(r"[ +()-]", "", value)
    if phone.startswith("86") and len(phone) == 13:
        phone = phone[2:]
    if not re.fullmatch(r"1[3-9]\d{9}", phone):
        raise HTTPException(400, "请输入有效的中国大陆手机号")
    return phone


def current_user(request: Request) -> dict[str, Any]:
    payload = verify_session(request.cookies.get("mvp_session"))
    if not payload:
        raise HTTPException(401, "请先完成手机号登录")
    with db.connect() as conn:
        user = conn.execute("SELECT * FROM users WHERE id=?", (payload["sub"],)).fetchone()
    if not user:
        raise HTTPException(401, "登录状态已失效")
    return dict(user)


def require_web_request(request: Request) -> None:
    if request.headers.get("x-mvp-request") != "1":
        raise HTTPException(403, "请求来源校验失败")


def require_admin(x_admin_key: str | None) -> None:
    if not x_admin_key or not hmac.compare_digest(x_admin_key, SETTINGS.admin_key):
        raise HTTPException(401, "管理员密钥不正确")


def require_site_sms() -> str:
    if SETTINGS.site_sms_mode != "mock" or not SETTINGS.development_site_otp:
        raise AdapterError("SITE_SMS_DISABLED", "本站短信服务尚未启用", 503)
    return SETTINGS.development_site_otp


def get_order_by_customer_token(conn: sqlite3.Connection, raw_token: str) -> sqlite3.Row:
    order = conn.execute(
        "SELECT * FROM orders WHERE customer_token_hash=?", (token_hash(raw_token),)
    ).fetchone()
    if not order:
        raise HTTPException(404, "订单链接无效")
    db.sweep(conn)
    order = conn.execute("SELECT * FROM orders WHERE id=?", (order["id"],)).fetchone()
    if order["expires_at"] <= db.now_ts():
        raise HTTPException(410, "订单链接已过期")
    return order


def require_mutable_customer_order(order: sqlite3.Row) -> None:
    if order["status"] not in {"AWAITING_INVITE", "ACTIVE"}:
        raise HTTPException(409, "订单已关闭，不能修改邀请信息")


def order_payload(
    conn: sqlite3.Connection,
    order: sqlite3.Row,
    include_tid: bool = False,
    include_invitation: bool = False,
) -> dict[str, Any]:
    counts = db.metrics(conn, order["id"])
    occupied = counts["active"] + counts["locked"]
    data = {
        "id": order["id"],
        "sku": order["outer_sku_id"],
        "quantity": order["quantity"],
        "target": order["target_n"],
        "status": order["status"],
        "expires_at": order["expires_at"],
        "silicon_mode": order["silicon_mode"],
        "task_url": f"/t/{order['public_slug']}",
        "counts": counts,
        "available": max(0, order["target_n"] - occupied),
    }
    if include_invitation:
        data.update(
            invitation_code=order["invitation_code"],
            invitation_url=order["invitation_url"],
            invitation_source=order["invitation_source"],
        )
    if include_tid:
        data["taobao_tid"] = order["taobao_tid"]
    return data


def audit(conn: sqlite3.Connection, actor_type: str, actor_id: str | None, action: str,
          object_type: str, object_id: str | None, metadata: dict[str, Any] | None = None) -> None:
    conn.execute(
        """
        INSERT INTO audit_events(id,actor_type,actor_id,action,object_type,object_id,metadata_json,created_at)
        VALUES(?,?,?,?,?,?,?,?)
        """,
        (db.new_id("evt"), actor_type, actor_id, action, object_type, object_id,
         json.dumps(metadata or {}, separators=(",", ":")), db.now_ts()),
    )


def normalize_upstream_account_id(value: str) -> str:
    normalized = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,128}", normalized):
        raise HTTPException(400, "SiliconFlow 用户 ID 格式不正确")
    return normalized


def mask_upstream_account_id(value: str) -> str:
    if len(value) <= 6:
        return value[:1] + "***" + value[-1:]
    return value[:3] + "***" + value[-3:]


def upstream_claim_payload(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if not row or row["claim_status"] is None:
        return None
    return {
        "status": row["claim_status"],
        "account_id_mask": row["account_id_mask"],
        "submitted_at": row["submitted_at"],
        "updated_at": row["claim_updated_at"],
        "reviewed_at": row["reviewed_at"],
    }


def insert_order(
    conn: sqlite3.Connection,
    taobao_tid: str,
    outer_sku_id: str,
    quantity: int,
    mode: str,
    current: int,
) -> tuple[sqlite3.Row, str]:
    target = target_people(outer_sku_id, quantity)
    customer_token = random_token(32)
    order_id = db.new_id("ord")
    conn.execute(
        """
        INSERT INTO orders(
            id,taobao_tid,outer_sku_id,quantity,target_n,status,paid_at,expires_at,
            customer_token_hash,public_slug,silicon_mode,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            order_id, taobao_tid, outer_sku_id, quantity, target, "AWAITING_INVITE", current,
            current + 24 * 3600, token_hash(customer_token), random_token(18), mode, current, current,
        ),
    )
    return conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone(), customer_token


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "environment": ENV,
        "taobao_order_mode": "manual",
        "silicon_default_mode": DEFAULT_SILICON_MODE,
        "site_sms_mode": SETTINGS.site_sms_mode,
        "remote_browser_mode": SETTINGS.remote_browser_mode,
        "real_upstream_writes_enabled": False,
    }


@app.post("/api/auth/send-code")
def send_site_code(body: PhoneRequest) -> dict[str, Any]:
    site_otp = require_site_sms()
    phone = normalize_phone(body.phone)
    current = db.now_ts()
    phone_key = hmac_hex(phone, "phone-index")
    with db.connect(immediate=True) as conn:
        recent = conn.execute(
            "SELECT COUNT(*) AS n FROM site_otps WHERE phone_hmac=? AND created_at>?",
            (phone_key, current - 3600),
        ).fetchone()["n"]
        if recent >= 5:
            raise HTTPException(429, "验证码请求过于频繁，请稍后再试")
        conn.execute(
            """
            INSERT INTO site_otps(id,phone_hmac,phone_mask,code_hmac,expires_at,created_at)
            VALUES(?,?,?,?,?,?)
            """,
            (db.new_id("otp"), phone_key, mask_phone(phone), hmac_hex(site_otp, "site-otp"),
             current + 300, current),
        )
    response = {"masked_phone": mask_phone(phone), "expires_in_seconds": 300}
    if SETTINGS.is_development:
        response["debug_code"] = site_otp
    return response


@app.post("/api/auth/verify")
def verify_site_code(body: PhoneVerify, response: Response) -> dict[str, Any]:
    require_site_sms()
    phone = normalize_phone(body.phone)
    current = db.now_ts()
    phone_key = hmac_hex(phone, "phone-index")
    with db.connect(immediate=True) as conn:
        record = conn.execute(
            """
            SELECT * FROM site_otps
            WHERE phone_hmac=? AND consumed_at IS NULL
            ORDER BY created_at DESC LIMIT 1
            """,
            (phone_key,),
        ).fetchone()
        if not record or record["expires_at"] <= current:
            raise HTTPException(400, "验证码已过期，请重新获取")
        if not hmac.compare_digest(record["code_hmac"], hmac_hex(body.code, "site-otp")):
            raise HTTPException(400, "验证码不正确")
        conn.execute("UPDATE site_otps SET consumed_at=? WHERE id=?", (current, record["id"]))
        user = conn.execute("SELECT * FROM users WHERE phone_hmac=?", (phone_key,)).fetchone()
        if not user:
            user_id = db.new_id("usr")
            conn.execute(
                "INSERT INTO users(id,phone_hmac,phone_mask,created_at) VALUES(?,?,?,?)",
                (user_id, phone_key, mask_phone(phone), current),
            )
            user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        audit(conn, "USER", user["id"], "LOGIN", "USER", user["id"])
    response.set_cookie(
        "mvp_session", sign_session(user["id"]), httponly=True, secure=SETTINGS.cookie_secure,
        samesite="lax", max_age=7 * 24 * 3600, path="/",
    )
    return {"user": {"id": user["id"], "phone": user["phone_mask"], "alipay_bound": bool(user["alipay_hmac"])}}


@app.post("/api/auth/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie("mvp_session", path="/")
    return {"ok": True}


@app.get("/api/me")
def me(request: Request) -> dict[str, Any]:
    user = current_user(request)
    return {
        "id": user["id"], "phone": user["phone_mask"],
        "alipay_bound": bool(user["alipay_hmac"]), "alipay": user["alipay_mask"],
    }


@app.put("/api/me/alipay")
def bind_alipay(body: AlipayBind, request: Request) -> dict[str, Any]:
    require_web_request(request)
    user = current_user(request)
    account = body.account.strip()
    real_name = body.real_name.strip()
    if not re.fullmatch(r"[A-Za-z0-9@._+-]{5,100}|1[3-9]\d{9}", account):
        raise HTTPException(400, "请输入有效的支付宝账号")
    account_key = hmac_hex(account.lower(), "alipay-index")
    try:
        with db.connect(immediate=True) as conn:
            conn.execute(
                """
                UPDATE users SET alipay_cipher=?, alipay_hmac=?, alipay_mask=?, alipay_name_cipher=?
                WHERE id=?
                """,
                (
                    encrypt_text(account, f"user:{user['id']}:alipay"), account_key, mask_alipay(account),
                    encrypt_text(real_name, f"user:{user['id']}:alipay-name"), user["id"],
                ),
            )
            audit(conn, "USER", user["id"], "BIND_ALIPAY", "USER", user["id"])
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "该支付宝账号已绑定其他本站账号") from exc
    return {"alipay_bound": True, "alipay": mask_alipay(account)}


@app.post("/api/admin/orders")
def create_order(body: OrderCreate, x_admin_key: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(x_admin_key)
    mode = body.silicon_mode or DEFAULT_SILICON_MODE
    if mode not in {"mock", "manual", "live-disabled"}:
        raise HTTPException(400, "未知 SiliconFlow 适配器模式")
    current = db.now_ts()
    try:
        with db.connect(immediate=True) as conn:
            order, customer_token = insert_order(
                conn, body.taobao_tid.strip(), body.outer_sku_id, body.quantity, mode, current
            )
            audit(conn, "ADMIN", "admin", "CREATE_ORDER", "ORDER", order["id"],
                  {"sku": body.outer_sku_id, "quantity": body.quantity, "target": order["target_n"], "mode": mode})
            payload = order_payload(conn, order, include_tid=True, include_invitation=True)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "淘宝订单号已存在") from exc
    payload["customer_url"] = f"/o/{customer_token}"
    payload["delivery_mode"] = "MANUAL_REQUIRED"
    return payload


@app.post("/api/integrations/taobao/webhook")
def taobao_webhook_disabled() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"error": {"code": "TAOBAO_INTEGRATION_DISABLED", "message": "淘宝生产验签与订单权限尚未启用"}},
    )


@app.post("/api/dev/taobao/events")
def taobao_mock_event(body: TaobaoMockEvent, x_admin_key: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(x_admin_key)
    if ENV != "development":
        raise HTTPException(404, "接口不存在")
    if body.topic not in {"PAYMENT_SUCCEEDED", "ORDER_REFUNDED", "ORDER_CLOSED"}:
        raise HTTPException(400, "未知淘宝事件类型")
    current = db.now_ts()
    payload_fingerprint = token_hash(body.model_dump_json())
    try:
        with db.connect(immediate=True) as conn:
            prior = conn.execute("SELECT * FROM taobao_events WHERE event_id=?", (body.event_id,)).fetchone()
            if prior:
                if prior["payload_hash"] != payload_fingerprint:
                    raise HTTPException(409, "同一事件 ID 的载荷不一致")
                order = conn.execute("SELECT * FROM orders WHERE taobao_tid=?", (body.taobao_tid,)).fetchone()
                return {
                    "idempotent": True,
                    "order": order_payload(
                        conn, order, include_tid=True, include_invitation=True
                    ) if order else None,
                }

            customer_token = None
            order = conn.execute("SELECT * FROM orders WHERE taobao_tid=?", (body.taobao_tid,)).fetchone()
            if body.topic == "PAYMENT_SUCCEEDED":
                if not body.outer_sku_id:
                    raise HTTPException(400, "付款事件缺少 outer_sku_id")
                if not order:
                    order, customer_token = insert_order(
                        conn, body.taobao_tid, body.outer_sku_id, body.quantity, DEFAULT_SILICON_MODE, current
                    )
            elif order:
                next_status = "REFUNDED" if body.topic == "ORDER_REFUNDED" else "CLOSED"
                conn.execute("UPDATE orders SET status=?, updated_at=? WHERE id=?", (next_status, current, order["id"]))
                conn.execute(
                    """
                    UPDATE assignments SET status='ORDER_EXPIRED', updated_at=?
                    WHERE order_id=? AND status IN ('ACTIVE','EXPIRED')
                    """,
                    (current, order["id"]),
                )
                conn.execute("DELETE FROM silicon_sessions WHERE order_id=?", (order["id"],))
                conn.execute(
                    """
                    UPDATE silicon_browser_handoffs
                    SET state='CANCELLED',terminal_at=?,failure_code='ORDER_ENDED'
                    WHERE order_id=? AND state IN ('STARTING','AWAITING_USER','PROCESSING')
                    """,
                    (current, order["id"]),
                )
                order = conn.execute("SELECT * FROM orders WHERE id=?", (order["id"],)).fetchone()

            conn.execute(
                "INSERT INTO taobao_events(event_id,topic,taobao_tid,payload_hash,created_at) VALUES(?,?,?,?,?)",
                (body.event_id, body.topic, body.taobao_tid, payload_fingerprint, current),
            )
            audit(conn, "TAOBAO_MOCK", body.event_id, body.topic, "ORDER", order["id"] if order else None)
            response = {
                "idempotent": False,
                "order": order_payload(
                    conn, order, include_tid=True, include_invitation=True
                ) if order else None,
            }
            if customer_token and order:
                response["customer_url"] = f"/o/{customer_token}"
                response["delivery_mode"] = "MANUAL_REQUIRED"
            return response
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "订单或事件已存在") from exc


@app.get("/api/customer/{raw_token}")
def customer_order(raw_token: str) -> dict[str, Any]:
    with db.connect(immediate=True) as conn:
        order = get_order_by_customer_token(conn, raw_token)
        payload = order_payload(
            conn, order, include_tid=True, include_invitation=True
        )
        payload["adapter"] = get_silicon_adapter(order["silicon_mode"]).capabilities()
        handoff = get_browser_handoff_broker(SETTINGS.remote_browser_mode).capabilities()
        payload["browser_handoff"] = {
            "enabled": handoff.enabled,
            "mode": handoff.mode,
            "session_ttl_seconds": handoff.session_ttl_seconds,
        }
        return payload


@app.post("/api/customer/{raw_token}/silicon/handoffs")
def start_customer_browser_handoff(
    raw_token: str, body: BrowserHandoffStart, request: Request
) -> dict[str, Any]:
    require_web_request(request)
    if not body.consent:
        raise HTTPException(400, "请先确认授权范围")
    with db.connect(immediate=True) as conn:
        order = get_order_by_customer_token(conn, raw_token)
        require_mutable_customer_order(order)

    # A real broker must be called outside the SQLite write transaction.
    broker = get_browser_handoff_broker(SETTINGS.remote_browser_mode)
    broker.start()
    raise RuntimeError("browser handoff broker returned without a session")


@app.post("/api/customer/{raw_token}/silicon/send-code")
def customer_silicon_send(
    raw_token: str, body: PhoneRequest, request: Request
) -> dict[str, Any]:
    require_web_request(request)
    phone = normalize_phone(body.phone)
    with db.connect(immediate=True) as conn:
        order = get_order_by_customer_token(conn, raw_token)
        require_mutable_customer_order(order)
        adapter = get_silicon_adapter(order["silicon_mode"])
        result = adapter.send_otp(phone)
        audit(conn, "CUSTOMER", hmac_hex(phone, "phone-index"), "SILICON_OTP_REQUEST", "ORDER", order["id"],
              {"adapter_mode": order["silicon_mode"]})
        return result


@app.post("/api/customer/{raw_token}/silicon/login")
def customer_silicon_login(
    raw_token: str, body: SiliconLogin, request: Request
) -> dict[str, Any]:
    require_web_request(request)
    if not body.consent:
        raise HTTPException(400, "请先确认授权范围")
    phone = normalize_phone(body.phone)
    current = db.now_ts()
    with db.connect(immediate=True) as conn:
        order = get_order_by_customer_token(conn, raw_token)
        require_mutable_customer_order(order)
        adapter = get_silicon_adapter(order["silicon_mode"])
        result = adapter.login(phone, body.otp)
        consent_id = db.new_id("consent")
        actor_ref = hmac_hex(phone, "phone-index")
        conn.execute(
            "INSERT INTO consents(id,order_id,actor_ref,scope,accepted_at) VALUES(?,?,?,?,?)",
            (consent_id, order["id"], actor_ref, "PROXY_LOGIN_READ_INVITATION", current),
        )
        session_id = db.new_id("sfs")
        expires_at = min(order["expires_at"], current + min(result.expires_in_seconds, 24 * 3600))
        aad = f"silicon:{session_id}:{order['id']}:{actor_ref}:{expires_at}"
        conn.execute(
            """
            INSERT INTO silicon_sessions(
                id,order_id,actor_ref,consent_id,token_cipher,upstream_user_key,created_at,expires_at
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (session_id, order["id"], actor_ref, consent_id, encrypt_text(result.session_token, aad),
             result.upstream_user_key, current, expires_at),
        )
        conn.execute(
            """
            UPDATE orders SET invitation_code=?, invitation_url=?, invitation_source=?, status='ACTIVE', updated_at=?
            WHERE id=?
            """,
            (result.invitation_code, result.invitation_url, result.source, current, order["id"]),
        )
        audit(conn, "CUSTOMER", actor_ref, "SILICON_PROXY_LOGIN", "ORDER", order["id"],
              {"adapter_mode": order["silicon_mode"], "session_expires_at": expires_at})
        order = conn.execute("SELECT * FROM orders WHERE id=?", (order["id"],)).fetchone()
        payload = order_payload(
            conn, order, include_tid=True, include_invitation=True
        )
        payload["session_expires_at"] = expires_at
        payload["adapter_result"] = adapter_result(result)
        return payload


@app.post("/api/customer/{raw_token}/manual-invitation")
def customer_manual_invite(
    raw_token: str, body: ManualInvite, request: Request
) -> dict[str, Any]:
    require_web_request(request)
    if not body.consent:
        raise HTTPException(400, "请先确认信息提交授权")
    code, url = parse_invitation(body.invitation)
    current = db.now_ts()
    with db.connect(immediate=True) as conn:
        order = get_order_by_customer_token(conn, raw_token)
        require_mutable_customer_order(order)
        conn.execute(
            """
            UPDATE orders SET invitation_code=?, invitation_url=?, invitation_source='USER_ASSERTED',
              status='ACTIVE', updated_at=? WHERE id=?
            """,
            (code, url, current, order["id"]),
        )
        audit(conn, "CUSTOMER", None, "SUBMIT_INVITATION", "ORDER", order["id"], {"source": "USER_ASSERTED"})
        order = conn.execute("SELECT * FROM orders WHERE id=?", (order["id"],)).fetchone()
        return order_payload(
            conn, order, include_tid=True, include_invitation=True
        )


@app.get("/api/tasks")
def public_tasks() -> dict[str, Any]:
    with db.connect(immediate=True) as conn:
        db.sweep(conn)
        orders = conn.execute("SELECT * FROM orders WHERE status='ACTIVE' ORDER BY created_at DESC").fetchall()
        return {"tasks": [order_payload(conn, order) for order in orders]}


@app.get("/api/tasks/{slug}")
def task_detail(slug: str) -> dict[str, Any]:
    with db.connect(immediate=True) as conn:
        db.sweep(conn)
        order = conn.execute("SELECT * FROM orders WHERE public_slug=?", (slug,)).fetchone()
        if not order:
            raise HTTPException(404, "任务不存在")
        return order_payload(conn, order)


@app.post("/api/tasks/{slug}/claim")
def claim_task(slug: str, request: Request) -> dict[str, Any]:
    require_web_request(request)
    user = current_user(request)
    if not user["alipay_hmac"]:
        raise HTTPException(409, "请先绑定支付宝收款信息")
    current = db.now_ts()
    with db.connect(immediate=True) as conn:
        db.sweep(conn, current)
        order = conn.execute("SELECT * FROM orders WHERE public_slug=?", (slug,)).fetchone()
        if not order:
            raise HTTPException(404, "任务不存在")
        if order["status"] != "ACTIVE" or order["expires_at"] <= current:
            raise HTTPException(409, "任务已结束")
        existing = conn.execute(
            "SELECT * FROM assignments WHERE order_id=? AND user_id=?", (order["id"], user["id"])
        ).fetchone()
        if existing:
            return {"assignment": dict(existing), "idempotent": True}
        counts = db.metrics(conn, order["id"], current)
        if counts["locked"] + counts["active"] >= order["target_n"]:
            raise HTTPException(409, "当前任务名额已满")
        assignment_id = db.new_id("asg")
        expires_at = current + 30 * 60
        conn.execute(
            """
            INSERT INTO assignments(
                id,order_id,user_id,status,claimed_at,reservation_expires_at,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (assignment_id, order["id"], user["id"], "ACTIVE", current, expires_at, current, current),
        )
        conn.execute(
            """
            INSERT INTO notifications(id,user_id,kind,message,dedupe_key,created_at)
            VALUES(?,?,?,?,?,?)
            """,
            (db.new_id("note"), user["id"], "CLAIMED", "抢单成功，30 分钟保护期已开始。",
             f"{assignment_id}:claimed", current),
        )
        audit(conn, "USER", user["id"], "CLAIM_TASK", "ASSIGNMENT", assignment_id, {"order_id": order["id"]})
        assignment = conn.execute("SELECT * FROM assignments WHERE id=?", (assignment_id,)).fetchone()
        return {"assignment": dict(assignment), "idempotent": False}


def lock_reward(conn: sqlite3.Connection, assignment: sqlite3.Row, upstream_key: str) -> dict[str, Any]:
    current = db.now_ts()
    db.sweep(conn, current)
    assignment = conn.execute("SELECT * FROM assignments WHERE id=?", (assignment["id"],)).fetchone()
    order = conn.execute("SELECT * FROM orders WHERE id=?", (assignment["order_id"],)).fetchone()
    if assignment["status"] in db.LOCKED_STATUSES:
        reward = conn.execute("SELECT * FROM rewards WHERE assignment_id=?", (assignment["id"],)).fetchone()
        return {"assignment": dict(assignment), "reward": dict(reward) if reward else None, "idempotent": True}
    if assignment["status"] in {"VERIFIED_NO_REWARD", "ORDER_EXPIRED"}:
        return {"assignment": dict(assignment), "reward": None, "idempotent": True}
    if order["expires_at"] <= current or order["status"] != "ACTIVE":
        conn.execute("UPDATE assignments SET status='ORDER_EXPIRED', updated_at=? WHERE id=?", (current, assignment["id"]))
        return {"assignment": dict(conn.execute("SELECT * FROM assignments WHERE id=?", (assignment["id"],)).fetchone()), "reward": None}
    prior = conn.execute("SELECT id FROM rewards WHERE upstream_user_key=?", (upstream_key,)).fetchone()
    if prior:
        conn.execute(
            "UPDATE assignments SET status='VERIFIED_NO_REWARD', registered_at=COALESCE(registered_at,?), verified_at=?, upstream_user_key=?, updated_at=? WHERE id=?",
            (current, current, upstream_key, current, assignment["id"]),
        )
        return {"assignment": dict(conn.execute("SELECT * FROM assignments WHERE id=?", (assignment["id"],)).fetchone()), "reward": None}
    if assignment["status"] == "EXPIRED":
        counts = db.metrics(conn, order["id"], current)
        if counts["locked"] + counts["active"] >= order["target_n"]:
            conn.execute(
                "UPDATE assignments SET status='VERIFIED_NO_REWARD', registered_at=COALESCE(registered_at,?), verified_at=?, upstream_user_key=?, updated_at=? WHERE id=?",
                (current, current, upstream_key, current, assignment["id"]),
            )
            updated = conn.execute("SELECT * FROM assignments WHERE id=?", (assignment["id"],)).fetchone()
            return {"assignment": dict(updated), "reward": None}
    user = conn.execute("SELECT * FROM users WHERE id=?", (assignment["user_id"],)).fetchone()
    if not user or not user["alipay_cipher"]:
        raise HTTPException(409, "支付宝收款信息缺失")
    account = decrypt_text(user["alipay_cipher"], f"user:{user['id']}:alipay")
    name = decrypt_text(user["alipay_name_cipher"], f"user:{user['id']}:alipay-name")
    reward_id = db.new_id("rwd")
    snapshot = encrypt_text(
        json.dumps({"account": account, "name": name}, ensure_ascii=False, separators=(",", ":")),
        f"reward:{reward_id}:alipay-snapshot",
    )
    conn.execute(
        """
        UPDATE assignments SET status='PAYOUT_PENDING', registered_at=COALESCE(registered_at,?),
          verified_at=?, upstream_user_key=?, updated_at=? WHERE id=?
        """,
        (current, current, upstream_key, current, assignment["id"]),
    )
    conn.execute(
        """
        INSERT INTO rewards(
            id,order_id,assignment_id,user_id,upstream_user_key,amount_cents,status,
            alipay_snapshot_cipher,created_at
        ) VALUES(?,?,?,?,?,500,'PAYOUT_PENDING',?,?)
        """,
        (reward_id, order["id"], assignment["id"], user["id"], upstream_key, snapshot, current),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO notifications(id,user_id,kind,message,dedupe_key,created_at)
        VALUES(?,?,?,?,?,?)
        """,
        (db.new_id("note"), user["id"], "VERIFIED", "有效认证已确认，5 元奖励待人工支付。",
         f"{assignment['id']}:verified", current),
    )
    updated = conn.execute("SELECT * FROM assignments WHERE id=?", (assignment["id"],)).fetchone()
    reward = conn.execute("SELECT * FROM rewards WHERE id=?", (reward_id,)).fetchone()
    return {"assignment": dict(updated), "reward": dict(reward), "idempotent": False}


@app.post("/api/assignments/{assignment_id}/mock-register")
def mock_register(assignment_id: str, request: Request) -> dict[str, Any]:
    require_web_request(request)
    user = current_user(request)
    if ENV != "development":
        raise HTTPException(404, "接口不存在")
    current = db.now_ts()
    with db.connect(immediate=True) as conn:
        db.sweep(conn, current)
        assignment = conn.execute("SELECT * FROM assignments WHERE id=? AND user_id=?", (assignment_id, user["id"])).fetchone()
        if not assignment:
            raise HTTPException(404, "抢单记录不存在")
        conn.execute(
            "UPDATE assignments SET registered_at=COALESCE(registered_at,?), updated_at=? WHERE id=?",
            (current, current, assignment_id),
        )
        return {"assignment": dict(conn.execute("SELECT * FROM assignments WHERE id=?", (assignment_id,)).fetchone())}


@app.post("/api/assignments/{assignment_id}/mock-verify")
def mock_verify(assignment_id: str, request: Request) -> dict[str, Any]:
    require_web_request(request)
    user = current_user(request)
    if ENV != "development":
        raise HTTPException(404, "接口不存在")
    with db.connect(immediate=True) as conn:
        assignment = conn.execute("SELECT * FROM assignments WHERE id=? AND user_id=?", (assignment_id, user["id"])).fetchone()
        if not assignment:
            raise HTTPException(404, "抢单记录不存在")
        upstream_key = hmac_hex("mock-upstream:" + user["id"], "upstream-user")
        result = lock_reward(conn, assignment, upstream_key)
        audit(conn, "USER", user["id"], "MOCK_VERIFY", "ASSIGNMENT", assignment_id)
        return result


@app.put("/api/assignments/{assignment_id}/silicon-account")
def submit_silicon_account(
    assignment_id: str, body: SiliconAccountClaim, request: Request
) -> dict[str, Any]:
    require_web_request(request)
    user = current_user(request)
    account_id = normalize_upstream_account_id(body.account_id)
    upstream_key = hmac_hex(account_id, "upstream-user")
    current = db.now_ts()
    with db.connect(immediate=True) as conn:
        db.sweep(conn, current)
        assignment = conn.execute(
            """
            SELECT a.*, o.status AS order_status, o.expires_at AS order_expires_at
            FROM assignments a JOIN orders o ON o.id=a.order_id
            WHERE a.id=? AND a.user_id=?
            """,
            (assignment_id, user["id"]),
        ).fetchone()
        if not assignment:
            raise HTTPException(404, "抢单记录不存在")
        if (
            assignment["status"] not in {"ACTIVE", "EXPIRED"}
            or assignment["order_status"] != "ACTIVE"
            or assignment["order_expires_at"] <= current
        ):
            raise HTTPException(409, "当前抢单记录不能提交 SiliconFlow 用户 ID")
        existing = conn.execute(
            "SELECT * FROM assignment_upstream_claims WHERE assignment_id=?",
            (assignment_id,),
        ).fetchone()
        if existing and existing["status"] != "PENDING":
            raise HTTPException(409, "SiliconFlow 用户 ID 已完成复核")
        if existing and hmac.compare_digest(existing["upstream_user_key"], upstream_key):
            return {
                "upstream_claim": {
                    "status": existing["status"],
                    "account_id_mask": existing["account_id_mask"],
                    "submitted_at": existing["submitted_at"],
                    "updated_at": existing["updated_at"],
                    "reviewed_at": existing["reviewed_at"],
                },
                "idempotent": True,
            }
        submitted_at = existing["submitted_at"] if existing else current
        conn.execute(
            """
            INSERT INTO assignment_upstream_claims(
                assignment_id,account_id_cipher,upstream_user_key,account_id_mask,status,
                submitted_at,updated_at
            ) VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(assignment_id) DO UPDATE SET
                account_id_cipher=excluded.account_id_cipher,
                upstream_user_key=excluded.upstream_user_key,
                account_id_mask=excluded.account_id_mask,
                status='PENDING',
                updated_at=excluded.updated_at,
                reviewed_at=NULL
            """,
            (
                assignment_id,
                encrypt_text(account_id, f"assignment:{assignment_id}:upstream-account"),
                upstream_key,
                mask_upstream_account_id(account_id),
                "PENDING",
                submitted_at,
                current,
            ),
        )
        audit(
            conn,
            "USER",
            user["id"],
            "SUBMIT_SILICON_ACCOUNT",
            "ASSIGNMENT",
            assignment_id,
            {"changed": bool(existing)},
        )
        claim = conn.execute(
            "SELECT * FROM assignment_upstream_claims WHERE assignment_id=?",
            (assignment_id,),
        ).fetchone()
        return {
            "upstream_claim": {
                "status": claim["status"],
                "account_id_mask": claim["account_id_mask"],
                "submitted_at": claim["submitted_at"],
                "updated_at": claim["updated_at"],
                "reviewed_at": claim["reviewed_at"],
            },
            "idempotent": False,
        }


@app.get("/api/me/assignments")
def my_assignments(request: Request) -> dict[str, Any]:
    user = current_user(request)
    with db.connect(immediate=True) as conn:
        db.sweep(conn)
        rows = conn.execute(
            """
            SELECT a.*, o.target_n, o.invitation_code, o.invitation_url, o.public_slug,
                   o.expires_at AS order_expires_at, r.id AS reward_id, r.status AS reward_status,
                   c.status AS claim_status, c.account_id_mask, c.submitted_at,
                   c.updated_at AS claim_updated_at, c.reviewed_at
            FROM assignments a JOIN orders o ON o.id=a.order_id
            LEFT JOIN rewards r ON r.assignment_id=a.id
            LEFT JOIN assignment_upstream_claims c ON c.assignment_id=a.id
            WHERE a.user_id=? ORDER BY a.created_at DESC
            """,
            (user["id"],),
        ).fetchall()
        assignments = []
        for row in rows:
            item = dict(row)
            item["upstream_claim"] = upstream_claim_payload(row)
            for key in (
                "claim_status", "account_id_mask", "submitted_at",
                "claim_updated_at", "reviewed_at",
            ):
                item.pop(key, None)
            assignments.append(item)
        return {"assignments": assignments}


@app.get("/api/me/notifications")
def my_notifications(request: Request) -> dict[str, Any]:
    user = current_user(request)
    with db.connect(immediate=True) as conn:
        db.sweep(conn)
        rows = conn.execute(
            "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 30", (user["id"],)
        ).fetchall()
        return {"notifications": [dict(row) for row in rows]}


@app.get("/api/admin/summary")
def admin_summary(x_admin_key: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(x_admin_key)
    with db.connect(immediate=True) as conn:
        db.sweep(conn)
        orders = conn.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
        order_data = []
        for order in orders:
            item = order_payload(
                conn, order, include_tid=True, include_invitation=True
            )
            assignment_rows = conn.execute(
                """
                SELECT a.id,a.status,a.claimed_at,a.reservation_expires_at,a.registered_at,a.verified_at,
                       u.phone_mask,r.id AS reward_id,r.status AS reward_status,
                       c.status AS claim_status,c.account_id_mask,c.submitted_at,
                       c.updated_at AS claim_updated_at,c.reviewed_at
                FROM assignments a JOIN users u ON u.id=a.user_id
                LEFT JOIN rewards r ON r.assignment_id=a.id
                LEFT JOIN assignment_upstream_claims c ON c.assignment_id=a.id
                WHERE a.order_id=? ORDER BY a.created_at
                """,
                (order["id"],),
            ).fetchall()
            item["assignments"] = []
            for row in assignment_rows:
                assignment_item = dict(row)
                assignment_item["upstream_claim"] = upstream_claim_payload(row)
                for key in (
                    "claim_status", "account_id_mask", "submitted_at",
                    "claim_updated_at", "reviewed_at",
                ):
                    assignment_item.pop(key, None)
                item["assignments"].append(assignment_item)
            order_data.append(item)
        rewards = [
            dict(row) for row in conn.execute(
                """
                SELECT r.id,r.order_id,r.assignment_id,r.amount_cents,r.status,r.payout_reference,
                       r.created_at,r.paid_at,u.phone_mask,u.alipay_mask
                FROM rewards r JOIN users u ON u.id=r.user_id ORDER BY r.created_at DESC
                """
            ).fetchall()
        ]
        return {"orders": order_data, "rewards": rewards}


@app.post("/api/admin/assignments/{assignment_id}/verify")
def admin_verify(assignment_id: str, body: ManualVerify, x_admin_key: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(x_admin_key)
    with db.connect(immediate=True) as conn:
        db.sweep(conn)
        assignment = conn.execute("SELECT * FROM assignments WHERE id=?", (assignment_id,)).fetchone()
        if not assignment:
            raise HTTPException(404, "抢单记录不存在")
        account_id = normalize_upstream_account_id(body.upstream_account_id)
        upstream_key = hmac_hex(account_id, "upstream-user")
        claim = conn.execute(
            "SELECT * FROM assignment_upstream_claims WHERE assignment_id=?",
            (assignment_id,),
        ).fetchone()
        if claim and not hmac.compare_digest(claim["upstream_user_key"], upstream_key):
            raise HTTPException(409, "复核的 SiliconFlow 用户 ID 与抢单人提交值不一致")
        if not body.valid_authentication:
            if assignment["status"] not in {"ACTIVE", "EXPIRED"}:
                raise HTTPException(409, "已进入奖励流程的记录不能改为无效")
            current = db.now_ts()
            conn.execute(
                "UPDATE assignments SET status='VERIFIED_NO_REWARD', registered_at=COALESCE(registered_at,?), verified_at=?, upstream_user_key=?, updated_at=? WHERE id=?",
                (current, current, upstream_key, current, assignment_id),
            )
            if claim:
                conn.execute(
                    """
                    UPDATE assignment_upstream_claims
                    SET status='REJECTED',reviewed_at=?,updated_at=? WHERE assignment_id=?
                    """,
                    (current, current, assignment_id),
                )
            result = {"assignment": dict(conn.execute("SELECT * FROM assignments WHERE id=?", (assignment_id,)).fetchone()), "reward": None}
        else:
            result = lock_reward(conn, assignment, upstream_key)
            if claim:
                current = db.now_ts()
                conn.execute(
                    """
                    UPDATE assignment_upstream_claims
                    SET status='CONFIRMED',reviewed_at=?,updated_at=? WHERE assignment_id=?
                    """,
                    (current, current, assignment_id),
                )
        audit(conn, "ADMIN", "admin", "VERIFY_ASSIGNMENT", "ASSIGNMENT", assignment_id,
              {"valid_authentication": body.valid_authentication})
        return result


@app.post("/api/admin/rewards/{reward_id}/pay")
def mark_paid(reward_id: str, body: PayoutInput, x_admin_key: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(x_admin_key)
    current = db.now_ts()
    try:
        with db.connect(immediate=True) as conn:
            reward = conn.execute("SELECT * FROM rewards WHERE id=?", (reward_id,)).fetchone()
            if not reward:
                raise HTTPException(404, "奖励记录不存在")
            if reward["status"] == "PAID":
                if reward["payout_reference"] != body.payout_reference:
                    raise HTTPException(409, "该奖励已经使用其他流水号支付")
                return {"reward": dict(reward), "idempotent": True}
            conn.execute(
                "UPDATE rewards SET status='PAID', payout_reference=?, paid_at=? WHERE id=?",
                (body.payout_reference.strip(), current, reward_id),
            )
            conn.execute("UPDATE assignments SET status='PAID', updated_at=? WHERE id=?", (current, reward["assignment_id"]))
            conn.execute(
                """
                INSERT OR IGNORE INTO notifications(id,user_id,kind,message,dedupe_key,created_at)
                VALUES(?,?,?,?,?,?)
                """,
                (db.new_id("note"), reward["user_id"], "PAID", "5 元奖励已人工支付，请核对到账情况。",
                 f"{reward_id}:paid", current),
            )
            audit(conn, "ADMIN", "admin", "MARK_REWARD_PAID", "REWARD", reward_id)
            updated = conn.execute("SELECT * FROM rewards WHERE id=?", (reward_id,)).fetchone()
            return {"reward": dict(updated), "idempotent": False}
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "该支付流水号已用于其他奖励") from exc


@app.get("/o/{raw_token}")
def customer_page(raw_token: str):
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/t/{slug}")
def task_page(slug: str):
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")
