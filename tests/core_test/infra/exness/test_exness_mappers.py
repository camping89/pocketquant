"""Exness mappers pinned against the recorded spike fixtures."""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.exness.exness_mappers import (
    EXNESS_INSTRUMENTS,
    candle_to_bar,
    composite_for,
    format_price,
    instrument_name,
    lots_to_units,
    tick_to_quote_dict,
    units_to_lots,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_candle_to_bar_maps_the_first_recorded_candle() -> None:
    candle = _load("candles_XAUUSD_M1.json")["candles"][0]

    bar = candle_to_bar(candle, "xauusd:exness", Interval.MINUTE_1)

    assert bar.symbol == "XAUUSD:EXNESS"
    assert bar.interval == Interval.MINUTE_1
    assert bar.datetime is not None
    assert bar.datetime.utcoffset() == timedelta(0)
    assert bar.close == candle["close"]
    assert bar.tick_count == int(candle["volume"])


def test_tick_to_quote_dict_uses_the_bid_as_last_price() -> None:
    tick = next(f for f in _load("ticks_sample.json") if "instrument" in f)

    quote = tick_to_quote_dict(tick, "XAUUSD:EXNESS")

    assert quote["last_price"] == tick["bid"]
    assert quote["bid"] == tick["bid"]
    assert quote["ask"] == tick["ask"]
    assert quote["timestamp"].tzinfo is not None
    assert quote["volume"] is None
    assert set(quote) == {
        "symbol",
        "timestamp",
        "last_price",
        "volume",
        "bid",
        "ask",
        "change",
        "change_percent",
        "open_price",
        "high_price",
        "low_price",
        "prev_close",
    }


def test_instrument_table_matches_the_recorded_names() -> None:
    summary = _load("summary.json")

    assert {f"{c}:EXNESS": n for c, n in summary["instrument_names"].items()} == (
        EXNESS_INSTRUMENTS
    )
    assert instrument_name("xauusd:exness") == "XAUUSD"
    assert instrument_name("XAUUSD:BINANCE") is None
    assert composite_for("XAUUSD") == "XAUUSD:EXNESS"
    assert composite_for("ZZZ") is None


def _xauusd_lots(quantity: str, max_lots: Decimal | None = None) -> Decimal | None:
    return units_to_lots(
        Decimal(quantity),
        contract_size=Decimal("100"),
        volume_min=Decimal("0.01"),
        volume_step=Decimal("0.01"),
        volume_max=Decimal("200"),
        max_lots=max_lots,
    )


def test_units_to_lots_follows_the_recorded_xauusd_grid() -> None:
    assert _xauusd_lots("0.5") is None
    assert _xauusd_lots("1") == Decimal("0.01")
    assert _xauusd_lots("7.9") == Decimal("0.01")
    assert _xauusd_lots("7.9", max_lots=Decimal("0.05")) == Decimal("0.05")


def test_lots_to_units_and_format_price() -> None:
    assert lots_to_units(Decimal("0.01"), Decimal("100")) == 1.0
    assert format_price(2345.678912, 3) == "2345.679"
