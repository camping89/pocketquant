from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pocketquant.core.domain.symbol import LINEAR_SPEC, ContractSpec


@dataclass
class BacktestConfig:
    strategy_code: str
    symbol: str
    intervals: list[str]
    start_date: datetime
    end_date: datetime
    initial_capital: float = 10_000.0
    slippage_bps: float = 0.1  # 0.1 bp = 0.001%, about 0.04 USD/oz on gold near 4000
    commission_bps: float = 3.0  # 3 bps default
    # Bars are bid prices; ask = bid + spread.
    spread: float = 0.0
    parameters: dict[str, Any] = field(default_factory=dict)
    name: str | None = None
    contract_spec: ContractSpec = LINEAR_SPEC

    @property
    def slippage_percent(self) -> float:
        return self.slippage_bps / 10_000
