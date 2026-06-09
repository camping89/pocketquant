"""repair_integrity forwards source kwarg into the SyncSymbolCommand it sends."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pocketquant.execution.market_data.app_services.integrity_jobs import repair_integrity
from pocketquant.execution.market_data.handlers.sync import SyncSymbolCommand
from pocketquant.core.domain.bar.entities import SOURCE_REST_REPAIR
from pocketquant.core.domain.shared.enums import Interval


@pytest.mark.asyncio
async def test_repair_integrity_sends_command_with_source() -> None:
    bar_repo = MagicMock()
    bar_repo.find_datetimes = AsyncMock(return_value=[])
    bar_repo.delete_many_by_ids = AsyncMock(return_value=0)
    mediator = MagicMock()
    mediator.send = AsyncMock()

    # Force a "gap" so the resync command is built and dispatched.
    async def fake_find_datetimes(*_a, **_kw):
        return []

    # Patch check_integrity result indirectly: by having no docs AND a wide gap.
    # repair_integrity calls check_integrity which reads find_datetimes; empty list
    # → full window is a gap. Force the path that builds + sends the command.
    bar_repo.find_datetimes = AsyncMock(side_effect=fake_find_datetimes)

    result = await repair_integrity(
        symbol="BTCUSDT:BINANCE",
        interval=Interval.MINUTE_1,
        bar_repo=bar_repo,
        mediator=mediator,
        source=SOURCE_REST_REPAIR,
        days_back=1,
    )

    # mediator.send must have been called with a SyncSymbolCommand carrying source.
    assert mediator.send.await_count >= 1
    sent_cmd = mediator.send.await_args.args[0]
    assert isinstance(sent_cmd, SyncSymbolCommand)
    assert sent_cmd.source == SOURCE_REST_REPAIR
    assert sent_cmd.skip_filter is True
    assert "gaps_resynced" in result
