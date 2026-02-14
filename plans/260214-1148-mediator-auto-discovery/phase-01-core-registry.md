# Phase 1: Core Registry — Decorator, Registry, Exception

**Priority:** Critical | **Status:** Pending

## Overview

Build the `@handles` decorator, `HandlerRegistry`, and `DuplicateHandlerError`. These are the foundation for auto-discovery.

## Key Insights

- Mirror `@event_handler` + `EventRegistry` pattern already in codebase
- `@handles` is a **class decorator** (not method decorator like `@event_handler`)
- Registry is a singleton, same as `EventRegistry`
- Duplicate detection happens at **registration time** (fail-fast)

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `src/common/mediator/exceptions.py` | Add `DuplicateHandlerError` |
| Create | `src/common/mediator/handler_registry.py` | `@handles` decorator + `HandlerRegistry` |
| Modify | `src/common/mediator/mediator.py` | Add duplicate check in `register()` |
| Modify | `src/common/mediator/__init__.py` | Export new symbols |

## Implementation Steps

### 1. Add `DuplicateHandlerError` to exceptions.py

```python
class DuplicateHandlerError(Exception):
    """Raised when two handlers register for the same command/query."""
    def __init__(self, request_type: type, existing_handler: type, new_handler: type):
        self.request_type = request_type
        super().__init__(
            f"Duplicate handler for {request_type.__name__}: "
            f"{existing_handler.__name__} already registered, "
            f"cannot register {new_handler.__name__}"
        )
```

### 2. Create `handler_registry.py`

```python
@handles(RequestType)  # class decorator
class MyHandler(Handler[RequestType, ResponseType]):
    ...
```

The decorator stores `_handles_request_type` on the class.

`HandlerRegistry`:
- `discover_handlers(module_path: str) -> list[type[Handler]]` — scan modules for decorated classes
- `validate_no_duplicates(handlers)` — throw if two handlers claim same request type
- `get_request_type(handler_cls) -> type` — read `_handles_request_type` from decorator

### 3. Add duplicate check in `Mediator.register()`

```python
def register(self, request_type: type, handler: Handler) -> None:
    if request_type in self._handlers:
        raise DuplicateHandlerError(
            request_type,
            type(self._handlers[request_type]),
            type(handler),
        )
    self._handlers[request_type] = handler
```

### 4. Update `__init__.py` exports

Add `DuplicateHandlerError`, `handles`, `HandlerRegistry` to `__all__`.

## Success Criteria

- [x] `@handles(CommandType)` decorator works on Handler subclasses
- [x] `HandlerRegistry` can scan a module and find all decorated handlers
- [x] `DuplicateHandlerError` thrown when registering duplicate
- [x] `Mediator.register()` enforces one-handler-per-request-type rule
- [x] Existing tests still pass (backward compatible)
