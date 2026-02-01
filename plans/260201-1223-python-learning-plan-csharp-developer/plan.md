---
title: "Python Mastery for C# Developers"
description: "4-week hands-on learning plan using PocketQuant codebase"
status: pending
priority: P2
effort: 20h
branch: feat/strategy-init
tags: [learning, python, csharp, onboarding]
created: 2026-02-01
---

# Python Mastery Learning Plan for C# Developers

## Overview

4-week structured learning plan for senior C# developers (10+ years) to master Python through hands-on exercises using the PocketQuant production codebase.

**Reference:** [Brainstorm Guide](../reports/brainstorm-260201-1223-python-learning-guide.md)

## Learner Profile

- 10+ years C# experience (async/await, DI, CQRS)
- New to Python syntax, asyncio, pytest
- Using VS Code + Pylance + Ruff
- Goal: Production-ready Python skills

## Learning Phases

| Phase | Week | Focus | Status | Effort |
|-------|------|-------|--------|--------|
| 1 | Week 1 | [Read & Understand Patterns](./phase-01-week1-read-understand-patterns.md) | pending | 4h |
| 2 | Week 2 | [Small Modifications](./phase-02-week2-small-modifications.md) | pending | 5h |
| 3 | Week 3 | [Create New Features](./phase-03-week3-create-new-features.md) | pending | 6h |
| 4 | Week 4 | [Testing Mastery](./phase-04-week4-testing-mastery.md) | pending | 5h |

## Key Concepts Mapped

| C# Concept | Python Equivalent | Example File |
|------------|------------------|--------------|
| MediatR | Custom Mediator | `src/common/mediator/mediator.py` |
| INotification | DomainEvent | `src/domain/shared/domain_event.py` |
| async/await | asyncio | `src/features/market_data/managers/bar_manager.py` |
| Record | @dataclass(frozen=True) | `src/domain/shared/value_objects.py` |
| DI Container | Singleton classes | `src/infrastructure/persistence/mongodb.py` |

## Success Criteria

- [ ] Can trace request flow through CQRS pipeline
- [ ] Understands asyncio vs C# ThreadPool difference
- [ ] Can write handler following project patterns
- [ ] Can write tests with mocked singletons
- [ ] Passes pyright type checking on new code

## Study Materials

Supplementary reference materials for each phase:

| Material | Topics |
|----------|--------|
| [Study Materials Index](./study-materials/00-study-materials-index.md) | Quick start guide |
| [C# to Python Cheatsheet](./study-materials/01-csharp-to-python-cheatsheet.md) | Syntax mapping |
| [AsyncIO Mental Model](./study-materials/02-asyncio-mental-model.md) | Concurrency, locks |
| [CQRS Pattern Diagram](./study-materials/03-cqrs-pattern-diagram.md) | Request flow |
| [Domain Events](./study-materials/04-domain-events-and-eventbus-pattern.md) | Event-driven patterns |
| [Singleton & Lifecycle](./study-materials/05-singleton-pattern-and-lifecycle-management.md) | DB connections |
| [Structured Logging](./study-materials/06-structured-logging-with-structlog.md) | Structlog usage |
| [Type Hints Guide](./study-materials/07-python-typing-for-csharp-developers.md) | Generics, pyright |
| [Pytest Testing](./study-materials/08-pytest-testing-guide-for-csharp-developers.md) | Fixtures, mocking |
| [Common Gotchas](./study-materials/09-common-gotchas-and-pitfalls-for-csharp-developers.md) | Pitfalls to avoid |

## Prerequisites

```bash
# Activate virtual environment
.venv\Scripts\activate

# Verify tools
pyright --version
ruff --version
pytest --version
```
