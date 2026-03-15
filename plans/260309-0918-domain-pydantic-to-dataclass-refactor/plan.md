---
title: "Refactor Domain Layer from Pydantic to Dataclasses"
description: "Replace Pydantic BaseModel with Python dataclasses in domain aggregates, value objects, and events for a purer domain layer."
status: superseded
superseded_by: [260315-0037-persistence-schema-consolidation]
priority: P2
effort: 3h
branch: feat/strategy-init
tags: [domain, refactor, clean-architecture, dataclass]
created: 2026-03-09
---

# Domain Layer: Pydantic to Dataclass Refactor

## Motivation

Domain layer should have zero framework dependencies. Pydantic is an infrastructure concern (serialization/validation). Python stdlib `dataclasses` is the right tool for pure domain models.

**Already using dataclasses:** `Bar`, `SyncStatus`, `BarBuilder`, `StrategyConfig`, `StopLossConfig`, `TakeProfitConfig`, `OrderConfig` -- proves the pattern works.

## Scope

### Convert to @dataclass (22 classes across 11 files)

| Category | Classes | Count |
|----------|---------|-------|
| Base Event | `DomainEvent` | 1 |
| Domain Events | `OrderSubmittedEvent`, `OrderFilledEvent`, `OrderPartiallyFilledEvent`, `OrderCancelledEvent`, `OrderRejectedEvent`, `PositionOpenedEvent`, `PositionUpdatedEvent`, `PositionClosedEvent`, `QuoteReceivedEvent`, `QuoteUpdatedEvent`, `HistoricalDataSyncedEvent`, `BarCompletedEvent`, `SignalGeneratedEvent` | 13 |
| Value Objects | `Symbol` (shared), `SymbolInfo`, `PnL`, `Price`, `QuoteTick`, `OHLCV`, `BarRange`, `RiskConfig`, `Signal` | 9 |
| Aggregates | `OrderAggregate`, `PositionAggregate`, `SymbolAggregate`, `QuoteAggregate`, `OHLCVAggregate` | 5 |

### Stays Pydantic (no changes)

- `src/persistence/schemas/*.py` -- DB document models
- `src/features/**/command.py`, `query.py` -- CQRS input validation
- `src/features/**/route.py` -- API request/response models
- `src/config.py` -- Settings (pydantic-settings)

## Phases

| # | Phase | Files | Status |
|---|-------|-------|--------|
| 1 | [Domain Events](./phase-01-domain-events.md) | 6 files | completed |
| 2 | [Value Objects](./phase-02-value-objects.md) | 5 files | completed |
| 3 | [Aggregates](./phase-03-aggregates.md) | 5 files | completed |
| 4 | [Persistence Mapping](./phase-04-persistence-mapping.md) | 2 files | completed |
| 5 | [Verify & Cleanup](./phase-05-verify-cleanup.md) | all | completed |

## Key Conversion Patterns

```python
# BEFORE (Pydantic)
class DomainEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    event_id: UUID = Field(default_factory=generate_id)

# AFTER (dataclass)
@dataclass(frozen=True)
class DomainEvent:
    event_id: UUID = field(default_factory=generate_id)
```

```python
# BEFORE (Pydantic aggregate)
class OrderAggregate(BaseModel):
    _events: list[DomainEvent] = PrivateAttr(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

# AFTER (dataclass aggregate)
@dataclass
class OrderAggregate:
    _events: list[DomainEvent] = field(default_factory=list, init=False, repr=False)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
```

```python
# BEFORE (Pydantic validator)
@field_validator("value")
@classmethod
def validate_value(cls, v: float) -> float:
    if v < 0: raise ValueError("...")
    return v

# AFTER (__post_init__)
def __post_init__(self) -> None:
    if self.value < 0:
        raise ValueError("...")
```

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Enum auto-coercion loss | Pydantic coerces `"buy"` -> `OrderSide.BUY`. Dataclass won't. | Document schemas already pass `OrderSide(self.side)` explicitly. No change needed. |
| `asdict()` recursion | May recurse into UUID, datetime | Use manual `to_dict()` only where needed (already pattern in Bar entity) |
| frozen event + inheritance | Python dataclass inheritance with `frozen=True` works if ALL parent + child are frozen | All events inherit from frozen DomainEvent, all children also frozen. OK. |
| `PositionSizer` uses `risk_config.risk_per_trade` | Attribute access unchanged between Pydantic and dataclass | No impact |
