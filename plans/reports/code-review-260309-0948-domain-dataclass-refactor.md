# Code Review: Domain Pydantic-to-Dataclass Refactor

**Date:** 2026-03-09
**Reviewer:** code-reviewer agent
**Branch:** feat/strategy-init
**Scope:** 22 domain classes across 17 files + persistence index naming + container async fixes

---

## Scope

- **Domain files reviewed:** 17 (all event, value object, aggregate files)
- **Persistence files reviewed:** 7 repositories + 2 schemas (order, position)
- **Other files reviewed:** container.py, main.py, main_extensions.py, 2 middleware, 1 route, 1 test
- **LOC changed:** ~450 (domain) + ~150 (infra/container)
- **Focus:** Correctness of Pydantic-to-dataclass conversion, edge cases, runtime safety

## Overall Assessment

**Solid refactor.** The conversion is mechanically correct and consistent. All 22 domain classes follow correct patterns. pyright 0 errors, ruff clean, 60 tests passing. Zero Pydantic references remain in domain layer. Persistence schemas correctly stay Pydantic. One medium-priority issue found (webhook serialization), plus good bonus improvements (index naming, container async, state machine ClassVar).

---

## Critical Issues

None.

---

## High Priority

### H1. WebhookDispatcher `asdict` + `json.dumps` will fail on Enum/UUID/datetime fields

**File:** `src/infrastructure/webhooks/dispatcher.py:72-79`

`_serialize_event()` calls `asdict(event)` then `_sign()` calls `json.dumps(payload, sort_keys=True)`. With dataclass events, `asdict` now succeeds (previously would have raised TypeError on Pydantic BaseModel), but produces:
- `UUID` objects (not JSON-serializable)
- `Enum` objects (e.g., `OrderSide.BUY` -- not JSON-serializable)
- `datetime` objects (not JSON-serializable)

**Note:** This is a pre-existing bug (dispatcher used `asdict` even when events were Pydantic), but the failure mode changed. Previously it crashed at `asdict()` call; now it crashes at `json.dumps()`.

**Fix:** Add a custom encoder or post-process the dict:
```python
def _serialize_event(self, event: DomainEvent) -> dict[str, Any]:
    data = asdict(event)
    data.pop("event_id", None)
    data.pop("occurred_at", None)
    return self._make_json_safe(data)

@staticmethod
def _make_json_safe(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: WebhookDispatcher._make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [WebhookDispatcher._make_json_safe(v) for v in obj]
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (UUID, datetime)):
        return str(obj)
    return obj
```

**Impact:** Any webhook dispatch involving events with Enum fields (OrderSubmittedEvent, PositionOpenedEvent, PositionClosedEvent) will raise TypeError at runtime.

---

## Medium Priority

### M1. Aggregates missing `eq=False` inconsistency

`OHLCVAggregate`, `QuoteAggregate`, `SymbolAggregate` use `@dataclass(eq=False)` and define custom `__eq__`/`__hash__`.

`OrderAggregate` and `PositionAggregate` use plain `@dataclass` (which generates `__eq__` comparing ALL fields) and do NOT define custom `__eq__`/`__hash__`. This means:
- Two orders with same ID but different `status` are considered NOT equal
- Cannot be used in sets/dicts (unhashable without `__hash__`)

This was the same behavior under Pydantic (BaseModel also compares all fields), so no regression. But now is a good time to make it consistent. Consider adding `eq=False` + custom identity-based equality to Order and Position aggregates for DDD correctness.

### M2. Bonus changes bundled into domain refactor PR

The diff includes several unrelated changes:
- Container async resolution (`resolve()` helper, `register_all_handlers` now async)
- Middleware cache access (`request.app.state.cache` instead of `container.cache()`)
- Repository index naming (adding `name=` params to all `create_index` calls)
- Strategy handler param rename (`strategy_engine` -> `engine`)
- `start_background_jobs` now awaited

These are individually fine but should ideally be separate commits for reviewability.

---

## Low Priority

### L1. `StrategyConfig`, `StopLossConfig`, `TakeProfitConfig`, `OrderConfig` -- no validation in `__post_init__`

These are `@dataclass` (not frozen) with no validation. `StrategyConfig.validate()` exists as an explicit method but is opt-in. This was likely the same under Pydantic if they had no validators, so no regression. The `from_dict` factory handles parsing but doesn't call `validate()` -- worth noting but not a blocker.

### L2. `SyncStatus` and `Bar` entities were already dataclasses

These were already converted in a prior refactor (entities.py). No changes needed, confirmed consistent.

---

## Edge Cases Found by Scout

1. **`SymbolInfo` inherits `Symbol.__post_init__`** -- Verified correct. Since `SymbolInfo` does not define its own `__post_init__`, Python automatically calls `Symbol.__post_init__` which validates `code` and `exchange`. If `SymbolInfo` ever adds its own `__post_init__`, it must call `super().__post_init__()` explicitly.

2. **`dataclasses.replace()` on frozen dataclass** -- Verified correct. `SymbolAggregate.deactivate()/activate()` use `replace(self.info, is_active=False)`. This correctly creates a new `SymbolInfo` and triggers `__post_init__` validation on the new instance.

3. **`asdict()` in webhook dispatcher** -- See H1 above. Functional change: previously crashed at `asdict()`, now crashes at `json.dumps()`.

4. **Persistence schema compatibility** -- Verified. `OrderDocument.to_aggregate()` and `PositionDocument.to_aggregate()` construct aggregates via keyword args. Dataclass constructors accept the same kwargs as Pydantic did. No issue.

5. **`ClassVar` on `OrderAggregate._VALID_TRANSITIONS`** -- Correct usage. `ClassVar` fields are excluded from dataclass `__init__`, `__repr__`, etc. The `frozenset` values are a nice improvement over per-call `set` allocation.

6. **Frozen events with `__post_init__`** -- Verified working. Python dataclasses allow `__post_init__` on frozen dataclasses for validation (reads only). The OHLCV, Quote, Risk value objects all validate correctly.

7. **`DomainEvent` frozen + mutable child events** -- Not an issue here. All child events are also `@dataclass(frozen=True, eq=False)`, matching the parent. No frozen/non-frozen inheritance mismatch.

---

## Positive Observations

1. **Consistent patterns** -- Events: `frozen=True, eq=False`. Value objects: `frozen=True`. Aggregates: mutable with `field(init=False, repr=False)` for `_events`.
2. **Clean validator migration** -- `field_validator`/`model_validator` -> `__post_init__` is straightforward and readable.
3. **`replace()` usage** -- Symbol activate/deactivate simplified from 7-line reconstruction to 1-line `replace()`.
4. **State machine ClassVar** -- Moving `_VALID_TRANSITIONS` to class-level `frozenset` avoids per-call dict+set allocation.
5. **Zero Pydantic in domain** -- `grep "pydantic" src/domain/` returns nothing. Clean separation.
6. **Index naming** -- All `ensure_indexes()` now use explicit `name=` params, preventing auto-generated name issues on schema changes.
7. **Container async safety** -- `resolve()` helper and `asyncio.gather` for handler registration properly handles async Resource providers.

---

## Metrics

| Metric | Value |
|--------|-------|
| pyright errors | 0 |
| ruff issues | 0 (domain) |
| Tests passing | 60/60 |
| Pydantic refs in domain | 0 |
| Domain files converted | 17 |
| Classes converted | 22 |

---

## Recommended Actions

1. **Fix webhook dispatcher serialization** (H1) -- Add JSON-safe conversion for UUID, Enum, datetime in `_serialize_event()`
2. **Consider `eq=False` for Order/Position aggregates** (M1) -- Add identity-based equality for DDD consistency
3. **Split unrelated changes** (M2) -- If possible, separate container/middleware/index changes into their own commits
4. **Add docstring to `SymbolInfo`** noting `__post_init__` inheritance caveat -- Future-proof against silent validation loss if child adds `__post_init__`

---

## Unresolved Questions

1. Is the webhook dispatcher actively used in production, or is it scaffolding? If scaffolding, H1 is lower priority.
2. Should `StrategyConfig.from_dict()` call `validate()` automatically, or is opt-in validation intentional?
