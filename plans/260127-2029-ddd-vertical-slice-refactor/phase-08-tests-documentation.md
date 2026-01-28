# Phase 8: Tests + Documentation

## Context Links
- Parent: [plan.md](plan.md)
- Blocked by: [Phase 6](phase-06-cross-cutting-middleware.md), [Phase 7](phase-07-integration-infrastructure.md)
- Research: N/A

## Overview

| Field | Value |
|-------|-------|
| Date | 2026-01-27 |
| Priority | P1 |
| Status | completed |
| Effort | 1h |

Update test suite for new architecture. Update documentation to reflect changes.

## Key Insights

Test updates needed:
- Mock mediator instead of services
- Test handlers in isolation
- Test middleware independently
- Verify domain purity

Documentation updates:
- Architecture diagrams
- Layer responsibilities
- API unchanged (verify)

## Requirements

### Functional
- All existing tests pass
- New tests for mediator/handlers
- Domain purity verification test

### Non-Functional
- 80%+ code coverage maintained
- Fast test execution
- CI-friendly

## Architecture

```
tests/
├── unit/
│   ├── common/
│   │   ├── test_mediator.py
│   │   ├── test_event_bus.py
│   │   └── test_middleware.py
│   ├── domain/
│   │   ├── test_value_objects.py
│   │   ├── test_aggregates.py
│   │   └── test_domain_purity.py
│   └── features/
│       └── market_data/
│           ├── test_sync_handler.py
│           ├── test_ohlcv_handler.py
│           └── test_quote_handler.py
├── integration/
│   └── test_routes.py
└── conftest.py
```

## Related Code Files

### Create
- `tests/unit/common/test_mediator.py`
- `tests/unit/common/test_event_bus.py`
- `tests/unit/common/test_middleware.py`
- `tests/unit/domain/test_value_objects.py`
- `tests/unit/domain/test_aggregates.py`
- `tests/unit/domain/test_domain_purity.py`

### Modify
- `tests/conftest.py` - Add mediator fixtures
- `docs/codebase-summary.md` - Update architecture
- `docs/system-architecture.md` - Update diagrams
- `README.md` - Update structure section

## Implementation Steps

1. **Create Mediator tests**
   ```python
   # tests/unit/common/test_mediator.py
   import pytest
   from src.common.mediator import Mediator, Handler, HandlerNotFoundError
   from dataclasses import dataclass

   @dataclass
   class TestCommand:
       value: str

   class TestHandler(Handler[TestCommand, str]):
       async def handle(self, cmd: TestCommand) -> str:
           return f"handled: {cmd.value}"

   @pytest.mark.asyncio
   async def test_mediator_dispatches_to_handler():
       mediator = Mediator()
       mediator.register(TestCommand, TestHandler())

       result = await mediator.send(TestCommand("test"))
       assert result == "handled: test"

   @pytest.mark.asyncio
   async def test_mediator_raises_for_unknown():
       mediator = Mediator()

       with pytest.raises(HandlerNotFoundError):
           await mediator.send(TestCommand("test"))
   ```

2. **Create Event Bus tests**
   ```python
   # tests/unit/common/test_event_bus.py
   import pytest
   from src.common.messaging import EventBus
   from src.domain.shared.events import DomainEvent
   from dataclasses import dataclass
   from datetime import datetime
   from uuid import uuid4

   @dataclass(frozen=True)
   class TestEvent(DomainEvent):
       data: str = ""

   @pytest.mark.asyncio
   async def test_event_bus_delivers_to_subscribers():
       bus = EventBus()
       received = []

       async def handler(event):
           received.append(event)

       bus.subscribe(TestEvent, handler)

       event = TestEvent(aggregate_id=uuid4(), occurred_at=datetime.utcnow(), data="test")
       await bus.publish(event)

       assert len(received) == 1
       assert received[0].data == "test"

   def test_event_bus_limits_history():
       bus = EventBus(max_history=5)

       # History bounded by deque, tested implicitly
       assert bus._history.maxlen == 5
   ```

3. **Create domain purity test**
   ```python
   # tests/unit/domain/test_domain_purity.py
   import ast
   import os

   FORBIDDEN_IMPORTS = [
       "pymongo", "motor", "redis", "aiohttp",
       "src.infrastructure", "src.common.database", "src.common.cache"
   ]

   def test_domain_has_no_io_imports():
       domain_path = "src/domain"
       violations = []

       for root, dirs, files in os.walk(domain_path):
           for file in files:
               if not file.endswith(".py"):
                   continue

               filepath = os.path.join(root, file)
               with open(filepath) as f:
                   try:
                       tree = ast.parse(f.read())
                   except SyntaxError:
                       continue

               for node in ast.walk(tree):
                   if isinstance(node, ast.Import):
                       for alias in node.names:
                           if any(f in alias.name for f in FORBIDDEN_IMPORTS):
                               violations.append(f"{filepath}: import {alias.name}")
                   elif isinstance(node, ast.ImportFrom):
                       if node.module and any(f in node.module for f in FORBIDDEN_IMPORTS):
                           violations.append(f"{filepath}: from {node.module}")

       assert not violations, f"Domain layer has I/O imports: {violations}"
   ```

4. **Create handler tests**
   ```python
   # tests/unit/features/market_data/test_sync_handler.py
   import pytest
   from unittest.mock import AsyncMock, MagicMock
   from src.features.market_data.sync.command import SyncSymbolCommand
   from src.features.market_data.sync.handler import SyncSymbolHandler

   @pytest.mark.asyncio
   async def test_sync_handler_fetches_and_saves():
       provider = AsyncMock()
       provider.fetch_ohlcv.return_value = [MagicMock() for _ in range(100)]

       event_bus = AsyncMock()

       handler = SyncSymbolHandler(provider, event_bus)

       cmd = SyncSymbolCommand(symbol="AAPL", exchange="NASDAQ", n_bars=100)
       result = await handler.handle(cmd)

       assert result["bars_synced"] == 100
       provider.fetch_ohlcv.assert_called_once()
       event_bus.publish_all.assert_called_once()
   ```

5. **Update conftest.py**
   ```python
   # tests/conftest.py
   import pytest
   from src.common.mediator import Mediator
   from src.common.messaging import EventBus

   @pytest.fixture
   def mediator():
       return Mediator()

   @pytest.fixture
   def event_bus():
       return EventBus()
   ```

6. **Update codebase-summary.md**
   - Update architecture diagram with new structure
   - Document layer responsibilities
   - Add middleware documentation
   - Update dependency flow

7. **Update README.md**
   - Update project structure section
   - Add new directories explanation
   - Keep API documentation unchanged

8. **Verify all tests pass**
   ```bash
   pytest -v --cov=src --cov-report=term-missing
   ```

## Todo List

- [ ] Create `test_mediator.py`
- [ ] Create `test_event_bus.py`
- [ ] Create `test_middleware.py`
- [ ] Create `test_value_objects.py`
- [ ] Create `test_aggregates.py`
- [ ] Create `test_domain_purity.py`
- [ ] Create handler tests
- [ ] Update `conftest.py` with fixtures
- [ ] Update `codebase-summary.md`
- [ ] Update `system-architecture.md`
- [ ] Update `README.md`
- [ ] Run full test suite
- [ ] Verify coverage >= 80%

## Success Criteria

- [ ] All tests pass
- [ ] Domain purity test enforced
- [ ] Coverage >= 80%
- [ ] Documentation reflects new architecture
- [ ] No API breaking changes verified

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Test gaps | Medium | Medium | Review coverage report |
| Stale docs | Low | Low | Update during each phase |
| Missing fixture | Low | Low | Import errors caught in CI |

## Security Considerations

- Test data should not contain real credentials
- Mocks for external services
- No sensitive data in test output

## Next Steps

After completion:
- Refactor complete
- Create PR for review
- Document lessons learned
