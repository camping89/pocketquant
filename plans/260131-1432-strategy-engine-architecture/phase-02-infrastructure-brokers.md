# Phase 2: Infrastructure Brokers

## Context Links

- **Parent Plan:** [plan.md](./plan.md)
- **Dependencies:** [Phase 1: Domain Layer](./phase-01-domain-layer-models.md)
- **Blocked By:** Phase 1 (Order/Position domain models)
- **Research:** [OKX SDK Integration](./research/researcher-01-okx-sdk-integration.md)

## Overview

| Field | Value |
|-------|-------|
| Date | 2026-01-31 |
| Priority | P1 |
| Status | pending |
| Effort | 4h |

Implement broker abstraction layer with IBroker interface, PaperBroker for simulation, and OKXBroker for live trading. All external I/O isolated in infrastructure layer.

## Key Insights

1. **python-okx preferred** - 1.3M downloads, 827 stars, 11 contributors, stable
2. **REST for orders, WS for status** - OKX rate limits favor this pattern
3. **TP/SL constraint** - Cannot attach to market orders, use algo orders
4. **Same interface** - PaperBroker and OKXBroker share IBroker interface
5. **Backtest parity** - PaperBroker simulates realistic fills with slippage

## Requirements

### Functional
- IBroker interface with submit_order, cancel_order, get_positions, get_balance
- PaperBroker simulates fills with configurable slippage
- OKXBroker uses okx-sdk for REST orders and WS status updates
- BrokerFactory creates broker instance from config string

### Non-Functional
- Thread-safe order submission
- Exponential backoff on connection failures
- Order ID tracking for reconciliation
- Async interface throughout

## Architecture

### Broker Layer Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    INFRASTRUCTURE LAYER                          │
│                    (All External I/O)                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                     IBroker (ABC)                            ││
│  │  - submit_order(order: Order) → OrderResult                 ││
│  │  - cancel_order(order_id: str) → bool                       ││
│  │  - get_positions() → list[Position]                         ││
│  │  - get_balance() → AccountBalance                           ││
│  │  - subscribe_order_updates(callback) → None                 ││
│  └──────────────────────┬──────────────────────────────────────┘│
│                         │                                        │
│           ┌─────────────┴─────────────┐                         │
│           ▼                           ▼                         │
│  ┌─────────────────┐        ┌─────────────────┐                │
│  │   PaperBroker   │        │   OKXBroker     │                │
│  │ (Simulation)    │        │ (Live Trading)  │                │
│  │                 │        │                 │                │
│  │ - In-memory     │        │ - okx-sdk REST  │                │
│  │ - Slippage sim  │        │ - okx-sdk WS    │                │
│  │ - Fill delay    │        │ - Auth handling │                │
│  └─────────────────┘        └─────────────────┘                │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                   BrokerFactory                              ││
│  │  create(broker_type: str, config: dict) → IBroker           ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### OKX Order Flow

```
Order → OKXBroker.submit_order()
           │
           ├──▶ REST: POST /api/v5/trade/order
           │         └── Returns: ordId, state
           │
           └──▶ WS: Subscribe orders channel
                     └── Receives: fill updates
                              │
                              ▼
                     OrderFilledEvent → PositionTracker
```

## Related Code Files

### Files to Create

```
src/infrastructure/brokers/
├── __init__.py
├── interface.py              # IBroker ABC
├── models.py                 # OrderResult, AccountBalance DTOs
├── factory.py                # BrokerFactory
├── paper/
│   ├── __init__.py
│   └── paper_broker.py       # PaperBroker implementation
└── okx/
    ├── __init__.py
    ├── okx_broker.py         # OKXBroker implementation
    ├── okx_auth.py           # Authentication helpers
    └── okx_mapper.py         # Map OKX responses to domain
```

### Files to Modify

```
src/infrastructure/__init__.py    # Export brokers module
src/config.py                     # Add OKX credentials settings
pyproject.toml                    # Add okx-sdk dependency
```

## Implementation Steps

### Step 1: Add python-okx Dependency (10 min)

1. Update `pyproject.toml` Python version:
   ```toml
   requires-python = ">=3.12"
   ```
2. Add dependency:
   ```toml
   [project.dependencies]
   python-okx = ">=0.4.1"
   ```
3. Update mypy config:
   ```toml
   python_version = "3.12"
   ```
4. Run `uv sync` to install

### Step 2: IBroker Interface (30 min)

1. Create `src/infrastructure/brokers/__init__.py`
2. Create `interface.py`:
   ```python
   from abc import ABC, abstractmethod
   from typing import Callable

   from src.domain.order import Order, OrderStatus
   from src.domain.position import Position

   class OrderResult:
       order_id: str
       status: OrderStatus
       filled_quantity: float
       filled_price: float | None
       error_message: str | None

   class AccountBalance:
       total_equity: float
       available_balance: float
       currency: str

   class IBroker(ABC):
       @abstractmethod
       async def submit_order(self, order: Order) -> OrderResult:
           """Submit order to broker."""
           ...

       @abstractmethod
       async def cancel_order(self, order_id: str) -> bool:
           """Cancel order by ID."""
           ...

       @abstractmethod
       async def get_positions(self) -> list[Position]:
           """Get all open positions."""
           ...

       @abstractmethod
       async def get_balance(self) -> AccountBalance:
           """Get account balance."""
           ...

       @abstractmethod
       async def subscribe_order_updates(
           self, callback: Callable[[OrderResult], None]
       ) -> None:
           """Subscribe to order status updates."""
           ...
   ```

### Step 3: PaperBroker Implementation (60 min)

1. Create `src/infrastructure/brokers/paper/__init__.py`
2. Create `paper_broker.py`:
   ```python
   class PaperBroker(IBroker):
       def __init__(
           self,
           initial_balance: float = 100_000.0,
           slippage_percent: float = 0.001,  # 0.1% default
           fill_delay_ms: int = 50
       ):
           self._balance = initial_balance
           self._positions: dict[str, Position] = {}
           self._orders: dict[str, Order] = {}
           self._slippage = slippage_percent
           self._fill_delay = fill_delay_ms
           self._order_callbacks: list[Callable] = []
           self._lock = asyncio.Lock()

       async def submit_order(self, order: Order) -> OrderResult:
           async with self._lock:
               # Simulate network delay
               await asyncio.sleep(self._fill_delay / 1000)

               # Apply slippage
               fill_price = self._apply_slippage(
                   order.price or order.limit_price,
                   order.side
               )

               # Update balance and position
               self._execute_fill(order, fill_price)

               result = OrderResult(
                   order_id=str(uuid4()),
                   status=OrderStatus.FILLED,
                   filled_quantity=order.quantity,
                   filled_price=fill_price
               )

               # Notify subscribers
               for callback in self._order_callbacks:
                   await callback(result)

               return result
   ```
3. Implement remaining methods

### Step 4: OKXBroker Implementation (90 min)

1. Create `src/infrastructure/brokers/okx/__init__.py`
2. Create `okx_auth.py` for credential management
3. Create `okx_mapper.py`:
   ```python
   def map_okx_order_state(state: str) -> OrderStatus:
       mapping = {
           "live": OrderStatus.SUBMITTED,
           "partially_filled": OrderStatus.PARTIALLY_FILLED,
           "filled": OrderStatus.FILLED,
           "canceled": OrderStatus.CANCELLED,
       }
       return mapping.get(state, OrderStatus.PENDING)

   def map_order_to_okx_params(order: Order) -> dict:
       return {
           "instId": f"{order.symbol}-USDT",
           "tdMode": "cash",
           "side": order.side.value,
           "ordType": order.order_type.value,
           "sz": str(order.quantity),
           "px": str(order.price) if order.price else None,
       }
   ```
4. Create `okx_broker.py`:
   ```python
   from okx import Trade, Account
   from okx.websocket import WsPrivate

   class OKXBroker(IBroker):
       def __init__(
           self,
           api_key: str,
           api_secret: str,
           passphrase: str,
           demo: bool = True
       ):
           flag = "1" if demo else "0"  # 1=demo, 0=live
           self._trade = Trade.TradeAPI(api_key, api_secret, passphrase, flag=flag)
           self._account = Account.AccountAPI(api_key, api_secret, passphrase, flag=flag)
           self._ws: WsPrivate | None = None
           self._demo = demo
           self._order_callbacks: list[Callable] = []

       async def submit_order(self, order: Order) -> OrderResult:
           params = map_order_to_okx_params(order)

           # Use thread pool for blocking SDK call
           loop = asyncio.get_event_loop()
           response = await loop.run_in_executor(
               None,
               lambda: self._trade.place_order(**params)
           )

           return OrderResult(
               order_id=response["data"][0]["ordId"],
               status=map_okx_order_state(response["data"][0]["sCode"]),
               filled_quantity=0,
               filled_price=None
           )

       async def subscribe_order_updates(self, callback: Callable) -> None:
           self._order_callbacks.append(callback)

           if not self._ws:
               self._ws = WsPrivate(...)
               # Subscribe to private orders channel
               self._ws.subscribe([{"channel": "orders", "instType": "SPOT"}])
   ```

### Step 5: BrokerFactory (20 min)

1. Create `factory.py`:
   ```python
   class BrokerFactory:
       @staticmethod
       def create(broker_type: str, config: dict) -> IBroker:
           if broker_type == "paper":
               return PaperBroker(
                   initial_balance=config.get("initial_balance", 100_000),
                   slippage_percent=config.get("slippage", 0.001)
               )
           elif broker_type == "okx":
               return OKXBroker(
                   api_key=config["api_key"],
                   api_secret=config["api_secret"],
                   passphrase=config["passphrase"],
                   demo=config.get("demo", True)
               )
           else:
               raise ValueError(f"Unknown broker type: {broker_type}")
   ```

### Step 6: Config Updates (15 min)

1. Update `src/config.py`:
   ```python
   # Add to Settings class
   okx_api_key: str | None = None
   okx_api_secret: str | None = None
   okx_passphrase: str | None = None
   okx_demo_mode: bool = True
   ```
2. Update `.env.example` with OKX placeholders

## Todo List

- [ ] Add okx-sdk to dependencies
- [ ] Create IBroker interface and models
- [ ] Implement PaperBroker with slippage simulation
- [ ] Implement OKXBroker REST order placement
- [ ] Implement OKXBroker WebSocket order updates
- [ ] Create BrokerFactory
- [ ] Add OKX settings to config.py
- [ ] Write unit tests for PaperBroker
- [ ] Write integration tests for OKXBroker (demo mode)

## Success Criteria

1. PaperBroker fills orders with configurable slippage
2. OKXBroker places orders via REST API
3. OKXBroker receives fill updates via WebSocket
4. BrokerFactory creates correct broker from string
5. Same test can run on both brokers (interface parity)

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| python-okx API changes | Low | Medium | Pin version, monitor releases |
| OKX rate limit hit | Medium | High | Queue orders, respect limits |
| WebSocket disconnect | Medium | Medium | Exponential backoff, auto-reconnect |
| Auth credential leak | Low | Critical | Use env vars, never log secrets |

## Security Considerations

- **Credentials in env vars only** - Never hardcode or log
- **Demo mode default** - OKX demo mode enabled by default
- **Passphrase hashing** - okx-sdk handles HMAC signing
- **WebSocket auth** - Separate auth from REST (SDK handles)

## Next Steps

After Phase 2 completion:
1. Proceed to [Phase 3: Feature Layer](./phase-03-feature-strategy-trading.md)
2. StrategyEngine will use IBroker for order submission
3. OrderManager will track orders across broker implementations
