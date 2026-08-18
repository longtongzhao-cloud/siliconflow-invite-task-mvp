from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from .adapters import AdapterError


@dataclass(frozen=True)
class SiteSmsSendResult:
    provider_reference: str | None = None


class SiteSmsProvider(Protocol):
    name: str

    def send_code(self, phone: str, out_id: str) -> SiteSmsSendResult: ...

    def verify_code(self, phone: str, code: str, out_id: str) -> bool: ...


class MockSiteSmsProvider:
    name = "mock"

    def __init__(self, code: str):
        self.code = code

    def send_code(self, phone: str, out_id: str) -> SiteSmsSendResult:
        return SiteSmsSendResult(provider_reference=out_id)

    def verify_code(self, phone: str, code: str, out_id: str) -> bool:
        return code == self.code


class AliyunDypnsSiteSmsProvider:
    name = "aliyun-dypns"

    def __init__(
        self,
        *,
        access_key_id: str,
        access_key_secret: str,
        sign_name: str,
        template_code: str,
        scheme_name: str,
        client: Any | None = None,
    ):
        try:
            from alibabacloud_dypnsapi20170525 import models
            from alibabacloud_dypnsapi20170525.client import (
                Client as Dypnsapi20170525Client,
            )
            from alibabacloud_tea_openapi import models as open_api_models
        except ImportError as exc:  # pragma: no cover - deployment packaging failure
            raise AdapterError(
                "SITE_SMS_SDK_MISSING", "本站短信服务组件未安装", 503
            ) from exc

        self._models = models
        self._sign_name = sign_name
        self._template_code = template_code
        self._scheme_name = scheme_name
        if client is None:
            config = open_api_models.Config(
                access_key_id=access_key_id,
                access_key_secret=access_key_secret,
                endpoint="dypnsapi.aliyuncs.com",
                connect_timeout=5000,
                read_timeout=5000,
            )
            client = Dypnsapi20170525Client(config)
        self._client = client

    def send_code(self, phone: str, out_id: str) -> SiteSmsSendResult:
        request = self._models.SendSmsVerifyCodeRequest(
            phone_number=phone,
            country_code="86",
            sign_name=self._sign_name,
            template_code=self._template_code,
            template_param=json.dumps(
                {"code": "##code##", "min": "5"}, separators=(",", ":")
            ),
            out_id=out_id,
            scheme_name=self._scheme_name,
            code_length=6,
            code_type=1,
            valid_time=300,
            interval=60,
            duplicate_policy=1,
            return_verify_code=False,
            auto_retry=1,
        )
        try:
            response = self._client.send_sms_verify_code(request)
        except Exception as exc:
            raise AdapterError(
                "SITE_SMS_PROVIDER_UNAVAILABLE", "短信验证码发送失败，请稍后重试", 502
            ) from exc

        body = getattr(response, "body", None)
        if (
            body is None
            or getattr(body, "code", None) != "OK"
            or getattr(body, "success", None) is not True
        ):
            raise AdapterError(
                "SITE_SMS_PROVIDER_REJECTED", "短信验证码发送失败，请稍后重试", 502
            )
        model = getattr(body, "model", None)
        provider_reference = getattr(model, "biz_id", None) if model else None
        return SiteSmsSendResult(provider_reference=provider_reference)

    def verify_code(self, phone: str, code: str, out_id: str) -> bool:
        request = self._models.CheckSmsVerifyCodeRequest(
            phone_number=phone,
            country_code="86",
            verify_code=code,
            out_id=out_id,
            scheme_name=self._scheme_name,
            case_auth_policy=2,
        )
        try:
            response = self._client.check_sms_verify_code(request)
        except Exception as exc:
            raise AdapterError(
                "SITE_SMS_PROVIDER_UNAVAILABLE", "验证码服务暂时不可用，请稍后重试", 502
            ) from exc

        body = getattr(response, "body", None)
        if (
            body is None
            or getattr(body, "code", None) != "OK"
            or getattr(body, "success", None) is not True
        ):
            raise AdapterError(
                "SITE_SMS_PROVIDER_REJECTED", "验证码服务暂时不可用，请稍后重试", 502
            )
        model = getattr(body, "model", None)
        verify_result = getattr(model, "verify_result", None) if model else None
        if verify_result == "PASS":
            return True
        if verify_result == "UNKNOWN":
            return False
        raise AdapterError(
            "SITE_SMS_PROVIDER_INVALID_RESPONSE", "验证码服务返回异常，请稍后重试", 502
        )


def build_site_sms_provider(settings: Any) -> SiteSmsProvider:
    if settings.site_sms_mode == "mock" and settings.development_site_otp:
        return MockSiteSmsProvider(settings.development_site_otp)
    if settings.site_sms_mode == "aliyun-dypns":
        return AliyunDypnsSiteSmsProvider(
            access_key_id=settings.aliyun_access_key_id,
            access_key_secret=settings.aliyun_access_key_secret,
            sign_name=settings.site_sms_sign_name,
            template_code=settings.site_sms_template_code,
            scheme_name=settings.site_sms_scheme_name,
        )
    raise AdapterError("SITE_SMS_DISABLED", "本站短信服务尚未启用", 503)
