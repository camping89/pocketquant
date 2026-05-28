---
phase: 3
title: "Brainstorm + decide on Database wrapper API"
status: pending
priority: P2
effort: "1h"
dependencies: []
---

# Phase 3: Database wrapper API debate

## Overview

`pocketquant.core.persistence.mongodb.Database` wraps `AsyncMongoClient` + `AsyncDatabase` and currently exposes:

```python
class Database:
    def __init__(self) -> None:
        self.__client: AsyncMongoClient | None = None     # name-mangled
        self.__database: AsyncDatabase | None = None      # name-mangled
    async def connect(self, settings: Settings) -> None: ...
    async def disconnect(self) -> None: ...
    def get_database(self) -> AsyncDatabase: ...           # public accessor
    def get_collection(self, name: str): ...               # public accessor
```

Consumers want raw `AsyncDatabase` for one-off ops:
- `db.list_collection_names()`
- `db[old_coll].rename(new_coll)`
- `db[coll].drop_index(name)`
- bulk ops, aggregations on multiple collections, etc.

Today they have to write `db.get_database().list_collection_names()` — verbose and asymmetric with the simpler `db.get_collection(name)`. The bug that shipped in 260528-2000 (`db.database.list_collection_names()`) was a tell: developers naturally reach for `db.database` because the underlying object semantically IS a database. Name mangling fights intuition.

This phase debates 3 options + locks one before Phase 4 implements.

## Options

### Option A: Add public `database` property

```python
class Database:
    @property
    def database(self) -> AsyncDatabase:
        if self.__database is None:
            raise RuntimeError("Database not connected. Call Database.connect() first.")
        return self.__database
```

Keep `get_database()` as a thin alias (or deprecate). Call sites become `db.database.list_collection_names()` — exactly what developers were already writing.

**Pros:** Matches existing developer intuition (no re-education). Backward-compatible if `get_database()` stays. Test file `test_strategy_id_migration.py` already uses `db.database` — would pass as-is.

**Cons:** Slightly leakier abstraction — consumers can now grab the raw `AsyncDatabase` and call anything on it, bypassing any future cross-cutting policy (transactions, telemetry, retry). Mostly theoretical.

### Option B: Strict encapsulation — domain helpers on `Database`

Forbid `.database` access entirely. Every needed operation gets a method on `Database`:

```python
class Database:
    async def list_collection_names(self) -> list[str]: ...
    async def rename_collection(self, old: str, new: str) -> None: ...
    async def drop_index(self, collection: str, index: str) -> None: ...
    async def collection_exists(self, name: str) -> bool: ...
```

`get_database()` stays for emergencies but is marked `# escape hatch`.

**Pros:** Wrapper actually wraps. Future cross-cutting concerns (transactions, telemetry) can be added in one place. Tests/migration code reads more like domain.

**Cons:** Endless growth — every new pymongo method needs a passthrough. Hard to enumerate up front. Migration helpers in `main_extensions.py` end up calling `db.list_collection_names()` + `db.rename_collection()` instead of using pymongo directly. Higher refactor cost (more call sites to change).

### Option C: Hybrid — public `database` property, but contract is "advanced"

Same code as A. But README + docstring + `# advanced` comment say: prefer `get_collection()` / new helpers for app code; `database` is for migrations + one-offs.

**Pros:** Pragmatic. Costs of A without the religious feel of B. Lets us add helpers OPPORTUNISTICALLY when a pattern repeats (don't have to enumerate everything up front).

**Cons:** Convention not enforcement — somebody will use `.database` for app-flow code. But this is what name-mangling was trying to prevent and it failed (developers wrote `db.database` anyway and got AttributeError instead of code review).

## Decision criteria

1. **Which option produces the smallest diff** while making test_strategy_id_migration.py + migration helpers correct?
2. **Which option matches the existing `Database` docstring**? (Read the docstring — "Repositories receive this class and call get_collection() — they never see the client" — implies B-ish encapsulation.)
3. **Which option has the lowest future-maintenance cost** as new pymongo methods land?
4. **Which option survives Phase 2's new tests** with the least churn?

## Requirements

- Functional:
  - Single chosen option + rationale documented in `plans/.../reports/phase-03-database-wrapper-decision.md`.
  - One-paragraph rebuttal for each rejected option.
  - Concrete diff sketch (≤30 lines) for the chosen option applied to `packages/pocketquant-core/src/pocketquant/core/persistence/mongodb.py`.
- Non-functional:
  - No code changes in this phase (Phase 4 implements).

## Architecture

See option blocks above.

## Related Code Files

(Read-only)
- `packages/pocketquant-core/src/pocketquant/core/persistence/mongodb.py`
- `packages/pocketquant-api/src/pocketquant/api/main_extensions.py`
- `packages/pocketquant-api/tests/unit/test_strategy_id_migration.py`
- Any repository file under `packages/*/src/.../persistence/` that reads `Database` (grep for `get_database\b` and `get_collection\b`).

## Implementation Steps

1. `grep -rn "get_database\b\|\.database\b" packages/ --include="*.py"` — full inventory of consumers.
2. For each call site, classify as: (a) needs raw AsyncDatabase, (b) is a one-off pattern that deserves a helper, (c) is a repository getting a collection (already served by `get_collection`).
3. Count call sites per category.
4. Apply decision criteria. Write decision report.
5. Sketch the concrete diff in the report.
6. Loop in a human reviewer (optional async DM) before Phase 4 fires.

## Success Criteria

- [ ] Decision recorded with rationale referencing the 4 criteria.
- [ ] Rejected options each get a 1-paragraph rebuttal so future readers understand the choice.
- [ ] Diff sketch fits in <30 lines and is mechanically applicable.
- [ ] Call-site inventory included so Phase 4 has zero guess work.

## Risk Assessment

| Risk | Mitigation |
|---|---|
| Endless debate, no decision | Hard time-box: 1 hour. If still split, pick Option C as default (cheapest reversible) and move on. |
| Decision conflicts with existing `Database` docstring intent | Update the docstring as part of Phase 4. Docstring is not load-bearing. |
| Choosing B requires enumerating every helper up front | If B is chosen, scope it to just the methods migration code needs TODAY; add more on demand. Phase 4 owns this. |
| `get_database()` callers outside `pocketquant-api` (e.g. backtest, trading) regress | Inventory in step 1 covers all packages; Phase 4 sweep includes them. |

## Next Steps

- Phase 4 applies the chosen option + sweeps call sites.
