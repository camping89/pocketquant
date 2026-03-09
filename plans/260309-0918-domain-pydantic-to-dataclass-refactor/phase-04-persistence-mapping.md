# Phase 4: Persistence Mapping Verification

## Overview
- **Priority:** High (must work after phases 1-3)
- **Status:** completed
- **Effort:** 20min

Verify and fix `Document.from_aggregate()` and `Document.to_aggregate()` methods in persistence schemas. These are the bridge between domain (now dataclass) and persistence (stays Pydantic).

## Files to Verify

| File | Methods | Risk |
|------|---------|------|
| `src/persistence/schemas/order_schema.py` | `from_aggregate()`, `to_aggregate()` | Low |
| `src/persistence/schemas/position_schema.py` | `from_aggregate()`, `to_aggregate()` | Low |

**Not affected:**
- `src/persistence/schemas/symbol_schema.py` -- does NOT use SymbolAggregate (has its own `Symbol` Pydantic model)
- `src/persistence/schemas/quote_schema.py` -- does NOT use QuoteAggregate (has its own `Quote` Pydantic model)
- `src/persistence/schemas/ohlcv_schema.py` -- does NOT use OHLCVAggregate (has its own `OHLCV` Pydantic model)

## Analysis: OrderDocument

```python
# from_aggregate() -- accesses aggregate fields
@classmethod
def from_aggregate(cls, order: OrderAggregate) -> OrderDocument:
    return cls(
        _id=order.id,                    # str attr -- works
        strategy_id=order.strategy_id,   # str attr -- works
        side=order.side.value,           # Enum.value -- works
        order_type=order.order_type.value, # Enum.value -- works
        status=order.status.value,       # Enum.value -- works
        ...                              # all simple attribute access
    )
```

**Verdict: NO CHANGES.** All access is simple attribute reads. Dataclass fields expose identical attributes.

```python
# to_aggregate() -- constructs aggregate via kwargs
def to_aggregate(self) -> OrderAggregate:
    return OrderAggregate(
        id=self.id,
        side=OrderSide(self.side),       # explicit enum conversion
        order_type=OrderType(self.order_type),
        status=OrderStatus(self.status),
        ...
    )
```

**Verdict: NO CHANGES.** Constructor kwargs work identically for dataclass. Explicit enum conversion already in place (no Pydantic auto-coercion relied upon).

## Analysis: PositionDocument

Same pattern as OrderDocument:

```python
# from_aggregate() -- simple attribute access
side=pos.side.value,  # PositionSide.value -- works

# to_aggregate() -- constructor kwargs
side=PositionSide(self.side),  # explicit conversion -- works
```

**Verdict: NO CHANGES.**

## Analysis: Repository model_dump() Calls

```python
# order_repository.py line 18
doc.model_dump(by_alias=True)  # doc is OrderDocument (Pydantic) -- STAYS PYDANTIC

# position_repository.py line 19
doc.model_dump(by_alias=True)  # doc is PositionDocument (Pydantic) -- STAYS PYDANTIC
```

`model_dump()` is called on Document objects (Pydantic), NOT on aggregates. No change needed.

## Implementation Steps

1. Read `order_schema.py` -- verify `from_aggregate`/`to_aggregate` use only attribute access and constructor kwargs
2. Read `position_schema.py` -- same verification
3. Run `pyright src/persistence/schemas/` after phases 1-3
4. Run integration test if available: ensure save/load round-trip works

## Todo

- [x] Verify OrderDocument mapping compiles with dataclass OrderAggregate
- [x] Verify PositionDocument mapping compiles with dataclass PositionAggregate
- [x] Run pyright on persistence/schemas/
- [x] Run any existing tests touching order/position persistence

## Success Criteria
- `from_aggregate()` works with dataclass aggregates (attribute access)
- `to_aggregate()` works (dataclass constructor kwargs)
- `model_dump()` calls on Document objects unaffected
- `pyright` passes on persistence layer
- Round-trip: create aggregate -> from_aggregate -> to_aggregate -> fields match
