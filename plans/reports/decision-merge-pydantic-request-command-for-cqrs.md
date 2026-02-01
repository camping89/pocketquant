# Brainstorm: Unified Request/Command Pattern

**Date:** 2026-02-01
**Decision:** Option A - Merge Request + Command (Pragmatic)

## Problem Statement

Current CQRS implementation has duplication:
- `SyncRequest` (Pydantic) for API validation
- `SyncSymbolCommand` (dataclass) for domain
- Manual mapping in every route handler

## Evaluated Approaches

### Option A: Merge Request + Command ✅ SELECTED
Commands become Pydantic models, used directly as API requests.

| Pros | Cons |
|------|------|
| Zero duplication | API = domain (tight coupling) |
| Fastest development | Harder to version API later |
| Fewer files to maintain | Violates Clean Architecture DIP |

### Option B: Keep Separation + Factory
Add `.to_command()` method to requests.

| Pros | Cons |
|------|------|
| Clean architecture compliant | Still 2 classes per operation |
| Easy to version later | Extra boilerplate |

### Option C: Shared Schema + Inheritance
Base class with shared fields, inherited by Request/Command.

| Pros | Cons |
|------|------|
| DRY field definitions | Complex inheritance |
| Can diverge when needed | Cognitive overhead |

## Research Findings

Industry best practices recommend separation ([Baeldung](https://www.baeldung.com/java-dto-pattern), [python-cqrs](https://pypi.org/project/python-cqrs/), [Clean Architecture examples](https://github.com/ivan-borovets/fastapi-clean-example)), but:
- Pydantic is near-ubiquitous in Python ecosystem
- YAGNI applies if no CLI/Celery/gRPC planned
- Pragmatic projects successfully use merged approach

## Final Decision

**Option A selected** - Accept framework coupling for velocity. Refactor later if versioning or multi-interface needs emerge.

## Implementation Strategy

### 1. Convert Commands to Pydantic
```python
# Before (dataclass)
@dataclass
class SyncSymbolCommand:
    symbol: str
    exchange: str

# After (Pydantic)
class SyncSymbolCommand(BaseModel):
    symbol: str = Field(..., description="Trading symbol")
    exchange: str = Field(..., description="Exchange name")
```

### 2. Handlers Return Response Models Directly
```python
async def handle(self, cmd: SyncSymbolCommand) -> SyncResponse:
    # ... business logic
    return SyncResponse(symbol=cmd.symbol, ...)
```

### 3. Routes Become Minimal
```python
@router.post("/sync", response_model=SyncResponse)
async def sync(cmd: SyncSymbolCommand, mediator: Mediator = Depends(get_mediator)):
    return await mediator.send(cmd)
```

## Files to Modify

| File | Change |
|------|--------|
| `src/features/market_data/sync/command.py` | dataclass → Pydantic |
| `src/features/market_data/sync/handler.py` | Return SyncResponse |
| `src/features/market_data/api/routes.py` | Remove SyncRequest, use command |
| `src/features/market_data/quote/command.py` | dataclass → Pydantic |
| `src/features/backtesting/handlers/backtest_commands.py` | dataclass → Pydantic |
| `src/features/strategy/handlers/commands.py` | dataclass → Pydantic |

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| API versioning needed later | Introduce adapter layer at that time |
| Non-HTTP interface (CLI/Celery) | Commands still work, just carry extra Field metadata |
| Breaking OpenAPI docs | Test OpenAPI output after migration |

## Success Criteria

- [ ] All commands are Pydantic BaseModel
- [ ] No separate Request classes in routes
- [ ] Handlers return Response models directly
- [ ] OpenAPI docs remain correct
- [ ] All tests pass

## Sources

- [PyMediator 2025](https://www.johal.in/mediatr-pymediator-request-handler-dispatch-for-loose-coupling-2025-4/)
- [python-cqrs](https://pypi.org/project/python-cqrs/)
- [FastAPI Clean Architecture](https://github.com/ivan-borovets/fastapi-clean-example)
- [DTO Pattern - Baeldung](https://www.baeldung.com/java-dto-pattern)
- [zhanymkanov/fastapi-best-practices](https://github.com/zhanymkanov/fastapi-best-practices)
