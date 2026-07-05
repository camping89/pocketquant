"""CollectedResults — output of BacktestReportAppService.finalize().

Holds the slimmed ``BacktestResult`` plus the standalone ``OrderRecord`` and
``Trade`` lists that will be persisted to their dedicated MongoDB collections.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pocketquant.core.domain.backtest import BacktestResult
from pocketquant.core.domain.order import OrderRecord
from pocketquant.core.domain.trading import Trade


@dataclass
class CollectedResults:
    """Bundle returned by ResultCollector.finalize().

    - ``run``    : slim BacktestResult (metrics + equity_curve + open_positions)
    - ``orders`` : every OrderRecord observed, with embedded events[]+fills[]
    - ``trades`` : closed round-trip trades

    BacktestAppService persists these to 3 collections in order
    (orders → trades → run) then returns ``run`` to the caller.
    """

    run: BacktestResult
    orders: list[OrderRecord] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)
