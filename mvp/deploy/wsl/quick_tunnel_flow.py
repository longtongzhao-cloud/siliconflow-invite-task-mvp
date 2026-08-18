from __future__ import annotations

import json
import os
import re
import secrets
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from typing import Any


BASE_URL = os.environ.get("QUICK_TUNNEL_BASE_URL", "").rstrip("/")
ADMIN_KEY = os.environ.get("QUICK_TUNNEL_ADMIN_KEY", "")
SITE_OTP = os.environ.get("QUICK_TUNNEL_SITE_OTP", "")


def request_json(
    opener: urllib.request.OpenerDirector,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    request_headers = {
        "Accept": "application/json",
        "User-Agent": "siliconflow-mvp-quick-tunnel-test",
        "X-MVP-Request": "1",
        **(headers or {}),
    }
    payload = None
    if body is not None:
        payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        BASE_URL + path,
        data=payload,
        headers=request_headers,
        method=method,
    )
    try:
        with opener.open(request, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"{method} {path} returned HTTP {exc.code}: {detail}") from exc


def main() -> None:
    if not re.fullmatch(r"https://[-a-z0-9]+\.trycloudflare\.com", BASE_URL):
        raise RuntimeError("QUICK_TUNNEL_BASE_URL is not a Quick Tunnel HTTPS URL")
    if len(ADMIN_KEY) < 16 or not re.fullmatch(r"\d{6}", SITE_OTP):
        raise RuntimeError("Quick Tunnel self-test credentials are missing")

    cookie_jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    suffix = secrets.token_hex(5)
    admin_headers = {"X-Admin-Key": ADMIN_KEY}

    order = request_json(
        opener,
        "POST",
        "/api/admin/orders",
        {
            "taobao_tid": f"TUNNEL-{suffix}",
            "outer_sku_id": "SF_INVITE_1",
            "quantity": 1,
            "silicon_mode": "mock",
        },
        admin_headers,
    )
    customer_api = order["customer_url"].replace("/o/", "/api/customer/")
    request_json(
        opener,
        "POST",
        customer_api + "/silicon/send-code",
        {"phone": "13800000001"},
    )
    customer = request_json(
        opener,
        "POST",
        customer_api + "/silicon/login",
        {"phone": "13800000001", "otp": "246810", "consent": True},
    )
    if customer["status"] != "ACTIVE" or len(customer["invitation_code"]) != 8:
        raise RuntimeError("Customer invitation activation failed")

    request_json(opener, "POST", "/api/auth/send-code", {"phone": "13900000001"})
    request_json(
        opener,
        "POST",
        "/api/auth/verify",
        {"phone": "13900000001", "code": SITE_OTP},
    )
    if not any(cookie.secure for cookie in cookie_jar):
        raise RuntimeError("Site session cookie is not marked Secure")
    request_json(
        opener,
        "PUT",
        "/api/me/alipay",
        {"account": f"tunnel-{suffix}@example.invalid", "real_name": "测试用户"},
    )

    slug = order["task_url"].split("/t/", 1)[1]
    claim = request_json(opener, "POST", f"/api/tasks/{slug}/claim")
    assignment_id = claim["assignment"]["id"]
    request_json(opener, "POST", f"/api/assignments/{assignment_id}/mock-register")
    verified = request_json(
        opener, "POST", f"/api/assignments/{assignment_id}/mock-verify"
    )
    if verified["assignment"]["status"] != "PAYOUT_PENDING":
        raise RuntimeError("Reward was not locked")

    reward_id = verified["reward"]["id"]
    paid = request_json(
        opener,
        "POST",
        f"/api/admin/rewards/{reward_id}/pay",
        {"payout_reference": f"TUNNEL-PAY-{suffix}"},
        admin_headers,
    )
    if paid["reward"]["status"] != "PAID":
        raise RuntimeError("Payout registration failed")

    print(json.dumps({"status": "passed", "reward_status": "PAID"}))


if __name__ == "__main__":
    main()
