"""cascade_for_symbol passes source=SOURCE_CASCADE on every upsert_bar call."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from pocketquant.api.market_data.app_services.cascade_aggregator import cascade_for_symbol
from pocketquant.core.domain.bar.entities import SOURCE_CASCADE, Bar
from pocketquant.core.domain.shared.enums import Interval


def _make_1m_bars(n: int = 60) -> list[Bar]:
    base = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    return [
        Bar(
            symbol="BTCUSDT:BINANCE",
            interval=Interval.MINUTE_1,
            datetime=base + timedelta(minutes=i),
            open=1.0,
            high=2.0,
            low=0.5,
            close=1.5,
            volume=10.0,
            tick_count=1,
        )
        for i in range(n)
    ]


@pytest.mark.asyncio
async def test_cascade_for_symbol_passes_source_cascade() -> None:
    bar_repo = AsyncMock()
    bar_repo.find = AsyncMock(return_value=_make_1m_bars(60))
    bar_repo.upsert_bar = AsyncMock()

    await cascade_for_symbol(
        symbol="BTCUSDT:BINANCE",
        lookback_minutes=60,
        bar_repo=bar_repo,
    )

    assert bar_repo.upsert_bar.await_count > 0
    for call in bar_repo.upsert_bar.await_args_list:
        assert call.kwargs.get("source") == SOURCE_CASCADE
