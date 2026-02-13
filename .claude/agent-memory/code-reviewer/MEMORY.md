# Code Reviewer Agent Memory

## Project: PocketQuant

### Architecture Pattern (confirmed 2026-02-13)
- **Vertical Slice Architecture**: Each feature uses operation folders at root (e.g., `get_all/`, `list_orders/`), shared infra in `base/`, router aggregation via `router.py`
- **CQRS**: Operations split into `command.py` + `handler.py` + `route.py` (commands) or `query.py` + `handler.py` + `route.py` (queries)
- **Each operation folder**: `__init__.py` (re-exports), `handler.py`, `query.py`/`command.py`, `route.py`
- **Feature `__init__.py`**: Facade re-exports for public API surface with `__all__`
- **Cross-feature imports**: Use `TYPE_CHECKING` guards to prevent circular deps

### Feature Structure
```
src/features/{feature}/
  __init__.py          # Facade re-exports
  router.py            # Aggregates operation routes
  base/                # Shared: models, managers, repositories, engine
  {operation}/         # get_all/, list_orders/, run/, optimize/, etc.
```

### Key Files
- `src/main.py` - App lifespan, mediator registration, router inclusion
- `src/common/mediator/` - CQRS mediator pattern (register command/query -> handler)
- `src/common/messaging/` - EventBus for domain events

### Known Minor Issues (as of 2026-02-13)
- `market_data/__init__.py` is thin (just docstring), no facade re-exports
- `list_symbols/__init__.py` missing `ListSymbolsHandler` re-export
- `main.py` has some direct `base/` imports bypassing feature facades
- `backtesting/router.py` uses module attribute access; others use direct import

### Tech Stack
- Python, FastAPI, Pydantic, structlog, MongoDB (pymongo native async), Redis, APScheduler
- Domain: src/domain/ (aggregates, value objects, events) - pure, no framework deps
- Infrastructure: src/infrastructure/ (brokers, persistence, tradingview, webhooks)
