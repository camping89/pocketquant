# Phase 1: Domain Layer Models

## Context Links

- **Parent Plan:** [plan.md](./plan.md)
- **Dependencies:** None (foundational)
- **Blocked By:** None
- **Research:** [Strategy Patterns](./research/researcher-02-strategy-engine-patterns.md)

## Overview

| Field | Value |
|-------|-------|
| Date | 2026-01-31 |
| Priority | P1 |
| Status | completed |
| Effort | 4h |

Create pure domain models for strategy, order, position, and risk aggregates. Zero I/O imports, frozen dataclasses, domain events for state changes.

## Key Insights

1. **Signal is a value object** - Immutable, carries direction + confidence
2. **Order has lifecycle** - State machine: pending → submitted → partial → filled/cancelled
3. **Position tracks P&L** - Entry price, current price, unrealized/realized P&L
4. **Risk config is per-strategy** - Not global, loaded from YAML

## Requirements

### Functional
- Signal value object with direction (LONG/SHORT/EXIT), confidence, timestamp
- Order aggregate with full lifecycle state machine
- Position aggregate with P&L calculation
- Risk config value object with sizing model selection

### Non-Functional
- All models frozen dataclasses (immutable)
- No external I/O imports (enforced by domain purity test)
- Type hints on all public methods
- Domain events for state transitions

## Architecture

### Domain Model Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        DOMAIN LAYER                              │
│                    (Pure, Zero I/O)                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────┐    ┌─────────────────┐                    │
│  │ strategy/       │    │ order/          │                    │
│  │ ├── Signal (VO) │    │ ├── Order (Agg) │                    │
│  │ ├── Direction   │───▶│ ├── OrderType   │                    │
│  │ └── events.py   │    │ ├── OrderSide   │                    │
│  └─────────────────┘    │ ├── OrderStatus │                    │
│                         │ └── events.py   │                    │
│  ┌─────────────────┐    └────────┬────────┘                    │
│  │ risk/           │             │                              │
│  │ ├── RiskConfig  │             ▼                              │
│  │ ├── RiskModel   │    ┌─────────────────┐                    │
│  │ └── PositionSizer│    │ position/       │                    │
│  └─────────────────┘    │ ├── Position(Agg)│                    │
│                         │ ├── PnL (VO)     │                    │
│                         │ └── events.py   │                    │
│                         └─────────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
```

### State Machine: Order Lifecycle

```
PENDING ──submit()──▶ SUBMITTED ──partial_fill()──▶ PARTIALLY_FILLED
   │                      │                               │
   │                      ├──────full_fill()─────────────▶│
   │                      │                               ▼
   │                      └───cancel()───▶ CANCELLED    FILLED
   │                                                      │
   └──reject()──▶ REJECTED                                ▼
                                                   (Closed)
```

## Related Code Files

### Files to Create

```
src/domain/strategy/
├── __init__.py
├── value_objects.py      # Signal, Direction enum
└── events.py             # SignalGenerated

src/domain/order/
├── __init__.py
├── aggregate.py          # OrderAggregate
├── value_objects.py      # OrderType, OrderSide, OrderStatus enums
└── events.py             # OrderSubmitted, OrderFilled, OrderCancelled

src/domain/position/
├── __init__.py
├── aggregate.py          # PositionAggregate
├── value_objects.py      # PnL, PositionSide enum
└── events.py             # PositionOpened, PositionClosed

src/domain/risk/
├── __init__.py
├── value_objects.py      # RiskConfig, RiskModel enum
└── services/
    ├── __init__.py
    └── position_sizer.py # Pure domain service
```

### Files to Modify

```
src/domain/__init__.py    # Export new modules
```

## Implementation Steps

### Step 1: Strategy Domain (30 min)

1. Create `src/domain/strategy/__init__.py`
2. Create `value_objects.py` with:
   ```python
   from dataclasses import dataclass
   from datetime import datetime
   from enum import Enum

   class Direction(Enum):
       LONG = "long"
       SHORT = "short"
       EXIT = "exit"
       FLAT = "flat"

   @dataclass(frozen=True)
   class Signal:
       symbol: str
       exchange: str
       direction: Direction
       confidence: float  # 0.0 - 1.0
       timestamp: datetime
       strategy_id: str
       entry_logic: str = ""
   ```
3. Create `events.py` with `SignalGenerated` event

### Step 2: Order Domain (60 min)

1. Create `src/domain/order/__init__.py`
2. Create `value_objects.py` with enums:
   ```python
   class OrderType(Enum):
       MARKET = "market"
       LIMIT = "limit"
       STOP_LIMIT = "stop_limit"

   class OrderSide(Enum):
       BUY = "buy"
       SELL = "sell"

   class OrderStatus(Enum):
       PENDING = "pending"
       SUBMITTED = "submitted"
       PARTIALLY_FILLED = "partially_filled"
       FILLED = "filled"
       CANCELLED = "cancelled"
       REJECTED = "rejected"
   ```
3. Create `aggregate.py` with OrderAggregate:
   - State machine methods: `submit()`, `partial_fill()`, `fill()`, `cancel()`, `reject()`
   - Validate transitions (e.g., can't fill a cancelled order)
   - Return domain events on transitions
4. Create `events.py` with domain events

### Step 3: Position Domain (60 min)

1. Create `src/domain/position/__init__.py`
2. Create `value_objects.py`:
   ```python
   @dataclass(frozen=True)
   class PnL:
       unrealized: float
       realized: float
       total: float

   class PositionSide(Enum):
       LONG = "long"
       SHORT = "short"
   ```
3. Create `aggregate.py` with PositionAggregate:
   - Properties: `entry_price`, `current_price`, `quantity`, `side`
   - Methods: `update_price()`, `add_quantity()`, `reduce_quantity()`, `close()`
   - Calculate P&L: `(current - entry) * quantity` for long, inverse for short
4. Create `events.py` with `PositionOpened`, `PositionUpdated`, `PositionClosed`

### Step 4: Risk Domain (45 min)

1. Create `src/domain/risk/__init__.py`
2. Create `value_objects.py`:
   ```python
   class RiskModel(Enum):
       PERCENT_RISK = "percent_risk"  # Fixed % of account
       KELLY = "kelly"                 # Kelly criterion
       FIXED = "fixed"                 # Fixed size

   @dataclass(frozen=True)
   class RiskConfig:
       model: RiskModel = RiskModel.PERCENT_RISK
       risk_per_trade: float = 0.01   # 1% default
       max_positions: int = 3
       max_exposure_percent: float = 0.1  # 10% total
   ```
3. Create `services/position_sizer.py`:
   ```python
   class PositionSizer:
       @staticmethod
       def calculate_size(
           account_balance: float,
           entry_price: float,
           stop_loss_price: float,
           risk_config: RiskConfig
       ) -> float:
           """Pure calculation, no I/O."""
           if risk_config.model == RiskModel.PERCENT_RISK:
               risk_amount = account_balance * risk_config.risk_per_trade
               price_risk = abs(entry_price - stop_loss_price)
               if price_risk == 0:
                   return 0.0
               return risk_amount / price_risk
           # ... other models
   ```

### Step 5: Update Exports (15 min)

1. Update each `__init__.py` to export public types
2. Update `src/domain/__init__.py` to include new modules
3. Run `ruff check src/domain/` to verify no syntax errors

## Todo List

- [x] Create strategy domain: Signal, Direction, SignalGenerated
- [x] Create order domain: OrderAggregate, enums, events
- [x] Create position domain: PositionAggregate, PnL, events
- [x] Create risk domain: RiskConfig, RiskModel, PositionSizer
- [x] Update domain exports in `__init__.py`
- [x] Run domain purity test (no I/O imports found)
- [x] Run syntax check (compilation successful)

## Success Criteria

1. All domain models are frozen dataclasses
2. No I/O imports in domain layer (purity test passes)
3. Order state machine validates transitions correctly
4. Position P&L calculation is accurate for long/short
5. PositionSizer returns correct size for 1% risk

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| State machine bugs | Medium | High | Unit tests for all transitions |
| P&L calculation errors | Low | High | Test with known values |
| Import violations | Low | Medium | Purity test on CI |

## Security Considerations

- No security concerns - pure domain models with no I/O
- RiskConfig limits exposure (max_positions, max_exposure_percent)

## Next Steps

After Phase 1 completion:
1. Proceed to [Phase 2: Infrastructure Brokers](./phase-02-infrastructure-brokers.md)
2. PaperBroker will use these domain models
3. OKXBroker will map OKX responses to domain events
