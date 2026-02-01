# AsyncIO Mental Model for C# Developers

## The Key Difference

### C# ThreadPool (Multi-Threaded)

```
┌─────────────────────────────────────────────────────┐
│                    ThreadPool                        │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐│
│  │Thread 1 │  │Thread 2 │  │Thread 3 │  │Thread N ││
│  │ Task A  │  │ Task B  │  │ Task C  │  │ Task D  ││
│  │ running │  │ running │  │ running │  │ running ││
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘│
└─────────────────────────────────────────────────────┘
                    ↓
           TRUE PARALLELISM
     (Multiple tasks run simultaneously)
```

### Python AsyncIO (Single-Threaded)

```
┌────────────────────────────────────────────────────────┐
│               Event Loop (1 Thread)                     │
│                                                         │
│   Time →                                                │
│   ═══════════════════════════════════════════════════  │
│                                                         │
│   Task A: [run]──[await I/O]────────────────[resume]   │
│   Task B: ────────[run]──[await I/O]────[resume]───    │
│   Task C: ──────────────[run]──[await]──────[run]──    │
│                                                         │
│   Only ONE task runs at any moment                      │
│   Others are SUSPENDED at await points                  │
└────────────────────────────────────────────────────────┘
                    ↓
            CONCURRENCY (not parallelism)
       (Tasks interleave, never run together)
```

## Why Lock in Single-Threaded Code?

### The Race Condition

```
Without Lock (BROKEN):
═══════════════════════════════════════════════════════

Time 1: Task A reads bar.volume = 100
Time 2: Task A starts await db.save()     ← SUSPENDED
Time 3: Task B reads bar.volume = 100     ← Same stale value!
Time 4: Task B adds 50, bar.volume = 150
Time 5: Task B completes await
Time 6: Task A resumes, adds 25           ← Overwrites B's work!
Time 7: bar.volume = 125                  ← Lost 50 from Task B!
```

```
With asyncio.Lock (CORRECT):
═══════════════════════════════════════════════════════

Time 1: Task A acquires lock
Time 2: Task A reads bar.volume = 100
Time 3: Task A awaits (lock held)
Time 4: Task B tries lock → WAITS         ← Blocked!
Time 5: Task A adds 25, volume = 125
Time 6: Task A releases lock
Time 7: Task B acquires lock
Time 8: Task B reads bar.volume = 125     ← Correct value!
Time 9: Task B adds 50, volume = 175      ← No data loss!
```

## PocketQuant Example: BarManager

```python
# src/features/market_data/managers/bar_manager.py

class BarManager:
    def __init__(self):
        self._lock = asyncio.Lock()  # ← Protects bar state
        self._bars: dict[str, Bar] = {}

    async def add_tick(self, tick: QuoteTick) -> None:
        # Multiple WebSocket messages arrive concurrently
        # Each calls add_tick() - but only ONE can modify at a time

        async with self._lock:  # ← Serialize access
            bar = self._bars.get(tick.symbol)
            if bar is None:
                bar = Bar(...)
                self._bars[tick.symbol] = bar

            bar.high = max(bar.high, tick.price)
            bar.low = min(bar.low, tick.price)
            bar.close = tick.price
            bar.volume += tick.volume
            # ↑ All updates happen atomically
```

## Common Patterns

### Pattern 1: Protect Shared State

```python
class OrderManager:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._pending: dict[str, Order] = {}

    async def submit(self, order: Order) -> None:
        async with self._lock:
            self._pending[order.id] = order

        # I/O outside lock (doesn't need protection)
        await self._broker.submit(order)
```

### Pattern 2: Read-Modify-Write

```python
async def update_position(self, fill: Fill) -> None:
    async with self._lock:
        position = self._positions.get(fill.symbol)
        if position:
            position.quantity += fill.quantity  # Atomic RMW
        else:
            self._positions[fill.symbol] = Position(...)
```

### Pattern 3: Ensure Order of Operations

```python
async def process_events(self, events: list[Event]) -> None:
    async with self._lock:
        for event in events:
            await self._handle(event)  # Events processed in order
```

## When NOT to Use Lock

```python
# ❌ Don't lock for independent reads
async def get_price(self, symbol: str) -> float:
    return self._prices.get(symbol, 0.0)  # Just reading, no race

# ❌ Don't lock for I/O-only operations
async def fetch_data(self, symbol: str) -> Data:
    return await self._api.get(symbol)  # No shared state modified

# ✅ Do lock when modifying shared state
async def update_price(self, symbol: str, price: float) -> None:
    async with self._lock:
        self._prices[symbol] = price
        self._last_update = datetime.now()
```

## Threading.Lock vs AsyncIO.Lock

```python
# ❌ WRONG - blocks entire event loop!
import threading
lock = threading.Lock()

async def bad_function():
    with lock:  # Event loop FROZEN here
        await some_io()  # Can't yield! Deadlock risk!

# ✅ CORRECT - yields to event loop
import asyncio
lock = asyncio.Lock()

async def good_function():
    async with lock:  # Other tasks can run while waiting
        await some_io()  # Yields properly
```

## Mental Checklist

Before adding asyncio.Lock, ask:

1. **Is there shared mutable state?** (dict, list, object attributes)
2. **Are there await points between read and write?**
3. **Could multiple coroutines access simultaneously?**

If YES to all three → Use `asyncio.Lock()`

## Comparison Table

| Aspect | C# SemaphoreSlim | Python asyncio.Lock |
|--------|-----------------|---------------------|
| Thread model | Multi-threaded | Single-threaded |
| Blocking | Blocks thread | Suspends coroutine |
| Acquisition | `await WaitAsync()` | `async with lock:` |
| Release | `finally { Release() }` | Automatic on exit |
| Timeout | `WaitAsync(timeout)` | `asyncio.timeout()` |
| Reentrant | No (use Semaphore) | No |
