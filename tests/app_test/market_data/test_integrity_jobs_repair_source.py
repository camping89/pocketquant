"""repair_integrity forwards source kwarg into the SyncSymbolCommand it calls on SyncService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pocketquant.core.domain.bar.entities import SOURCE_REST_REPAIR
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.engine.market_data.app_services.integrity_jobs import repair_integrity
from pocketquant.engine.market_data.sync_service import SyncService, SyncSymbolCommand


@pytest.mark.asyncio
async def test_repair_integrity_sends_command_with_source() -> None:
    bar_repo = MagicMock()
    bar_repo.find_datetimes = AsyncMock(return_value=[])
    bar_repo.delete_many_by_ids = AsyncMock(return_value=0)

    sync_service = MagicMock(spec=SyncService)
    sync_service.sync_one = AsyncMock()

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
        sync_service=sync_service,
        source=SOURCE_REST_REPAIR,
        days_back=1,
    )

    # sync_service.sync_one must have been called with a SyncSymbolCommand carrying source.
    assert sync_service.sync_one.await_count >= 1
    sent_cmd = sync_service.sync_one.await_args.args[0]
    assert isinstance(sent_cmd, SyncSymbolCommand)
    assert sent_cmd.source == SOURCE_REST_REPAIR
    assert sent_cmd.skip_filter is True
    assert "gaps_resynced" in result
