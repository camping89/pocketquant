# Code Review: Mediator Auto-Discovery Feature

**Reviewer:** code-reviewer | **Date:** 2026-02-14 | **Branch:** feat/strategy-init

## Scope

- **Core files:** `handler_registry.py` (NEW), `exceptions.py`, `mediator.py`, `__init__.py`
- **Feature registrations:** 4 `register.py` files (market_data, backtesting, strategy, trading)
- **Entry point:** `src/main.py` (simplified from 30+ handler imports to 4 register calls)
- **Tests:** `tests/unit/common/test_mediator.py` (4 new tests)
- **LOC changed (core):** ~120 new, ~80 removed from main.py
- **Focus:** Correctness, edge cases, pattern adherence

## Overall Assessment

**PASS -- Clean, well-structured implementation.** The auto-discovery pattern is correctly implemented, consistent with the existing `EventRegistry` pattern, and all 27 handlers are correctly wired. No critical or high-priority issues found.

## Verification Results

| Check | Result |
|-------|--------|
| Ruff (project rules) | 0 errors |
| Pyright (strict) | 0 errors, 0 warnings (all 6 new/changed files) |
| Unit tests | 8/8 passed (4 existing + 4 new) |
| Full test suite | 60/60 passed |
| Handler count | 27 @handles decorators = 27 handlers in register.py files |

### Handler Count Breakdown

| Feature | @handles | register.py | Match |
|---------|----------|-------------|-------|
| market_data | 13 | 13 | Yes |
| backtesting | 5 | 5 | Yes |
| strategy | 5 | 5 | Yes |
| trading | 4 | 4 | Yes |
| **Total** | **27** | **27** | **Yes** |

## Key Rules Verified

1. **One handler per command/query** -- `DuplicateHandlerError` thrown in `Mediator.register()` on duplicate. Tested.
2. **@handles only on Handler subclasses** -- TypeError raised for non-Handler classes and functions. Verified manually.
3. **HandlerRegistry.register_all() rejects undecorated** -- TypeError with "not decorated" message. Tested.
4. **All 27 handlers registered** -- Grep confirms 27 `@handles` decorators across feature handlers, matching exactly the 27 handlers instantiated in register.py files.
5. **No logic changes in handler files** -- Spot-checked 4 handlers (sync_one, load, list_orders, run backtest). Only additions: `@handles(RequestType)` decorator + `handles` import. No logic touched.

## Edge Cases Scouted

| Edge Case | Status |
|-----------|--------|
| @handles on non-Handler class | Correctly raises TypeError |
| @handles on function | Correctly raises TypeError (issubclass check fails on non-type) |
| Undecorated handler in register_all | Correctly raises TypeError |
| Duplicate handler registration | Correctly raises DuplicateHandlerError |
| get_request_type on undecorated handler | Returns None correctly |
| RiskCheckHandler not in mediator | Correct -- it's a domain service, not a CQRS Handler subclass |

## Pattern Consistency

### vs EventRegistry (`src/common/messaging/event_registry.py`)

| Aspect | EventRegistry | HandlerRegistry | Consistent? |
|--------|---------------|-----------------|-------------|
| Decorator | `@event_handler(EventType)` | `@handles(RequestType)` | Yes, same pattern |
| Registry class | `EventRegistry` | `HandlerRegistry` | Yes |
| Auto-register method | `register_instance()` | `register_all()` | Yes (adapted for CQRS) |
| Attribute storage | `method._event_types` | `cls._handles_request_type` | Same mechanism |
| Singleton | Global `_registry` singleton | No singleton (instantiated per call) | **Differs** (see note) |
| TYPE_CHECKING guard | `EventBus` import | `Mediator` import | Yes |

**Note on singleton:** HandlerRegistry not being a singleton is fine. It's stateless (no `_registered` list like EventRegistry). Each `register.py` creates its own instance, uses it once, discards it. No state leaks.

## Low Priority Issues

### 1. `register_handler()` method is dead code in production

`D:\w\_me\pocketquant\src\common\mediator\mediator.py` line 25-27:

```python
def register_handler(self, handler: Handler, request_type: type) -> None:
    """Register a handler for a request type (alternative signature)."""
    self.register(request_type, handler)
```

Only called in test (`test_mediator_register_alternative_signature`). Not used anywhere in production code. Consider removing if backward compatibility is not needed, or keep as a convenience method with a note.

### 2. Pytest collection warning for TestCommand

`tests/unit/common/test_mediator.py` line 15 -- `TestCommand` class name matches pytest's `Test*` collection pattern, but has an `__init__`, so pytest warns. Rename to `SampleCommand` or `FakeCommand` to avoid the warning.

### 3. `handles()` return type is `Any`

`D:\w\_me\pocketquant\src\common\mediator\handler_registry.py` line 19:

```python
def handles(request_type: type) -> Any:
```

The `Any` return type means pyright/mypy cannot verify that the decorated class retains its type. This is pragmatic (class decorators are hard to type in Python), but could be improved with `Callable[[type[T]], type[T]]` pattern if type precision becomes important.

### 4. No `__all__` in register.py files

The 4 `register.py` files export `register_handlers` function but have no `__all__`. Minor inconsistency with the codebase pattern where feature `__init__.py` files use `__all__`. Not a real issue since these files have exactly one public function.

## Positive Observations

1. **Clean separation of concerns** -- Decorator, registry, and mediator each have one job
2. **Defensive validation** -- @handles checks issubclass, register_all checks for decorator, mediator checks for duplicates -- three layers of safety
3. **main.py dramatically simplified** -- From ~30 handler/query imports to 4 clean `register_*()` calls
4. **Consistent with existing EventRegistry pattern** -- Same decorator + registry approach
5. **Good test coverage** -- All 4 key behaviors tested: dispatch, decorator storage, auto-register, rejection
6. **TYPE_CHECKING guard** for Mediator import in handler_registry.py prevents circular imports
7. **Feature register.py files** properly group handler construction with dependency injection

## Recommended Actions

1. (Optional) Rename `TestCommand` to `SampleCommand` in tests to eliminate pytest warning
2. (Optional) Remove `register_handler()` method if not needed for backward compat
3. No blocking issues -- safe to merge

## Metrics

- Type coverage: 100% (pyright strict, 0 errors)
- Test coverage: 8 mediator tests, all pass
- Linting: 0 issues (project-configured ruff rules)
- Full suite: 60/60 pass

## Unresolved Questions

None.
