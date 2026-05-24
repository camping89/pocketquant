---
phase: 3
title: "Wire source through all callers"
status: pending
priority: P1
effort: "2h"
dependencies: [2]
---

# Phase 3: Wire source through all callers

## Overview

Truyền `source: str` từ mọi điểm gọi `BarRepository.upsert_bar` / `insert_many`. Thêm field `source` vào `SyncSymbolCommand` để cron callers label rõ ràng. Sử dụng `SOURCE_*` constants từ Phase 1 (refactor-safe khi đổi label). Tất cả callers cùng commit/PR — no transitional state.

## Requirements

**Functional:**
- `SyncSymbolCommand` thêm `source: str` (required) — caller hard-code label.
- `SyncSymbolHandler._persist_bars` truyền `source=request.source` qua `insert_many`.
- `sync_jobs._sync_by_intervals` construct `SyncSymbolCommand` với `source` từ caller-specific label.
- `sync_1m` → `SOURCE_REST_SYNC_1M`.
- `sync_backfill` → `SOURCE_REST_BACKFILL`.
- `repair_integrity` (sync_repair) → construct `SyncSymbolCommand(source=SOURCE_REST_REPAIR)`.
- `cascade_for_symbol` → call `upsert_bar(bar, source=SOURCE_CASCADE)`.
- `tracked_symbols/backfill/handler` → call `upsert_bar(bar, source=SOURCE_TRACKED_SYMBOL_BACKFILL)` ở cả `_direct` và `_cascade` (1m upsert) paths. Cascade phần gọi `cascade_for_symbol` đã tự dùng `SOURCE_CASCADE` cho higher tfs.

**Non-functional:**
- Type-check pass: required kwargs trên `upsert_bar`/`insert_many` ép caller cung cấp; mypy/pyright catch missing.
- Logging: `source` được log ở `market_data.sync.started` / `cascade.completed_tf` cho observability.

## Architecture

### Caller table

| File | Function | Source value | Mechanism |
|------|----------|--------------|-----------|
| `sync_one/command.py` | `SyncSymbolCommand` | (field) | Add `source: str = Field(...)` required |
| `sync_one/handler.py` | `_persist_bars` | `request.source` | Pass to `insert_many` |
| `sync_jobs.py` | `_sync_by_intervals` | (param) | Add `source: str` param, propagate to Command |
| `sync_jobs.py` | `sync_1m`, `_run_sync` | `SOURCE_REST_SYNC_1M`, `SOURCE_REST_BACKFILL` | Hard-coded per entry point |
| `sync_jobs.py` | `_run_repair` → `repair_integrity` | `SOURCE_REST_REPAIR` | Pass `source` arg through |
| `integrity_jobs.py` | `repair_integrity` | (param) | Add `source: str`, propagate to Command |
| `cascade_aggregator.py` | `cascade_for_symbol` | `SOURCE_CASCADE` | Hard-coded inside function |
| `tracked_symbols/backfill/handler.py` | `_direct`, `_cascade` (1m loop) | `SOURCE_TRACKED_SYMBOL_BACKFILL` | Hard-coded |

### Code sketches

**`SyncSymbolCommand`** (`handlers/sync/sync_one/command.py`):
```python
class SyncSymbolCommand(BaseModel):
    symbol: str = Field(...)
    exchange: str = Field(...)
    interval: Interval = Field(default=Interval.DAY_1)
    n_bars: int = Field(default=LIMIT_TVDATAFEED_MAX_BARS, ge=1, le=LIMIT_TVDATAFEED_MAX_BARS)
    skip_filter: bool = Field(default=False)
    source: str = Field(..., description="Audit label identifying write path (rest_sync_1m, rest_backfill, ...).")
```

**`SyncSymbolHandler._persist_bars`** (`handlers/sync/sync_one/handler.py`):
```python
async def _persist_bars(
    self, symbol: str, exchange: str, records: list[Bar], source: str
) -> int:
    if not records:
        return 0
    inserted_count = await self._bar_repo.insert_many(records, source=source)
    await self._symbol_repo.upsert(Symbol.create(code=symbol, exchange=exchange))
    return inserted_count

# In handle():
inserted_count = await self._persist_bars(symbol, exchange, records, request.source)
```

**`sync_jobs._sync_by_intervals`** — add `source` param:
```python
async def _sync_by_intervals(
    intervals: list[Interval],
    n_bars: int,
    job_name: str,
    mediator: Mediator,
    tracked_symbol_repo: TrackedSymbolRepository,
    history_repo: JobHistoryRepository,
    doc_id: str | None,
    source: str,  # NEW
) -> tuple[int, int]:
    ...
    command = SyncSymbolCommand(
        symbol=symbol, exchange=exchange, interval=interval, n_bars=n_bars, source=source,
    )
    ...
```

**`sync_jobs._run_sync`** + `sync_1m`:
```python
async def _run_sync(name: str, intervals: list[Interval], n_bars: int, source: str) -> None:
    ...
    total_inserted, total_fetched = await _sync_by_intervals(
        intervals, n_bars, name, mediator, tracked_symbol_repo, history_repo, doc_id, source,
    )
    ...

async def sync_1m() -> None:
    ...
    total_inserted, total_fetched = await _sync_by_intervals(
        [Interval.MINUTE_1], 100, name, mediator, tracked_symbol_repo, history_repo, doc_id,
        source=SOURCE_REST_SYNC_1M,
    )
    ...

async def sync_backfill() -> None:
    await _run_sync("sync_backfill", SYNC_INTERVALS, 5000, source=SOURCE_REST_BACKFILL)
```

**`sync_jobs._run_repair`**:
```python
result = await repair_integrity(
    symbol, exchange, interval, bar_repo, mediator,
    source=SOURCE_REST_REPAIR,
)
```

**`integrity_jobs.repair_integrity`**:
```python
async def repair_integrity(
    symbol: str, exchange: str, interval: Interval,
    bar_repo: BarRepository, mediator: Mediator,
    *, source: str, days_back: int = 7,
) -> dict:
    ...
    command = SyncSymbolCommand(
        symbol=symbol, exchange=exchange, interval=interval,
        n_bars=5000, skip_filter=True, source=source,
    )
    ...
```

**`cascade_aggregator.cascade_for_symbol`** — hard-code inside (cascade chỉ có 1 caller path):
```python
from pocketquant.core.domain.bar.entities import Bar, SOURCE_CASCADE
...
await bar_repo.upsert_bar(bar, source=SOURCE_CASCADE)
```

**`tracked_symbols/backfill/handler.py`**:
```python
from pocketquant.core.domain.bar.entities import SOURCE_TRACKED_SYMBOL_BACKFILL

async def _direct(self, symbol, exchange, interval, n) -> int:
    ...
    await self._bar_repo.upsert_bar(bar, source=SOURCE_TRACKED_SYMBOL_BACKFILL)
    ...

async def _cascade(self, symbol, exchange, interval, n) -> int:
    ...
    # 1m upsert loop uses tracked_symbol_backfill (the user-initiated path).
    for bar in bars_1m:
        await self._bar_repo.upsert_bar(bar, source=SOURCE_TRACKED_SYMBOL_BACKFILL)
    # Cascade function itself uses SOURCE_CASCADE for higher tfs.
    await cascade_for_symbol(...)
    ...
```

### Logging additions (low-effort, high observability)

Trong `SyncSymbolHandler.handle`:
```python
logger.info(
    "market_data.sync.started",
    symbol=symbol, exchange=exchange, interval=interval.value,
    source=request.source,  # NEW
)
```

Trong `cascade_aggregator.cascade_for_symbol`:
```python
logger.info(
    "cascade.completed_tf",
    ...,
    source=SOURCE_CASCADE,  # NEW (already correct but explicit)
)
```

## Related Code Files

**Modify:**
- `packages/pocketquant-api/src/pocketquant/api/market_data/handlers/sync/sync_one/command.py`
- `packages/pocketquant-api/src/pocketquant/api/market_data/handlers/sync/sync_one/handler.py`
- `packages/pocketquant-api/src/pocketquant/api/market_data/app_services/sync_jobs.py`
- `packages/pocketquant-api/src/pocketquant/api/market_data/app_services/integrity_jobs.py`
- `packages/pocketquant-api/src/pocketquant/api/market_data/app_services/cascade_aggregator.py`
- `packages/pocketquant-api/src/pocketquant/api/market_data/handlers/tracked_symbols/backfill/handler.py`

**Sanity-check (grep then modify if found):** `bar_repo.upsert_bar(` and `bar_repo.insert_many(` callers — full list trên repo (đã scout):
1. `cascade_aggregator.cascade_for_symbol` ✓ covered
2. `tracked_symbols/backfill/handler` ✓ covered
3. `sync_one/handler._persist_bars` ✓ covered (via insert_many)
4. Test files — adjust trong Phase 4

## Implementation Steps

1. Add `source: str = Field(..., description=...)` vào `SyncSymbolCommand`.
2. Update `_persist_bars(self, ..., source: str)` ở `SyncSymbolHandler`; pass `request.source` từ `handle()`.
3. Add `source: str` log field vào `market_data.sync.started`.
4. Update `_sync_by_intervals` signature — `source: str` param; propagate to `SyncSymbolCommand`.
5. Update `_run_sync(name, intervals, n_bars, source)`; update `sync_backfill()` call.
6. Update `sync_1m()` để truyền `source=SOURCE_REST_SYNC_1M` qua `_sync_by_intervals`.
7. Update `_run_repair` để truyền `source=SOURCE_REST_REPAIR` qua `repair_integrity`.
8. Update `repair_integrity(*, source: str, ...)` propagate to `SyncSymbolCommand`.
9. Update `cascade_for_symbol` — import `SOURCE_CASCADE`, pass qua `upsert_bar`.
10. Update `BackfillTrackedSymbolHandler` — import `SOURCE_TRACKED_SYMBOL_BACKFILL`, pass qua `_direct` và `_cascade._1m_upsert_loop`.
11. Grep `upsert_bar(` và `insert_many(` lại toàn repo — verify mọi callsite đã có kwarg `source=`.
12. Run `uv run python -c "from pocketquant.api.market_data.app_services.sync_jobs import sync_1m"` smoke compile.

## Todo List

- [ ] SyncSymbolCommand.source field
- [ ] SyncSymbolHandler propagate source
- [ ] _sync_by_intervals source param
- [ ] sync_1m + sync_backfill labels
- [ ] _run_repair → repair_integrity source
- [ ] cascade_for_symbol SOURCE_CASCADE
- [ ] backfill handler SOURCE_TRACKED_SYMBOL_BACKFILL
- [ ] Final grep verification all callsites
- [ ] Smoke compile

## Success Criteria

- [ ] Mọi callsite của `upsert_bar` / `insert_many` truyền kwarg `source=`.
- [ ] `grep -rn "upsert_bar(" packages/ scripts/` → zero callsite thiếu source (sau Phase 5 cũng vậy).
- [ ] `SyncSymbolCommand(symbol="X", exchange="Y")` raises Pydantic ValidationError (`source` required).
- [ ] `uv run pytest packages/pocketquant-api/tests/ -k "sync_jobs"` import + collection pass (test correctness về source ở Phase 4).
- [ ] Log line `market_data.sync.started` chứa `source` field.

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Forgot callsite ngoài 4 file đã list | Required kwarg + Python type checker catch at runtime/static. Grep verification step 11. |
| External caller (REST API client?) construct SyncSymbolCommand | Grep `SyncSymbolCommand(` → chỉ internal use (sync_jobs + integrity_jobs + test). Confirmed scout. |
| Existing tests fail vì `source` missing | Fix tests as part of Phase 4. |

## Next Steps

→ Phase 4 viết tests cover cache + diff + source paths.
