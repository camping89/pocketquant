"""Unit tests for exness_spike.py: URL allowlist, redaction, limits and the spike session."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from pocketquant.core.infra.exness.exness_client import (
    allowed_access_point,
    history_age_days,
    min_request_interval,
    validate_base_url,
    ws_url,
)
from scripts.exness_spike import Session, SpikeConfig, redact


def test_validate_base_url_accepts_https_on_confirmed_host() -> None:
    assert validate_base_url("https://api.example.test/", "api.example.test") == (
        "https://api.example.test"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://api.example.test",
        "https://evil.test",
        "https://u:p@api.example.test",
        "https://api.example.test/?x=1",
    ],
)
def test_validate_base_url_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(ValueError):
        validate_base_url(url, "api.example.test")


def test_ws_url_switches_scheme_and_appends_path() -> None:
    assert ws_url("https://api.example.test", "/v1/x") == "wss://api.example.test/v1/x"


def test_allowed_access_point_accepts_exness_subdomain() -> None:
    assert allowed_access_point("ap-x.trading.exness.com") == "ap-x.trading.exness.com"


@pytest.mark.parametrize("url", ["https://ap-x.exness.com", "https://ap-x.exness.com/"])
def test_allowed_access_point_accepts_plain_https_url(url: str) -> None:
    assert allowed_access_point(url) == "ap-x.exness.com"


@pytest.mark.parametrize(
    "host",
    [
        "exness.com.evil.test",
        "evil.test",
        "http://ap-x.exness.com",
        "https://ap-x.exness.com.evil.test",
        "https://u:p@ap-x.exness.com",
        "https://ap-x.exness.com:8443",
        "https://ap-x.exness.com/v1",
    ],
)
def test_allowed_access_point_rejects_foreign_hosts(host: str) -> None:
    with pytest.raises(ValueError):
        allowed_access_point(host)


def test_redact_masks_identity_and_money_but_keeps_currency() -> None:
    result = redact(
        {
            "account_id": "9",
            "items": [{"deal": {"profit": {"amount": "-12.5", "currency": "USD"}, "deal_id": "7"}}],
        }
    )

    deal = result["items"][0]["deal"]
    assert result["account_id"] == "REDACTED"
    assert deal["profit"]["amount"] == "0.00"
    assert deal["profit"]["currency"] == "USD"
    assert deal["deal_id"] == "REDACTED"


def _limits(deals_limits: dict[str, int] | None = None) -> dict[str, object]:
    deals: dict[str, object] = {
        "api_operation_id": "getDealsHistory",
        "rate_limit": {"limit": 2, "window_seconds": 1},
    }
    if deals_limits is not None:
        deals["limits"] = deals_limits
    return {
        "limits": {
            "rest": {
                "global_account_rate": {"limit": 10, "window_seconds": 1},
                "methods": [
                    {
                        "api_operation_id": "getLimits",
                        "rate_limit": {"limit": 4, "window_seconds": 1},
                    },
                    deals,
                ],
            }
        }
    }


def test_min_request_interval_follows_the_strictest_rate_with_headroom() -> None:
    assert min_request_interval(_limits()) == pytest.approx(0.6)


def test_history_age_days_reads_deals_limit_with_default() -> None:
    assert history_age_days(_limits({"history_age_days": 14})) == 14
    assert history_age_days(_limits()) == 30


async def test_session_sends_requests_to_the_access_point_once_resolved() -> None:
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, json={})

    cfg = SpikeConfig(
        base_url="https://api.example.test",
        account_id="1",
        api_key="k",
        private_key=Ed25519PrivateKey.generate(),
        out=Path("unused"),
        tick_seconds=1,
        instruments=["XAUUSD"],
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        session = Session(cfg=cfg, client=client)
        await session.get("/v1/a")
        session.ap_base = "https://ap-x.exness.com"
        await session.get("/v1/b", {"x": 1})
    assert [u.host for u in seen] == ["api.example.test", "ap-x.exness.com"]
    assert seen[1].raw_path == b"/v1/b?x=1"


async def test_session_retries_a_rate_limited_request_and_counts_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = [httpx.Response(429, json={"error_message": "REQUEST_RATE_LIMIT"})]

    def handler(request: httpx.Request) -> httpx.Response:
        return responses.pop(0) if responses else httpx.Response(200, json={"ok": True})

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("scripts.exness_spike.asyncio.sleep", no_sleep)
    cfg = SpikeConfig(
        base_url="https://api.example.test",
        account_id="1",
        api_key="k",
        private_key=Ed25519PrivateKey.generate(),
        out=Path("unused"),
        tick_seconds=1,
        instruments=["XAUUSD"],
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        session = Session(cfg=cfg, client=client)
        status, body = await session.get("/v1/a")
    assert (status, body, session.rate_limited_retries) == (200, {"ok": True}, 1)
