"""SyncSymbolCommand.source is a required field — Pydantic validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pocketquant.core.domain.shared.enums import Interval
from pocketquant.engine.market_data.sync_service import SyncSymbolCommand


def test_missing_source_raises_validation_error() -> None:
    with pytest.raises(ValidationError) as excinfo:
        SyncSymbolCommand(symbol="BTCUSDT:BINANCE", interval=Interval.MINUTE_1)  # pyright: ignore[reportCallIssue]
    assert "source" in str(excinfo.value)


def test_source_accepts_arbitrary_string() -> None:
    cmd = SyncSymbolCommand(
        symbol="BTCUSDT:BINANCE",
        interval=Interval.MINUTE_1,
        source="rest_sync_1m",
    )
    assert cmd.source == "rest_sync_1m"


def test_source_accepts_custom_label() -> None:
    cmd = SyncSymbolCommand(
        symbol="BTCUSDT:BINANCE",
        interval=Interval.MINUTE_1,
        source="my_label",
    )
    assert cmd.source == "my_label"
