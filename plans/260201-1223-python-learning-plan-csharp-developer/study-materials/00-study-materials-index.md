# Python Learning Study Materials Index

> Supplementary materials for C# developers learning Python through PocketQuant

## Quick Start

1. Start with **Cheatsheet** for syntax reference
2. Read **AsyncIO Mental Model** before touching async code
3. Reference **CQRS Pattern** and **Domain Events** when reading handlers
4. Keep **Common Gotchas** open as you code

## Materials

| # | Document | Purpose |
|---|----------|---------|
| 01 | [C# to Python Cheatsheet](./01-csharp-to-python-cheatsheet.md) | Syntax mapping, common patterns |
| 02 | [AsyncIO Mental Model](./02-asyncio-mental-model.md) | Single-threaded concurrency, locks |
| 03 | [CQRS Pattern Diagram](./03-cqrs-pattern-diagram.md) | Request flow, mediator pattern |
| 04 | [Domain Events & EventBus](./04-domain-events-and-eventbus-pattern.md) | Event-driven architecture |
| 05 | [Singleton & Lifecycle](./05-singleton-pattern-and-lifecycle-management.md) | Database connections, context managers |
| 06 | [Structured Logging](./06-structured-logging-with-structlog.md) | Structlog configuration, patterns |
| 07 | [Type Hints Guide](./07-python-typing-for-csharp-developers.md) | Generics, protocols, pyright |
| 08 | [Pytest Testing Guide](./08-pytest-testing-guide-for-csharp-developers.md) | Fixtures, mocking, async tests |
| 09 | [Common Gotchas](./09-common-gotchas-and-pitfalls-for-csharp-developers.md) | Mutable defaults, scope issues |

---

## Learning Flow: Step-by-Step

### Phase 1: Read & Understand (Week 1, ~4h)

| Step | Read First | Then Do Exercise | Reference |
|------|-----------|------------------|-----------|
| 1.1 | [01-cheatsheet](./01-csharp-to-python-cheatsheet.md) | Exercise 1.1: Trace CQRS flow | [03-cqrs](./03-cqrs-pattern-diagram.md) |
| 1.2 | [05-singleton](./05-singleton-pattern-and-lifecycle-management.md) | Exercise 1.2: Singleton lifecycle | - |
| 1.3 | [04-events](./04-domain-events-and-eventbus-pattern.md) | Exercise 1.3: Map domain events | - |
| 1.4 | [02-asyncio](./02-asyncio-mental-model.md) | Exercise 1.4: Compare async models | - |

**Workflow:**
```
1. Open study material → Read diagrams & explanations
2. Open phase-01 → Follow exercise instructions
3. Open referenced source files in VS Code
4. Trace code, draw diagrams, check success criteria
```

### Phase 2: Small Modifications (Week 2, ~5h)

| Step | Pre-read | Exercise | Keep Open |
|------|----------|----------|-----------|
| 2.1 | [06-logging](./06-structured-logging-with-structlog.md) | Add logging to handler | [09-gotchas](./09-common-gotchas-and-pitfalls-for-csharp-developers.md) |
| 2.2 | [07-typing](./07-python-typing-for-csharp-developers.md) | Add DTO field | [01-cheatsheet](./01-csharp-to-python-cheatsheet.md) |
| 2.3 | [04-events](./04-domain-events-and-eventbus-pattern.md) | Create subscriber | - |
| 2.4 | [07-typing](./07-python-typing-for-csharp-developers.md) | Add command validation | - |

**Workflow:**
```
1. Read study material for context
2. Open phase-02 exercise
3. Make code changes in VS Code
4. Run: pyright src/features/... && ruff check src/features/...
5. Verify success criteria
```

### Phase 3: Create New Features (Week 3, ~6h)

| Step | Reference | Exercise |
|------|-----------|----------|
| 3.1 | [03-cqrs](./03-cqrs-pattern-diagram.md) + [07-typing](./07-python-typing-for-csharp-developers.md) | Create new handler from scratch |
| 3.2 | [04-events](./04-domain-events-and-eventbus-pattern.md) | Create new domain event |
| 3.3 | All materials | Build complete vertical slice |

### Phase 4: Testing Mastery (Week 4, ~5h)

| Step | Must Read | Exercise |
|------|-----------|----------|
| 4.1 | [08-pytest](./08-pytest-testing-guide-for-csharp-developers.md) | Write unit tests |
| 4.2 | [08-pytest](./08-pytest-testing-guide-for-csharp-developers.md) (mocking) | Mock singletons |
| 4.3 | [08-pytest](./08-pytest-testing-guide-for-csharp-developers.md) (async) | Async handler tests |

---

## 10-Day Schedule

```
DAY 1 (1.5h)
├── 01-cheatsheet.md (skim, bookmark)
├── 02-asyncio-mental-model.md (study carefully)
└── phase-01 exercises 1.1, 1.4

DAY 2 (1.5h)
├── 03-cqrs-pattern-diagram.md
├── 04-domain-events.md
└── phase-01 exercises 1.1, 1.3

DAY 3 (1h)
├── 05-singleton-pattern.md
└── phase-01 exercise 1.2

DAY 4-5 (2.5h)
├── 06-structured-logging.md
├── 07-python-typing.md
├── 09-common-gotchas.md (keep open!)
└── phase-02 all exercises

DAY 6-8 (6h)
├── Review all materials as needed
└── phase-03 all exercises

DAY 9-10 (5h)
├── 08-pytest-testing-guide.md (deep read)
└── phase-04 all exercises
```

---

## VS Code Layout

Open in split view while working:

```
┌─────────────────────┬─────────────────────┐
│ Study Material      │ Phase Exercise      │
│ (left pane)         │ (right pane)        │
├─────────────────────┼─────────────────────┤
│ Source Code         │ Terminal            │
│ (bottom left)       │ pyright/ruff/pytest │
└─────────────────────┴─────────────────────┘
```

## Key Files in Codebase

| Pattern | File | Lines |
|---------|------|-------|
| Mediator | `src/common/mediator/mediator.py` | 37 |
| Handler Base | `src/common/mediator/handler.py` | 17 |
| Domain Event | `src/domain/shared/domain_event.py` | 22 |
| EventBus | `src/common/messaging/event_bus.py` | 67 |
| Database Singleton | `src/infrastructure/persistence/mongodb.py` | 64 |
| Logging Setup | `src/common/logging/setup.py` | 78 |
| Async Lock Usage | `src/features/market_data/managers/bar_manager.py` | 289 |

## Verification Commands

```bash
# Activate virtual environment
.venv\Scripts\activate

# Type check
pyright src/

# Lint
ruff check src/

# Run tests
pytest

# Run specific test file
pytest tests/unit/test_order.py -v

# Run with coverage
pytest --cov=src --cov-report=html
```
