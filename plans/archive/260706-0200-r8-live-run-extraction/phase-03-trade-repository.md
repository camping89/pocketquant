# Phase 3 — TradeRepository (live `trades` collection)

**Context:** [plan.md](./plan.md) · [phase-02](./phase-02-fold-rehydrate-bootstrap.md)
**Priority:** P2 · **Status:** Done · **Track:** logic (infra mới, chưa đổi behavior)

## Overview

Persistence cho live `Trade` docs. Mirror `BacktestTradeRepository` shape nhưng collection `trades` + query theo `subscription_id` (= `run_id` với live). Chưa có consumer ở phase này — collector (Phase 4) ghi, metrics (Phase 5) đọc.

## Key insights

- `BacktestTradeRepository` (`core/infra/persistence/repositories/backtest_trade_repository.py`): `save_many(trades)`, `get(trade_id)`, `list_by_run(run_id)`, `_collection_name`, upsert `replace_one({_id}, ..., upsert=True)`.
- Live: `run_id == subscription_id` → `list_by_subscription(sub_id)` = filter `{"run_id": sub_id}`. `Trade` đã có `run_id` field.
- Incremental: collector đóng từng trade → `save_many([trade])` (hoặc `save(trade)`). Reuse `save_many` cho DRY.
- Collection name const → thêm `COLLECTION_TRADES = "trades"` cạnh `COLLECTION_BACKTEST_TRADES` (tìm file constants persistence).

## Related code files

**Create:**
- `src/pocketquant/core/infra/persistence/repositories/trade_repository.py` — `class TradeRepository(BaseRepository)`.

**Touch:**
- constants collection (nơi định nghĩa `COLLECTION_BACKTEST_TRADES`) — thêm `COLLECTION_TRADES = "trades"`.
- `src/pocketquant/app/di/persistence.py` — provide `TradeRepository`.
- `src/pocketquant/app/main_extensions.py:_REPO_TYPES` — thêm `TradeRepository` (ensure_indexes on startup).

## Implementation steps

1. Tạo `TradeRepository(BaseRepository)`:
   - `_collection_name = COLLECTION_TRADES`
   - `async def save_many(self, trades: list[Trade]) -> None` (upsert `_id`=trade_id, mirror backtest).
   - `async def list_by_subscription(self, subscription_id: str, limit: int = 500) -> list[Trade]` (filter `run_id`, sort `entry_time`).
   - `async def ensure_indexes(self)` — index `run_id` + `entry_time` (mirror backtest indexes, tên collection `trades`).
   - Serialize/deserialize `Trade` reuse helper của backtest repo (DRY — nếu có `_to_doc`/`_from_doc` dùng chung, extract; nếu không, mirror mảnh nhỏ).
2. Thêm const `COLLECTION_TRADES = "trades"`.
3. DI provide `TradeRepository` (persistence.py, scope APP mirror repo khác).
4. Thêm vào `_REPO_TYPES`.
5. Gate xanh (test/ruff/pyright/lint-imports). Test: unit repo save→list round-trip (dùng conftest test DB, KHÔNG prod).

## Todo

- [x] `TradeRepository` (save_many/list_by_subscription/ensure_indexes)
- [x] const `COLLECTION_TRADES = "trades"`
- [x] DI provide + `_REPO_TYPES` append
- [x] Unit test round-trip
- [x] Gate xanh

## Success criteria

- `TradeRepository` save→list round-trip qua test DB.
- Startup `ensure_all_indexes` tạo index `trades` (log `..._indexes_created`).
- Gate xanh; import-linter: repo ở `core.infra` (đúng — mọi repo ở core).

## Risk assessment

- **Trade (de)serialize:** `Trade` có nested/optional (`sl_price`/`tp_price` None). Reuse chính xác cách backtest repo (de)serialize để tránh drift schema.
- **Collection trùng:** đảm bảo `trades` chưa dùng cho mục đích khác (grep). Backtest dùng `backtest_trades` — tách biệt.

## Next steps

→ Phase 4 (collector ghi vào repo này).
