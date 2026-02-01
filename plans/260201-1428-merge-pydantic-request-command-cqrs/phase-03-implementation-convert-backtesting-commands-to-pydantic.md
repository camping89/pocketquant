# Phase 3: Backtesting Commands

## Context

- Parent: [plan.md](plan.md)
- Depends on: Phase 1

## Overview

- **Priority:** P2
- **Status:** pending
- **Effort:** 30m

Convert backtesting commands from dataclass to Pydantic and simplify routes.

## Files to Modify

| File | Changes |
|------|---------|
| `src/features/backtesting/handlers/backtest_commands.py` | dataclass → Pydantic |
| `src/features/backtesting/api/backtest_routes.py` | Remove Request classes, use commands |

## Implementation Steps

### 1. Convert backtest_commands.py

Before:
```python
from dataclasses import dataclass

@dataclass
class RunBacktestCommand:
    strategy_id: str
    symbol: str
    ...
```

After:
```python
from pydantic import BaseModel, Field
from datetime import date
from typing import Any

class RunBacktestCommand(BaseModel):
    """Command to execute a single backtest run."""
    strategy_id: str = Field(..., description="Strategy identifier")
    symbol: str = Field(..., description="Trading symbol (e.g., BTCUSDT)")
    exchange: str = Field(..., description="Exchange name (e.g., OKX)")
    interval: str = Field(..., description="Bar interval (e.g., 5m, 1h)")
    start_date: date = Field(..., description="Backtest start date")
    end_date: date = Field(..., description="Backtest end date")
    initial_capital: float = Field(default=10_000.0, ge=100)
    slippage_bps: float = Field(default=10.0, ge=0)
    commission_bps: float = Field(default=10.0, ge=0)
    parameters: dict[str, Any] | None = Field(default=None)

class RunOptimizationCommand(BaseModel):
    """Command to run grid optimization."""
    strategy_id: str = Field(..., description="Strategy identifier")
    symbol: str = Field(...)
    exchange: str = Field(...)
    interval: str = Field(...)
    start_date: date = Field(...)
    end_date: date = Field(...)
    parameter_grid: dict[str, list[Any]] = Field(...)
    initial_capital: float = Field(default=10_000.0, ge=100)
    slippage_bps: float = Field(default=10.0, ge=0)
    commission_bps: float = Field(default=10.0, ge=0)
    target_metric: str = Field(default="sharpe_ratio")
    max_workers: int = Field(default=4, ge=1, le=16)

# Queries stay as dataclass (read-only, no validation needed)
@dataclass
class GetBacktestQuery:
    run_id: str

@dataclass
class GetOptimizationQuery:
    optimization_id: str

@dataclass
class ListBacktestsQuery:
    strategy_id: str
    limit: int = 20
    include_failed: bool = False
```

### 2. Simplify backtest_routes.py

Before:
```python
class RunBacktestRequest(BaseModel):
    strategy_id: str = Field(...)
    ...

@router.post("/run")
async def run_backtest(request: RunBacktestRequest, mediator: ...):
    command = RunBacktestCommand(
        strategy_id=request.strategy_id,
        ...
    )
    result = await mediator.send(command)
    return {...}
```

After:
```python
@router.post("/run", response_model=RunBacktestResponse)
async def run_backtest(cmd: RunBacktestCommand, mediator: ...):
    result = await mediator.send(cmd)
    return {...}  # Still needs response formatting
```

- Remove: RunBacktestRequest, RunOptimizationRequest classes
- Keep: Response classes (RunBacktestResponse, etc.)
- Note: Response formatting still needed (handlers return domain objects)

## Todo

- [ ] Convert RunBacktestCommand to Pydantic
- [ ] Convert RunOptimizationCommand to Pydantic
- [ ] Keep queries as dataclass (or convert if preferred)
- [ ] Simplify routes
- [ ] Run pyright

## Success Criteria

- [ ] Command classes are Pydantic models
- [ ] Routes use commands directly
- [ ] No type errors
- [ ] Backtest endpoints work

## Notes

- Query classes can stay as dataclass (no API validation needed)
- Response formatting still needed in routes (handlers return domain objects, not Pydantic)
- Consider creating Pydantic response models in handlers (future phase)
