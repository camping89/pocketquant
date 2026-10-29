from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pocketquant.core.domain.symbol import LINEAR_SPEC, ContractSpec


@dataclass
class BacktestConfig:
    strategy_code: str
    symbol: str
    interval: str
    start_date: datetime
    end_date: datetime
    initial_capital: float = 10_000.0
    slippage_bps: float = 0.5  # 0.5 bp = 0.005% default
    commission_bps: float = 3.0  # 3 bps default
    # Bars are bid prices; ask = bid + spread.
    spread: float = 0.0
    parameters: dict[str, Any] = field(default_factory=dict)
    name: str | None = None
    contract_spec: ContractSpec = LINEAR_SPEC

    @property
    def slippage_percent(self) -> float:
        return self.slippage_bps / 10_000
