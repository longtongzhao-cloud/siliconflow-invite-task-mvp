from __future__ import annotations

from dataclasses import dataclass

from .adapters import AdapterError


@dataclass(frozen=True)
class BrowserHandoffCapabilities:
    enabled: bool
    mode: str
    session_ttl_seconds: int


class BrowserHandoffBroker:
    mode = "disabled"

    def capabilities(self) -> BrowserHandoffCapabilities:
        return BrowserHandoffCapabilities(
            enabled=False,
            mode=self.mode,
            session_ttl_seconds=300,
        )

    def start(self) -> None:
        raise AdapterError(
            "REMOTE_BROWSER_DISABLED",
            "手机安全登录服务尚未配置，请使用手动邀请码",
            503,
        )


def get_browser_handoff_broker(mode: str) -> BrowserHandoffBroker:
    if mode == "disabled":
        return BrowserHandoffBroker()
    raise AdapterError(
        "REMOTE_BROWSER_MODE_INVALID",
        "手机安全登录配置无效",
        503,
    )
