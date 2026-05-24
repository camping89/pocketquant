---
phase: 4
title: "Tests (unit + integration)"
status: pending
priority: P1
effort: "3h"
dependencies: [3]
---

# Phase 4: Tests (unit + integration)

## Overview

Cover hành vi mới: entity serialization, repo cache hit/miss, diff detection chỉ bump `updated_at` khi OHLCV đổi, source label propagation qua từng caller. Mock-based unit tests cho repository (theo pattern hiện tại `test_bar_repository_delete_range.py`). Integration test optional cho cascade end-to-end nếu test infra hỗ trợ (skip nếu phải standup Mongo container).

## Requirements

**Functional coverage:**
- Entity: `to_mongo()` không có `updated_at`/`source`; `from_mongo()` parse đúng; `to_dict()` có audit fields.
- Repository cache: hit khi same value → 0 IO; miss khi value khác → write; new doc → `$setOnInsert created_at`.
- Diff: 2 calls cùng OHLCV → 1 write; thay đổi `close` → write thứ 2.
- Source: kwarg required (TypeError nếu thiếu); value đi vào `$set` payload.
- `insert_many` loop: gọi `upsert_bar` đúng N lần với cùng `source`.
- `SyncSymbolCommand.source` required (Pydantic ValidationError).
- `cascade_for_symbol` truyền `source=SOURCE_CASCADE`.
- `repair_integrity` truyền `source=SOURCE_REST_REPAIR` xuống Command.

**Non-functional:**
- Test files dưới 200 LOC mỗi file → tách per-concern.
- Reuse `_make_repo` mock pattern từ `test_bar_repository_delete_range.py` (consistency).
- Reset `_BAR_VALUE_CACHE` giữa các test (fixture autouse).

## Architecture

### Test layout

```
packages/pocketquant-core/tests/unit/domain/bar/
  test_entities_audit_fields.py             # NEW
packages/pocketquant-core/tests/unit/persistence/
  test_bar_repository_upsert_cache.py       # NEW — cache hit/miss/diff/source
  test_bar_repository_insert_many_upsert.py # NEW — loop semantics + source propagation
  test_bar_repository_delete_range.py       # EXISTING — no change

packages/pocketquant-api/tests/market_data/
  test_cascade_aggregator_source.py         # NEW — verify SOURCE_CASCADE wired
  test_integrity_jobs_repair_source.py      # NEW — verify SOURCE_REST_REPAIR wired
  test_sync_jobs_source_labels.py           # NEW — verify sync_1m/sync_backfill labels

packages/pocketquant-api/tests/unit/handlers/sync/
  test_sync_symbol_command_source.py        # NEW — Pydantic required field
```

### Fixture: cache reset

```python
# conftest.py (test-scoped) hoặc inline trong each test file
import pytest
from pocketquant.core.persistence.repositories.bar_repository import _BAR_VALUE_CACHE

@pytest.fixture(autouse=True)
def reset_bar_value_cache():
    _BAR_VALUE_CACHE.clear()
    yield
    _BAR_VALUE_CACHE.clear()
```

### Key test cases

**`test_entities_audit_fields.py`:**
- `test_to_mongo_excludes_updated_at_and_source`
- `test_from_mongo_parses_updated_at_and_source`
- `test_from_mongo_handles_missing_audit_fields` (legacy doc) → fields = None
- `test_to_dict_includes_audit_fields`
- `test_source_constants_string_values` (sanity check labels)

**`test_bar_repository_upsert_cache.py`:**
- `test_cache_hit_same_value_no_db_call` — pre-populate `_BAR_VALUE_CACHE[key] = value`, call `upsert_bar`, assert collection.find_one + update_one không gọi.
- `test_cache_miss_new_doc_setOnInsert_created_at_and_source` — find_one returns None, upsert with new fields.
- `test_cache_miss_existing_doc_same_value_no_write` — find_one returns matching OHLCV, no update_one call, cache populated.
- `test_cache_miss_existing_doc_diff_value_writes_updated_at_source` — close khác → update_one called với `$set updated_at + source + new OHLCV`, KHÔNG `$setOnInsert created_at`.
- `test_upsert_bar_missing_source_kwarg_raises` — `await repo.upsert_bar(bar)` → TypeError.

**`test_bar_repository_insert_many_upsert.py`:**
- `test_insert_many_calls_upsert_per_bar` — 3 bars → 3 `upsert_bar` calls (patch `upsert_bar` on instance, count calls, verify `source=` kwarg).
- `test_insert_many_empty_list_returns_zero`.
- `test_insert_many_missing_source_raises`.
- `test_insert_many_continues_on_individual_failure` — 1 bar raises, other 2 vẫn upsert; return count chính xác.

**`test_sync_symbol_command_source.py`:**
- `test_missing_source_raises_validation_error`
- `test_source_accepts_arbitrary_string` (KISS, not Enum)

**`test_cascade_aggregator_source.py`:**
- Mock `bar_repo.upsert_bar` (AsyncMock); call `cascade_for_symbol`; assert all calls có `source=SOURCE_CASCADE`.

**`test_integrity_jobs_repair_source.py`:**
- Mock `mediator.send`; call `repair_integrity(..., source=SOURCE_REST_REPAIR)`; assert command sent có `source=SOURCE_REST_REPAIR`.

**`test_sync_jobs_source_labels.py`:**
- Mock `mediator.send`, `tracked_symbol_repo.list_all`; call `sync_1m()`; assert any `SyncSymbolCommand` sent has `source=SOURCE_REST_SYNC_1M`.
- Cùng pattern cho `sync_backfill` → `SOURCE_REST_BACKFILL`.

### Integration (optional — defer if Mongo container không có)

`tests/integration/test_bar_audit_roundtrip.py`:
- Spin lên Mongo testcontainer.
- Call `upsert_bar(bar, source="test")` → query doc → assert `created_at` set, `updated_at` set, `source = "test"`.
- Call lại cùng bar OHLCV → query doc → `updated_at` unchanged.
- Call với close khác → query doc → `updated_at` đã bump, `created_at` không đổi.

**Decision:** skip integration nếu repo chưa có Mongo testcontainer pattern (kiểm tra `tests/integration/` hiện trạng); unit tests đủ confidence với mock-based verification.

## Related Code Files

**Create:**
- `packages/pocketquant-core/tests/unit/domain/bar/test_entities_audit_fields.py`
- `packages/pocketquant-core/tests/unit/persistence/test_bar_repository_upsert_cache.py`
- `packages/pocketquant-core/tests/unit/persistence/test_bar_repository_insert_many_upsert.py`
- `packages/pocketquant-api/tests/unit/handlers/sync/test_sync_symbol_command_source.py`
- `packages/pocketquant-api/tests/market_data/test_cascade_aggregator_source.py`
- `packages/pocketquant-api/tests/market_data/test_integrity_jobs_repair_source.py`
- `packages/pocketquant-api/tests/market_data/test_sync_jobs_source_labels.py`

**Conditional:**
- `tests/integration/test_bar_audit_roundtrip.py` — skip if no Mongo testcontainer.

## Implementation Steps

1. Verify `cachetools` test-importable: `uv run python -c "from cachetools import TTLCache"`.
2. Write `test_entities_audit_fields.py` — 5 test cases per outline.
3. Write `test_bar_repository_upsert_cache.py` — 5 cache/diff cases dùng `_make_repo` mock pattern + cache reset fixture.
4. Write `test_bar_repository_insert_many_upsert.py` — 4 cases (patch `upsert_bar` on instance, count + verify kwargs).
5. Write `test_sync_symbol_command_source.py` — 2 Pydantic cases.
6. Write `test_cascade_aggregator_source.py` — single test, mock `bar_repo.upsert_bar` + `find` returns minimal 1m bars.
7. Write `test_integrity_jobs_repair_source.py` — mock mediator, assert Command sent has correct source.
8. Write `test_sync_jobs_source_labels.py` — mock container deps, run `sync_1m`/`sync_backfill`, assert source labels.
9. Run `uv run pytest packages/pocketquant-core/tests/unit/domain/bar/ packages/pocketquant-core/tests/unit/persistence/ -x -v` → all green.
10. Run `uv run pytest packages/pocketquant-api/tests/ -x -v -k "source or audit"` → all green.
11. Run full suite `uv run pytest -x` → no regression in unrelated tests.

## Todo List

- [ ] Entities audit fields tests
- [ ] Upsert cache hit/miss/diff tests
- [ ] Insert_many loop tests
- [ ] SyncSymbolCommand source field test
- [ ] Cascade source test
- [ ] Repair source test
- [ ] Sync_jobs labels test
- [ ] Cache reset fixture (autouse)
- [ ] Full test suite pass (no regression)

## Success Criteria

- [ ] Coverage cho 3 cache branches (hit, miss-new, miss-existing-same, miss-existing-diff).
- [ ] Verify required-kwarg behavior (missing source → error).
- [ ] Verify source propagation từ cron entrypoint → SyncSymbolCommand → repo.
- [ ] `uv run pytest packages/` exit code 0.
- [ ] No flaky tests (cache state isolation via autouse fixture).

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Mock complexity cho `find_one` projection vs full doc | Test fixtures dùng MagicMock; projection chỉ trả 5 OHLCV field nên fixture nhỏ. |
| Cache leakage giữa tests → false positives | autouse `reset_bar_value_cache` fixture. |
| Existing tests dùng `insert_many(records)` cũ (positional) sẽ break | Find + fix as part of Phase 4 (grep step 11 ở Phase 3 đã list ra). |
| `_BAR_VALUE_CACHE` private name → linter complain on test import | Acceptable; private import for test cache reset is common pattern. |

## Next Steps

→ Phase 5 viết migration script cho legacy docs.
