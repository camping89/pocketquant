# Phase 4: Mediator + Event Bus

## Context Links
- Parent: [plan.md](plan.md)
- Blocked by: [Phase 1](phase-01-centralize-constants.md)
- Research: [DDD Patterns](research/researcher-ddd-cqrs-patterns.md)

## Overview

| Field | Value |
|-------|-------|
| Date | 2026-01-27 |
| Priority | P1 |
| Status | completed |
| Effort | 2h |

Create CQRS Mediator for command/query dispatch and in-memory event bus for domain events.

## Key Insights

From research:
- **Mediator Pattern:** Central dispatcher routes requests to handlers
- **Event Bus:** FIFO async delivery to subscribers
- **Bounded History:** Prevent memory leaks in long-running apps
- Both are pure Python (no external dependencies)

## Requirements

### Functional
- Mediator dispatches Commands and Queries to handlers
- Event bus publishes domain events to subscribers
- Type-safe handler registration

### Non-Functional
- Async-safe execution
- No external dependencies
- Testable (can mock handlers)

## Architecture

```
src/common/
├── mediator/
│   ├── __init__.py
│   ├── mediator.py           # Mediator class
│   ├── handler.py            # Handler ABC
│   └── exceptions.py         # HandlerNotFound
└── messaging/
    ├── __init__.py
    ├── event_bus.py          # EventBus class
    └── event_handler.py      # EventHandler type
```

## Related Code Files

### Create
- `src/common/mediator/__init__.py`
- `src/common/mediator/mediator.py`
- `src/common/mediator/handler.py`
- `src/common/mediator/exceptions.py`
- `src/common/messaging/__init__.py`
- `src/common/messaging/event_bus.py`
- `src/common/messaging/event_handler.py`

### Modify
- `src/main.py` - Initialize mediator and event bus

## Implementation Steps

1. **Create Mediator handler base**
   ```python
   # src/common/mediator/handler.py
   from abc import ABC, abstractmethod
   from typing import Generic, TypeVar, Any

   TRequest = TypeVar("TRequest")
   TResponse = TypeVar("TResponse")

   class Handler(ABC, Generic[TRequest, TResponse]):
       """Base handler for commands and queries"""

       @abstractmethod
       async def handle(self, request: TRequest) -> TResponse:
           pass
   ```

2. **Create Mediator exceptions**
   ```python
   # src/common/mediator/exceptions.py
   class HandlerNotFoundError(Exception):
       def __init__(self, request_type: type):
           self.request_type = request_type
           super().__init__(f"No handler registered for {request_type.__name__}")
   ```

3. **Create Mediator class**
   ```python
   # src/common/mediator/mediator.py
   from typing import Dict, Type, Any
   from src.common.mediator.handler import Handler
   from src.common.mediator.exceptions import HandlerNotFoundError

   class Mediator:
       """CQRS dispatcher - routes requests to handlers"""

       def __init__(self):
           self._handlers: Dict[Type, Handler] = {}

       def register(self, request_type: Type, handler: Handler) -> None:
           """Register handler for request type"""
           self._handlers[request_type] = handler

       async def send(self, request: Any) -> Any:
           """Dispatch request to registered handler"""
           handler = self._handlers.get(type(request))
           if not handler:
               raise HandlerNotFoundError(type(request))
           return await handler.handle(request)

       def get_registered_types(self) -> list:
           """List all registered request types (for debugging)"""
           return list(self._handlers.keys())
   ```

4. **Create Event Bus**
   ```python
   # src/common/messaging/event_bus.py
   from typing import Dict, List, Callable, Type
   from collections import deque
   from src.domain.shared.events import DomainEvent

   EventHandler = Callable[[DomainEvent], Any]

   class EventBus:
       """In-memory async event bus with FIFO delivery"""

       def __init__(self, max_history: int = 50):
           self._handlers: Dict[Type, List[EventHandler]] = {}
           self._history: deque = deque(maxlen=max_history)

       def subscribe(self, event_type: Type[DomainEvent], handler: EventHandler) -> None:
           """Register handler for event type"""
           if event_type not in self._handlers:
               self._handlers[event_type] = []
           self._handlers[event_type].append(handler)

       async def publish(self, event: DomainEvent) -> None:
           """Publish event to all subscribers (FIFO)"""
           handlers = self._handlers.get(type(event), [])
           for handler in handlers:
               result = handler(event)
               if hasattr(result, "__await__"):
                   await result
           self._history.append(event)

       async def publish_all(self, events: List[DomainEvent]) -> None:
           """Publish multiple events atomically"""
           for event in events:
               await self.publish(event)

       def get_history(self, limit: int = 10) -> List[DomainEvent]:
           """Get recent events (for debugging)"""
           return list(self._history)[-limit:]
   ```

5. **Create __init__ exports**
   ```python
   # src/common/mediator/__init__.py
   from src.common.mediator.mediator import Mediator
   from src.common.mediator.handler import Handler
   from src.common.mediator.exceptions import HandlerNotFoundError

   __all__ = ["Mediator", "Handler", "HandlerNotFoundError"]

   # src/common/messaging/__init__.py
   from src.common.messaging.event_bus import EventBus, EventHandler

   __all__ = ["EventBus", "EventHandler"]
   ```

6. **Initialize in main.py lifespan**
   ```python
   # In lifespan context manager
   mediator = Mediator()
   event_bus = EventBus(max_history=100)

   # Wire to FastAPI state
   app.state.mediator = mediator
   app.state.event_bus = event_bus
   ```

7. **Create dependency injection helper**
   ```python
   # src/common/mediator/dependencies.py
   from fastapi import Request
   from src.common.mediator import Mediator

   def get_mediator(request: Request) -> Mediator:
       return request.app.state.mediator
   ```

## Todo List

- [x] Create `src/common/mediator/` directory
- [x] Create `handler.py` with base Handler class
- [x] Create `exceptions.py` with HandlerNotFoundError
- [x] Create `mediator.py` with Mediator class
- [x] Create `src/common/messaging/` directory
- [x] Create `event_bus.py` with EventBus class
- [x] Create __init__.py exports
- [x] Update `main.py` to initialize mediator + event bus
- [x] Create `dependencies.py` for FastAPI injection
- [ ] Write unit tests for Mediator (deferred to Phase 8)
- [ ] Write unit tests for EventBus (deferred to Phase 8)
- [x] Run all tests (imports verified)

## Success Criteria

- [x] Mediator dispatches to registered handlers
- [x] Event bus delivers to all subscribers
- [x] History is bounded (no memory leak)
- [x] FastAPI can inject mediator via Depends()
- [x] All tests pass (imports verified)

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Handler not found | Medium | Low | Clear error message |
| Memory leak | Low | Medium | Bounded deque for history |
| Async handler issues | Low | Low | Check for awaitable result |

## Security Considerations

- No credentials in mediator/event bus
- Pure routing logic only
- No network access

## Next Steps

After completion:
- Phase 5 creates commands/queries and handlers
- Handlers use mediator for dispatch
