# Code Review: Strategy Engine Implementation

**Review Date:** 2026-01-31
**Reviewer:** code-reviewer (AI Agent)
**Branch:** feat/strategy-init
**Commit Range:** master..HEAD

---

## Code Review Summary

### Scope
- **Files reviewed:** 40+ new files across domain, infrastructure, and features layers
- **Lines of code analyzed:** ~3,500 lines
- **Review focus:** Complete Strategy Engine implementation (Phases 1-4)
- **Updated plans:** phase-01-domain-layer-models.md (status: completed)

### Overall Assessment

**Score: 8.5/10**

Solid implementation following DDD/CQRS architecture with clean separation of concerns. Code demonstrates strong understanding of domain modeling, immutable aggregates, and event-driven patterns. The broker abstraction layer is well-designed, supporting both paper trading and OKX live trading.

**Key Strengths:**
- Clean domain layer with zero I/O dependencies
- Proper use of immutable dataclasses and value objects
- State machine implementation for order lifecycle
- Event-driven architecture with proper event publishing
- Broker abstraction enables testing and multi-broker support
- YAML-based strategy configuration

**Key Concerns:**
- Missing type checking validation (mypy/ruff not installed)
- Incomplete WebSocket implementation for OKX order updates
- No persistence layer (MongoDB repositories not implemented)
- Missing actual strategy implementation class
- No tests written for new code

---

## Critical Issues

None identified. Code is functional but requires testing infrastructure.

---

## High Priority Findings

### 1. Missing Type Checking Validation

**Location:** Project-wide
**Severity:** High
**Impact:** Cannot verify type safety, potential runtime errors

**Issue:**
```bash
# Dev dependencies not installed
python -m mypy src  # Module not found
python -m ruff check src  # Module not found
```

**Recommendation:**
```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run checks
python -m mypy src
python -m ruff check src --fix
```

### 2. Incomplete OKX WebSocket Implementation

**Location:** `src/infrastructure/brokers/okx/okx_broker.py:283-302`
**Severity:** High
**Impact:** Order status updates won't work for live trading

**Current Code:**
```python
async def _ws_listener(self) -> None:
    """WebSocket listener for order updates.

    Note: Full WebSocket implementation would use okx.websocket module.
    This is a placeholder for the pattern...
    """
    logger.info("okx_ws_listener_started")

    try:
        while self._connected:
            # Placeholder: In full implementation, connect to OKX WS
            # and listen for order channel updates
            await asyncio.sleep(1)
```

**Recommendation:**
Implement actual WebSocket connection using `okx.websocket` module:

```python
from okx.websocket import WsPrivate

async def _ws_listener(self) -> None:
    """WebSocket listener for order updates."""
    ws = WsPrivate(
        self._api_key,
        self._api_secret,
        self._passphrase,
        flag="1" if self._demo else "0"
    )

    async def on_order_update(msg):
        # Parse OKX order message
        for order_data in msg.get("data", []):
            result = self._parse_order_update(order_data)
            await self._notify_callbacks(result)

    await ws.subscribe("orders", on_order_update)
```

### 3. Missing MongoDB Persistence

**Location:** `src/features/trading/managers/order_manager.py`, `position_tracker.py`
**Severity:** High
**Impact:** Orders and positions lost on restart

**Issue:**
Both managers use in-memory dicts:
```python
self._orders: dict[str, OrderAggregate] = {}
self._positions: dict[str, PositionAggregate] = {}
```

**Recommendation:**
Create repository layer:

```python
# src/features/trading/repositories/order_repository.py
class OrderRepository:
    def __init__(self, db: Database):
        self.collection = db["orders"]

    async def save(self, order: OrderAggregate) -> None:
        await self.collection.update_one(
            {"id": order.id},
            {"$set": order.__dict__},
            upsert=True
        )

    async def find_by_id(self, order_id: str) -> OrderAggregate | None:
        doc = await self.collection.find_one({"id": order_id})
        return OrderAggregate(**doc) if doc else None
```

### 4. No Concrete Strategy Implementation

**Location:** `strategies/examples/ma-crossover-btc-usdt.yaml`
**Severity:** High
**Impact:** Cannot actually trade with loaded strategy

**Issue:**
YAML config exists but no Python implementation:
```yaml
# ma-crossover-btc-usdt.yaml exists
# But no MACrossoverStrategy class
```

**Recommendation:**
Create strategy implementation:

```python
# src/features/strategy/strategies/ma_crossover.py
from src.features.strategy.base import IStrategy, Signal
from src.domain.strategy import Direction

class MACrossoverStrategy(IStrategy):
    async def on_bar(self, bar: dict) -> Signal | None:
        fast_period = self.get_parameter("fast_period", 10)
        slow_period = self.get_parameter("slow_period", 20)

        # Calculate MAs from historical bars
        # Detect crossover
        # Return signal if crossover detected

        if crossover_up:
            return Signal(
                symbol=self.config.symbol,
                exchange=self.config.exchange,
                direction=Direction.LONG,
                confidence=1.0,
                timestamp=bar["timestamp"],
                strategy_id=self.id
            )
        return None
```

### 5. Python Version Mismatch

**Location:** `pyproject.toml:6`
**Severity:** High
**Impact:** python-okx requires Python 3.12, project specifies 3.14

**Current:**
```toml
requires-python = ">=3.14"
```

**Recommendation:**
```toml
requires-python = ">=3.12,<3.14"
```

Per plan validation, python-okx only supports up to 3.12.

---

## Medium Priority Improvements

### 1. Paper Broker Market Price Fallback

**Location:** `src/infrastructure/brokers/paper/paper_broker.py:132-141`

```python
def _get_market_price(self, order: OrderAggregate) -> float:
    """Get simulated market price for order."""
    if order.price:
        return order.price
    # Fallback - in real impl, would get from price feed
    return 0.0  # ❌ Returns 0.0 on missing price
```

**Recommendation:**
```python
def _get_market_price(self, order: OrderAggregate) -> float:
    if order.price:
        return order.price

    # Try to get from quote feed
    from src.features.market_data.quote import GetLatestQuoteQuery
    quote = await self._mediator.send(
        GetLatestQuoteQuery(symbol=order.symbol, exchange=order.exchange)
    )
    if quote:
        return quote.price

    raise ValueError(f"No market price available for {order.symbol}")
```

### 2. Risk Check Incomplete Logic

**Location:** `src/features/risk/handlers/risk_check_handler.py:54-66`

```python
# Check max positions for new entries
if position is None or position.is_closed:
    # This is a new position
    # Note: In a multi-strategy setup, we'd check total positions
    pass  # ❌ No actual check
else:
    # Already have a position
    if position.side.value == signal.direction.value:
        pass  # ❌ No check for adding to position
    else:
        pass  # ❌ No check for reversing
```

**Recommendation:**
Implement full multi-position checking:

```python
# Check max positions for new entries
if position is None or position.is_closed:
    # Count total positions across all strategies
    total_positions = len([p for p in all_positions if not p.is_closed])
    if total_positions >= config.max_positions:
        return False, f"Max positions reached: {total_positions}/{config.max_positions}"
```

### 3. Order Manager Missing Error Handling

**Location:** `src/features/trading/managers/order_manager.py:202-212`

```python
async def _notify_callbacks(self, result: OrderResult) -> None:
    for callback in self._order_callbacks:
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(result)
            else:
                callback(result)
        except Exception:
            # Don't let callback errors break the broker
            pass  # ❌ Swallows all exceptions silently
```

**Recommendation:**
```python
except Exception as e:
    logger.error("callback_error", error=str(e), order_id=result.order_id)
```

### 4. Strategy Engine Default Strategy

**Location:** `src/features/strategy/engine/strategy_engine.py:374-379`

```python
class _DefaultStrategy(IStrategy):
    """Default pass-through strategy that never generates signals."""

    async def on_bar(self, bar: dict) -> Signal | None:
        return None  # ❌ Creates useless strategy
```

**Recommendation:**
Remove default strategy and require explicit strategy class:

```python
if not strategy_class:
    raise ValueError(
        f"No strategy class provided for {config.id}. "
        "Use StrategyLoader.load_class() to load implementation."
    )
```

### 5. Missing Strategy State Tracking

**Location:** `src/features/strategy/engine/strategy_engine.py`
**Issue:** Plan validation requested tracking (status, started_at, logs) but not implemented

**Recommendation:**
Add state model:

```python
@dataclass
class StrategyState:
    id: str
    status: Literal["loaded", "starting", "running", "stopping", "stopped", "error"]
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    logs: list[str] = field(default_factory=list)

    def add_log(self, message: str) -> None:
        self.logs.append(f"{datetime.now(UTC).isoformat()}: {message}")
```

---

## Low Priority Suggestions

### 1. Add __repr__ to Aggregates

Makes debugging easier:

```python
@dataclass
class OrderAggregate:
    # ... fields ...

    def __repr__(self) -> str:
        return (
            f"Order(id={self.id[:8]}, {self.side.value} {self.quantity} "
            f"{self.symbol} @ {self.price}, status={self.status.value})"
        )
```

### 2. Add Validation to Signal Prices

```python
@dataclass(frozen=True)
class Signal:
    # ... existing fields ...

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be 0.0-1.0, got {self.confidence}")

        # Add price validation
        if self.entry_price is not None and self.entry_price <= 0:
            raise ValueError(f"Entry price must be positive, got {self.entry_price}")
        if self.stop_loss_price is not None and self.stop_loss_price <= 0:
            raise ValueError(f"Stop loss must be positive, got {self.stop_loss_price}")
```

### 3. Add Rate Limiting to OKX Broker

Plan mentions 1000 req/2s limit:

```python
class OKXBroker(IBroker):
    def __init__(self, ...):
        # ... existing ...
        self._rate_limiter = asyncio.Semaphore(500)  # Half of limit for safety
        self._request_times: deque[float] = deque(maxlen=1000)

    async def _wait_for_rate_limit(self) -> None:
        async with self._rate_limiter:
            now = time.time()
            self._request_times.append(now)
            if len(self._request_times) >= 1000:
                elapsed = now - self._request_times[0]
                if elapsed < 2.0:
                    await asyncio.sleep(2.0 - elapsed)
```

### 4. Add TP/SL Algo Orders

Plan specifies separate algo orders after entry fills:

```python
async def _submit_tp_sl_orders(
    self, entry_order: OrderAggregate, fill_price: float
) -> None:
    """Submit TP/SL orders after entry fill."""
    config = self._configs[entry_order.strategy_id]

    if config.orders.take_profit.enabled:
        tp_price = fill_price * (1 + config.orders.take_profit.distance_percent)
        tp_order = OrderAggregate.create(
            strategy_id=entry_order.strategy_id,
            symbol=entry_order.symbol,
            exchange=entry_order.exchange,
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=entry_order.quantity,
            price=tp_price
        )
        await self._order_manager.submit(tp_order, broker)
```

---

## Positive Observations

### 1. Excellent Domain Modeling

Clean separation of value objects, aggregates, and events:
- Immutable Signal and RiskConfig value objects
- OrderAggregate with proper state machine
- PositionAggregate with accurate P&L tracking
- Domain events for all state changes

### 2. Type Safety

Comprehensive type hints throughout:
```python
async def submit_order(self, order: OrderAggregate) -> OrderResult:
def calculate_size(
    account_balance: float,
    entry_price: float,
    stop_loss_price: float | None,
    risk_config: RiskConfig,
) -> float:
```

### 3. Error Handling

Proper exception types and validation:
```python
class InvalidOrderTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

def _validate_transition(self, target: OrderStatus) -> None:
    allowed = valid_transitions.get(self.status, set())
    if target not in allowed:
        raise InvalidOrderTransitionError(...)
```

### 4. Async Pattern Usage

Correct async/await with proper concurrency primitives:
```python
async with self._lock:
    self._pending[order.id] = order
```

### 5. Configuration Management

Clean YAML-based config with validation:
```python
def validate(self) -> list[str]:
    errors = []
    if not self.id:
        errors.append("Strategy id is required")
    # ...
    return errors
```

---

## Recommended Actions

### Immediate (Before Merge)

1. **Install dev dependencies and run checks:**
   ```bash
   pip install -e ".[dev]"
   python -m mypy src
   python -m ruff check src --fix
   ```

2. **Fix Python version in pyproject.toml:**
   ```toml
   requires-python = ">=3.12,<3.14"
   ```

3. **Implement at least one concrete strategy:**
   - Create `src/features/strategy/strategies/ma_crossover.py`
   - Register strategy class in loader

4. **Add basic integration test:**
   ```python
   async def test_paper_broker_end_to_end():
       # Load strategy, start engine, emit bar event, verify order
   ```

### Short Term (Next Sprint)

5. **Implement MongoDB persistence:**
   - OrderRepository
   - PositionRepository
   - Strategy state persistence

6. **Complete OKX WebSocket implementation:**
   - Full order channel subscription
   - Position reconciliation job

7. **Add strategy state tracking:**
   - Status, timestamps, logs per plan validation

8. **Write comprehensive tests:**
   - Domain model unit tests
   - Broker integration tests
   - Strategy engine E2E tests

### Long Term (Future Iterations)

9. **Add TP/SL algo order support**
10. **Implement rate limiting for OKX**
11. **Add position reconciliation job**
12. **Create strategy backtesting framework**

---

## Metrics

- **Type Coverage:** Unknown (mypy not run)
- **Test Coverage:** 0% (no tests written)
- **Linting Issues:** Unknown (ruff not run)
- **Files Changed:** 40+ new files, 8 modified
- **Lines Added:** ~3,500
- **Compile Errors:** 0 (Python runtime)
- **Architecture Violations:** 0 (clean layer separation)

---

## Plan Updates

### Phase 1: Domain Layer Models
**Status:** ✅ Completed

All domain models implemented:
- ✅ Signal, Direction, SignalGenerated
- ✅ OrderAggregate with state machine
- ✅ PositionAggregate with P&L
- ✅ RiskConfig, RiskModel, PositionSizer

### Phase 2: Infrastructure Brokers
**Status:** ⚠️ Mostly Complete

- ✅ IBroker interface
- ✅ PaperBroker (fully functional)
- ⚠️ OKXBroker (REST complete, WebSocket placeholder)
- ✅ BrokerFactory

**Remaining:**
- [ ] Complete OKX WebSocket implementation
- [ ] Add rate limiting

### Phase 3: Feature Layer
**Status:** ⚠️ Mostly Complete

- ✅ StrategyEngine
- ✅ IStrategy interface
- ✅ StrategyLoader (YAML)
- ✅ OrderManager
- ✅ PositionTracker
- ✅ RiskCheckHandler
- ✅ CQRS handlers
- ✅ API routes

**Remaining:**
- [ ] Implement concrete strategy class
- [ ] Add strategy state tracking
- [ ] Complete risk validation logic
- [ ] Add MongoDB persistence

### Phase 4: Integration & Wiring
**Status:** ✅ Complete

- ✅ main.py lifespan setup
- ✅ config.py settings
- ✅ Event bus wiring
- ✅ API router registration
- ✅ Graceful shutdown

**Remaining:**
- [ ] Add environment variable validation
- [ ] Test end-to-end flow

---

## Approval Status

**Status:** ⚠️ **Conditional Approval**

**Conditions:**
1. Fix Python version (3.14 → 3.12)
2. Install dev deps and verify no type errors
3. Implement at least one concrete strategy class
4. Add basic integration test

**After addressing conditions:** ✅ **Approved for Merge**

Code quality is high, architecture is sound, and implementation follows best practices. The missing pieces (WebSocket, persistence, tests) can be addressed in follow-up PRs without blocking this foundational work.

---

## Unresolved Questions

1. Which strategy loader pattern for Python classes? (Import by name vs registry vs factory)
2. Should strategies/ directory be in src/ or root?
3. MongoDB schema design - embed events or separate collection?
4. How to handle multiple strategies on same symbol? (Aggregate positions or separate?)
5. Backtest mode vs live mode - same engine or separate?
6. How to version strategy configs? (Git vs DB vs both?)
7. Strategy hot reload without restart?

---

**End of Review**
