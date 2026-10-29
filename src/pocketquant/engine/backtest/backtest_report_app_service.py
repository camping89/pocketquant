from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from pocketquant.core.common.time import to_utc_iso
from pocketquant.core.common.time.simulation import get_current_time
from pocketquant.core.common.uuid import generate_id
from pocketquant.core.domain.backtest import BacktestConfig, BacktestResult, OpenLot
from pocketquant.core.domain.brokers.broker_port import IBrokerPort
from pocketquant.core.domain.brokers.events import OrderEvent
from pocketquant.core.domain.market_data.trading_calendar_port import ITradingCalendarPort
from pocketquant.core.domain.order import OrderRecord, OrderSide, OrderStatus, OrderType
from pocketquant.core.domain.position import PositionAggregate, TradeClosedEvent
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.trading import (
    EquityPoint,
    Fill,
    PerformanceCalculatorDomainService,
    PerformanceMetrics,
    Trade,
)

logger = logging.getLogger(__name__)

# 1m × 2y ≈ 1.1M points blows past Mongo's 16MB doc cap; cap the persisted curve
# while keeping every trade-carrying point. Sharpe is computed on the full
# in-memory series before downsampling.
_MAX_PERSISTED_EQUITY_POINTS = 5000


@dataclass
class CollectedResults:
    run: BacktestResult
    orders: list[OrderRecord] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)


# Equity is read from broker.get_balance(): the broker's ledger is the only source,
# so this collector keeps none of its own. Commission is stamped on the Fill; the
# broker owns the balance debit.
class BacktestReportAppService:
    def __init__(
        self,
        config: BacktestConfig,
        initial_capital: float,
        broker: IBrokerPort,
        calendar: ITradingCalendarPort,
        run_id: str,
    ) -> None:
        self._config = config
        self._initial_capital = initial_capital
        self._broker = broker
        self._calendar = calendar
        self._run_id = run_id

        self._equity_curve: list[EquityPoint] = []
        # Per-bar mark-to-market curve (realized + unrealized), filled by
        # ``mark_to_market`` once per bar. Sharpe/Sortino annualize off this even
        # series; ``_equity_curve`` (realized-only, trade-keyed) drives
        # total_return/cagr/max_drawdown unchanged.
        self._mtm_curve: list[EquityPoint] = []
        self._orders_by_id: dict[str, OrderRecord] = {}
        self._trades: list[Trade] = []

        self._equity_curve.append(
            EquityPoint(
                timestamp=config.start_date,
                equity=initial_capital,
                drawdown=0.0,
            )
        )

    async def on_fill(self, result: Any) -> None:
        if result.filled_quantity is None or result.filled_quantity <= 0:
            self._upsert_order_status(result)  # still mirror status (CANCELLED/EXPIRED)
            return
        fill_price = result.filled_price or 0.0
        fill_qty = result.filled_quantity
        if fill_price <= 0:
            return

        timestamp = get_current_time()
        # Stamped on the Fill doc; the broker owns the balance debit.
        commission = result.commission

        order = self._upsert_order(result, fill_price, fill_qty, commission, timestamp)
        self._append_fill(order, result, fill_price, fill_qty, commission, timestamp)

    # Runs after the exit fill's on_fill (broker dispatch order), so the exit OrderRecord
    # already exists for the resulting_trade_id back-link. The broker updates its balance
    # under its lock before it dispatches, so get_balance() here is the post-close balance.
    async def on_trade(self, event: TradeClosedEvent) -> None:
        exit_time = event.exit_time or get_current_time()
        trade = Trade(
            trade_id=generate_id(),
            run_id=self._run_id,
            strategy_code=self._config.strategy_code,
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
        self._trades.append(trade)
        balance = await self._broker.get_balance()
        self._record_equity_point(exit_time, balance.available_balance)

        if event.exit_order_id is not None:
            exit_order = self._orders_by_id.get(event.exit_order_id)
            if exit_order is not None and exit_order.resulting_trade_id is None:
                exit_order.resulting_trade_id = str(trade.trade_id)

    async def on_event(self, order_id: str, event: OrderEvent) -> None:
        order = self._orders_by_id.get(order_id)
        if order is None:
            # OrderRecord seen first via event before any fill — create a stub from event data.
            order = self._create_stub_order(order_id, event)
            self._orders_by_id[order_id] = order
        order.events.append(event)
        order.status = event.to_status
        order.last_updated_at = event.timestamp

    def _upsert_order(
        self,
        result: Any,
        fill_price: float,
        fill_qty: float,
        commission: float,
        timestamp: datetime,
    ) -> OrderRecord:
        side = result.side or OrderSide.BUY  # broker sets side on every fill
        existing = self._orders_by_id.get(result.order_id)
        if existing is not None:
            # Backfill stub fields the on_event handler couldn't know.
            # A stub created by on_event is recognised by its placeholder quantity of 0.0.
            if existing.quantity == 0.0:
                existing.side = side
                existing.quantity = fill_qty
                existing.sl_price = result.sl_price
                existing.tp_price = result.tp_price
            existing.last_updated_at = timestamp
            return existing
        order = OrderRecord(
            order_id=UUID(result.order_id),
            run_id=self._run_id,
            strategy_code=self._config.strategy_code,
            symbol=self._config.symbol,
            side=side,
            # MARKET assumption; LIMIT path also fills as MARKET-on-cross
            order_type=OrderType.MARKET,
            quantity=fill_qty,
            price=None,
            sl_price=result.sl_price,
            tp_price=result.tp_price,
            status=OrderStatus.FILLED,
            submitted_at=result.submitted_at or timestamp,
            last_updated_at=timestamp,
        )
        self._orders_by_id[result.order_id] = order
        return order

    def _upsert_order_status(self, result: Any) -> None:
        order = self._orders_by_id.get(result.order_id)
        if order is None:
            # Event callback may have created the stub already; if not, skip.
            return
        if order.quantity == 0.0 and result.side is not None:
            order.side = result.side
        order.status = result.status
        order.last_updated_at = get_current_time()

    def _create_stub_order(self, order_id: str, event: OrderEvent) -> OrderRecord:
        return OrderRecord(
            order_id=UUID(order_id),
            run_id=self._run_id,
            strategy_code=self._config.strategy_code,
            symbol=self._config.symbol,
            side=OrderSide.BUY,  # unknown until fill; placeholder
            order_type=OrderType.MARKET,
            quantity=0.0,
            price=None,
            sl_price=None,
            tp_price=None,
            status=event.to_status,
            submitted_at=event.timestamp,
            last_updated_at=event.timestamp,
        )

    def _append_fill(
        self,
        order: OrderRecord,
        result: Any,
        fill_price: float,
        fill_qty: float,
        commission: float,
        timestamp: datetime,
    ) -> None:
        side = order.side if isinstance(order.side, OrderSide) else OrderSide(order.side)
        order.fills.append(
            Fill(
                fill_id=generate_id(),
                order_id=str(order.order_id),
                symbol=order.symbol,
                side=side,
                quantity=fill_qty,
                price=fill_price,
                commission=commission,
                slippage=0.0,  # PaperBrokerAdapter bakes slippage into fill_price already
                timestamp=timestamp,
            )
        )

    def _record_equity_point(self, timestamp: datetime, equity: float) -> None:
        # Drawdown is recomputed against a running peak at persist time
        # (``_with_drawdown``); the realized point only carries the equity value.
        self._equity_curve.append(EquityPoint(timestamp=timestamp, equity=equity, drawdown=0.0))

    # Read-only accounting: this feeds only the MTM curve behind the per-bar
    # Sharpe/Sortino returns. The realized curve is untouched, so total_return and
    # cagr stay realized-only.
    def mark_to_market(self, timestamp: datetime, total_equity: float) -> None:
        self._mtm_curve.append(EquityPoint(timestamp=timestamp, equity=total_equity, drawdown=0.0))

    # Over the cap the curve is strided down but keeps trade timestamps, the equity
    # break points. The cap is hard so the persisted doc stays inside Mongo's size
    # budget even with very many trades.
    def _downsample_equity_curve(self) -> list[EquityPoint]:
        source = self._mtm_curve if self._mtm_curve else self._equity_curve
        with_dd = self._with_drawdown(source)
        if len(with_dd) <= _MAX_PERSISTED_EQUITY_POINTS:
            return with_dd

        trade_timestamps = {p.timestamp for p in self._equity_curve}
        stride = len(with_dd) // _MAX_PERSISTED_EQUITY_POINTS + 1
        kept: list[EquityPoint] = []
        last = len(with_dd) - 1
        for i, point in enumerate(with_dd):
            if i % stride == 0 or i == last or point.timestamp in trade_timestamps:
                kept.append(point)
        if len(kept) <= _MAX_PERSISTED_EQUITY_POINTS:
            return kept
        # Trade points alone exceeded the cap — stride the kept set down too so
        # the cap is a hard guarantee (preserve first + last). Striding alone
        # yields ≤ cap points; swap the final sampled point for the true last so
        # the closing equity survives without growing the list past the cap.
        final_stride = len(kept) // _MAX_PERSISTED_EQUITY_POINTS + 1
        capped = kept[::final_stride]
        if capped[-1] is not kept[-1]:
            capped[-1] = kept[-1]
        return capped

    @staticmethod
    def _with_drawdown(curve: list[EquityPoint]) -> list[EquityPoint]:
        out: list[EquityPoint] = []
        peak = float("-inf")
        for p in curve:
            peak = max(peak, p.equity)
            drawdown = (p.equity - peak) / peak if peak > 0 else 0.0
            out.append(EquityPoint(timestamp=p.timestamp, equity=p.equity, drawdown=drawdown))
        return out

    @staticmethod
    def _position_to_open_lot(pos: PositionAggregate) -> OpenLot:
        # ``entry_commission`` is already the proportional remainder after any
        # partial reduce (drained in PositionAggregate.reduce_quantity).
        return OpenLot(
            symbol=pos.symbol,
            direction=pos.side.name,
            entry_price=pos.entry_price,
            entry_time=pos.opened_at,
            quantity=pos.quantity,
            sl_price=pos.sl_price,
            tp_price=pos.tp_price,
            entry_order_id=pos.entry_order_id,
            entry_commission_portion=pos.entry_commission,
        )

    async def finalize(
        self,
        started_at: datetime,
        completed_at: datetime,
        status: str = "finished",
        error_message: str | None = None,
        positions: list[PositionAggregate] | None = None,
    ) -> CollectedResults:
        open_positions = [
            self._position_to_open_lot(p) for p in (positions or []) if not p.is_closed
        ]
        # Annualization belongs to the symbol's calendar: an Exness FX year holds
        # 312 daily bars, not 365 days, and Sharpe scales by its square
        # root. A stale queued request can still carry an interval that is no
        # longer an Interval member, and that still skips scaling rather than
        # raising.
        try:
            interval = Interval(self._config.interval)
        except ValueError:
            periods_per_year = None
            logger.warning(
                "unknown interval %r — skipping Sharpe/Sortino annualization",
                self._config.interval,
            )
        else:
            periods_per_year = self._calendar.periods_per_year(interval)
        balance = await self._broker.get_balance()
        current_equity = balance.available_balance
        total_commission = sum(f.commission for o in self._orders_by_id.values() for f in o.fills)
        metrics: PerformanceMetrics = PerformanceCalculatorDomainService.build(
            closed_trades=self._trades,
            equity_curve=self._equity_curve,
            initial_capital=self._initial_capital,
            current_equity=current_equity,
            total_commission=total_commission,
            start_date=self._config.start_date,
            end_date=self._config.end_date,
            periods_per_year=periods_per_year,
            returns_curve=self._mtm_curve or None,
        )
        persisted_curve = self._downsample_equity_curve()

        config_snapshot = {
            "strategy_code": self._config.strategy_code,
            "symbol": self._config.symbol,
            "interval": self._config.interval,
            "start_date": to_utc_iso(self._config.start_date),
            "end_date": to_utc_iso(self._config.end_date),
            "initial_capital": self._config.initial_capital,
            "slippage_bps": self._config.slippage_bps,
            "commission_bps": self._config.commission_bps,
            "spread": self._config.spread,
            "parameters": self._config.parameters,
            "name": self._config.name,
        }

        run = BacktestResult(
            # run_id circulates as str (Order/Trade FK fields); the entity PK is UUID.
            id=UUID(self._run_id),
            strategy_code=self._config.strategy_code,
            config_snapshot=config_snapshot,
            metrics=metrics,
            equity_curve=persisted_curve,
            open_positions=open_positions,
            started_at=started_at,
            completed_at=completed_at,
            status=status,
            symbol=self._config.symbol.upper(),
            interval=self._config.interval,
            error_message=error_message,
            parameters=self._config.parameters,
            name=self._config.name,
        )
        return CollectedResults(
            run=run, orders=list(self._orders_by_id.values()), trades=list(self._trades)
        )
