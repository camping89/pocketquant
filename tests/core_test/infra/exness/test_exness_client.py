"""ExnessClient: signing, access-point routing, errors, secret hygiene, live gate,
pacing, transport retries, the 429 rule and the URL and limits helpers."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
import structlog
import structlog.testing
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import SecretStr

from pocketquant.core.common.time.simulation import clear_simulation_time, set_simulation_time
from pocketquant.core.config import Settings
from pocketquant.core.infra.exness import exness_client
from pocketquant.core.infra.exness.exness_client import (
    ExnessApiError,
    ExnessClient,
    _RequestPacer,
    allowed_access_point,
    history_age_days,
    min_request_interval,
    order_request_interval,
    validate_base_url,
    ws_url,
)
from pocketquant.core.infra.exness.exness_signer import body_hash
from tests.core_test.infra.market_data.conftest import build_settings

FIXTURES = Path(__file__).parent / "fixtures"
LIMITS = json.loads((FIXTURES / "limits.json").read_text(encoding="utf-8"))
API_KEY = "api-key-DO-NOT-LOG"
CANDLES = {
    "instrument": "XAUUSD",
    "timeframe": "M1",
    "from": "2026-10-13T09:00:00+00:00",
    "count": -5,
}

Answer = httpx.Response | Exception


def _secret() -> str:
    key = Ed25519PrivateKey.generate()
    return (key.private_bytes_raw() + key.public_key().public_bytes_raw()).hex()


def _settings(**update: Any) -> Settings:
    values: dict[str, Any] = {
        "exness_api_base_url": "https://api.exness.com",
        "exness_account_id": "1",
        "exness_api_key": SecretStr(API_KEY),
        "exness_secret_key": SecretStr(_secret()),
        "exness_live_trading": False,
    }
    values.update(update)
    return build_settings().model_copy(update=values)


def _decoded_data(request: httpx.Request) -> dict[str, Any]:
    value = request.headers["EXN-DATA"]
    return json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))


class _Exness:
    """A mock Exness: discovery and limits answered, other calls scripted."""

    def __init__(self, answers: Sequence[Answer] | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self.access_point: Answer = httpx.Response(
            200, json={"access_point": "https://ap-1.exness.com"}
        )
        self.answers = list(answers or [])

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/v1/trading/access-point":
            answer = self.access_point
        elif path.endswith("/limits"):
            answer = httpx.Response(200, json=LIMITS)
        else:
            answer = self.answers.pop(0) if self.answers else httpx.Response(200, json={})
        if isinstance(answer, Exception):
            raise answer
        return answer

    def other(self) -> list[httpx.Request]:
        return [
            r
            for r in self.requests
            if r.url.path != "/v1/trading/access-point" and not r.url.path.endswith("/limits")
        ]

    def discoveries(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path == "/v1/trading/access-point"]


@pytest.fixture(autouse=True)
def _no_pacing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exness_client, "_BOOTSTRAP_INTERVAL_S", 0.0)
    monkeypatch.setattr(exness_client, "logger", structlog.get_logger("test.exness_client"))


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock()
    monkeypatch.setattr(exness_client.asyncio, "sleep", mock)
    return mock


def _client(
    exness: _Exness, monkeypatch: pytest.MonkeyPatch, *, paced: bool = False, **update: Any
) -> ExnessClient:
    if not paced:
        monkeypatch.setattr(exness_client, "min_request_interval", lambda _limits: 0.0)
        monkeypatch.setattr(exness_client, "order_request_interval", lambda _limits, _fraction: 0.0)
    client = ExnessClient(_settings(**update))
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(exness.handler))
    return client


def _delays(sleeps: AsyncMock) -> list[float]:
    return [c.args[0] for c in sleeps.await_args_list]


async def test_every_call_after_discovery_goes_to_the_access_point(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exness = _Exness()
    client = _client(exness, monkeypatch)

    await client.call("getCandleHistory", params=CANDLES)
    await client.call("getCandleHistory", params=CANDLES)

    assert [r.url.host for r in exness.discoveries()] == ["api.exness.com"]
    assert all(r.url.host == "ap-1.exness.com" for r in exness.requests[1:])
    candles = exness.other()[0]
    assert _decoded_data(candles)["path"] == candles.url.raw_path.decode()
    assert "exness.com" not in _decoded_data(candles)["path"]
    assert candles.headers["EXN-IDEMPOTENCY-KEY"] == ""


async def test_a_421_clears_the_access_point_and_the_next_call_resolves_it_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exness = _Exness([httpx.Response(421)])
    client = _client(exness, monkeypatch)

    with structlog.testing.capture_logs() as logs, pytest.raises(ExnessApiError) as exc:
        await client.call("getCandleHistory", params=CANDLES)
    exness.access_point = httpx.Response(200, json={"access_point": "https://ap-2.exness.com"})
    await client.call("getCandleHistory", params=CANDLES)

    assert exc.value.status == 421
    assert len(exness.discoveries()) == 2
    assert [r.url.host for r in exness.other()] == ["ap-1.exness.com", "ap-2.exness.com"]
    assert [(e["event"], e["reason"]) for e in logs if e["event"].endswith("_reset")] == [
        ("exness.access_point_reset", "421")
    ]


async def test_a_transport_failure_clears_the_access_point(
    monkeypatch: pytest.MonkeyPatch, sleeps: AsyncMock
) -> None:
    exness = _Exness([httpx.ConnectError("boom")] * 3)
    client = _client(exness, monkeypatch)

    with pytest.raises(ExnessApiError) as exc:
        await client.call("getCandleHistory", params=CANDLES)
    await client.call("getCandleHistory", params=CANDLES)

    assert exc.value.code == "TRANSPORT"
    assert len(exness.discoveries()) == 2
    assert len(exness.other()) == 4


async def test_a_foreign_access_point_is_refused_and_not_stored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exness = _Exness()
    exness.access_point = httpx.Response(200, json={"access_point": "https://exness.com.evil.test"})
    client = _client(exness, monkeypatch)

    with pytest.raises(ValueError):
        await client.access_point()
    with pytest.raises(ValueError):
        await client.access_point()

    assert len(exness.discoveries()) == 2


async def test_a_failed_discovery_raises_the_http_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exness = _Exness()
    exness.access_point = httpx.Response(404)
    client = _client(exness, monkeypatch)

    with pytest.raises(ExnessApiError) as exc:
        await client.access_point()

    assert exc.value.status == 404


async def test_an_error_body_maps_to_its_error_message(monkeypatch: pytest.MonkeyPatch) -> None:
    exness = _Exness(
        [httpx.Response(400, json={"code": 1001, "error_message": "REQUEST_INVALID_COUNT"})]
    )
    client = _client(exness, monkeypatch)

    with pytest.raises(ExnessApiError) as exc:
        await client.call("getCandleHistory", params=CANDLES)

    assert exc.value.status == 400
    assert exc.value.code == "REQUEST_INVALID_COUNT"


async def test_no_log_event_carries_the_api_key(
    monkeypatch: pytest.MonkeyPatch, sleeps: AsyncMock
) -> None:
    exness = _Exness([httpx.Response(429), httpx.Response(500)])

    with structlog.testing.capture_logs() as logs:
        ExnessClient(_settings(exness_api_base_url="http://api.exness.com"))
        client = _client(exness, monkeypatch)
        with pytest.raises(ExnessApiError):
            await client.call("getCandleHistory", params=CANDLES)

    assert logs
    assert all(API_KEY not in str(event) for event in logs)


def _pem() -> str:
    return (
        Ed25519PrivateKey.generate()
        .private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        .decode()
    )


@pytest.mark.parametrize(
    "update",
    [
        {"exness_api_key": None},
        {"exness_api_base_url": "http://api.exness.com"},
        {"exness_api_base_url": "https://api.other.test"},
        {"exness_secret_key": SecretStr(_pem())},
    ],
)
async def test_bad_settings_fail_closed_without_a_request(
    update: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    exness = _Exness()
    client = _client(exness, monkeypatch, **update)

    assert client.is_configured is False
    with pytest.raises(ExnessApiError) as exc:
        await client.call("getCandleHistory", params=CANDLES)

    assert exc.value.code == "NOT_CONFIGURED"
    assert exness.requests == []


async def test_order_calls_are_refused_while_live_trading_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exness = _Exness()
    client = _client(exness, monkeypatch, exness_live_trading=False)

    with pytest.raises(ExnessApiError) as opened:
        await client.call(
            "openPosition", json_body={"instrument": "XAUUSD"}, idempotency_key="order-00001"
        )

    assert opened.value.code == "LIVE_TRADING_DISABLED"
    assert exness.requests == []


async def test_a_transport_error_is_retried_with_the_same_idempotency_key(
    monkeypatch: pytest.MonkeyPatch, sleeps: AsyncMock
) -> None:
    exness = _Exness([httpx.ConnectError("boom"), httpx.Response(202, json={"ok": True})])
    client = _client(exness, monkeypatch, exness_live_trading=True)

    body = await client.call(
        "openPosition", json_body={"instrument": "XAUUSD"}, idempotency_key="order-00001"
    )

    assert body == {"ok": True}
    first, second = exness.other()
    assert first.headers["EXN-IDEMPOTENCY-KEY"] == second.headers["EXN-IDEMPOTENCY-KEY"]
    assert second.headers["EXN-IDEMPOTENCY-KEY"] == "order-00001"
    assert _decoded_data(second)["body_hash"] == body_hash(second.content)
    assert second.headers["Content-Type"] == "application/json"


T = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


async def test_an_order_whose_deadline_passes_during_the_pacer_wait_is_not_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exness = _Exness()
    client = _client(exness, monkeypatch, exness_live_trading=True)
    pacer = await client._pacer_for("openPosition")

    async def late_wait() -> None:
        set_simulation_time(T + timedelta(seconds=2))

    monkeypatch.setattr(pacer, "wait", late_wait)
    try:
        set_simulation_time(T)
        with pytest.raises(ExnessApiError) as exc:
            await client.call(
                "openPosition",
                json_body={"instrument": "XAUUSD"},
                idempotency_key="k",
                deadline=T + timedelta(seconds=1),
            )
    finally:
        clear_simulation_time()

    assert exc.value.code == "ORDER_DEADLINE"
    assert [r for r in exness.other() if r.method == "POST"] == []


async def test_a_transport_error_is_not_resent_after_the_deadline(
    monkeypatch: pytest.MonkeyPatch, sleeps: AsyncMock
) -> None:
    exness = _Exness([httpx.ConnectError("boom"), httpx.Response(202, json={"ok": True})])
    client = _client(exness, monkeypatch, exness_live_trading=True)
    sleeps.side_effect = lambda _s: set_simulation_time(T + timedelta(seconds=2))
    try:
        set_simulation_time(T)
        with pytest.raises(ExnessApiError) as exc:
            await client.call(
                "openPosition",
                json_body={"instrument": "XAUUSD"},
                idempotency_key="k",
                deadline=T + timedelta(seconds=1),
            )
    finally:
        clear_simulation_time()

    assert exc.value.code == "TRANSPORT"
    assert len([r for r in exness.other() if r.method == "POST"]) == 1


async def test_a_rate_limited_data_call_is_retried_with_backoff(
    monkeypatch: pytest.MonkeyPatch, sleeps: AsyncMock
) -> None:
    ok = httpx.Response(200, json={"candles": [1]})
    exness = _Exness([httpx.Response(429), httpx.Response(429), ok])
    client = _client(exness, monkeypatch)

    with structlog.testing.capture_logs() as logs:
        body = await client.call("getCandleHistory", params=CANDLES)

    assert body == {"candles": [1]}
    assert len(exness.other()) == 3
    assert _delays(sleeps) == [1, 2]
    assert [e["event"] for e in logs].count("exness.rate_limited_retry") == 2


async def test_a_data_call_gives_up_after_three_rate_limit_retries(
    monkeypatch: pytest.MonkeyPatch, sleeps: AsyncMock
) -> None:
    exness = _Exness([httpx.Response(429)] * 4)
    client = _client(exness, monkeypatch)

    with pytest.raises(ExnessApiError) as exc:
        await client.call("getCandleHistory", params=CANDLES)

    assert (exc.value.status, exc.value.code) == (429, "REQUEST_RATE_LIMIT")
    assert len(exness.other()) == 4
    assert _delays(sleeps) == [1, 2, 4]


async def test_retry_after_sets_the_rate_limit_delay(
    monkeypatch: pytest.MonkeyPatch, sleeps: AsyncMock
) -> None:
    exness = _Exness([httpx.Response(429, headers={"Retry-After": "3"})])
    client = _client(exness, monkeypatch)

    await client.call("getCandleHistory", params=CANDLES)

    assert _delays(sleeps) == [3]


async def test_a_rate_limited_order_call_is_never_retried(
    monkeypatch: pytest.MonkeyPatch, sleeps: AsyncMock
) -> None:
    exness = _Exness([httpx.Response(429)])
    client = _client(exness, monkeypatch, exness_live_trading=True)

    with structlog.testing.capture_logs() as logs:
        with pytest.raises(ExnessApiError) as exc:
            await client.call(
                "openPosition", json_body={"instrument": "XAUUSD"}, idempotency_key="o-1"
            )

    assert exc.value.code == "REQUEST_RATE_LIMIT"
    assert len(exness.other()) == 1
    assert "exness.rate_limited_retry" not in [e["event"] for e in logs]
    assert "exness.rate_limited" in [e["event"] for e in logs]
    assert _delays(sleeps) == []


def _fake_time() -> tuple[list[float], Callable[[], float]]:
    now = [0.0]
    return now, lambda: now[0]


async def test_the_pacer_spaces_requests_by_its_interval() -> None:
    now, clock = _fake_time()

    async def advance(delay: float) -> None:
        now[0] += delay

    pacer = _RequestPacer(0.6, clock=clock, sleep=advance)
    starts = []
    for _ in range(3):
        await pacer.wait()
        starts.append(now[0])

    assert all(b - a >= 0.6 - 1e-9 for a, b in zip(starts, starts[1:], strict=False))


async def test_three_order_waits_leave_point_three_apart() -> None:
    now, clock = _fake_time()

    async def advance(delay: float) -> None:
        now[0] += delay

    pacer = _RequestPacer(0.3, clock=clock, sleep=advance)
    starts = []
    for _ in range(3):
        await pacer.wait()
        starts.append(now[0])

    assert starts == pytest.approx([0.0, 0.3, 0.6])


def test_order_request_interval_uses_the_order_limits() -> None:
    assert order_request_interval(LIMITS, 0.6) == pytest.approx(0.3)
    assert order_request_interval(LIMITS, 0.05) == pytest.approx(2.4)


async def test_order_calls_use_their_own_lane(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(_Exness(), monkeypatch, paced=True, exness_rate_fraction=0.6)

    order = await client._pacer_for("openPosition")

    assert order is await client._pacer_for("getOperationStatus")
    assert order.min_interval_s == pytest.approx(0.3)
    data = await client._pacer_for("getCandleHistory")
    assert data is not order
    assert data.min_interval_s == pytest.approx(1.0)


async def test_the_rate_fraction_widens_the_pacer_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exness = _Exness()
    client = _client(exness, monkeypatch, paced=True, exness_rate_fraction=0.5)

    pacer = await client._pacer_for("getCandleHistory")

    assert pacer.min_interval_s == pytest.approx(1.2)


async def test_the_deals_window_stays_inside_the_history_age(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(_Exness(), monkeypatch)

    assert await client.deals_window_days() == 29


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
