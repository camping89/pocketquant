# Python Asyncio Guide

Comprehensive asyncio guide for developers building trading systems, with Python 3.14 improvements.

## Coroutine vs Regular Functions

### Regular Functions (Synchronous)

```python
import time

def fetch_price(symbol: str) -> float:
    """Synchronous function - blocks until complete."""
    time.sleep(1)  # Simulates network delay
    return 150.25

def process_orders(symbols: list[str]) -> list[float]:
    """Sequential execution - slow for multiple symbols."""
    prices = []
    for symbol in symbols:
        price = fetch_price(symbol)  # Blocks for 1 second
        prices.append(price)
    return prices

# Takes 3 seconds for 3 symbols
start = time.time()
prices = process_orders(["AAPL", "MSFT", "GOOGL"])
print(f"Time: {time.time() - start:.2f}s")  # ~3.0s
```

### Coroutines (Asynchronous)

```python
import asyncio
from typing import Coroutine

async def fetch_price_async(symbol: str) -> float:
    """Async coroutine - yields control during I/O."""
    await asyncio.sleep(1)  # Non-blocking sleep
    return 150.25

async def process_orders_async(symbols: list[str]) -> list[float]:
    """Concurrent execution - fast for multiple symbols."""
    tasks = [fetch_price_async(symbol) for symbol in symbols]
    prices = await asyncio.gather(*tasks)
    return list(prices)

# Takes 1 second for 3 symbols (concurrent)
async def main():
    start = asyncio.get_event_loop().time()
    prices = await process_orders_async(["AAPL", "MSFT", "GOOGL"])
    elapsed = asyncio.get_event_loop().time() - start
    print(f"Time: {elapsed:.2f}s")  # ~1.0s

asyncio.run(main())
```

### Key Differences

| Feature | Regular Function | Coroutine |
|---------|-----------------|-----------|
| Definition | `def func():` | `async def func():` |
| Execution | Blocking | Non-blocking |
| Return type | Direct value | Awaitable/Coroutine |
| Call method | `result = func()` | `result = await func()` |
| Entry point | Direct call | `asyncio.run()` |
| Concurrency | Threading/multiprocessing | Event loop |

## inspect Module Functions

### iscoroutine() vs iscoroutinefunction()

```python
import asyncio
import inspect

async def async_fetch_price(symbol: str) -> float:
    await asyncio.sleep(0.1)
    return 150.25

def sync_fetch_price(symbol: str) -> float:
    return 150.25

# Check if function is a coroutine function
print(inspect.iscoroutinefunction(async_fetch_price))  # True
print(inspect.iscoroutinefunction(sync_fetch_price))   # False

# Check if object is a coroutine instance
coro = async_fetch_price("AAPL")  # Returns coroutine object
print(inspect.iscoroutine(coro))                       # True
print(inspect.iscoroutine(async_fetch_price))          # False (function, not instance)

# Clean up coroutine
coro.close()
```

### asyncio.iscoroutinefunction() (Recommended)

```python
import asyncio

async def handler_async(event_data: dict):
    await asyncio.sleep(0.1)
    print(f"Async: {event_data}")

def handler_sync(event_data: dict):
    print(f"Sync: {event_data}")

# Use asyncio.iscoroutinefunction() - more robust
print(asyncio.iscoroutinefunction(handler_async))  # True
print(asyncio.iscoroutinefunction(handler_sync))   # False

# Also works with wrapped functions
import functools

@functools.wraps(handler_async)
def wrapped():
    return handler_async({"test": "data"})

print(asyncio.iscoroutinefunction(handler_async))  # True
```

### Practical Usage in Event System

```python
import asyncio
import inspect
from typing import Callable, Any

class EventBus:
    """Handle both sync and async event handlers."""

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = {}

    def register(self, event_type: str, handler: Callable) -> None:
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    async def emit(self, event_type: str, **kwargs) -> None:
        """Emit event, auto-detecting sync/async handlers."""
        if event_type not in self._handlers:
            return

        tasks = []
        for handler in self._handlers[event_type]:
            # Use asyncio.iscoroutinefunction for detection
            if asyncio.iscoroutinefunction(handler):
                tasks.append(handler(**kwargs))
            else:
                # Run sync handler in executor to avoid blocking
                loop = asyncio.get_event_loop()
                tasks.append(loop.run_in_executor(None, lambda h=handler: h(**kwargs)))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

# Usage
bus = EventBus()

async def async_logger(symbol: str, price: float):
    await asyncio.sleep(0.1)
    print(f"Async log: {symbol} @ {price}")

def sync_logger(symbol: str, price: float):
    print(f"Sync log: {symbol} @ {price}")

bus.register("price_update", async_logger)
bus.register("price_update", sync_logger)

async def main():
    await bus.emit("price_update", symbol="AAPL", price=150.25)

asyncio.run(main())
```

## Python 3.14 Asyncio Improvements

### TaskGroup with Improved Error Handling

```python
import asyncio
from asyncio import TaskGroup

async def fetch_market_data(symbol: str) -> dict:
    """Fetch market data with potential failure."""
    await asyncio.sleep(0.5)
    if symbol == "INVALID":
        raise ValueError(f"Invalid symbol: {symbol}")
    return {"symbol": symbol, "price": 150.25, "volume": 1000000}

async def process_symbols_v314():
    """Python 3.14 TaskGroup - improved exception handling."""
    symbols = ["AAPL", "MSFT", "GOOGL", "INVALID"]

    try:
        async with TaskGroup() as tg:
            # All tasks run concurrently
            tasks = [tg.create_task(fetch_market_data(s)) for s in symbols]

        # Only reached if all tasks succeed
        results = [t.result() for t in tasks]
        return results

    except* ValueError as eg:
        # ExceptionGroup - handle multiple exceptions
        print(f"Caught {len(eg.exceptions)} ValueErrors:")
        for exc in eg.exceptions:
            print(f"  - {exc}")
        return None

# Run
asyncio.run(process_symbols_v314())
```

### Timeout Improvements

```python
import asyncio

async def fetch_with_timeout_v314(symbol: str) -> float:
    """Python 3.14 improved timeout handling."""

    async def slow_fetch():
        await asyncio.sleep(5)  # Simulates slow API
        return 150.25

    try:
        # Cleaner timeout syntax in 3.14
        async with asyncio.timeout(2.0):
            price = await slow_fetch()
            return price
    except TimeoutError:
        print(f"Timeout fetching {symbol}")
        return 0.0

async def main():
    price = await fetch_with_timeout_v314("AAPL")
    print(f"Price: {price}")

asyncio.run(main())
```

### Eager Task Factory (Performance Boost)

```python
import asyncio

async def compute_indicator(values: list[float]) -> float:
    """CPU-bound calculation wrapped in async."""
    # Eagerly execute before awaiting in Python 3.14
    result = sum(values) / len(values)  # Simple moving average
    await asyncio.sleep(0)  # Yield control point
    return result

async def main_v314():
    """Use eager task factory for better performance."""
    # Set eager task factory (Python 3.14+)
    asyncio.get_event_loop().set_task_factory(
        asyncio.eager_task_factory
    )

    values = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
    tasks = [asyncio.create_task(compute_indicator(v)) for v in values]

    # Tasks may complete before gather() is called
    results = await asyncio.gather(*tasks)
    print(f"Indicators: {results}")

asyncio.run(main_v314())
```

## Common Mistakes (Blocking Event Loop)

### Mistake 1: Blocking I/O in Async Function

```python
import asyncio
import time
import requests  # Synchronous HTTP library

# BAD: Blocks event loop
async def fetch_price_bad(symbol: str) -> float:
    # Blocks entire event loop for 1 second!
    response = requests.get(f"https://api.example.com/price/{symbol}")
    return response.json()["price"]

# GOOD: Use async HTTP library
import aiohttp

async def fetch_price_good(symbol: str) -> float:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.example.com/price/{symbol}") as resp:
            data = await resp.json()
            return data["price"]
```

### Mistake 2: time.sleep() Instead of asyncio.sleep()

```python
import asyncio
import time

# BAD: Blocks event loop
async def process_order_bad(order_id: str):
    print(f"Processing {order_id}")
    time.sleep(1)  # BLOCKS EVENT LOOP!
    print(f"Completed {order_id}")

# GOOD: Non-blocking sleep
async def process_order_good(order_id: str):
    print(f"Processing {order_id}")
    await asyncio.sleep(1)  # Yields control
    print(f"Completed {order_id}")

# Demonstrate difference
async def test_blocking():
    start = time.time()
    await asyncio.gather(
        process_order_bad("ORD-1"),
        process_order_bad("ORD-2"),
    )
    print(f"Bad version: {time.time() - start:.2f}s")  # ~2.0s (sequential!)

async def test_non_blocking():
    start = time.time()
    await asyncio.gather(
        process_order_good("ORD-1"),
        process_order_good("ORD-2"),
    )
    print(f"Good version: {time.time() - start:.2f}s")  # ~1.0s (concurrent!)
```

### Mistake 3: CPU-Bound Work Without Executor

```python
import asyncio
from concurrent.futures import ProcessPoolExecutor

def calculate_indicators(prices: list[float]) -> dict:
    """CPU-intensive calculation."""
    # Complex technical indicators calculation
    sma = sum(prices[-20:]) / 20
    ema = prices[-1] * 0.1 + sma * 0.9
    return {"sma": sma, "ema": ema}

# BAD: Blocks event loop
async def analyze_symbols_bad(symbols: dict[str, list[float]]):
    results = {}
    for symbol, prices in symbols.items():
        results[symbol] = calculate_indicators(prices)  # BLOCKS!
    return results

# GOOD: Use ProcessPoolExecutor for CPU-bound work
async def analyze_symbols_good(symbols: dict[str, list[float]]):
    loop = asyncio.get_event_loop()
    with ProcessPoolExecutor() as pool:
        tasks = [
            loop.run_in_executor(pool, calculate_indicators, prices)
            for symbol, prices in symbols.items()
        ]
        results_list = await asyncio.gather(*tasks)

    return dict(zip(symbols.keys(), results_list))
```

### Mistake 4: Forgetting to Await Coroutines

```python
import asyncio

async def save_trade(trade_id: str, data: dict):
    await asyncio.sleep(0.1)  # Simulate DB write
    print(f"Saved trade {trade_id}")

# BAD: Forgot to await
async def process_trade_bad(trade_id: str):
    save_trade(trade_id, {"symbol": "AAPL"})  # Returns coroutine object, doesn't execute!
    print("Trade processed")  # Prints immediately

# GOOD: Await the coroutine
async def process_trade_good(trade_id: str):
    await save_trade(trade_id, {"symbol": "AAPL"})  # Actually executes
    print("Trade processed")  # Prints after save completes

# Python will warn about unawaited coroutine
asyncio.run(process_trade_bad("TR-001"))  # RuntimeWarning!
```

## Mixed Sync/Async Handler Patterns

### Pattern 1: Event Bus with Mixed Handlers

```python
import asyncio
from typing import Callable, Any

class MixedEventBus:
    """Support both sync and async handlers gracefully."""

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = {}

    def on(self, event_type: str):
        def decorator(func: Callable):
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append(func)
            return func
        return decorator

    async def emit(self, event_type: str, **kwargs):
        """Smart emission handling both sync/async."""
        handlers = self._handlers.get(event_type, [])

        # Separate sync and async handlers
        sync_handlers = [h for h in handlers if not asyncio.iscoroutinefunction(h)]
        async_handlers = [h for h in handlers if asyncio.iscoroutinefunction(h)]

        # Run sync handlers in thread pool
        loop = asyncio.get_event_loop()
        sync_tasks = [
            loop.run_in_executor(None, lambda h=h: h(**kwargs))
            for h in sync_handlers
        ]

        # Run async handlers directly
        async_tasks = [h(**kwargs) for h in async_handlers]

        # Wait for all
        await asyncio.gather(*sync_tasks, *async_tasks, return_exceptions=True)

# Usage
bus = MixedEventBus()

@bus.on("trade_executed")
def sync_handler(symbol: str, price: float):
    print(f"Sync: {symbol} @ {price}")

@bus.on("trade_executed")
async def async_handler(symbol: str, price: float):
    await asyncio.sleep(0.1)
    print(f"Async: {symbol} @ {price}")

async def main():
    await bus.emit("trade_executed", symbol="AAPL", price=150.25)

asyncio.run(main())
```

### Pattern 2: Sync Wrapper for Async Functions

```python
import asyncio
from functools import wraps
from typing import TypeVar, Callable

T = TypeVar('T')

def sync_wrapper(async_func: Callable[..., T]) -> Callable[..., T]:
    """Wrap async function to be callable from sync code."""

    @wraps(async_func)
    def wrapper(*args, **kwargs) -> T:
        try:
            # Try to get existing event loop
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No loop running, create new one
            return asyncio.run(async_func(*args, **kwargs))
        else:
            # Loop exists, run in executor
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, async_func(*args, **kwargs))
                return future.result()

    return wrapper

# Usage
async def fetch_price_async(symbol: str) -> float:
    await asyncio.sleep(0.1)
    return 150.25

# Create sync version
fetch_price_sync = sync_wrapper(fetch_price_async)

# Call from sync code
price = fetch_price_sync("AAPL")
print(f"Price: {price}")
```

### Pattern 3: Async Context Manager

```python
import asyncio
from typing import AsyncIterator

class DatabaseConnection:
    """Async context manager for database connections."""

    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.connection = None

    async def __aenter__(self):
        """Async enter - acquire connection."""
        await asyncio.sleep(0.1)  # Simulate connection
        self.connection = f"Connected to {self.connection_string}"
        print(f"Acquired: {self.connection}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async exit - release connection."""
        await asyncio.sleep(0.1)  # Simulate cleanup
        print(f"Released: {self.connection}")
        self.connection = None

    async def execute(self, query: str):
        """Execute query."""
        await asyncio.sleep(0.05)
        return f"Result of: {query}"

# Usage
async def save_trade(trade_id: str):
    async with DatabaseConnection("postgresql://localhost") as db:
        result = await db.execute(f"INSERT INTO trades VALUES ('{trade_id}')")
        print(result)

asyncio.run(save_trade("TR-001"))
```

## Best Practices for Trading Systems

1. **Use async for I/O-bound operations:**
   - Database queries
   - HTTP API calls
   - WebSocket connections
   - Message queue operations

2. **Use threads/processes for CPU-bound:**
   - Technical indicator calculations
   - Backtesting simulations
   - Data transformations
   - Heavy number crunching

3. **Avoid blocking the event loop:**
   - Use `asyncio.sleep()` not `time.sleep()`
   - Use `aiohttp` not `requests`
   - Use async database drivers (asyncpg, motor)

4. **Handle exceptions properly:**
   - Use `try/except` in coroutines
   - Use `gather(..., return_exceptions=True)`
   - Log all exceptions for audit trails

5. **Use timeouts for external calls:**
   - Always timeout API calls
   - Use `asyncio.timeout()` context manager
   - Set reasonable timeout values

6. **Monitor event loop lag:**
   - Use `loop.slow_callback_duration`
   - Profile async code with `asyncio` debug mode
   - Watch for blocking operations

## References

- [Python 3.14 Asyncio Documentation](https://docs.python.org/3.14/library/asyncio.html)
- [PEP 492: Coroutines with async/await](https://peps.python.org/pep-0492/)
- [Real Python: Async IO Guide](https://realpython.com/async-io-python/)
