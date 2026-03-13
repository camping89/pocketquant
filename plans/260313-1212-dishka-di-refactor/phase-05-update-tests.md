# Phase 5: Update Tests

## Context Links
- [Phase 4: Delete Dead Code](./phase-04-delete-dead-code.md) — must be complete first
- [Current test files](../../tests/) — 7 test files + conftest

## Overview
- **Priority**: P2
- **Status**: pending
- **Description**: Update existing tests to work with dishka. Add container validation test.

## Current Test Inventory

```
tests/
    conftest.py                  — fixtures: Settings, Mediator, EventBus
    unit/
        common/
            test_mediator.py     — Mediator dispatch tests (self-contained)
            test_event_bus.py    — EventBus tests (self-contained)
        domain/
            test_domain_purity.py — AST check, no DI deps
            test_value_objects.py — pure domain tests
        infrastructure/
            tradingview/
                test_websocket.py — WebSocket tests
    integration/
        tradingview/
            test_websocket_integration.py
```

## Key Insights

1. **Most tests are unaffected**: Unit tests for Mediator, EventBus, domain, and infrastructure don't use `Services`, `dependencies.py`, or `handler_registration.py`
2. **conftest.py**: Creates `Mediator()` and `EventBus()` directly — no changes needed since these are plain constructors
3. **No API/route tests exist**: No test currently imports from `src.dependencies` or uses FastAPI `TestClient`
4. **New test**: Add container creation validation test to catch missing factories early

## Files to Modify

| File | Change |
|------|--------|
| `tests/conftest.py` | No change needed (fixtures create instances directly) |

## Files to Create

| File | Purpose |
|------|---------|
| `tests/unit/test_container.py` | Validates dishka container graph is complete |

## Implementation Steps

### 1. Verify existing tests still pass

```bash
pytest tests/ -v --tb=short
```

All existing tests should pass unchanged since they don't depend on the deleted files.

### 2. Search for any test imports of deleted modules

```bash
rg "from src.services import" tests/
rg "from src.dependencies import" tests/
rg "from src.handler_registration import" tests/
```

Expected: zero matches.

### 3. Create container validation test

```python
"""Test that dishka container graph is valid and all deps resolve."""

import pytest

from src.container import create_container


def test_container_creation_succeeds():
    """Container creation validates the dependency graph.

    Dishka checks for missing factories, circular deps, and scope violations
    at container creation time. If this passes, the graph is valid.
    """
    container = create_container()
    assert container is not None


@pytest.mark.asyncio
async def test_container_resolves_mediator():
    """Verify Mediator can be resolved from the container."""
    from src.common.mediator.mediator import Mediator

    container = create_container()
    async with container:
        mediator = await container.get(Mediator)
        assert mediator is not None
        assert isinstance(mediator, Mediator)
```

**NOTE**: Full resolution test (resolving Database, Cache etc.) requires running MongoDB/Redis. Keep it as integration test or skip in CI without infra:

```python
@pytest.mark.asyncio
@pytest.mark.integration
async def test_container_resolves_all_app_deps():
    """Full resolution test — requires MongoDB + Redis running."""
    container = create_container()
    async with container:
        from src.persistence.mongodb import Database
        from src.persistence.redis import Cache

        db = await container.get(Database)
        cache = await container.get(Cache)
        assert db is not None
        assert cache is not None
```

### 4. Run full test suite

```bash
pytest tests/ -v --tb=short
```

## Todo List

- [ ] Verify no tests import deleted modules
- [ ] Run existing tests — all pass
- [ ] Create `tests/unit/test_container.py`
- [ ] Run `test_container_creation_succeeds` — passes
- [ ] Run full test suite — all pass
- [ ] Run `pyright tests/` — zero errors

## Success Criteria

- All existing tests pass unchanged
- Container validation test passes
- No test imports from deleted modules
- `pyright` and `ruff` pass on test files

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Container creation test fails due to import side effects | Test fails in CI | Isolate with careful imports; mock env vars if needed |
| Settings fixture in conftest needs `.env` | Tests fail without .env | Already handled — current fixture creates Settings with explicit values |
| Future API tests need dishka TestClient setup | Tests harder to write | Document pattern: `dishka.integrations.fastapi.TestClient` or override container in tests |
