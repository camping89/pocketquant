# Phase 3: Feature Layer (Strategy & Trading)

## Context Links

- **Parent Plan:** [plan.md](./plan.md)
- **Dependencies:** [Phase 1](./phase-01-domain-layer-models.md), [Phase 2](./phase-02-infrastructure-brokers.md)
- **Blocked By:** Phase 2 (IBroker interface)
- **Research:** [Strategy Patterns](./research/researcher-02-strategy-engine-patterns.md)

## Overview

| Field | Value |
|-------|-------|
| Date | 2026-01-31 |
| Priority | P1 |
| Status | pending |
| Effort | 6h |

Implement strategy and trading features following vertical slice architecture. YAML-based strategy loading, StrategyEngine event dispatch, OrderManager lifecycle, PositionTracker per-strategy, and CQRS handlers.

## Key Insights

1. **IStrategy interface** - `on_bar()` primary, `on_tick()` optional for intra-bar adjustments
2. **StrategyEngine as EventBus subscriber** - Listens to BarCompleted/QuoteReceived
3. **OrderManager tracks lifecycle** - Bridges domain Order to IBroker
4. **PositionTracker per-strategy** - Isolated positions, independent P&L
5. **RiskCheckHandler as gate** - Validates before order submission

## Requirements

### Functional
- IStrategy base class with on_bar(), on_tick(), on_fill() hooks
- YAML loader parses strategy config into StrategyConfig dataclass
- StrategyEngine dispatches events to active strategies by symbol
- OrderManager submits orders via IBroker, tracks status
- PositionTracker maintains position state per strategy
- RiskCheckHandler validates position size before submission

### Non-Functional
- Async handlers throughout
- Strategy code identical for backtest/live
- Max 200 LOC per file (split as needed)
- CQRS pattern for all mutations

## Architecture

### Feature Layer Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                       FEATURE LAYER                              │
│                 (CQRS Handlers + Services)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    strategy/ feature                         ││
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ ││
│  │  │ IStrategy   │  │ YAML Loader │  │ StrategyEngine      │ ││
│  │  │ (ABC)       │  │             │  │ - subscribes to     │ ││
│  │  │ - on_bar()  │  │ - parse()   │  │   BarCompleted      │ ││
│  │  │ - on_tick() │  │ - validate()│  │ - dispatches to     │ ││
│  │  │ - on_fill() │  │             │  │   strategies        │ ││
│  │  └─────────────┘  └─────────────┘  └─────────────────────┘ ││
│  │                                                              ││
│  │  api/: GET /strategies, POST /strategies/{id}/start          ││
│  │  handlers/: LoadStrategyHandler, StartStrategyHandler        ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    trading/ feature                          ││
│  │  ┌─────────────────┐  ┌─────────────────────────────────┐  ││
│  │  │ OrderManager    │  │ PositionTracker                  │  ││
│  │  │ - submit_order()│  │ - get_position(strategy_id)      │  ││
│  │  │ - track_status()│  │ - update_on_fill()               │  ││
│  │  │ - cancel_order()│  │ - calculate_pnl()                │  ││
│  │  └─────────────────┘  └─────────────────────────────────┘  ││
│  │                                                              ││
│  │  api/: GET /orders, GET /positions, POST /orders/cancel      ││
│  │  handlers/: SubmitOrderHandler, GetPositionsHandler          ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                      risk/ feature                           ││
│  │  ┌─────────────────────────────────────────────────────────┐││
│  │  │ RiskCheckHandler                                         │││
│  │  │ - validate_position_size()                               │││
│  │  │ - check_max_exposure()                                   │││
│  │  │ - check_max_positions()                                  │││
│  │  └─────────────────────────────────────────────────────────┘││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### Event Flow (Signal to Order)

```
BarCompleted (EventBus)
    │
    ▼
StrategyEngine.on_bar_completed()
    │
    ├──▶ Find strategies for symbol
    │
    ▼
strategy.on_bar(bar) → Signal
    │
    ▼
RiskCheckHandler.validate(signal, account)
    │
    ├── PASS ──▶ PositionSizer.calculate_size()
    │                    │
    │                    ▼
    │            Order (domain model)
    │                    │
    │                    ▼
    │            OrderManager.submit(order)
    │                    │
    │                    ▼
    │            IBroker.submit_order()
    │
    └── FAIL ──▶ Log rejection, skip
```

## Related Code Files

### Files to Create

```
src/features/strategy/
├── __init__.py
├── api/
│   ├── __init__.py
│   └── routes.py                # GET/POST strategy endpoints
├── base/
│   ├── __init__.py
│   ├── strategy_interface.py    # IStrategy ABC
│   └── strategy_config.py       # StrategyConfig dataclass
├── loader/
│   ├── __init__.py
│   └── yaml_loader.py           # Parse YAML to StrategyConfig
├── engine/
│   ├── __init__.py
│   └── strategy_engine.py       # Event dispatch to strategies
├── registry/
│   ├── __init__.py
│   └── strategy_registry.py     # Track active strategies
├── handlers/
│   ├── __init__.py
│   ├── command.py               # LoadStrategy, StartStrategy commands
│   ├── query.py                 # GetStrategies, GetStrategyStatus
│   ├── command_handler.py
│   └── query_handler.py
└── dto.py

src/features/trading/
├── __init__.py
├── api/
│   ├── __init__.py
│   └── routes.py                # Orders/positions endpoints
├── managers/
│   ├── __init__.py
│   ├── order_manager.py         # Order lifecycle management
│   └── position_tracker.py      # Per-strategy positions
├── handlers/
│   ├── __init__.py
│   ├── command.py               # SubmitOrder, CancelOrder
│   ├── query.py                 # GetOrders, GetPositions
│   ├── command_handler.py
│   └── query_handler.py
└── dto.py

src/features/risk/
├── __init__.py
├── handlers/
│   ├── __init__.py
│   ├── command.py               # ValidateRisk command
│   └── risk_check_handler.py    # Risk validation logic
└── dto.py
```

### Files to Modify

```
src/main.py                       # Register new handlers/routes
src/features/__init__.py          # Export new features
```

## Implementation Steps

### Step 1: IStrategy Interface (30 min)

1. Create `src/features/strategy/base/__init__.py`
2. Create `strategy_interface.py`:
   ```python
   from abc import ABC, abstractmethod
   from typing import Optional

   from src.domain.ohlcv import OHLCVBar
   from src.domain.quote import QuoteTick
   from src.domain.strategy import Signal
   from src.domain.order import Order

   class IStrategy(ABC):
       def __init__(self, config: "StrategyConfig"):
           self.config = config
           self.id = config.id

       @abstractmethod
       async def on_bar(self, bar: OHLCVBar) -> Optional[Signal]:
           """Process bar close, return signal if entry/exit."""
           ...

       async def on_tick(self, tick: QuoteTick) -> Optional[Order]:
           """Optional: Adjust orders intra-bar (trailing stop)."""
           return None

       async def on_fill(self, order: Order, fill_price: float) -> None:
           """Optional: Post-fill callback for state update."""
           pass
   ```
3. Create `strategy_config.py`:
   ```python
   @dataclass
   class StrategyConfig:
       id: str
       name: str
       symbol: str
       exchange: str
       interval: str
       trigger: Literal["bar", "tick"] = "bar"
       broker: str = "paper"
       parameters: dict = field(default_factory=dict)
       risk: RiskConfig = field(default_factory=RiskConfig)
       orders: OrderConfig = field(default_factory=OrderConfig)
   ```

### Step 2: YAML Loader (30 min)

1. Create `src/features/strategy/loader/__init__.py`
2. Create `yaml_loader.py`:
   ```python
   import yaml
   from pathlib import Path

   class StrategyLoader:
       @staticmethod
       def load(path: Path) -> StrategyConfig:
           with open(path) as f:
               data = yaml.safe_load(f)

           return StrategyConfig(
               id=data.get("id", path.stem),
               name=data["name"],
               symbol=data["symbol"],
               exchange=data["exchange"],
               interval=data["interval"],
               trigger=data.get("trigger", "bar"),
               broker=data.get("broker", "paper"),
               parameters=data.get("parameters", {}),
               risk=RiskConfig(**data.get("risk", {})),
               orders=OrderConfig(**data.get("orders", {}))
           )

       @staticmethod
       def load_all(directory: Path) -> list[StrategyConfig]:
           configs = []
           for path in directory.glob("*.yaml"):
               configs.append(StrategyLoader.load(path))
           return configs
   ```

### Step 3: StrategyEngine (60 min)

1. Create `src/features/strategy/engine/__init__.py`
2. Create `strategy_engine.py`:
   ```python
   class StrategyEngine:
       def __init__(
           self,
           event_bus: EventBus,
           broker_factory: BrokerFactory,
           order_manager: OrderManager,
           position_tracker: PositionTracker
       ):
           self._event_bus = event_bus
           self._broker_factory = broker_factory
           self._order_manager = order_manager
           self._position_tracker = position_tracker
           self._strategies: dict[str, IStrategy] = {}
           self._brokers: dict[str, IBroker] = {}

       async def start(self) -> None:
           self._event_bus.subscribe(BarCompleted, self._on_bar_completed)
           self._event_bus.subscribe(QuoteReceived, self._on_quote_received)

       async def register_strategy(
           self, strategy: IStrategy, broker_config: dict
       ) -> None:
           self._strategies[strategy.id] = strategy
           self._brokers[strategy.id] = self._broker_factory.create(
               strategy.config.broker, broker_config
           )

       async def _on_bar_completed(self, event: BarCompleted) -> None:
           for strategy in self._find_strategies(
               event.symbol, event.exchange, event.interval
           ):
               if strategy.config.trigger != "bar":
                   continue

               bar = self._event_to_bar(event)
               signal = await strategy.on_bar(bar)

               if signal:
                   await self._process_signal(strategy, signal)

       async def _process_signal(
           self, strategy: IStrategy, signal: Signal
       ) -> None:
           # Get broker and position
           broker = self._brokers[strategy.id]
           position = self._position_tracker.get(strategy.id)
           balance = await broker.get_balance()

           # Risk check
           if not self._validate_risk(strategy, signal, balance, position):
               return

           # Calculate size
           size = PositionSizer.calculate_size(
               balance.available_balance,
               signal.entry_price,
               signal.stop_loss_price,
               strategy.config.risk
           )

           # Create and submit order
           order = self._create_order(signal, size)
           await self._order_manager.submit(order, broker)
   ```

### Step 4: OrderManager (45 min)

1. Create `src/features/trading/managers/__init__.py`
2. Create `order_manager.py`:
   ```python
   class OrderManager:
       def __init__(self, event_bus: EventBus):
           self._event_bus = event_bus
           self._orders: dict[str, Order] = {}
           self._pending: dict[str, Order] = {}

       async def submit(self, order: Order, broker: IBroker) -> OrderResult:
           self._pending[order.id] = order

           result = await broker.submit_order(order)

           if result.status == OrderStatus.FILLED:
               self._orders[result.order_id] = order
               await self._event_bus.publish(OrderFilled(
                   order_id=result.order_id,
                   filled_price=result.filled_price,
                   filled_quantity=result.filled_quantity
               ))
           elif result.status == OrderStatus.REJECTED:
               del self._pending[order.id]

           return result

       async def cancel(self, order_id: str, broker: IBroker) -> bool:
           success = await broker.cancel_order(order_id)
           if success and order_id in self._pending:
               del self._pending[order_id]
           return success

       def get_order(self, order_id: str) -> Order | None:
           return self._orders.get(order_id) or self._pending.get(order_id)

       def get_all_orders(self) -> list[Order]:
           return list(self._orders.values()) + list(self._pending.values())
   ```

### Step 5: PositionTracker (45 min)

1. Create `position_tracker.py`:
   ```python
   class PositionTracker:
       def __init__(self, event_bus: EventBus):
           self._event_bus = event_bus
           self._positions: dict[str, PositionAggregate] = {}

       async def start(self) -> None:
           self._event_bus.subscribe(OrderFilled, self._on_order_filled)

       async def _on_order_filled(self, event: OrderFilled) -> None:
           strategy_id = event.strategy_id

           if strategy_id not in self._positions:
               # New position
               position = PositionAggregate.open(
                   strategy_id=strategy_id,
                   symbol=event.symbol,
                   side=event.side,
                   entry_price=event.filled_price,
                   quantity=event.filled_quantity
               )
               self._positions[strategy_id] = position
               await self._event_bus.publish(PositionOpened(...))
           else:
               # Update existing
               position = self._positions[strategy_id]
               if event.side == position.side:
                   position = position.add_quantity(
                       event.filled_quantity, event.filled_price
                   )
               else:
                   position = position.reduce_quantity(
                       event.filled_quantity, event.filled_price
                   )
               self._positions[strategy_id] = position

       def get(self, strategy_id: str) -> PositionAggregate | None:
           return self._positions.get(strategy_id)

       def get_all(self) -> list[PositionAggregate]:
           return list(self._positions.values())
   ```

### Step 6: RiskCheckHandler (30 min)

1. Create `src/features/risk/__init__.py`
2. Create `risk_check_handler.py`:
   ```python
   class RiskCheckHandler:
       def validate(
           self,
           signal: Signal,
           account: AccountBalance,
           position: PositionAggregate | None,
           config: RiskConfig
       ) -> tuple[bool, str]:
           # Check max positions
           if position and config.max_positions <= 1:
               return False, "Max positions reached"

           # Check max exposure
           exposure = self._calculate_exposure(position, account)
           if exposure > config.max_exposure_percent:
               return False, f"Exposure {exposure:.1%} exceeds max"

           return True, ""

       def _calculate_exposure(
           self, position: PositionAggregate | None, account: AccountBalance
       ) -> float:
           if not position:
               return 0.0
           return (position.quantity * position.current_price) / account.total_equity
   ```

### Step 7: CQRS Handlers (45 min)

1. Create command/query classes for each feature
2. Create handlers following existing pattern
3. Register in main.py

### Step 8: API Routes (30 min)

1. Create strategy routes:
   - `GET /api/v1/strategies` - List loaded strategies
   - `POST /api/v1/strategies/{id}/start` - Start strategy
   - `POST /api/v1/strategies/{id}/stop` - Stop strategy
2. Create trading routes:
   - `GET /api/v1/orders` - List orders
   - `GET /api/v1/positions` - List positions
   - `POST /api/v1/orders/{id}/cancel` - Cancel order

## Todo List

- [ ] Create IStrategy interface and StrategyConfig
- [ ] Implement YAML loader with validation
- [ ] Implement StrategyEngine event dispatch
- [ ] Create StrategyRegistry for active strategies
- [ ] Implement OrderManager with lifecycle tracking
- [ ] Implement PositionTracker with P&L calculation
- [ ] Implement RiskCheckHandler validation
- [ ] Create CQRS command/query handlers
- [ ] Create API routes
- [ ] Register handlers and routes in main.py
- [ ] Write unit tests for each component

## Success Criteria

1. Strategy loaded from YAML and registered in engine
2. BarCompleted event triggers strategy.on_bar()
3. Signal generates correctly sized order
4. Order submitted to broker, status tracked
5. Position updated on fill, P&L calculated
6. Risk checks reject oversized positions

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Race conditions | Medium | High | Use asyncio.Lock on shared state |
| Event ordering | Medium | Medium | FIFO EventBus guarantees |
| Memory leaks | Low | Medium | Bounded collections, cleanup on stop |
| Strategy exceptions | High | Medium | Try-except in engine dispatch |

## Security Considerations

- **Strategy isolation** - Each strategy has own position/broker
- **Risk limits enforced** - RiskCheckHandler validates before submit
- **No code injection** - YAML config only, no eval()

## Next Steps

After Phase 3 completion:
1. Proceed to [Phase 4: Integration](./phase-04-integration-wiring.md)
2. Wire StrategyEngine to existing EventBus
3. Create example strategy YAML
