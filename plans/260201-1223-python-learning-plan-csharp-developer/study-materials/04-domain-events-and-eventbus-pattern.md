# Domain Events & EventBus Pattern

## Event Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    ORDER FILL SCENARIO                          │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────┐
│   OrderManager   │
│                  │
│  on_fill():      │
│    event = OrderFilledEvent(
│        order_id="123",
│        symbol="AAPL",
│        filled_price=150.0
│    )
│    await event_bus.publish(event)  ──────────────────┐
│                  │                                    │
└──────────────────┘                                    │
                                                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                         EVENT BUS                                │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  _subscribers: dict[type, list[Callable]]                 │  │
│  │                                                           │  │
│  │  {                                                        │  │
│  │    OrderFilledEvent: [                                    │  │
│  │      position_tracker._on_order_filled,  ←───┐            │  │
│  │      risk_manager._on_order_filled,      ←───┤ Handlers   │  │
│  │      notification._on_order_filled       ←───┘            │  │
│  │    ],                                                     │  │
│  │    BarCompletedEvent: [                                   │  │
│  │      strategy._on_bar,                                    │  │
│  │      dashboard._on_bar                                    │  │
│  │    ]                                                      │  │
│  │  }                                                        │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  async def publish(event):                                      │
│      for handler in _subscribers[type(event)]:                  │
│          await handler(event)  # Call each subscriber           │
│                                                                  │
└────────────────────┬───────────────────┬───────────────────┬────┘
                     │                   │                   │
                     ▼                   ▼                   ▼
        ┌────────────────┐  ┌────────────────┐  ┌────────────────┐
        │PositionTracker │  │  RiskManager   │  │ Notification   │
        │                │  │                │  │                │
        │ _on_order_     │  │ _on_order_     │  │ _on_order_     │
        │ filled(event): │  │ filled(event): │  │ filled(event): │
        │   # Update     │  │   # Check      │  │   # Send       │
        │   # position   │  │   # exposure   │  │   # alert      │
        └────────────────┘  └────────────────┘  └────────────────┘
```

## Event Class Structure

```python
# src/domain/shared/domain_event.py

@dataclass(frozen=True)  # ← Immutable!
class DomainEvent:
    """Base class for all domain events."""
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, DomainEvent):
            return self.event_id == other.event_id
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.event_id)
```

```python
# src/domain/order/order_event.py

@dataclass(frozen=True)
class OrderFilledEvent(DomainEvent):
    """Published when order is completely filled."""
    order_id: str
    strategy_id: str
    symbol: str
    exchange: str
    side: str  # "BUY" or "SELL"
    filled_quantity: float
    filled_price: float
```

## C# INotification Comparison

```
┌──────────────────────────────────┬──────────────────────────────────┐
│           C# MediatR             │        Python PocketQuant         │
├──────────────────────────────────┼──────────────────────────────────┤
│                                  │                                   │
│  // Event (notification)         │  # Event                          │
│  public class OrderFilledEvent   │  @dataclass(frozen=True)          │
│    : INotification               │  class OrderFilledEvent(          │
│  {                               │      DomainEvent                  │
│    public Guid OrderId { get; }  │  ):                               │
│    public decimal Price { get; } │      order_id: str                │
│  }                               │      filled_price: float          │
│                                  │                                   │
├──────────────────────────────────┼──────────────────────────────────┤
│                                  │                                   │
│  // Handler                      │  # Handler (just a function)      │
│  public class PositionHandler    │  async def on_order_filled(       │
│    : INotificationHandler<       │      event: OrderFilledEvent      │
│        OrderFilledEvent>         │  ) -> None:                       │
│  {                               │      # Update position            │
│    public Task Handle(           │      ...                          │
│      OrderFilledEvent e,         │                                   │
│      CancellationToken ct        │                                   │
│    ) { ... }                     │                                   │
│  }                               │                                   │
│                                  │                                   │
├──────────────────────────────────┼──────────────────────────────────┤
│                                  │                                   │
│  // Subscription (DI auto)       │  # Subscription (manual)          │
│  services.AddMediatR(...)        │  event_bus.subscribe(             │
│  // Auto-discovers handlers      │      OrderFilledEvent,            │
│                                  │      on_order_filled              │
│                                  │  )                                │
│                                  │                                   │
├──────────────────────────────────┼──────────────────────────────────┤
│                                  │                                   │
│  // Publishing                   │  # Publishing                     │
│  await _mediator.Publish(        │  await event_bus.publish(         │
│    new OrderFilledEvent(...)     │      OrderFilledEvent(...)        │
│  );                              │  )                                │
│                                  │                                   │
└──────────────────────────────────┴──────────────────────────────────┘
```

## Why Frozen (Immutable) Events?

```
┌─────────────────────────────────────────────────────────────────┐
│  PROBLEM: Mutable Events                                        │
│                                                                  │
│  event = OrderFilledEvent(price=100.0)                          │
│  await event_bus.publish(event)                                 │
│                                                                  │
│  # Handler A modifies event!                                    │
│  event.price = 999.0  # Mutation!                               │
│                                                                  │
│  # Handler B sees wrong price!                                  │
│  print(event.price)  # 999.0 ← Data corruption!                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  SOLUTION: frozen=True                                          │
│                                                                  │
│  @dataclass(frozen=True)                                        │
│  class OrderFilledEvent:                                        │
│      price: float                                               │
│                                                                  │
│  event = OrderFilledEvent(price=100.0)                          │
│  event.price = 999.0                                            │
│  # ↑ FrozenInstanceError! Cannot modify!                        │
│                                                                  │
│  # All handlers see original value                              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## EventBus Implementation

```python
# src/common/messaging/event_bus.py

class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[type, list[EventHandler]] = {}
        self._history: deque[DomainEvent] = deque(maxlen=50)

    def subscribe(
        self,
        event_type: type[T],
        handler: EventHandler[T]
    ) -> None:
        """Register handler for event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    async def publish(self, event: DomainEvent) -> None:
        """Publish event to all subscribers."""
        self._history.append(event)

        handlers = self._subscribers.get(type(event), [])
        for handler in handlers:
            result = handler(event)
            if inspect.iscoroutine(result):
                await result  # Await if async handler

    async def publish_all(self, events: list[DomainEvent]) -> None:
        """Publish multiple events in order."""
        for event in events:
            await self.publish(event)
```

## Decoupling Benefit

```
┌─────────────────────────────────────────────────────────────────┐
│  WITHOUT EVENTS (Tight Coupling)                                │
│                                                                  │
│  class OrderManager:                                            │
│      def __init__(                                              │
│          self,                                                  │
│          position_tracker,    # ← Knows about positions        │
│          risk_manager,        # ← Knows about risk             │
│          notification,        # ← Knows about notifications    │
│          dashboard,           # ← Knows about UI               │
│          analytics            # ← Knows about analytics        │
│      ):                                                         │
│          ...                                                    │
│                                                                  │
│      async def on_fill(self, order):                            │
│          await self._position.update(...)   # Direct call      │
│          await self._risk.check(...)        # Direct call      │
│          await self._notify.send(...)       # Direct call      │
│          await self._dashboard.refresh(...) # Direct call      │
│          await self._analytics.track(...)   # Direct call      │
│                                                                  │
│  # Adding new subscriber = modify OrderManager!                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  WITH EVENTS (Loose Coupling)                                   │
│                                                                  │
│  class OrderManager:                                            │
│      def __init__(self, event_bus):  # Only knows EventBus     │
│          self._event_bus = event_bus                            │
│                                                                  │
│      async def on_fill(self, order):                            │
│          # Just publish - doesn't know who listens!            │
│          await self._event_bus.publish(                         │
│              OrderFilledEvent(...)                              │
│          )                                                      │
│                                                                  │
│  # Adding new subscriber = just subscribe!                      │
│  # OrderManager unchanged!                                      │
│                                                                  │
│  event_bus.subscribe(OrderFilledEvent, new_feature.handle)      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## File Locations

```
src/
├── domain/
│   ├── shared/
│   │   └── domain_event.py      # Base DomainEvent class
│   ├── order/
│   │   └── order_event.py       # OrderFilledEvent, etc.
│   ├── ohlcv/
│   │   └── ohlcv_event.py       # BarCompletedEvent, etc.
│   └── quote/
│       └── quote_event.py       # QuoteReceivedEvent
│
├── common/
│   └── messaging/
│       ├── event_bus.py         # EventBus class
│       └── event_handler.py     # EventHandler type alias
│
├── features/
│   └── trading/
│       └── managers/
│           ├── order_manager.py     # Publishes events
│           └── position_tracker.py  # Subscribes to events
│
└── main.py                      # Event subscriptions (lifespan)
```

## Registration Pattern

```python
# main.py - lifespan context manager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create event bus
    event_bus = EventBus()

    # Create managers with event bus
    position_tracker = PositionTracker(event_bus)
    order_manager = OrderManager(event_bus)

    # Subscribe to events
    event_bus.subscribe(
        OrderFilledEvent,
        position_tracker._on_order_filled
    )
    event_bus.subscribe(
        OrderFilledEvent,
        risk_manager._on_order_filled
    )

    yield

    # Cleanup
```
