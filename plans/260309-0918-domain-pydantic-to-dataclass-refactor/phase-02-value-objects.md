# Phase 2: Value Objects -> @dataclass(frozen=True)

## Overview
- **Priority:** High (after events, before aggregates)
- **Status:** completed
- **Effort:** 45min

Medium difficulty. Some VOs have `@field_validator` or `@model_validator` that need conversion to `__post_init__`. Frozen dataclasses can run `__post_init__` for validation (read-only).

## Files to Modify

| File | Classes to Convert | Already Dataclass |
|------|-------------------|-------------------|
| `src/domain/shared/value_objects.py` | `Symbol` | `Interval` (Enum, no change) |
| `src/domain/symbol/value_objects.py` | `SymbolInfo` | -- |
| `src/domain/position/value_objects.py` | `PnL` | `PositionSide` (Enum, no change) |
| `src/domain/quote/value_objects.py` | `Price`, `QuoteTick` | -- |
| `src/domain/ohlcv/value_objects.py` | `OHLCV`, `BarRange` | -- |
| `src/domain/risk/value_objects.py` | `RiskConfig` | `RiskModel` (Enum, no change) |
| `src/domain/strategy/value_objects.py` | `Signal` | `StrategyConfig` etc already dataclass |

**Not modified:** Enums (`Interval`, `OrderSide`, `OrderStatus`, `OrderType`, `PositionSide`, `RiskModel`, `Direction`) -- already stdlib, no Pydantic.

## Conversion Details Per File

### 1. `src/domain/shared/value_objects.py` -- Symbol

```python
# BEFORE
class Symbol(BaseModel):
    model_config = ConfigDict(frozen=True)
    code: str
    exchange: str

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        if not v: raise ValueError("Symbol code is required")
        return v

    @field_validator("exchange")
    @classmethod
    def validate_exchange(cls, v: str) -> str:
        if not v: raise ValueError("Exchange is required")
        return v

    def __str__(self) -> str:
        return f"{self.exchange}:{self.code}"

    @classmethod
    def from_string(cls, symbol_key: str) -> Symbol:
        if ":" not in symbol_key:
            raise ValueError(f"Invalid symbol format: {symbol_key}")
        exchange, code = symbol_key.split(":", 1)
        return cls(code=code.upper(), exchange=exchange.upper())
```

```python
# AFTER
@dataclass(frozen=True)
class Symbol:
    """Value object representing a tradeable symbol."""
    code: str
    exchange: str

    def __post_init__(self) -> None:
        if not self.code:
            raise ValueError("Symbol code is required")
        if not self.exchange:
            raise ValueError("Exchange is required")

    def __str__(self) -> str:
        return f"{self.exchange}:{self.code}"

    @classmethod
    def from_string(cls, symbol_key: str) -> Symbol:
        if ":" not in symbol_key:
            raise ValueError(f"Invalid symbol format: {symbol_key}")
        exchange, code = symbol_key.split(":", 1)
        return cls(code=code.upper(), exchange=exchange.upper())
```

**Remove:** `from pydantic import BaseModel, ConfigDict, field_validator`
**Add:** `from dataclasses import dataclass`

### 2. `src/domain/symbol/value_objects.py` -- SymbolInfo

```python
# BEFORE: inherits from Pydantic Symbol
class SymbolInfo(Symbol):
    name: str | None = None
    asset_type: str | None = None
    is_active: bool = True

    @property
    def symbol_key(self) -> str:
        return f"{self.exchange}:{self.code}"
```

```python
# AFTER: inherits from dataclass Symbol
@dataclass(frozen=True)
class SymbolInfo(Symbol):
    """Immutable symbol metadata extending shared Symbol."""
    name: str | None = None
    asset_type: str | None = None
    is_active: bool = True

    @property
    def symbol_key(self) -> str:
        return f"{self.exchange}:{self.code}"
```

**Note:** Frozen parent + frozen child = OK. Validation in `Symbol.__post_init__` still runs (Python calls parent `__post_init__` automatically when child doesn't override it; if child has `__post_init__`, must call `super().__post_init__()` manually). Since SymbolInfo adds no validation, no `__post_init__` needed -- but we must verify Python calls parent's. **Actually, with dataclass inheritance, `__post_init__` of child replaces parent's.** Since SymbolInfo has no `__post_init__`, the parent's runs. If we later add one to SymbolInfo, must call `super().__post_init__()`.

### 3. `src/domain/position/value_objects.py` -- PnL

```python
# BEFORE
class PnL(BaseModel):
    model_config = ConfigDict(frozen=True)
    unrealized: float
    realized: float

    @property
    def total(self) -> float: ...
    @property
    def is_profitable(self) -> bool: ...
```

```python
# AFTER
@dataclass(frozen=True)
class PnL:
    """Profit and Loss calculation result."""
    unrealized: float
    realized: float

    @property
    def total(self) -> float:
        return self.unrealized + self.realized

    @property
    def is_profitable(self) -> bool:
        return self.total > 0
```

Straightforward. No validators. Remove Pydantic imports entirely from file.

### 4. `src/domain/quote/value_objects.py` -- Price, QuoteTick

**Price:**
```python
# AFTER
@dataclass(frozen=True)
class Price:
    """Immutable price value."""
    value: float

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError("Price must be non-negative")

    def __float__(self) -> float:
        return self.value
```

**QuoteTick:**
```python
# AFTER
@dataclass(frozen=True)
class QuoteTick:
    """Immutable tick data from real-time feed."""
    symbol: str
    exchange: str
    timestamp: datetime
    price: float
    volume: float | None = None
    bid: float | None = None
    ask: float | None = None

    def __post_init__(self) -> None:
        if self.price < 0:
            raise ValueError("Price must be non-negative")
        if self.volume is not None and self.volume < 0:
            raise ValueError("Volume must be non-negative")

    @property
    def symbol_key(self) -> str:
        return f"{self.exchange}:{self.symbol}"
```

### 5. `src/domain/ohlcv/value_objects.py` -- OHLCV, BarRange

**OHLCV:** Has `@model_validator(mode="after")` -- maps to `__post_init__`.

```python
# AFTER
@dataclass(frozen=True)
class OHLCV:
    """Immutable OHLCV price bar data."""
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if self.high < self.low:
            raise ValueError("High must be >= Low")
        if self.open < self.low or self.open > self.high:
            raise ValueError("Open must be between Low and High")
        if self.close < self.low or self.close > self.high:
            raise ValueError("Close must be between Low and High")
        if self.volume < 0:
            raise ValueError("Volume must be non-negative")
```

**BarRange:** Has `@model_validator(mode="after")` + methods.

```python
# AFTER
@dataclass(frozen=True)
class BarRange:
    """Time range for a bar."""
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError("End must be after start")

    def contains(self, timestamp: datetime) -> bool:
        return self.start <= timestamp < self.end

    @property
    def duration_seconds(self) -> int:
        return int((self.end - self.start).total_seconds())
```

### 6. `src/domain/risk/value_objects.py` -- RiskConfig

Has `@model_validator(mode="after")` with multi-field validation.

```python
# AFTER
@dataclass(frozen=True)
class RiskConfig:
    """Risk configuration for a strategy."""
    model: RiskModel = RiskModel.PERCENT_RISK
    risk_per_trade: float = 0.02
    max_positions: int = 3
    max_exposure_percent: float = 0.10

    def __post_init__(self) -> None:
        if not 0 < self.risk_per_trade <= 0.10:
            raise ValueError(f"risk_per_trade must be 0-10%, got {self.risk_per_trade:.1%}")
        if self.max_positions < 1:
            raise ValueError("max_positions must be >= 1")
        if not 0 < self.max_exposure_percent <= 1.0:
            raise ValueError(f"max_exposure_percent must be 0-100%, got {self.max_exposure_percent:.1%}")
```

**Consumer check:** `PositionSizer` accesses `risk_config.risk_per_trade`, `risk_config.model`, etc. -- pure attribute access, no change needed. `StrategyConfig.from_dict()` creates `RiskConfig(model=..., risk_per_trade=...)` -- works identically with dataclass.

### 7. `src/domain/strategy/value_objects.py` -- Signal

Only `Signal` needs conversion. `StrategyConfig`, `StopLossConfig`, `TakeProfitConfig`, `OrderConfig` are already dataclasses.

```python
# AFTER
@dataclass(frozen=True)
class Signal:
    """Immutable trading signal from a strategy."""
    symbol: str
    exchange: str
    direction: Direction
    confidence: float
    timestamp: datetime
    strategy_id: str
    entry_price: float | None = None
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    entry_logic: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be 0.0-1.0, got {self.confidence}")

    @property
    def is_entry(self) -> bool:
        return self.direction in (Direction.LONG, Direction.SHORT)

    @property
    def is_exit(self) -> bool:
        return self.direction == Direction.EXIT
```

**Remove:** Pydantic imports from strategy/value_objects.py. Only `Signal` used Pydantic; the rest are already dataclass/enum.

## Implementation Steps

1. Convert `src/domain/shared/value_objects.py` (Symbol)
2. Convert `src/domain/symbol/value_objects.py` (SymbolInfo)
3. Convert `src/domain/position/value_objects.py` (PnL)
4. Convert `src/domain/quote/value_objects.py` (Price, QuoteTick)
5. Convert `src/domain/ohlcv/value_objects.py` (OHLCV, BarRange)
6. Convert `src/domain/risk/value_objects.py` (RiskConfig)
7. Convert `src/domain/strategy/value_objects.py` (Signal only)
8. Run `ruff check src/domain/` and `pyright src/domain/`

## Todo

- [x] Convert Symbol (shared) -- has field_validator -> __post_init__
- [x] Convert SymbolInfo -- inherits Symbol
- [x] Convert PnL -- simple, no validators
- [x] Convert Price -- has field_validator
- [x] Convert QuoteTick -- has 2 field_validators
- [x] Convert OHLCV -- has model_validator
- [x] Convert BarRange -- has model_validator
- [x] Convert RiskConfig -- has model_validator
- [x] Convert Signal -- has field_validator
- [x] Lint + type check pass

## Success Criteria
- All 9 VO classes are `@dataclass(frozen=True)`
- Zero Pydantic imports in VO files
- Validators moved to `__post_init__`
- `ruff check` and `pyright` pass
- `PositionSizer` still works (attribute access unchanged)
- `StrategyConfig.from_dict()` still creates `RiskConfig` correctly
