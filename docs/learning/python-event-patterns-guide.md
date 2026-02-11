# Python Event Patterns Guide

Event-driven patterns for Python developers transitioning from .NET, with focus on trading systems.

## Observer Pattern in Python

### Basic Observer Implementation

```python
from typing import Callable, Any
from collections import defaultdict

class Observable:
    """Simple observer pattern implementation."""

    def __init__(self):
        self._observers: dict[str, list[Callable]] = defaultdict(list)

    def subscribe(self, event_name: str, callback: Callable) -> None:
        """Subscribe to event."""
        self._observers[event_name].append(callback)

    def unsubscribe(self, event_name: str, callback: Callable) -> None:
        """Unsubscribe from event."""
        self._observers[event_name].remove(callback)

    def notify(self, event_name: str, *args, **kwargs) -> None:
        """Notify all subscribers."""
        for callback in self._observers[event_name]:
            callback(*args, **kwargs)

# Usage example
class TradingEngine(Observable):
    def execute_trade(self, symbol: str, quantity: int, price: float):
        # Execute trade logic...
        self.notify("trade_executed", symbol=symbol, quantity=quantity, price=price)

# Subscribe to events
engine = TradingEngine()
engine.subscribe("trade_executed", lambda **kwargs: print(f"Trade: {kwargs}"))
engine.execute_trade("AAPL", 100, 150.25)
```

### Observer with Type Safety

```python
from typing import Protocol, Callable
from collections.abc import Iterable

class TradeEvent:
    """Typed event data."""
    def __init__(self, symbol: str, quantity: int, price: float):
        self.symbol = symbol
        self.quantity = quantity
        self.price = price

class TradeObserver(Protocol):
    """Type-safe observer interface."""
    def on_trade_executed(self, event: TradeEvent) -> None: ...

class TypedObservable:
    """Type-safe observable."""

    def __init__(self):
        self._trade_observers: list[TradeObserver] = []

    def add_observer(self, observer: TradeObserver) -> None:
        self._trade_observers.append(observer)

    def notify_trade(self, event: TradeEvent) -> None:
        for observer in self._trade_observers:
            observer.on_trade_executed(event)

# Usage
class TradeLogger:
    def on_trade_executed(self, event: TradeEvent) -> None:
        print(f"Logged: {event.symbol} @ {event.price}")

class RiskManager:
    def on_trade_executed(self, event: TradeEvent) -> None:
        print(f"Risk check: {event.symbol}")

observable = TypedObservable()
observable.add_observer(TradeLogger())
observable.add_observer(RiskManager())
observable.notify_trade(TradeEvent("AAPL", 100, 150.25))
```

## Decorator-Based Registry Pattern

### Event Handler Registry

```python
from typing import Callable, Any
from collections import defaultdict
import functools

class EventBus:
    """Centralized event bus with decorator registration."""

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = defaultdict(list)

    def on(self, event_type: str) -> Callable:
        """Decorator for registering event handlers."""
        def decorator(func: Callable) -> Callable:
            self._handlers[event_type].append(func)

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            return wrapper
        return decorator

    def emit(self, event_type: str, *args, **kwargs) -> None:
        """Emit event to all registered handlers."""
        for handler in self._handlers[event_type]:
            handler(*args, **kwargs)

    def emit_async(self, event_type: str, *args, **kwargs) -> list[Any]:
        """Emit to async handlers (returns awaitables)."""
        awaitables = []
        for handler in self._handlers[event_type]:
            result = handler(*args, **kwargs)
            if hasattr(result, '__await__'):
                awaitables.append(result)
        return awaitables

# Global event bus
event_bus = EventBus()

# Register handlers using decorator
@event_bus.on("order_placed")
def log_order(order_id: str, symbol: str, quantity: int):
    print(f"Order {order_id}: {symbol} x{quantity}")

@event_bus.on("order_placed")
def update_positions(order_id: str, symbol: str, quantity: int):
    print(f"Position updated for {symbol}")

@event_bus.on("order_placed")
def notify_risk_system(order_id: str, symbol: str, quantity: int):
    print(f"Risk check for {symbol}")

# Emit event
event_bus.emit("order_placed", order_id="ORD-001", symbol="AAPL", quantity=100)
```

### Auto-Discovery Pattern

```python
import inspect
from typing import Any

class EventHandler:
    """Base class for event handlers with auto-discovery."""

    @classmethod
    def get_event_handlers(cls) -> dict[str, Callable]:
        """Auto-discover methods decorated with @handles."""
        handlers = {}
        for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
            if hasattr(method, '_event_type'):
                handlers[method._event_type] = method
        return handlers

def handles(event_type: str):
    """Decorator marking method as event handler."""
    def decorator(func: Callable) -> Callable:
        func._event_type = event_type
        return func
    return decorator

# Usage
class OrderEventHandler(EventHandler):
    @handles("order_placed")
    def handle_order_placed(self, order_id: str, symbol: str):
        print(f"Handling order: {order_id}")

    @handles("order_cancelled")
    def handle_order_cancelled(self, order_id: str):
        print(f"Handling cancellation: {order_id}")

    def regular_method(self):
        """Not an event handler."""
        pass

# Auto-register handlers
handler = OrderEventHandler()
for event_type, method in handler.get_event_handlers().items():
    event_bus.on(event_type)(lambda **kwargs: method(handler, **kwargs))
```

## Comparison with .NET Event Handling

### .NET Style (C#)

```csharp
// C# event pattern
public class TradingEngine
{
    public event EventHandler<TradeEventArgs> TradeExecuted;

    protected virtual void OnTradeExecuted(TradeEventArgs e)
    {
        TradeExecuted?.Invoke(this, e);
    }

    public void ExecuteTrade(string symbol, int quantity)
    {
        // Execute trade...
        OnTradeExecuted(new TradeEventArgs { Symbol = symbol, Quantity = quantity });
    }
}

// Subscribe
engine.TradeExecuted += (sender, e) => Console.WriteLine($"Trade: {e.Symbol}");
```

### Python Equivalent

```python
from typing import Callable
from dataclasses import dataclass

@dataclass
class TradeEventArgs:
    symbol: str
    quantity: int
    price: float

class TradingEngine:
    """Python equivalent of .NET event pattern."""

    def __init__(self):
        self._trade_executed_handlers: list[Callable[[TradeEventArgs], None]] = []

    @property
    def trade_executed(self):
        """Property-based event subscription."""
        class EventSubscription:
            def __init__(self, handlers: list):
                self._handlers = handlers

            def __iadd__(self, handler: Callable[[TradeEventArgs], None]):
                """Subscribe using += operator."""
                self._handlers.append(handler)
                return self

            def __isub__(self, handler: Callable[[TradeEventArgs], None]):
                """Unsubscribe using -= operator."""
                self._handlers.remove(handler)
                return self

            def invoke(self, args: TradeEventArgs):
                """Invoke all handlers."""
                for handler in self._handlers:
                    handler(args)

        return EventSubscription(self._trade_executed_handlers)

    def execute_trade(self, symbol: str, quantity: int, price: float):
        # Execute trade...
        args = TradeEventArgs(symbol=symbol, quantity=quantity, price=price)
        self.trade_executed.invoke(args)

# Usage (similar to C#)
engine = TradingEngine()
engine.trade_executed += lambda e: print(f"Trade: {e.symbol}")
engine.execute_trade("AAPL", 100, 150.25)
```

## Asyncio Considerations

### Mixed Sync/Async Event Handlers

```python
import asyncio
import inspect
from typing import Callable, Any

class AsyncEventBus:
    """Event bus supporting both sync and async handlers."""

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = {}

    def on(self, event_type: str):
        """Register handler (sync or async)."""
        def decorator(func: Callable):
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append(func)
            return func
        return decorator

    async def emit(self, event_type: str, *args, **kwargs) -> None:
        """Emit event, handling both sync and async handlers."""
        if event_type not in self._handlers:
            return

        tasks = []
        for handler in self._handlers[event_type]:
            if asyncio.iscoroutinefunction(handler):
                # Async handler - schedule as task
                tasks.append(asyncio.create_task(handler(*args, **kwargs)))
            else:
                # Sync handler - run in executor to avoid blocking
                loop = asyncio.get_event_loop()
                tasks.append(loop.run_in_executor(None, handler, *args))

        # Wait for all handlers to complete
        await asyncio.gather(*tasks, return_exceptions=True)

# Usage
bus = AsyncEventBus()

@bus.on("market_data")
async def async_handler(symbol: str, price: float):
    await asyncio.sleep(0.1)  # Simulate async operation
    print(f"Async: {symbol} @ {price}")

@bus.on("market_data")
def sync_handler(symbol: str, price: float):
    print(f"Sync: {symbol} @ {price}")

# Emit event
async def main():
    await bus.emit("market_data", symbol="AAPL", price=150.25)

asyncio.run(main())
```

### Async Event Stream

```python
import asyncio
from typing import AsyncIterator, Any

class AsyncEventStream:
    """Async iterator for event streams."""

    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._subscribers: list[asyncio.Queue] = []

    def publish(self, event: Any) -> None:
        """Publish event to all subscribers."""
        for queue in self._subscribers:
            queue.put_nowait(event)

    async def subscribe(self) -> AsyncIterator[Any]:
        """Subscribe to event stream."""
        queue = asyncio.Queue()
        self._subscribers.append(queue)
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            self._subscribers.remove(queue)

# Usage
stream = AsyncEventStream()

async def consumer():
    """Consume events from stream."""
    async for event in stream.subscribe():
        print(f"Received: {event}")

async def producer():
    """Produce events."""
    for i in range(5):
        stream.publish(f"Event {i}")
        await asyncio.sleep(0.5)

async def main():
    await asyncio.gather(consumer(), producer())
```

## EventBus + Auto-Discovery Example

Complete implementation for trading system:

```python
import asyncio
import inspect
from typing import Callable, Any
from collections import defaultdict

class EventBus:
    """Production-ready event bus with auto-discovery."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._handlers = defaultdict(list)
        return cls._instance

    def register_handler(self, event_type: str, handler: Callable) -> None:
        """Register event handler."""
        self._handlers[event_type].append(handler)

    def auto_register(self, handler_instance: Any) -> None:
        """Auto-register all @handles decorated methods."""
        for name, method in inspect.getmembers(handler_instance):
            if hasattr(method, '_event_types'):
                for event_type in method._event_types:
                    self.register_handler(event_type, method)

    async def emit_async(self, event_type: str, **kwargs) -> None:
        """Emit event asynchronously."""
        tasks = []
        for handler in self._handlers[event_type]:
            if asyncio.iscoroutinefunction(handler):
                tasks.append(handler(**kwargs))
            else:
                loop = asyncio.get_event_loop()
                tasks.append(loop.run_in_executor(None, lambda: handler(**kwargs)))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

def handles(*event_types: str):
    """Decorator for marking event handlers."""
    def decorator(func: Callable) -> Callable:
        func._event_types = event_types
        return func
    return decorator

# Example handlers
class OrderHandlers:
    @handles("order_placed", "order_updated")
    async def log_order(self, order_id: str, symbol: str, **kwargs):
        print(f"LOG: Order {order_id} - {symbol}")

    @handles("order_placed")
    def update_risk(self, order_id: str, symbol: str, **kwargs):
        print(f"RISK: Checking {symbol}")

# Register and use
bus = EventBus()
bus.auto_register(OrderHandlers())

async def main():
    await bus.emit_async("order_placed", order_id="ORD-001", symbol="AAPL")

asyncio.run(main())
```

## Best Practices

1. **Use type hints** for event data structures
2. **Prefer dataclasses** for event arguments over kwargs
3. **Handle exceptions** in event handlers to prevent cascade failures
4. **Use async for I/O-bound** handlers (database, network)
5. **Use threading for CPU-bound** handlers in async context
6. **Keep handlers idempotent** for retry safety
7. **Log all events** for debugging and audit trails
8. **Use weak references** to prevent memory leaks with long-lived observers

## Common Pitfalls

- **Blocking the event loop** with sync I/O in async handlers
- **Circular event chains** causing infinite loops
- **Memory leaks** from unsubscribed handlers
- **Race conditions** in async event handlers
- **Exception propagation** breaking event chains
