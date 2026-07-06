"""LiveMetricsQueryService — on-demand performance metrics per subscription (M1).

Reads persisted live Trades, builds a cumulative-PnL equity curve anchored at the
paper account nominal, and runs the shared PerformanceCalculatorDomainService.
Stateless — recomputes from the ``trades`` collection every call.

Model M1 (relative-per-sub):
- Equity curve is trade-keyed (one point per closure), anchored at the paper
  account nominal. A positive anchor keeps ``max_drawdown``'s relative formula
  finite — a zero anchor divides by a zero/near-zero running peak → garbage
  (``-inf`` → ``np.nan_to_num`` → ``-1.79e308``).
- ``total_return``/``cagr`` are nulled: dividing one sub's PnL by the whole shared
  account understates its return, so an honest null beats a misleading number.
  ``max_drawdown`` is kept — a peak-to-trough giveback measured against the account
  nominal is a valid, bounded risk read (and finite by construction).
- ``sharpe_ratio``/``sortino_ratio`` are NOT annualized (``periods_per_year=None``):
  a trade-keyed curve has no fixed time step to annualize by. Passing bars/year
  (as backtest does for its even per-bar curve) would annualize per-*trade* returns
  by √(bars/year) and overstate Sharpe by orders of magnitude. A per-bar live
  equity sampler would be needed for a real annualized figure — out of scope; build
  returns 0.0 for both (its established "not annualizable" value).
"""

from __future__ import annotations

from typing import Any

from pocketquant.core.domain.trading import (
    EquityPoint,
    PerformanceCalculatorDomainService,
    PerformanceMetrics,
    Trade,
)
from pocketquant.core.infra.persistence.repositories.trade_repository import TradeRepository

# %-of-capital returns need a per-subscription starting capital, which live subs
# (sharing one account) do not have — these fields are nulled in the response.
_OMITTED_PERCENT_RETURNS = ("total_return", "cagr")


class LiveMetricsQueryService:
    def __init__(self, trade_repo: TradeRepository, baseline: float) -> None:
        self._trade_repo = trade_repo
        self._baseline = baseline

    async def get_metrics(self, subscription_id: str) -> dict[str, Any]:
        trades = await self._trade_repo.list_by_subscription(subscription_id)
        if not trades:
            return self._serialize(PerformanceMetrics.empty())

        equity_curve = self._equity_curve(trades)
        current_equity = self._baseline + sum(t.pnl for t in trades)
        total_commission = sum(t.commission for t in trades)

        metrics = PerformanceCalculatorDomainService.build(
            closed_trades=trades,
            equity_curve=equity_curve,
            initial_capital=self._baseline,
            current_equity=current_equity,
            total_commission=total_commission,
            start_date=trades[0].entry_time,
            end_date=trades[-1].exit_time,
            # Trade-keyed curve — no fixed bar step to annualize by (see module docstring).
            periods_per_year=None,
        )
        return self._serialize(metrics)

    def _equity_curve(self, trades: list[Trade]) -> list[EquityPoint]:
        """Baseline anchor + running cumulative PnL, one point per trade exit.

        ``trades`` arrive oldest-first (``list_by_subscription`` sorts entry_time).
        build recomputes drawdown against this curve's running peak.
        """
        points = [EquityPoint(timestamp=trades[0].entry_time, equity=self._baseline, drawdown=0.0)]
        equity = self._baseline
        for t in trades:
            equity += t.pnl
            points.append(EquityPoint(timestamp=t.exit_time, equity=equity, drawdown=0.0))
        return points

    @staticmethod
    def _serialize(metrics: PerformanceMetrics) -> dict[str, Any]:
        data = metrics.to_dict()
        for field in _OMITTED_PERCENT_RETURNS:
            data[field] = None
        return data
