"""Backtest value objects (Backtrader / QuantConnect naming).

- ``Fill``                — atomic execution event
- ``Trade``               — round-trip outcome (closed entry + exit)
- ``Order`` / ``OrderEvent`` — order intent with lifecycle audit trail
- ``OpenLot``             — still-open lot snapshot at run-end
- ``EquityPoint``         — equity curve point
- ``BacktestMetrics``     — performance summary
- ``OptimizationResultEntry`` — single optimizer grid entry
"""

from pocketquant.backtest.domain.value_objects.equity import EquityPoint
from pocketquant.backtest.domain.value_objects.fill import Fill
from pocketquant.backtest.domain.value_objects.metrics import BacktestMetrics
from pocketquant.backtest.domain.value_objects.open_lot import OpenLot
from pocketquant.backtest.domain.value_objects.optimization import OptimizationResultEntry
from pocketquant.backtest.domain.value_objects.order import Order, OrderEvent
from pocketquant.backtest.domain.value_objects.trade import Trade

__all__ = [
    "BacktestMetrics",
    "EquityPoint",
    "Fill",
    "OpenLot",
    "OptimizationResultEntry",
    "Order",
    "OrderEvent",
    "Trade",
]
