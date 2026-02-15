# Race Condition & DI Audit — PocketQuant

**Date:** 2026-02-15
**Scope:** Project-wide database operation safety, DI lifecycle correctness, concurrency risks

---

## CRITICAL: Repository Static Call Bug

**Severity: BLOCKER — Will crash at runtime**

Three services call repository **instance methods** as if they were **class methods** (no `self`):

### OrderManager (`src/application/trading/order_manager.py`)
- Lines 46, 65, 89, 100, 114, 150, 190, 209, 214, 227, 231
- Example: `await OrderRepository.save(order)` — `save()` is an instance method needing `self._database`
- `__init__` only takes `event_bus`, no repository injected

### PositionTracker (`src/application/trading/position_tracker.py`)
- Lines 36, 68, 101, 113, 183
- Example: `await PositionRepository.find_open()` — instance method, not classmethod
- `__init__` only takes `event_bus`, no repository injected

### BacktestRunner (`src/application/backtesting/backtest_runner.py`)
- Lines 123, 142, 157-158
- `await BacktestRepository.save(result)` and `OHLCVRepository.stream(...)` — both instance methods
- `__init__` takes `event_bus, strategy_engine, broker` — no repositories

**Root cause:** Container (`src/container.py:162-168`) correctly wires repository singletons with DI, but these services import the **class** directly and call unbound methods. Python will raise `TypeError: missing required positional argument` at runtime.

**Fix:** Inject repository instances via constructor. Container already has them wired — just need to thread them through.

---

## DI Lifecycle Summary

| Provider | Lifecycle | Safe? |
|---|---|---|
| `settings` | Singleton | OK |
| `database` | Resource (singleton-like) | OK — connection pool |
| `cache` | Resource (singleton-like) | OK — Redis pool |
| All 7 repositories | Singleton | OK for MongoDB — stateless, uses connection pool |
| `event_bus` | Singleton | See below |
| `mediator` | Singleton | OK — stateless dispatcher |
| `broker_factory` | Singleton | OK — factory pattern |
| `bar_manager` | Singleton | See below |
| `quote_service` | Singleton | OK |
| `order_manager` | Resource (singleton-like) | See below |
| `position_tracker` | Resource (singleton-like) | See below |
| `strategy_engine` | Resource (singleton-like) | See below |
| All CQRS handlers | Factory (transient) | OK |

**Verdict on singleton vs transient:** The DI lifecycle choices are correct for this architecture. Repositories as singletons are fine — MongoDB driver handles connection pooling internally. CQRS handlers as Factory (transient) is correct for request isolation. No issues with DI scoping.

---

## Race Condition Analysis

### LOW RISK: EventBus Sequential Publish (OK for now)

`event_bus.py:34-41` — `publish()` awaits each handler sequentially in FIFO order. This means:
- No concurrent handler execution within a single `publish()` call
- Handlers run one at a time, no races between them
- **Safe for current single-event-loop async model**
- Would become a bottleneck if handlers are slow (blocks subsequent handlers)

### LOW RISK: Singleton Services with Locks

`OrderManager`, `PositionTracker`, `StrategyEngine`, `BarManager` all use `asyncio.Lock()` to protect mutable state. Since Python asyncio is single-threaded cooperative multitasking:

- **In-memory dict mutations are atomic** between `await` points
- The locks correctly protect across `await` boundaries (e.g., DB writes)
- No true parallelism — only concurrency at `await` points

**However**, some DB writes happen inside `async with self._lock` (e.g., `order_manager.py:65`, `position_tracker.py:68`). This means:
- Lock is held during DB I/O → potential contention if many events fire quickly
- Not a correctness issue, but a performance concern
- Acceptable for current throughput expectations

### LOW RISK: Parallel Backtest Optimization

`grid_optimizer.py` runs multiple backtests with `asyncio.gather()` + `Semaphore`. Each backtest creates a fresh `PaperBroker`, but:
- They share the same `StrategyEngine` singleton
- They share the same `EventBus` singleton
- Event handlers from different backtests could interleave

**Mitigated by:** Python asyncio single-threaded model — `gather()` tasks interleave at `await` points but don't run truly in parallel. The `StrategyEngine` lock protects shared state.

**Potential issue:** If backtest A's strategy publishes an event that backtest B's handler picks up. Needs verification of event isolation per-backtest.

### NOT A RISK: MongoDB Operations

MongoDB async driver (`motor`/`pymongo.asynchronous`) uses connection pooling internally. Multiple concurrent `replace_one`/`find` calls are safe — the driver handles connection checkout/return. No shared session state. Individual document operations are atomic in MongoDB.

---

## Summary

| Issue | Severity | Status |
|---|---|---|
| Repository static calls (3 services) | **BLOCKER** | Must fix before any runtime testing |
| DI lifecycle choices | OK | Correct singleton/factory split |
| In-memory state locks | OK | Properly implemented for asyncio |
| EventBus sequential delivery | OK | No concurrent handler execution |
| MongoDB operation safety | OK | Driver handles pooling |
| Parallel backtest event isolation | LOW | Verify event scoping |
| Lock held during DB I/O | LOW | Performance concern, not correctness |

---

## Recommended Actions

### Must Fix (Before Review)
1. **Inject repositories into OrderManager** — add `order_repository: OrderRepository` to `__init__`, update container wiring
2. **Inject repositories into PositionTracker** — add `position_repository: PositionRepository` to `__init__`, update container wiring
3. **Inject repositories into BacktestRunner** — add `backtest_repository` + `ohlcv_repository` to `__init__`, update all callers

### Consider Later
4. **Backtest event isolation** — verify parallel backtests don't leak events across runs (or create per-run EventBus)
5. **Optimistic locking** — add `version` field to aggregates if concurrent updates become a real scenario
6. **Move DB writes outside locks** — for performance, decouple in-memory state mutation from persistence

---

## Unresolved Questions
- Are parallel backtests actually used in production, or only grid optimization? (affects priority of event isolation fix)
- Is there a plan to add multi-threaded workers? (would change concurrency model significantly)
