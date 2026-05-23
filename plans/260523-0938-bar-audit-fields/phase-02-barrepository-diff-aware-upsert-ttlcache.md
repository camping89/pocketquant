---
phase: 2
title: "BarRepository diff-aware upsert + TTLCache"
status: pending
priority: P1
effort: "3h"
dependencies: [1]
---

# Phase 2: BarRepository diff-aware upsert + TTLCache

## Overview

Refactor `BarRepository` để: (a) viết `source` + `updated_at` qua `$set` / `$setOnInsert` cho mọi write; (b) chỉ bump `updated_at` khi OHLCV thực sự khác giá trị hiện tại trong DB (diff-aware); (c) module-level `cachetools.TTLCache` để cascade re-runs cùng value skip cả read + write (zero IO trên cache hit); (d) convert `insert_many` thành upsert loop để fix bug ngầm "bar 1m đang building không update".

## Requirements

**Functional:**
- `upsert_bar(bar: Bar, *, source: str) -> None` — required kwarg `source`.
- `insert_many(records: list[Bar], *, source: str) -> int` — required kwarg `source`. Loop gọi `upsert_bar`. Return count of inserted-or-updated (best effort; có thể count cả no-op nếu khó disambiguate — accept).
- Cache hit khi `(symbol, exchange, interval_value, datetime_iso)` exist và `(o,h,l,c,v)` match → return ngay, 0 IO.
- Cache miss: `find_one` doc:
  - Không tồn tại → upsert mới: `$setOnInsert: {_id, created_at, source}`, `$set: {OHLCV, updated_at, source}`. Cache value.
  - Tồn tại + OHLCV giống → cache value, no-write.
  - Tồn tại + OHLCV khác → `$set OHLCV + updated_at + source`. Cache new value.

**Non-functional:**
- `cachetools.TTLCache(maxsize=20_000, ttl=3600)` — module-level singleton.
- `tick_count` KHÔNG tham gia diff detection (decision 6 brainstorm).
- File hiện tại ~250 LOC. Sau thêm sẽ ~330 LOC → cân nhắc tách helper sang `bar_repository_cache.py` nếu vượt 350 LOC.

**Dep changes:**
- Thêm `cachetools>=5.0.0` vào `packages/pocketquant-core/pyproject.toml`.

## Architecture

### Module-level cache

```python
# packages/pocketquant-core/src/pocketquant/core/persistence/repositories/bar_repository.py

from cachetools import TTLCache

# Process-local. Restart → cold start, ~5 cascade ticks warm up.
# Key: (symbol_upper, exchange_upper, interval_value, datetime_iso_utc)
# Value: (open, high, low, close, volume)  — tick_count excluded
_BAR_VALUE_CACHE: TTLCache = TTLCache(maxsize=20_000, ttl=3600)


def _cache_key(bar: Bar) -> tuple[str, str, str, str]:
    interval_val = bar.interval.value if bar.interval else ""
    dt_iso = bar.datetime.isoformat() if bar.datetime else ""
    return (
        bar.symbol.upper(),
        bar.exchange.upper(),
        interval_val,
        dt_iso,
    )


def _cache_value(bar: Bar) -> tuple[float, float, float, float, float]:
    return (bar.open, bar.high, bar.low, bar.close, bar.volume)
```

### Refactored `upsert_bar` flow

```python
async def upsert_bar(self, bar: Bar, *, source: str) -> None:
    key = _cache_key(bar)
    new_value = _cache_value(bar)

    # 1. Cache hit + same value → zero IO.
    cached = _BAR_VALUE_CACHE.get(key)
    if cached == new_value:
        return

    collection = self._collection()
    now = datetime.now(UTC)
    filter_q = {
        "symbol": bar.symbol.upper(),
        "exchange": bar.exchange.upper(),
        "interval": bar.interval.value if bar.interval else None,
        "datetime": bar.datetime,
    }

    # 2. Cache miss or different → check DB.
    existing = await collection.find_one(
        filter_q, {"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}
    )

    if existing is None:
        # New doc: $setOnInsert created_at, $set OHLCV + updated_at + source.
        doc = bar.to_mongo()
        bar_id = doc.pop("_id")
        created_at = doc.pop("created_at")
        await collection.update_one(
            filter_q,
            {
                "$setOnInsert": {
                    "_id": bar_id,
                    "created_at": created_at,
                },
                "$set": {**doc, "updated_at": now, "source": source},
            },
            upsert=True,
        )
        _BAR_VALUE_CACHE[key] = new_value
        return

    existing_value = (
        existing["open"], existing["high"], existing["low"],
        existing["close"], existing["volume"],
    )
    if existing_value == new_value:
        # DB already has same value — refresh cache, no write.
        _BAR_VALUE_CACHE[key] = new_value
        return

    # Value-change: bump updated_at + source, leave created_at untouched.
    await collection.update_one(
        filter_q,
        {
            "$set": {
                "open": bar.open, "high": bar.high, "low": bar.low,
                "close": bar.close, "volume": bar.volume,
                "tick_count": bar.tick_count,
                "updated_at": now,
                "source": source,
            },
        },
    )
    _BAR_VALUE_CACHE[key] = new_value
```

### Refactored `insert_many`

```python
async def insert_many(self, records: list[Bar], *, source: str) -> int:
    """Upsert each bar — fixes bug where in-progress 1m bar wasn't updated."""
    if not records:
        return 0
    count = 0
    for bar in records:
        try:
            await self.upsert_bar(bar, source=source)
            count += 1
        except Exception:
            logger.error(
                "bar_repo.insert_many.upsert_failed",
                symbol=bar.symbol, datetime=str(bar.datetime),
                source=source, exc_info=True,
            )
    logger.info(
        "bar_repo.insert_many.completed",
        attempted=len(records), upserted=count, source=source,
    )
    return count
```

### Why module-level (not instance-level) cache

- Repositories thường được tạo per-request (DI scope). Instance cache không persistent qua requests.
- Cascade chạy mỗi phút trong cùng process → module-level cache giữ value qua mọi instance.
- Cache stale risk (brainstorm decision 5): app là single writer chính → accept.

### Cache eviction semantics

- LRU eviction khi maxsize đạt: oldest accessed key bị drop trước.
- TTL=3600s: key cũ > 1h bị evict tự nhiên — phù hợp lookback_minutes=100 cascade.

## Related Code Files

- **Modify:** `packages/pocketquant-core/src/pocketquant/core/persistence/repositories/bar_repository.py`
- **Modify:** `packages/pocketquant-core/pyproject.toml` (add `cachetools>=5.0.0`)
- **Possible:** tách `bar_repository_cache.py` nếu file vượt 350 LOC (defer; bắt đầu inline).

## Implementation Steps

1. Add `cachetools>=5.0.0` dep vào `packages/pocketquant-core/pyproject.toml`; chạy `uv sync` để verify install.
2. Import `cachetools.TTLCache` ở đầu `bar_repository.py`.
3. Define module-level `_BAR_VALUE_CACHE`, `_cache_key`, `_cache_value` helpers (private prefix `_`).
4. Refactor `upsert_bar` thành signature `async def upsert_bar(self, bar: Bar, *, source: str) -> None`.
5. Implement 3-branch flow: cache-hit / new-doc / existing-doc same-value / existing-doc diff-value.
6. Refactor `insert_many` thành signature `async def insert_many(self, records: list[Bar], *, source: str) -> int`; loop call upsert_bar.
7. Grep callers `bar_repo.upsert_bar(` and `bar_repo.insert_many(` trên codebase — sẽ break tới khi Phase 3 wire xong. **OK**: Phase 2 + 3 cùng PR, không build/run giữa hai phase.
8. Run `uv run python -c "from pocketquant.core.persistence.repositories.bar_repository import BarRepository, _BAR_VALUE_CACHE; print(type(_BAR_VALUE_CACHE).__name__)"` smoke compile.

## Todo List

- [ ] Add cachetools dependency
- [ ] uv sync verify
- [ ] Module-level cache + helpers
- [ ] Refactor upsert_bar signature + 3-branch flow
- [ ] Refactor insert_many to upsert loop
- [ ] Smoke compile
- [ ] Note: callers in Phase 3 will compile clean afterward

## Success Criteria

- [ ] `cachetools` installed in lockfile.
- [ ] `upsert_bar(bar, source=...)` keyword-only signature compiles.
- [ ] `insert_many(records, source=...)` keyword-only signature compiles.
- [ ] `_BAR_VALUE_CACHE` accessible from test (importable).
- [ ] Unit tests in Phase 4 verify cache hit/miss/diff branches.

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| `insert_many` loop chậm hơn `bulk_write` cũ | Measure trên dev với 100 bars × 20 symbols. Nếu sync_1m latency > 2x trước, optimize sang `bulk_write([UpdateOne...])` ở Phase 2.5 (defer YAGNI). |
| Cache stale nếu out-of-band writer (debug script) đổi DB | Acceptable per brainstorm decision 5. Debug scripts hiếm + manual; restart container sau dùng. |
| `find_one` projection thiếu field → so sánh sai | Projection chỉ lấy 5 OHLCV field, đủ cho diff. Test cover. |
| `interval` field None edge case | `bar.interval.value if bar.interval else None` — đã pattern hiện tại. |

## Next Steps

→ Phase 3 wire `source` kwarg qua mọi callsite của `upsert_bar` / `insert_many`.
