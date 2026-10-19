"""ExnessAdapter: pagination, in-progress filtering and error propagation."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from pocketquant.core.domain.bar.services.bar_builder_domain_service import get_bar_start
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.exness.exness_adapter import ExnessAdapter
from pocketquant.core.infra.exness.exness_client import ExnessApiError

FIXTURES = Path(__file__).parent / "fixtures"
CANDLES: list[dict[str, Any]] = json.loads(
    (FIXTURES / "candles_XAUUSD_M1.json").read_text(encoding="utf-8")
)["candles"]


def _limits(page: int) -> dict[str, Any]:
    limits = json.loads((FIXTURES / "limits.json").read_text(encoding="utf-8"))
    for method in limits["limits"]["rest"]["methods"]:
        if method["api_operation_id"] == "getCandleHistory":
            method["limits"]["max_candles_per_request"] = page
    return limits


def _client(candles: list[dict[str, Any]], page: int = 100) -> MagicMock:
    """A client answering ``count`` candles ending at ``from`` (inclusive), ascending."""

    async def call(op: str, *, params: dict[str, Any]) -> dict[str, Any]:
        assert op == "getCandleHistory"
        until = datetime.fromisoformat(params["from"])
        older = [c for c in candles if datetime.fromisoformat(c["time"]) <= until]
        return {"candles": older[params["count"] :]}

    client = MagicMock()
    client.limits = AsyncMock(return_value=_limits(page))
    client.call = AsyncMock(side_effect=call)
    return client


async def test_fetch_pages_backwards_by_the_published_page_size() -> None:
    client = _client(CANDLES)

    bars = await ExnessAdapter(client).fetch_ohlcv("XAUUSD:EXNESS", Interval.MINUTE_1, 250)

    params = [c.kwargs["params"] for c in client.call.await_args_list]
    assert [p["count"] for p in params] == [-100, -100, -50]
    assert all(p["instrument"] == "XAUUSD" and p["price_type"] == "bid" for p in params)
    times = [b.datetime for b in bars if b.datetime is not None]
    assert len(times) == len(bars)
    assert times == sorted(times)
    assert len(times) == len(set(times))
    assert all(b.symbol == "XAUUSD:EXNESS" for b in bars)


async def test_the_in_progress_candle_is_excluded() -> None:
    cutoff = get_bar_start(datetime.now(UTC), Interval.MINUTE_1)
    in_progress = copy.deepcopy(CANDLES[-1])
    in_progress["time"] = cutoff.isoformat()
    client = _client([*CANDLES[-5:], in_progress])

    bars = await ExnessAdapter(client).fetch_ohlcv("XAUUSD:EXNESS", Interval.MINUTE_1, 10)

    assert cutoff not in [b.datetime for b in bars]
    assert len(bars) == 5


async def test_the_in_progress_week_opens_on_sunday() -> None:
    now = datetime.now(UTC)
    this_week = (now - timedelta(days=(now.weekday() + 1) % 7)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    weeks = []
    for start in (this_week - timedelta(weeks=1), this_week):
        candle = copy.deepcopy(CANDLES[-1])
        candle["time"] = start.isoformat()
        weeks.append(candle)

    bars = await ExnessAdapter(_client(weeks)).fetch_ohlcv("XAUUSD:EXNESS", Interval.WEEK_1, 10)

    assert this_week.weekday() == 6
    assert [b.datetime for b in bars] == [this_week - timedelta(weeks=1)]


async def test_an_unknown_symbol_returns_nothing_without_a_call() -> None:
    client = _client(CANDLES)

    assert await ExnessAdapter(client).fetch_ohlcv("ZZZ:EXNESS", Interval.MINUTE_1, 10) == []
    client.call.assert_not_awaited()


async def test_a_client_error_propagates_without_an_adapter_retry() -> None:
    client = _client(CANDLES)
    client.call = AsyncMock(side_effect=ExnessApiError(429, "REQUEST_RATE_LIMIT", "x"))

    with pytest.raises(ExnessApiError):
        await ExnessAdapter(client).fetch_ohlcv("XAUUSD:EXNESS", Interval.MINUTE_1, 10)

    assert client.call.await_count == 1
