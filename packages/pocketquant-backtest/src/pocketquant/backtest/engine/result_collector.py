"""Result collector - tracks equity and positions during backtest execution.

Uses FIFO lot tracking (see ``lot_tracker.py``) so long/short/scale-in/scale-out
/partial-fill/flip behave per Backtrader / QuantConnect convention.
"""

from __future__ import annotations

import logging
from datetime import datetime

from pocketquant.backtest.domain import (
    BacktestResult,
    EquityPoint,
    PositionRecord,
    TradeRecord,
)
from pocketquant.backtest.engine.lot_tracker import ConsumedLot, Direction, FillOutcome, LotTracker
from pocketquant.backtest.engine.metrics_builder import build_metrics
from pocketquant.backtest.optimization.models.backtest_config import BacktestConfig
from pocketquant.core.common.time.simulation import get_current_time
from pocketquant.core.domain.order import OrderSide
from pocketquant.core.infrastructure.brokers.models import OrderResult

logger = logging.getLogger(__name__)


class BacktestResultCollector:
    """Collects positions and equity snapshots during backtest, then calculates metrics.

    Equity is recorded only when a close (realized PnL) occurs.
    Commission uses ``BacktestConfig.commission_percent`` (decimal, e.g. 0.001 = 0.1%).
    """

    def __init__(self, config: BacktestConfig, initial_capital: float) -> None:
        self._config = config
        self._initial_capital = initial_capital
        self._current_equity = initial_capital
        self._peak_equity = initial_capital

        self._equity_curve: list[EquityPoint] = []
        self._trades: list[TradeRecord] = []
        self._closed_positions: list[PositionRecord] = []
        self._total_commission = 0.0

        self._lot_tracker = LotTracker()

        # Initial equity point at backtest start
        self._equity_curve.append(
            EquityPoint(
                timestamp=datetime.combine(config.start_date, datetime.min.time()),
                equity=initial_capital,
                drawdown=0.0,
            )
        )

    async def on_fill(self, result: OrderResult) -> None:
        """Handle order fill — update FIFO lots, emit closed PositionRecords, append equity points."""
        if result.filled_quantity is None or result.filled_quantity <= 0:
            return
        fill_price = result.filled_price or 0.0
        fill_qty = result.filled_quantity
        if fill_price <= 0:
            return

        timestamp = get_current_time()
        commission = fill_price * fill_qty * self._config.commission_percent
        self._total_commission += commission
        # Debit commission from equity immediately on every fill (matches legacy behavior)
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

        # Emit one closed PositionRecord per consumed lot (also updates equity with realized PnL)
        self._emit_closed_positions(outcome, exit_price=fill_price, exit_time=timestamp)
        # If fill was pure open (no consumed lots) still record an equity point
        if not outcome.consumed:
            self._record_equity_point(timestamp)

        # Always record TradeRecord (legacy use)
        self._trades.append(
            TradeRecord(
                order_id=result.order_id,
                symbol=self._config.symbol,
                side="BUY" if side_dir == "LONG" else "SELL",
                quantity=fill_qty,
                price=fill_price,
                commission=commission,
                pnl=sum(self._consumed_pnl(c, fill_price) for c in outcome.consumed),
                timestamp=timestamp,
                sl_price=result.sl_price if outcome.opened is not None else None,
                tp_price=result.tp_price if outcome.opened is not None else None,
            )
        )

    def _resolve_side(self, result: OrderResult) -> Direction:
        """Pick LONG/SHORT direction for this fill.

        Prefer ``OrderResult.side`` (BUY→LONG, SELL→SHORT). Fallback: infer from
        current lot state (legacy behavior — long-only assumption).
        """
        if result.side == OrderSide.BUY:
            return "LONG"
        if result.side == OrderSide.SELL:
            return "SHORT"
        # Fallback for legacy fills missing side
        logger.warning(
            "OrderResult.side missing on fill %s; falling back to long-only inference",
            result.order_id,
        )
        return "SHORT" if self._lot_tracker.has_long_lot() else "LONG"

    def _emit_closed_positions(
        self, outcome: FillOutcome, exit_price: float, exit_time: datetime
    ) -> None:
        for consumed in outcome.consumed:
            pnl = self._consumed_pnl(consumed, exit_price)
            # Commission already debited at each fill (entry + exit) — only add realized PnL here
            self._current_equity += pnl
            commission = consumed.entry_commission_portion + consumed.exit_commission_portion

            self._closed_positions.append(
                PositionRecord(
                    symbol=self._config.symbol,
                    direction=consumed.lot.direction,
                    entry_price=consumed.lot.entry_price,
                    entry_time=consumed.lot.entry_time,
                    quantity=consumed.qty_closed,
                    sl_price=consumed.lot.sl_price,
                    tp_price=consumed.lot.tp_price,
                    exit_price=exit_price,
                    exit_time=exit_time,
                    pnl=pnl,
                    commission=commission,
                )
            )
            self._record_equity_point(exit_time)

    def _record_equity_point(self, timestamp: datetime) -> None:
        if self._current_equity > self._peak_equity:
            self._peak_equity = self._current_equity
        drawdown = 0.0
        if self._peak_equity > 0:
            drawdown = (self._current_equity - self._peak_equity) / self._peak_equity
        self._equity_curve.append(
            EquityPoint(timestamp=timestamp, equity=self._current_equity, drawdown=drawdown)
        )

    @staticmethod
    def _consumed_pnl(consumed: ConsumedLot, exit_price: float) -> float:
        """PnL for one consumed lot. Commission excluded — added by caller."""
        if consumed.lot.direction == "LONG":
            return (exit_price - consumed.lot.entry_price) * consumed.qty_closed
        return (consumed.lot.entry_price - exit_price) * consumed.qty_closed

    def finalize(
        self,
        run_id: str,
        started_at: datetime,
        completed_at: datetime,
        status: str = "completed",
        error_message: str | None = None,
    ) -> BacktestResult:
        """Finalize backtest and calculate all metrics."""
        positions = self._build_positions()
        metrics = build_metrics(
            closed_positions=self._closed_positions,
            equity_curve=self._equity_curve,
            initial_capital=self._initial_capital,
            current_equity=self._current_equity,
            total_commission=self._total_commission,
            start_date=self._config.start_date,
            end_date=self._config.end_date,
        )

        config_snapshot = {
            "strategy_id": self._config.strategy_id,
            "symbol": self._config.symbol,
            "interval": self._config.interval,
            "start_date": self._config.start_date.isoformat(),
            "end_date": self._config.end_date.isoformat(),
            "initial_capital": self._config.initial_capital,
            "slippage_bps": self._config.slippage_bps,
            "commission_bps": self._config.commission_bps,
            "parameters": self._config.parameters,
        }

        return BacktestResult(
            id=run_id,
            strategy_id=self._config.strategy_id,
            config_snapshot=config_snapshot,
            metrics=metrics,
            equity_curve=self._equity_curve,
            trades=self._trades,
            positions=positions,
            started_at=started_at,
            completed_at=completed_at,
            status=status,
            error_message=error_message,
            parameters=self._config.parameters,
        )

    def _build_positions(self) -> list[PositionRecord]:
        """Closed positions + still-open lots as PositionRecord(exit_price=None)."""
        result: list[PositionRecord] = list(self._closed_positions)
        for lot in self._lot_tracker.lots:
            if lot.qty_remaining <= 1e-12:
                continue
            # Entry commission for still-open lots is proportional to qty_remaining
            entry_comm_portion = (
                lot.entry_commission * (lot.qty_remaining / lot.qty_original)
                if lot.qty_original > 0
                else 0.0
            )
            result.append(
                PositionRecord(
                    symbol=self._config.symbol,
                    direction=lot.direction,
                    entry_price=lot.entry_price,
                    entry_time=lot.entry_time,
                    quantity=lot.qty_remaining,
                    sl_price=lot.sl_price,
                    tp_price=lot.tp_price,
                    exit_price=None,
                    exit_time=None,
                    pnl=0.0,
                    commission=entry_comm_portion,
                )
            )
        return result

