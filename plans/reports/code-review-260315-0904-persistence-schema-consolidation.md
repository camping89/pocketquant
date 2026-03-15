# Code Review: Persistence Schema Consolidation

**Reviewer**: code-reviewer | **Date**: 2026-03-15
**Branch**: `feat/strategy-init` | **Scope**: Unstaged working tree changes
**Plan**: `plans/260315-0037-persistence-schema-consolidation/plan.md`

## Scope

- **Files modified**: 22 (6 domain, 5 repos, 6 import consumers, 2 infra, 2 docs, 1 plan)
- **Files deleted**: 6 (`src/persistence/schemas/` entire directory)
- **Files created**: 1 (`src/application/market_data/quote_dto.py`)
- **LOC delta**: Net reduction (~180 lines removed, duplication eliminated)
- **Tests**: 60/60 passing
- **Ruff**: Clean (1 pre-existing UP046)
- **Pyright**: 5 errors (all pre-existing, none introduced)

## Overall Assessment

**Strong refactor.** Successfully eliminates the dual-hierarchy problem (domain dataclass + persistence Pydantic schema) by making domain entities the single source of truth for MongoDB serialization. The `to_mongo()`/`from_mongo()` pattern is consistently applied. No regressions introduced. All stale schema references have been cleaned up.

The decision to reverse the earlier dataclass-purity refactor for pragmatic duplication elimination is sound -- the codebase was maintaining two parallel type hierarchies with no behavioral difference.

---

## Critical Issues

None.

---

## High Priority

### H1. `SyncStatus.from_mongo()` mutates input dict

**File**: `src/domain/ohlcv/entities.py:120-122`

```python
@classmethod
def from_mongo(cls, doc: dict[str, Any]) -> SyncStatus:
    doc.pop("_id", None)
    return cls(**doc)
```

`doc.pop("_id", None)` mutates the caller's dict. If the caller reuses the dict (e.g., for logging, caching, or retry logic), the `_id` field will be missing. Every other `from_mongo()` in the codebase uses `doc.get()` without mutation.

**Fix**: Copy before mutating, or use explicit field mapping like the other entities:

```python
@classmethod
def from_mongo(cls, doc: dict[str, Any]) -> SyncStatus:
    return cls(
        symbol=doc.get("symbol", ""),
        exchange=doc.get("exchange", ""),
        interval=doc.get("interval", ""),
        status=doc.get("status", "pending"),
        last_sync_at=doc.get("last_sync_at"),
        last_bar_at=doc.get("last_bar_at"),
        bar_count=doc.get("bar_count", 0),
        error_message=doc.get("error_message"),
    )
```

Note: This was inherited from the old schema -- same pattern existed there. But since this refactor touches it, worth fixing.

### H2. `SyncStatus.from_mongo()` fragile `**doc` pattern

Related to H1: the `cls(**doc)` pattern will raise `ValidationError` if MongoDB returns any unexpected field (e.g., `updated_at` added by a future repo method, or any extra metadata). The explicit field-mapping approach used by `Bar.from_mongo()`, `OrderAggregate.from_mongo()`, and `PositionAggregate.from_mongo()` is more defensive and should be used consistently.

### H3. `SyncStatus` missing `to_mongo()` method

`SyncStatus` has `from_mongo()` but no `to_mongo()`. The repo (`SyncStatusRepository.upsert()`) constructs the dict manually at lines 29-38. This breaks the pattern established for all other entities. If `SyncStatus` fields change, the repo must be updated separately.

**Recommendation**: Add `to_mongo()` to `SyncStatus` and have the repo call it, same as `Bar`/`SymbolAggregate`/etc.

### H4. `Bar.from_mongo()` calls `_utc_now()` at parse time as default

**File**: `src/domain/ohlcv/entities.py:87`

```python
created_at=doc.get("created_at", _utc_now()),
```

`_utc_now()` is evaluated **every call** even when `created_at` exists in the doc. This is a minor perf issue (datetime creation is cheap), but more importantly it means reconstructed bars from old docs without `created_at` get the **read time** as their creation time, not the original insertion time. This is a data integrity concern for backfilled data.

**Recommendation**: Use sentinel pattern:

```python
created_at=doc.get("created_at") or _utc_now(),
```

Or accept `None` and let the field default handle it. Though the current approach is not strictly wrong for new data.

---

## Medium Priority

### M1. `SymbolAggregate` dropped `currency` and `updated_at` fields

The old `SymbolBase` schema had `currency: str | None` and `Symbol` schema had `updated_at: datetime`. These fields are not present in the new `SymbolAggregate.to_mongo()` / `from_mongo()`.

- **`currency`**: If any existing MongoDB documents have this field, it will be ignored on read (safe). If any consumer needed it, they would break (no current consumers found).
- **`updated_at`**: Per the plan, this is intentional (repo sets it server-side). But `SymbolRepository.upsert()` does NOT set `updated_at` in `$set` -- so existing docs with `updated_at` will keep stale values, and new docs will never get one.

**Impact**: Low for now (no current code reads `currency` or `updated_at` from symbols). Worth documenting as a known gap.

### M2. `SymbolAggregate.deactivate()` uses `dataclasses.replace()` on a frozen dataclass inside a Pydantic model

**File**: `src/domain/symbol/aggregate.py:3, 53-56`

```python
from dataclasses import replace
...
def deactivate(self) -> None:
    if self.info:
        self.info = replace(self.info, is_active=False)
```

This works because `SymbolInfo` is a frozen dataclass and `replace()` creates a new instance. But `SymbolAggregate` is now a Pydantic model, and `self.info = ...` triggers Pydantic's `__set__` which validates the new value. This should work correctly, but it's mixing dataclass utilities with Pydantic models. Not a bug, just a code smell to note.

### M3. `OHLCVAggregate` and `QuoteAggregate` are not persisted but have `model_config = ConfigDict(populate_by_name=True)`

These aggregates are in-memory only (noted in docstrings). The `populate_by_name=True` config is unnecessary since they have no aliased fields. It's harmless but adds confusion about whether they're intended for MongoDB use.

### M4. `Bar.to_mongo()` includes `_id` using `str(self.id)` but `from_mongo()` handles `ObjectId` via `str(raw_id)`

The `_id` handling is asymmetric. `to_mongo()` always stringifies UUID, but `from_mongo()` handles `raw_id` that could be `ObjectId` from legacy data. This is correct defensive coding for migration, but worth noting the asymmetry.

### M5. `SyncStatus.interval` is `str` while `Bar.interval` is `Interval | None`

`SyncStatus` stores interval as raw `str`, not as the `Interval` enum. The old schema also did this. Since `SyncStatusRepository.upsert()` already passes `interval.value`, the string storage is intentional. But the inconsistency with `Bar` could cause confusion.

### M6. Docstring in `src/persistence/__init__.py` still mentions "schemas"

**File**: `src/persistence/__init__.py:1`

```python
"""Persistence layer - Database, Cache, repositories, schemas."""
```

The schemas directory no longer exists. Update docstring.

---

## Low Priority

### L1. `OrderAggregate` and `PositionAggregate` use `str` id, others use `UUID`

`OrderAggregate.id: str` and `PositionAggregate.id: str` vs `Bar.id: UUID` and `SymbolAggregate.id: UUID`. This is pre-existing and carried over from the original design (Order/Position used `generate_id_str()` which returns `str`). Not introduced by this refactor.

### L2. `Bar` field named `datetime` shadows the `datetime` type

Addressed correctly with `from datetime import datetime as dt`. The alias is consistent within the file. Minor readability cost.

### L3. CRLF/LF line ending warnings

Git reports LF-to-CRLF warnings on 4 files. Not a code quality issue, but may cause noisy diffs.

---

## Edge Cases Found by Scouting

1. **No remaining imports from `src.persistence.schemas`** -- confirmed clean via grep across entire codebase including tests.
2. **No stale references to old class names** (`OHLCVBase`, `SymbolBase`, `OrderDocument`, `PositionDocument`) -- confirmed clean.
3. **Backtest/Optimization repos unaffected** -- they use `to_dict()`/`from_dict()` pattern on `BacktestResult`/`OptimizationResult`, which is a separate concern.
4. **DI providers clean** -- no schema imports in `src/providers/`.
5. **`from __future__ import annotations` removed from Pydantic models** -- correctly done; only remains in `value_objects.py` and `ohlcv/value_objects.py` which are pure dataclasses (safe).
6. **`_VALID_TRANSITIONS` as `ClassVar`** works correctly in Pydantic -- Pydantic ignores `ClassVar` annotated attributes as intended.
7. **`PrivateAttr` for `_events`** -- correctly excluded from `model_dump()`, serialization, and `__init__` parameters. Events are only accessible via methods.

---

## Positive Observations

1. **Clean elimination of duplication**: ~6 schema files removed with zero functional loss. Every field mapping verified.
2. **Consistent `to_mongo()`/`from_mongo()` pattern**: All 4 persisted entity types follow the same structure.
3. **Proper `PrivateAttr` usage**: `_events` excluded from serialization in all aggregates. Domain event lifecycle unaffected.
4. **Good separation**: Quote DTOs correctly relocated to `src/application/market_data/quote_dto.py` -- they're infrastructure/cache concerns, not domain.
5. **Plan quality**: The plan doc is excellent -- clear motivation, explicit decisions table, risk mitigation.
6. **`OHLCVResponse` inlined**: Moved to the route file where it's used. No unnecessary indirection.
7. **Zero test regressions**: All 60 tests pass.

---

## Recommended Actions (prioritized)

1. **H1/H2**: Replace `SyncStatus.from_mongo()` `**doc` splat with explicit field mapping (consistency + safety)
2. **H3**: Add `SyncStatus.to_mongo()` to complete the pattern
3. **M6**: Update `persistence/__init__.py` docstring to remove "schemas"
4. **M1**: Document `currency`/`updated_at` field removal as intentional in commit message or ADR

---

## Metrics

| Metric | Value |
|--------|-------|
| Type Coverage | Good (pyright 5 errors, all pre-existing) |
| Test Coverage | 60/60 passing |
| Linting Issues | 1 (pre-existing UP046) |
| Stale References | 0 |
| Schema Files Removed | 6 |
| New Files Created | 1 |
| Pattern Consistency | High (minor `SyncStatus` outlier) |

---

## Unresolved Questions

1. Should `SyncStatus` be promoted to a proper entity with `id` field and `to_mongo()`? Currently it's a semi-entity (no identity, no `_id` generation). The repo constructs its own upsert dict.
2. The plan mentions "Repos: always `$set updated_at: datetime.now(UTC)` on every write" but `SymbolRepository.upsert()` and `OHLCVRepository.upsert_many()` do **not** do this. Was this intentionally skipped or missed?
