---
phase: 1
title: "Bar entity audit fields"
status: pending
priority: P2
effort: "1h"
dependencies: []
---

# Phase 1: Bar entity audit fields

## Overview

Mở rộng `Bar` Pydantic model với 2 field audit mới (`updated_at`, `source`). Read-only từ entity perspective — `to_mongo()` KHÔNG include chúng (BarRepository là single writer cho audit fields). `from_mongo()` đọc về để debug/admin tools dùng. Định nghĩa `SOURCE_*` constants ở module để cho callers refactor-safe.

## Requirements

**Functional:**
- `Bar.updated_at: dt | None = None` — populated bởi `from_mongo`, không serialize qua `to_mongo`.
- `Bar.source: str | None = None` — populated bởi `from_mongo`, không serialize qua `to_mongo`.
- `from_mongo()` parse cả 2 field nếu document có (coerce datetime UTC cho `updated_at`).
- `to_mongo()` GIỮ NGUYÊN behavior cũ: vẫn include `created_at`, KHÔNG include `updated_at`/`source`.
- Module-level `SOURCE_*` constants ở `core/domain/bar/entities.py` (Phase 2/3/5 import từ đây — đồng nhất một module).

**Non-functional:**
- Backwards compatible với docs hiện có (legacy không có `source`/`updated_at` → fields = None).
- File hiện tại ~100 LOC, sau thay đổi vẫn dưới 200 LOC → giữ trong cùng file.

## Architecture

### Entity diff

```python
# packages/pocketquant-core/src/pocketquant/core/domain/bar/entities.py

# NEW — module-level constants (KISS: str literals, no Enum)
SOURCE_REST_SYNC_1M = "rest_sync_1m"
SOURCE_REST_BACKFILL = "rest_backfill"
SOURCE_REST_REPAIR = "rest_repair"
SOURCE_CASCADE = "cascade"
SOURCE_TRACKED_SYMBOL_BACKFILL = "tracked_symbol_backfill"
SOURCE_ONE_TIME_LEGACY = "one_time_legacy"


class Bar(BaseModel):
    ...
    created_at: dt = Field(default_factory=utc_now)
    updated_at: dt | None = None  # NEW — read-only from entity perspective
    source: str | None = None     # NEW — read-only from entity perspective

    def to_mongo(self) -> dict[str, Any]:
        # GIỮ NGUYÊN: KHÔNG include updated_at/source.
        # BarRepository sẽ set chúng trong $set / $setOnInsert.
        return {
            "_id": str(self.id),
            ...
            "created_at": self.created_at,
        }

    @classmethod
    def from_mongo(cls, doc: dict[str, Any]) -> Bar:
        return cls(
            ...,
            created_at=coerce_utc(doc.get("created_at")) or utc_now(),
            updated_at=coerce_utc(doc.get("updated_at")),   # NEW
            source=doc.get("source"),                       # NEW
        )
```

### Why entity doesn't serialize audit fields

Repository áp đặt invariant "repo là single writer cho audit". Nếu `to_mongo()` include `updated_at`, một test/script tạo `Bar(updated_at=old_value)` rồi gọi `upsert_bar()` sẽ ghi đè stale value lên DB. Bỏ qua serialization ngăn class lỗi này by design.

## Related Code Files

- **Modify:** `packages/pocketquant-core/src/pocketquant/core/domain/bar/entities.py`

## Implementation Steps

1. Thêm 6 constants `SOURCE_*` ở top của `entities.py` (sau imports, trước `class Bar`).
2. Thêm `updated_at: dt | None = None` và `source: str | None = None` vào `Bar` model.
3. Cập nhật `from_mongo()` parse 2 field mới (dùng `coerce_utc` cho datetime).
4. Verify `to_mongo()` KHÔNG đổi (audit fields không serialize ra).
5. Verify `to_dict()` API: quyết định có expose audit fields không. **Decision:** thêm `updated_at` + `source` vào `to_dict()` để admin/debug UI đọc được qua API responses.
6. Run `uv run python -c "from pocketquant.core.domain.bar.entities import Bar; b = Bar(); print(b.model_dump())"` để smoke compile.

## Todo List

- [ ] Add SOURCE_* constants
- [ ] Add updated_at field
- [ ] Add source field
- [ ] Update from_mongo
- [ ] Update to_dict to include audit fields
- [ ] Smoke compile check

## Success Criteria

- [ ] `Bar(updated_at=None, source=None)` construct OK (defaults).
- [ ] `Bar.from_mongo({...})` đọc đúng `updated_at` và `source` từ doc, hoặc None nếu missing.
- [ ] `Bar.to_mongo()` output KHÔNG có key `updated_at` hoặc `source`.
- [ ] `Bar.to_dict()` output có cả `updated_at` (iso string hoặc None) và `source`.
- [ ] `from pocketquant.core.domain.bar.entities import SOURCE_CASCADE` import OK.

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Existing code path tạo Bar rồi gọi to_mongo() insert trực tiếp (bypass repo) | Grep `bar_repo.collection.insert` / `to_mongo()` callers — chỉ qua BarRepository. Confirmed scout: no direct callers ngoài repo. |
| Pydantic strict mode reject None cho dt field | `dt \| None = None` đúng pattern, đã test với pydantic 2.5+. |

## Next Steps

→ Phase 2 (BarRepository sử dụng `SOURCE_*` constants + viết audit fields qua `$set`/`$setOnInsert`).
