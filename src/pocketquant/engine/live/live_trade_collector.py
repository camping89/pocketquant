"""LiveTradeCollector — persists round-trip Trades during live/paper trading.

EventBus subscriber. Each ``TradeClosedEvent`` (which carries its own
``subscription_id``) is mapped to a ``Trade`` with ``run_id`` = subscription_id
and appended to the live ``trades`` collection. Unlike the backtest collector it
keeps no equity ledger — metrics are derived on demand (LiveMetricsQueryService).

N subscriptions sharing one broker are attributed correctly: the event, not the
broker, carries the ``subscription_id``, so a single broker→bus forward feeds
every subscription's trades through this one handler.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.messaging import EventBus, event_handler, get_event_registry
from pocketquant.core.common.uuid import generate_id
from pocketquant.core.domain.position import TradeClosedEvent
from pocketquant.core.domain.trading import Trade
from pocketquant.core.infra.persistence.repositories.trade_repository import TradeRepository
from pocketquant.engine.strategy.strategy_app_service import StrategyAppService

logger = get_logger(__name__)


class LiveTradeCollector:
    """Bus-subscriber that turns live ``TradeClosedEvent``s into persisted Trades.

    Args:
        event_bus: Global bus the live broker forwards trade closures onto.
        trade_repo: Live ``trades`` persistence.
        strategy_service: In-memory config lookup for ``strategy_code`` (free —
            no Mongo hit); keyed by the subscription id the event carries.
    """

    def __init__(
        self,
        event_bus: EventBus,
        trade_repo: TradeRepository,
        strategy_service: StrategyAppService,
    ) -> None:
        self._event_bus = event_bus
        self._trade_repo = trade_repo
        self._strategy_service = strategy_service

    async def start(self) -> None:
        """Subscribe the trade handler to the global bus (mirrors StrategyAppService)."""
        get_event_registry().register_instance(self, self._event_bus)
        logger.info("live_trade_collector_started")

    @event_handler(TradeClosedEvent)
    async def _on_trade_closed(self, event: TradeClosedEvent) -> None:
        # Single-underscore name is required: EventRegistry.register_instance only
        # scans ``_``-prefixed methods for @event_handler bindings.
        config = self._strategy_service.get_config(event.subscription_id)
        strategy_code = config.name if config else ""
        exit_time = event.exit_time or datetime.now(UTC)
        trade = Trade(
            trade_id=generate_id(),
            run_id=event.subscription_id,
            strategy_code=strategy_code,
            symbol=event.symbol,
            direction=event.direction,
            entry_order_id=event.entry_order_id,
            entry_price=event.entry_price,
            entry_time=event.entry_time or exit_time,
            quantity=event.quantity,
            exit_order_id=event.exit_order_id,
            exit_price=event.exit_price,
            exit_time=exit_time,
            sl_price=event.sl_price,
            tp_price=event.tp_price,
            pnl=event.pnl,
            commission=event.commission,
            duration_seconds=event.duration_seconds,
        )
        # Error boundary (mirrors sibling bus handlers): this runs inside the
        # broker's synchronous dispatch chain, which re-raises. An unguarded Mongo
        # failure would abort the remaining subscribers of the triggering bus event
        # AND lose the closed Trade. Swallow + log — the broker RAM already advanced.
        try:
            await self._trade_repo.save_many([trade])
        except Exception as exc:
            logger.error(
                "live_trade_persist_failed",
                subscription_id=event.subscription_id,
                pnl=event.pnl,
                error=str(exc),
            )
            return
        logger.debug(
            "live_trade_persisted", subscription_id=event.subscription_id, pnl=event.pnl
        )
