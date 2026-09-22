"""TradingView mapper tests — the naive-local-time trap, closed on any host.

``tvDatafeed`` builds every DataFrame index entry with
``datetime.fromtimestamp(...)`` and no timezone, and does not re-expose the raw
epoch. A bar's instant therefore depends on the zone of the host that fetched
it, and this suite is what proves our recovery of the true epoch does not.

The fixture epochs straddle the 2026-03-08 US spring-forward deliberately.
Spring forward *skips* local times, so every instant still maps to exactly one
local time and the naive round trip is exact. The autumn fall-back is the
ambiguous direction, where ``naive.timestamp()`` would resolve to ``fold=0`` and
could be an hour out — it cannot bite here, because the ambiguous 01:00-02:00
window lands on a Sunday morning while CME equity-index futures are shut. Moving
this fixture to a November transition would break these tests for a real reason.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import tvDatafeed

from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.tradingview.tradingview_client_interface import RawBar
from pocketquant.core.infra.tradingview.tradingview_mappers import (
    INTERVAL_TO_TRADINGVIEW,
    raw_bar_to_bar,
    split_futures_symbol,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "es_1h_raw.json"


def _raw_bars() -> list[RawBar]:
    rows = json.loads(_FIXTURE.read_text())
    return [RawBar(**row) for row in rows]


def test_split_es_futures_symbol() -> None:
    assert split_futures_symbol("ES1!:CME_MINI") == ("ES", "CME_MINI", 1)


def test_split_non_futures_symbol() -> None:
    assert split_futures_symbol("BTCUSDT:BINANCE") == ("BTCUSDT", "BINANCE", None)


def test_split_rejects_a_symbol_with_no_exchange() -> None:
    """A bare code must fail loudly rather than reach the scraper as ':ES'."""
    with pytest.raises(ValueError, match="needs an exchange"):
        split_futures_symbol("ES1!")


def test_interval_map_is_total() -> None:
    assert set(INTERVAL_TO_TRADINGVIEW) == set(Interval)
    assert all(isinstance(v, tvDatafeed.Interval) for v in INTERVAL_TO_TRADINGVIEW.values())


def test_raw_bar_to_bar_is_utc_aware() -> None:
    for raw in _raw_bars():
        bar = raw_bar_to_bar(raw, "ES1!:CME_MINI", Interval.HOUR_1)
        assert bar.datetime is not None
        assert bar.datetime.tzinfo is UTC


def test_raw_bar_epoch_round_trip() -> None:
    for raw in _raw_bars():
        bar = raw_bar_to_bar(raw, "ES1!:CME_MINI", Interval.HOUR_1)
        assert bar.datetime is not None
        assert bar.datetime.timestamp() == raw.epoch_seconds


def test_naive_local_datetime_recovers_the_same_epoch() -> None:
    """Mirror the library: build a naive host-local instant, recover the epoch.

    This is the assertion that makes the CI timezone matrix meaningful — it is
    the only one whose result depends on ``TZ``.
    """
    for raw in _raw_bars():
        naive = datetime.fromtimestamp(raw.epoch_seconds)  # noqa: DTZ006 — mirrors the library
        assert naive.tzinfo is None
        assert naive.timestamp() == raw.epoch_seconds
