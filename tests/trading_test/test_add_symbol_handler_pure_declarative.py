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
from pocketquant.core.domain.subscription import Subscription
from pocketquant.trading.handlers.strategy.add_symbol.command import AddSymbolCommand
from pocketquant.trading.handlers.strategy.add_symbol.handler import AddSymbolHandler


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
async def test_persists_subscription_keyed_by_deterministic_id() -> None:
    handler, sub_add, _ = _make_handler(tracked_exists=True)

    result = await handler.handle(
        AddSymbolCommand(strategy_id="hitnrun2", symbol="BTCUSDT:BINANCE", interval="1h")
    )

    expected_sub_id = Subscription.deterministic_id("hitnrun2", "BTCUSDT:BINANCE", "1h")
    sub_add.assert_awaited_once()
    assert sub_add.await_args is not None
    persisted: Any = sub_add.await_args.args[0]
    assert persisted.id == expected_sub_id
    assert persisted.strategy_code == "hitnrun2"
    assert persisted.desired_state == "stopped"
    assert persisted.actual_state == "stopped"
    assert result["id"] == expected_sub_id
    assert result["strategy_code"] == "hitnrun2"


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
