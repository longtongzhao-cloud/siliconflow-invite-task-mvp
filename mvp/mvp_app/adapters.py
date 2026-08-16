from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import asdict, dataclass
from typing import Any

from .security import random_token


SKU_PEOPLE = {
    "SF_INVITE_1": 1,
    "SF_INVITE_5": 5,
    "SF_INVITE_10": 10,
}


class AdapterError(RuntimeError):
    def __init__(self, code: str, safe_message: str, status_code: int = 409):
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.status_code = status_code


@dataclass(frozen=True)
class SiliconLoginResult:
    session_token: str
    invitation_code: str
    invitation_url: str
    upstream_user_key: str
    expires_in_seconds: int
    source: str


class SiliconFlowAdapter:
    mode = "live-disabled"

    def capabilities(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "network": False,
            "send_otp": False,
            "proxy_login": False,
            "read_invitation": False,
            "read_referrals": False,
            "source": "NONE",
        }

    def send_otp(self, phone: str) -> dict[str, Any]:
        raise AdapterError("POLICY_DISABLED", "真实 SiliconFlow 登录适配器尚未启用")

    def login(self, phone: str, otp: str) -> SiliconLoginResult:
        raise AdapterError("POLICY_DISABLED", "真实 SiliconFlow 登录适配器尚未启用")


class MockSiliconFlowAdapter(SiliconFlowAdapter):
    mode = "mock"
    demo_otp = "246810"

    def capabilities(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "network": False,
            "send_otp": True,
            "proxy_login": True,
            "read_invitation": True,
            "read_referrals": True,
            "source": "MOCK",
        }

    def send_otp(self, phone: str) -> dict[str, Any]:
        return {
            "challenge_id": random_token(18),
            "masked_phone": f"{phone[:3]}****{phone[-4:]}",
            "retry_after_seconds": 60,
            "debug_code": self.demo_otp,
        }

    def login(self, phone: str, otp: str) -> SiliconLoginResult:
        if otp != self.demo_otp:
            raise AdapterError("OTP_INVALID", "验证码不正确", 400)
        digest = hashlib.sha256(phone.encode("ascii")).digest()
        code = base64.b32encode(digest).decode("ascii").rstrip("=")[:8]
        upstream_key = hashlib.sha256(("sf-user:" + phone).encode("ascii")).hexdigest()
        return SiliconLoginResult(
            session_token="mock_sf_session_" + random_token(32),
            invitation_code=code,
            invitation_url=f"https://cloud.siliconflow.cn/i/{code}",
            upstream_user_key=upstream_key,
            expires_in_seconds=24 * 3600,
            source="MOCK",
        )


class ManualSiliconFlowAdapter(SiliconFlowAdapter):
    mode = "manual"

    def capabilities(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "network": False,
            "send_otp": False,
            "proxy_login": False,
            "read_invitation": True,
            "read_referrals": True,
            "source": "MANUAL_EVIDENCE",
        }

    def send_otp(self, phone: str) -> dict[str, Any]:
        raise AdapterError("MANUAL_ACTION_REQUIRED", "请在 SiliconFlow 官方页面完成登录")

    def login(self, phone: str, otp: str) -> SiliconLoginResult:
        raise AdapterError("MANUAL_ACTION_REQUIRED", "人工模式不在本站接收 SiliconFlow 验证码")


def get_silicon_adapter(mode: str) -> SiliconFlowAdapter:
    if mode == "mock":
        return MockSiliconFlowAdapter()
    if mode == "manual":
        return ManualSiliconFlowAdapter()
    return SiliconFlowAdapter()


def parse_invitation(value: str) -> tuple[str, str]:
    raw = value.strip()
    if re.fullmatch(r"[A-Za-z0-9]{8}", raw):
        code = raw.upper()
        return code, f"https://cloud.siliconflow.cn/i/{code}"
    match = re.fullmatch(r"https://cloud[.]siliconflow[.]cn/i/([A-Za-z0-9]{8})/?", raw)
    if not match:
        raise AdapterError("INVALID_INVITATION", "请输入 8 位邀请码或官方完整邀请链接", 400)
    code = match.group(1).upper()
    return code, f"https://cloud.siliconflow.cn/i/{code}"


def target_people(outer_sku_id: str, quantity: int) -> int:
    if outer_sku_id not in SKU_PEOPLE:
        raise AdapterError("UNKNOWN_SKU", "未知 SKU，需要人工处理", 400)
    if quantity < 1 or quantity > 100:
        raise AdapterError("INVALID_QUANTITY", "购买数量必须在 1 到 100 之间", 400)
    return SKU_PEOPLE[outer_sku_id] * quantity


def adapter_result(result: SiliconLoginResult) -> dict[str, Any]:
    data = asdict(result)
    data.pop("session_token", None)
    return data

