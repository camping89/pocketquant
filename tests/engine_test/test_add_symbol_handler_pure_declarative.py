"""Unit tests for AddSymbolHandler — pure-declarative persist (no RAM load).

After the app/bff split, add_symbol persists the subscription doc only. The app
control-plane (reconcile) materializes the runtime instance. The handler keeps
its fail-fast checks: unknown template → 404, untracked symbol → 404.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.uuid import UUID
from pocketquant.engine.strategy_command_service import AddSymbolCommand


class AddSymbolHandler:
    """Shim: map old Handler(sub_repo, tracked_repo) + handle(cmd) to StrategyCommandService."""

    def __init__(
        self,
        subscription_repository: Any,
        tracked_symbol_repository: Any,
    ) -> None:
        from unittest.mock import MagicMock

        from pocketquant.engine.strategy_command_service import StrategyCommandService

        self._svc = StrategyCommandService(
            subscription_repository=subscription_repository,
            backtest_repository=MagicMock(),
            backtest_request_repository=MagicMock(),
            tracked_symbol_repository=tracked_symbol_repository,
        )

    async def handle(self, request: Any) -> dict:
        return await self._svc.add_symbol(request)  # type: ignore[arg-type]


def _make_handler(
    *,
    tracked_exists: bool = True,
) -> tuple[AddSymbolHandler, AsyncMock, AsyncMock]:
    sub_repo = MagicMock()
    sub_repo.add = AsyncMock()

    tracked_repo = MagicMock()
    tracked_repo.exists = AsyncMock(return_value=tracked_exists)

    handler = AddSymbolHandler(
        subscription_repository=sub_repo,
        tracked_symbol_repository=tracked_repo,
    )
    return handler, sub_repo.add, tracked_repo.exists


@pytest.mark.asyncio
async def test_persists_subscription_keyed_by_uuid7() -> None:
    handler, sub_add, _ = _make_handler(tracked_exists=True)

    result = await handler.handle(
        AddSymbolCommand(strategy_id="hitnrun2", symbol="BTCUSDT:BINANCE", interval="1h")
    )

    sub_add.assert_awaited_once()
    assert sub_add.await_args is not None
    persisted: Any = sub_add.await_args.args[0]
    assert UUID(str(persisted.id)).version == 7
    assert persisted.strategy_code == "hitnrun2"
    assert persisted.desired_state == "stopped"
    assert persisted.actual_state == "stopped"
    assert result["id"] == str(persisted.id)
    assert result["strategy_code"] == "hitnrun2"


@pytest.mark.asyncio
async def test_two_adds_same_triple_get_distinct_ids() -> None:
    """Ids are random per add — dedup is the repo's compound index, not the id."""
    handler, sub_add, _ = _make_handler(tracked_exists=True)

    await handler.handle(
        AddSymbolCommand(strategy_id="hitnrun2", symbol="BTCUSDT:BINANCE", interval="1h")
    )
    await handler.handle(
        AddSymbolCommand(strategy_id="hitnrun2", symbol="BTCUSDT:BINANCE", interval="1h")
    )

    first, second = (call.args[0] for call in sub_add.await_args_list)
    assert first.id != second.id


@pytest.mark.asyncio
async def test_404_when_unknown_template() -> None:
    handler, sub_add, _ = _make_handler(tracked_exists=True)

    with pytest.raises(NotFoundError):
        await handler.handle(
            AddSymbolCommand(strategy_id="does-not-exist", symbol="BTCUSDT:BINANCE", interval="1h")
        )

    sub_add.assert_not_called()


@pytest.mark.asyncio
async def test_404_when_symbol_not_tracked() -> None:
    handler, sub_add, _ = _make_handler(tracked_exists=False)

    with pytest.raises(NotFoundError) as exc:
        await handler.handle(
            AddSymbolCommand(strategy_id="hitnrun2", symbol="BTCUSDT:BINANCE", interval="1h")
        )
    assert exc.value.error_code == "SYMBOL_NOT_TRACKED"
    sub_add.assert_not_called()
