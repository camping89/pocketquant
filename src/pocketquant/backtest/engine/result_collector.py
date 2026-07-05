"""Result collector — builds Orders + Trades + OpenLots during backtest replay.

Subscribes to PaperBroker via two channels:
- ``on_fill(OrderResult)``  → upsert Order, append Fill, feed FIFO lot tracker,
                              emit one ``Trade`` per consumed lot
- ``on_event(order_id, OrderEvent)`` → append OrderEvent to the Order, mirror
                                       Order.status / last_updated_at

At ``finalize()`` returns ``CollectedResults(run, orders, trades)`` where
``run`` is the slimmed ``BacktestResult`` (metrics + equity_curve + open_positions)
and ``orders``/``trades`` are persisted to dedicated collections by the caller.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from pocketquant.backtest.engine.collected_results import CollectedResults
from pocketquant.backtest.engine.lot_tracking_helper import (
    ConsumedLot,
    Direction,
    FillOutcome,
    LotTrackingHelper,
)
from pocketquant.backtest.engine.metrics_builder import build_metrics
from pocketquant.backtest.models.backtest_config import BacktestConfig
from pocketquant.core.common.time.simulation import get_current_time
from pocketquant.core.common.uuid import generate_id
from pocketquant.core.domain.backtest import (
    BacktestMetrics,
    BacktestResult,
    EquityPoint,
    Fill,
    OpenLot,
    Order,
    Trade,
)
from pocketquant.core.domain.brokers.events import OrderEvent
from pocketquant.core.domain.order import OrderSide, OrderStatus, OrderType
from pocketquant.core.domain.shared.enums import Interval

logger = logging.getLogger(__name__)

# 1m × 2y ≈ 1.1M points blows past Mongo's 16MB doc cap; cap the persisted curve
# while keeping every trade-carrying point. Sharpe is computed on the full
# in-memory series before downsampling.
_MAX_PERSISTED_EQUITY_POINTS = 5000


class BacktestResultCollector:
    """Collects Orders + Trades + equity snapshots during backtest, then computes metrics.

    Equity is recorded on close (realized PnL) and on pure opens (for drawdown
    granularity). Commission uses ``BacktestConfig.commission_percent`` and is
    debited from equity at every fill.
    """

    def __init__(
        self,
        config: BacktestConfig,
        initial_capital: float,
        run_id: str | None = None,
    ) -> None:
        self._config = config
        self._initial_capital = initial_capital
        self._current_equity = initial_capital
        self._peak_equity = initial_capital
        self._run_id = run_id or ""

        self._equity_curve: list[EquityPoint] = []
        # Per-bar mark-to-market curve (realized + unrealized), filled by
        # ``mark_to_market`` once per bar. Sharpe/Sortino annualize off this even
        # series; ``_equity_curve`` (realized-only, trade-keyed) drives
        # total_return/cagr/max_drawdown unchanged.
        self._mtm_curve: list[EquityPoint] = []
        self._orders_by_id: dict[str, Order] = {}
        self._trades: list[Trade] = []
        self._total_commission = 0.0

        self._lot_tracker = LotTrackingHelper()

        self._equity_curve.append(
            EquityPoint(
                timestamp=config.start_date,
                equity=initial_capital,
                drawdown=0.0,
            )
        )

    def set_run_id(self, run_id: str) -> None:
        self._run_id = run_id

    async def on_fill(self, result: Any) -> None:
        if result.filled_quantity is None or result.filled_quantity <= 0:
            self._upsert_order_status(result)  # still mirror status (CANCELLED/EXPIRED)
            return
        fill_price = result.filled_price or 0.0
        fill_qty = result.filled_quantity
        if fill_price <= 0:
            return

        timestamp = get_current_time()
        commission = fill_price * fill_qty * self._config.commission_percent
        self._total_commission += commission
        self._current_equity -= commission

        side_dir = self._resolve_side(result)
        outcome = self._lot_tracker.feed(
            side=side_dir,
            qty=fill_qty,
            price=fill_price,
            time=timestamp,
            order_id=result.order_id,
            commission=commission,
            sl_price=result.sl_price,
            tp_price=result.tp_price,
        )

        order = self._upsert_order(result, fill_price, fill_qty, commission, timestamp)
        self._append_fill(order, result, fill_price, fill_qty, commission, timestamp)

        self._emit_trades(
            outcome, exit_order_id=result.order_id, exit_price=fill_price, exit_time=timestamp
        )
        if not outcome.consumed:
            self._record_equity_point(timestamp)

    async def on_event(self, order_id: str, event: OrderEvent) -> None:
        """PaperBroker lifecycle event callback. Mirror status into Order."""
        order = self._orders_by_id.get(order_id)
        if order is None:
            # Order seen first via event before any fill — create a stub from event data.
            order = self._create_stub_order(order_id, event)
            self._orders_by_id[order_id] = order
        order.events.append(event)
        order.status = event.to_status
        order.last_updated_at = event.timestamp

    def _resolve_side(self, result: Any) -> Direction:
        if result.side == OrderSide.BUY:
            return "LONG"
        if result.side == OrderSide.SELL:
            return "SHORT"
        logger.warning(
            "OrderResult.side missing on fill %s; falling back to long-only inference",
            result.order_id,
        )
        return "SHORT" if self._lot_tracker.has_long_lot() else "LONG"

    def _upsert_order(
        self,
        result: Any,
        fill_price: float,
        fill_qty: float,
        commission: float,
        timestamp: datetime,
    ) -> Order:
        """Create or update an Order from a fill result.

        If a stub already exists (created via on_event before on_fill), backfill
        the authoritative side / quantity / sl_price / tp_price from this fill.
        Stubs are detected by their placeholder ``quantity == 0.0``.
        """
        side = result.side or (
            OrderSide.BUY if self._lot_tracker.has_long_lot() else OrderSide.SELL
        )
        existing = self._orders_by_id.get(result.order_id)
        if existing is not None:
            # Backfill stub fields the on_event handler couldn't know.
            if existing.quantity == 0.0:
                existing.side = side
                existing.quantity = fill_qty
                existing.sl_price = result.sl_price
                existing.tp_price = result.tp_price
            existing.last_updated_at = timestamp
            return existing
        order = Order(
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
        """Mirror a non-fill terminal status (CANCELLED / EXPIRED / REJECTED) onto the Order.

        Backfills `side` from the result when the existing entry is a stub
        (created via on_event before on_fill).
        """
        order = self._orders_by_id.get(result.order_id)
        if order is None:
            # Event callback may have created the stub already; if not, skip.
            return
        if order.quantity == 0.0 and result.side is not None:
            order.side = result.side
        order.status = result.status
        order.last_updated_at = get_current_time()

    def _create_stub_order(self, order_id: str, event: OrderEvent) -> Order:
        """Create a minimal Order from an early-arriving event (no fill yet)."""
        return Order(
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
        order: Order,
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
                slippage=0.0,  # PaperBroker bakes slippage into fill_price already
                timestamp=timestamp,
            )
        )

    def _emit_trades(
        self,
        outcome: FillOutcome,
        exit_order_id: str,
        exit_price: float,
        exit_time: datetime,
    ) -> None:
        for consumed in outcome.consumed:
            pnl = self._consumed_pnl(consumed, exit_price)
            self._current_equity += pnl
            commission = consumed.entry_commission_portion + consumed.exit_commission_portion
            duration = (exit_time - consumed.lot.entry_time).total_seconds()
            trade = Trade(
                trade_id=generate_id(),
                run_id=self._run_id,
                strategy_code=self._config.strategy_code,
                symbol=self._config.symbol,
                direction=consumed.lot.direction,
                entry_order_id=consumed.lot.entry_order_id,
                entry_price=consumed.lot.entry_price,
                entry_time=consumed.lot.entry_time,
                quantity=consumed.qty_closed,
                exit_order_id=exit_order_id,
                exit_price=exit_price,
                exit_time=exit_time,
                sl_price=consumed.lot.sl_price,
                tp_price=consumed.lot.tp_price,
                pnl=pnl,
                commission=commission,
                duration_seconds=duration,
            )
            self._trades.append(trade)
            self._record_equity_point(exit_time)
            # Back-link the exit order to its resulting trade.
            exit_order = self._orders_by_id.get(exit_order_id)
            if exit_order is not None and exit_order.resulting_trade_id is None:
                exit_order.resulting_trade_id = str(trade.trade_id)

    def _record_equity_point(self, timestamp: datetime) -> None:
        if self._current_equity > self._peak_equity:
            self._peak_equity = self._current_equity
        drawdown = 0.0
        if self._peak_equity > 0:
            drawdown = (self._current_equity - self._peak_equity) / self._peak_equity
        self._equity_curve.append(
            EquityPoint(timestamp=timestamp, equity=self._current_equity, drawdown=drawdown)
        )

    def mark_to_market(self, timestamp: datetime, total_equity: float) -> None:
        """Append a per-bar mark-to-market equity point — READ-ONLY accounting.

        ``total_equity`` is ``broker.get_balance().total_equity`` (realized
        balance + unrealized PnL), the broker's single source of truth. This
        feeds the per-bar return series Sharpe/Sortino annualize. It MUST NOT
        touch ``self._current_equity`` — that stays realized-only so
        ``total_return``/``cagr`` are unaffected. Drawdown here is marked against
        a separate MTM peak so the persisted curve's drawdown reflects unrealized
        swings without polluting realized accounting.

        Points carrying a trade (fill/exit, recorded via ``_record_equity_point``)
        are preserved at persist time; MTM points fill the gaps for even
        sampling.
        """
        self._mtm_curve.append(
            EquityPoint(timestamp=timestamp, equity=total_equity, drawdown=0.0)
        )

    def _downsample_equity_curve(self) -> list[EquityPoint]:
        """Curve to persist: per-bar MTM series (with drawdown), hard-capped at 5000.

        Uses the MTM curve when present (even per-bar sampling FE plots),
        otherwise the realized curve. Drawdown is recomputed across the chosen
        source. When the source exceeds the cap it is strided down while
        preferentially keeping trade-carrying timestamps (the equity break
        points). The result is then hard-sliced to the cap so the persisted doc
        can never exceed Mongo's size budget even with very many trades.
        """
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
        """Return ``curve`` with drawdown recomputed against a running peak."""
        out: list[EquityPoint] = []
        peak = float("-inf")
        for p in curve:
            peak = max(peak, p.equity)
            drawdown = (p.equity - peak) / peak if peak > 0 else 0.0
            out.append(EquityPoint(timestamp=p.timestamp, equity=p.equity, drawdown=drawdown))
        return out

    @staticmethod
    def _consumed_pnl(consumed: ConsumedLot, exit_price: float) -> float:
        if consumed.lot.direction == "LONG":
            return (exit_price - consumed.lot.entry_price) * consumed.qty_closed
        return (consumed.lot.entry_price - exit_price) * consumed.qty_closed

    def _build_open_positions(self) -> list[OpenLot]:
        out: list[OpenLot] = []
        for lot in self._lot_tracker.lots:
            if lot.qty_remaining <= 1e-12:
                continue
            entry_comm_portion = (
                lot.entry_commission * (lot.qty_remaining / lot.qty_original)
                if lot.qty_original > 0
                else 0.0
            )
            out.append(
                OpenLot(
                    symbol=self._config.symbol,
                    direction=lot.direction,
                    entry_price=lot.entry_price,
                    entry_time=lot.entry_time,
                    quantity=lot.qty_remaining,
                    sl_price=lot.sl_price,
                    tp_price=lot.tp_price,
                    entry_order_id=lot.entry_order_id,
                    entry_commission_portion=entry_comm_portion,
                )
            )
        return out

    def finalize(
        self,
        run_id: str,
        started_at: datetime,
        completed_at: datetime,
        status: str = "finished",
        error_message: str | None = None,
    ) -> CollectedResults:
        # Late-bind run_id onto stubs created before set_run_id was known.
        if not self._run_id:
            self._run_id = run_id
            for order in self._orders_by_id.values():
                if not order.run_id:
                    order.run_id = run_id
            for trade in self._trades:
                if not trade.run_id:
                    trade.run_id = run_id

        open_positions = self._build_open_positions()
        periods_per_year = Interval.periods_per_year_for(self._config.interval)
        if periods_per_year is None:
            logger.warning(
                "unknown interval %r — skipping Sharpe/Sortino annualization",
                self._config.interval,
            )
        metrics: BacktestMetrics = build_metrics(
            closed_trades=self._trades,
            equity_curve=self._equity_curve,
            initial_capital=self._initial_capital,
            current_equity=self._current_equity,
            total_commission=self._total_commission,
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
            "start_date": self._config.start_date.isoformat(),
            "end_date": self._config.end_date.isoformat(),
            "initial_capital": self._config.initial_capital,
            "slippage_bps": self._config.slippage_bps,
            "commission_bps": self._config.commission_bps,
            "parameters": self._config.parameters,
        }

        run = BacktestResult(
            # run_id circulates as str (Order/Trade FK fields); the entity PK is UUID.
            id=UUID(run_id),
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
        )
        return CollectedResults(
            run=run, orders=list(self._orders_by_id.values()), trades=list(self._trades)
        )
