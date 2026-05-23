"""Unit tests for AddSymbolHandler auto-load behavior.

Verify that when a strategy template is in STRATEGY_REGISTRY but not yet
loaded into the engine, AddSymbol auto-loads it instead of returning 404.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.concepts.strategy.value_objects import StrategyConfig
from pocketquant.trading.handlers.strategy.add_symbol.command import AddSymbolCommand
from pocketquant.trading.handlers.strategy.add_symbol.handler import AddSymbolHandler


def _make_handler(
    *,
    tracked_exists: bool = True,
    loaded_strategy: Any = None,
) -> tuple[AddSymbolHandler, MagicMock, AsyncMock, AsyncMock]:
    strategy_service = MagicMock()
    strategy_service.get_strategy = MagicMock(return_value=loaded_strategy)
    strategy_service.load_strategy = AsyncMock(return_value="loaded-id")

    sub_repo = MagicMock()
    sub_repo.add = AsyncMock()

    tracked_repo = MagicMock()
    tracked_repo.exists = AsyncMock(return_value=tracked_exists)

    handler = AddSymbolHandler(
        strategy_app_service=strategy_service,
        strategy_subscription_repository=sub_repo,
        tracked_symbol_repository=tracked_repo,
    )
    return handler, strategy_service, sub_repo.add, tracked_repo.exists


@pytest.mark.asyncio
async def test_autoload_when_template_in_registry_and_not_loaded() -> None:
    handler, svc, sub_add, _ = _make_handler(tracked_exists=True, loaded_strategy=None)

    result = await handler.handle(
        AddSymbolCommand(
            strategy_id="ma_crossover",
            symbol="BTCUSDT:BINANCE",
            interval="1h",
        )
    )

    svc.load_strategy.assert_awaited_once()
    cfg = svc.load_strategy.await_args.args[0]
    assert isinstance(cfg, StrategyConfig)
    assert cfg.id == "ma_crossover"
    assert cfg.symbol == "BTCUSDT:BINANCE"
    assert cfg.interval == "1h"
    sub_add.assert_awaited_once()
    assert result["strategy_id"] == "ma_crossover"
    assert result["symbol"] == "BTCUSDT:BINANCE"
    assert result["interval"] == "1h"


@pytest.mark.asyncio
async def test_no_autoload_when_strategy_already_loaded() -> None:
    handler, svc, sub_add, _ = _make_handler(
        tracked_exists=True,
        loaded_strategy=MagicMock(),
    )

    await handler.handle(
        AddSymbolCommand(
            strategy_id="ma_crossover",
            symbol="BTCUSDT:BINANCE",
            interval="1h",
        )
    )

    svc.load_strategy.assert_not_called()
    sub_add.assert_awaited_once()


@pytest.mark.asyncio
async def test_404_when_unknown_template_and_not_loaded() -> None:
    handler, svc, _, _ = _make_handler(tracked_exists=True, loaded_strategy=None)

    with pytest.raises(NotFoundError):
        await handler.handle(
            AddSymbolCommand(
                strategy_id="does-not-exist",
                symbol="BTCUSDT:BINANCE",
                interval="1h",
            )
        )

    svc.load_strategy.assert_not_called()


@pytest.mark.asyncio
async def test_404_when_symbol_not_tracked() -> None:
    handler, svc, _, _ = _make_handler(tracked_exists=False, loaded_strategy=None)

    with pytest.raises(NotFoundError) as exc:
        await handler.handle(
            AddSymbolCommand(
                strategy_id="ma_crossover",
                symbol="BTCUSDT:BINANCE",
                interval="1h",
            )
        )
    assert exc.value.error_code == "SYMBOL_NOT_TRACKED"
    svc.load_strategy.assert_not_called()
