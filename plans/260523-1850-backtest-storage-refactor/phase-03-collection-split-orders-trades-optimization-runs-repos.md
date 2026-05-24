---
phase: 3
title: "Collection split (orders/trades/optimization_runs) + repos"
status: pending
priority: P2
effort: "1d"
dependencies: [1]
---

# Phase 3: Collection split (orders/trades/optimization_runs) + repos

## Overview

Split single embedded `backtest_runs` model into 4 MongoDB collections (all prefixed `backtest_`):
- `backtest_runs` — slimmed: metrics + config + equity_curve[] (embed) + open_positions[] (embed); drops `trades[]` + `positions[]`
- `backtest_orders` — new: lifecycle audit with embed `events[]` + `fills[]`
- `backtest_trades` — new: round-trip ledger with entry/exit order refs + pnl
- `backtest_optimization_runs` — rename from `optimization_runs`

Add 2 new repositories (`OrderRepository`, `TradeRepository`); rewire `BacktestRepository`; rename `OptimizationRepository` collection constant. Add indexes per collection.

## Requirements

- Functional: All 4 collections exist with `ensure_indexes()` callable at app startup
- Functional: New repos follow existing repo pattern (`BaseRepository` inheritance, async methods, MongoDB direct access)
- Functional: `BacktestResult.to_mongo()` no longer embeds `trades`/`positions`; embeds `equity_curve` + `open_positions` only
- Non-functional: Indexes designed for known query patterns (per-run drill-down, cross-run analytics, subscription cache lookup)
- Non-functional: Collection constants in `constants.py` updated; legacy name `optimization_runs` removed

## Architecture

### Collection schemas (frozen)

**`backtest_runs`** (slimmed):
```json
{
  "_id": "run-uuid",
  "strategy_id": "...",
  "subscription_id": "..." | null,
  "status": "completed" | "failed" | "running",
  "started_at": ISODate,
  "completed_at": ISODate,
  "error_message": null | "...",
  "config_snapshot": {
    "strategy_id": "...",
    "symbol": "BTCUSDT:BINANCE",
    "interval": "1m",
    "start_date": "2025-01-01",
    "end_date": "2025-12-31",
    "initial_capital": 10000,
    "slippage_bps": 5,
    "commission_bps": 10,
    "parameters": { /* strategy params */ }
  },
  "parameters": { /* duplicate of config_snapshot.parameters for optimizer compat */ },
  "metrics": {
    "total_return": 0.15, "cagr": 0.12,
    "sharpe_ratio": 1.4, "sortino_ratio": 2.1,
    "max_drawdown": -0.08, "win_rate": 0.55,
    "profit_factor": 1.8, "total_trades": 120,
    "winning_trades": 66, "losing_trades": 54,
    "avg_win": 80.5, "avg_loss": -45.2,
    "avg_trade_duration_seconds": 3600,
    "total_commission": 245.6
  },
  "equity_curve": [
    { "timestamp": ISODate, "equity": 10000.0, "drawdown": 0.0 },
    /* ... */
  ],
  "open_positions": [
    {
      "symbol": "BTCUSDT:BINANCE", "direction": "LONG",
      "entry_price": 65000, "entry_time": ISODate,
      "quantity": 0.01, "sl_price": 64000, "tp_price": 67000,
      "entry_order_id": "ord-uuid", "entry_commission_portion": 0.15
    }
  ]
}
```

**`backtest_orders`** (new):
```json
{
  "_id": "order-uuid",
  "run_id": "run-uuid",
  "strategy_id": "...",
  "symbol": "BTCUSDT:BINANCE",
  "side": "BUY" | "SELL",
  "order_type": "MARKET" | "LIMIT" | "STOP",
  "quantity": 0.01,
  "price": null | 65000,
  "sl_price": null | 64000,
  "tp_price": null | 67000,
  "status": "FILLED" | "CANCELLED" | "REJECTED" | "EXPIRED",
  "submitted_at": ISODate,
  "last_updated_at": ISODate,
  "events": [
    { "timestamp": ISODate, "from_status": null, "to_status": "SUBMITTED", "reason": "submit" },
    { "timestamp": ISODate, "from_status": "SUBMITTED", "to_status": "FILLED", "reason": "market_fill" }
  ],
  "fills": [
    { "fill_id": "fill-uuid", "timestamp": ISODate, "qty": 0.01, "price": 65010, "commission": 0.65, "slippage": 0.00015 }
  ],
  "resulting_trade_id": "trade-uuid" | null
}
```

**`backtest_trades`** (new, round-trip):
```json
{
  "_id": "trade-uuid",
  "run_id": "run-uuid",
  "strategy_id": "...",
  "symbol": "BTCUSDT:BINANCE",
  "direction": "LONG" | "SHORT",
  "entry_order_id": "ord-uuid", "entry_price": 65000, "entry_time": ISODate, "quantity": 0.01,
  "exit_order_id": "ord-uuid", "exit_price": 67000, "exit_time": ISODate,
  "sl_price": 64000, "tp_price": 67000,
  "pnl": 19.85, "commission": 1.30, "duration_seconds": 7200
}
```

**`backtest_optimization_runs`** (rename only): same shape as current `optimization_runs`.

### Indexes per collection

**`backtest_runs`** (preserve existing 8 from `backtest_repository.py:248-277`):
1. `("strategy_id")`
2. `("started_at")`
3. `("status")`
4. `[("strategy_id", 1), ("started_at", -1)]`
5. `[("strategy_id", 1), ("metrics.sharpe_ratio", -1)]`
6. `[("strategy_id", 1), ("metrics.sortino_ratio", -1)]`
7. `[("strategy_id", 1), ("metrics.win_rate", -1)]`
8. `("subscription_id", unique=True, sparse=True)`

**`backtest_orders`** (new):
1. `("run_id")` — drill-down per-run
2. `[("strategy_id", 1), ("status", 1)]` — find all pending/cancelled across runs
3. `("submitted_at")` — time-range scans
4. `[("run_id", 1), ("status", 1)]` — per-run status filter

**`backtest_trades`** (new):
1. `("run_id")` — drill-down per-run
2. `[("strategy_id", 1), ("direction", 1)]` — long vs short performance
3. `("entry_time")` — time-range scans
4. `("pnl")` — find biggest winners/losers (descending sort)
5. `[("run_id", 1), ("entry_time", 1)]` — per-run chronological list

**`backtest_optimization_runs`**: preserve existing (`strategy_id`, `created_at`).

### Repository interfaces

```python
# packages/pocketquant-backtest/src/pocketquant/backtest/persistence/order_repository.py
class OrderRepository(BaseRepository):
    COLLECTION = COLLECTION_BACKTEST_ORDERS

    async def save_many(self, orders: list[Order]) -> None: ...
    async def get(self, order_id: str) -> Order | None: ...
    async def list_by_run(self, run_id: str) -> list[Order]: ...
    async def list_by_strategy_status(self, strategy_id: str, status: str, limit=100) -> list[Order]: ...
    async def delete_by_run(self, run_id: str) -> int: ...
    async def delete_by_strategy(self, strategy_id: str) -> int: ...
    async def ensure_indexes(self) -> None: ...

# packages/pocketquant-backtest/src/pocketquant/backtest/persistence/trade_repository.py
class TradeRepository(BaseRepository):
    COLLECTION = COLLECTION_BACKTEST_TRADES

    async def save_many(self, trades: list[Trade]) -> None: ...
    async def get(self, trade_id: str) -> Trade | None: ...
    async def list_by_run(self, run_id: str) -> list[Trade]: ...
    async def list_by_strategy(self, strategy_id: str, limit=200) -> list[Trade]: ...
    async def list_top_pnl(self, strategy_id: str, top=10, ascending=False) -> list[Trade]: ...
    async def delete_by_run(self, run_id: str) -> int: ...
    async def delete_by_strategy(self, strategy_id: str) -> int: ...
    async def ensure_indexes(self) -> None: ...
```

### Existing `BacktestRepository` changes

- `save(result: BacktestResult)` — still writes `backtest_runs` doc; now without `trades[]`/`positions[]`
- Add helper `delete_run_cascade(run_id)` — cascade delete to orders + trades collections (call `OrderRepository.delete_by_run` + `TradeRepository.delete_by_run` first, then own delete). Used by `delete_by_strategy`.
- `delete_by_strategy` — iterate runs, cascade-delete each
- Keep all subscription-scoped methods (`save_for_subscription`, `upsert_status`, `find_doc_by_subscription`, `get_subscription_status`, etc.) — these now operate on slimmed docs but mechanism same
- `mark_stale_running_as_failed` unchanged

### `OptimizationRepository` rename

- Update `COLLECTION_OPTIMIZATION_RUNS = "optimization_runs"` → `COLLECTION_BACKTEST_OPTIMIZATION_RUNS = "backtest_optimization_runs"` in `constants.py`
- Update `optimization_repository.py` to use new constant
- Class name stays `OptimizationRepository` (Python class != Mongo collection)

## Related Code Files

- **Create:**
  - `packages/pocketquant-backtest/src/pocketquant/backtest/persistence/order_repository.py`
  - `packages/pocketquant-backtest/src/pocketquant/backtest/persistence/trade_repository.py`
- **Modify:**
  - `packages/pocketquant-core/src/pocketquant/core/common/constants.py`:
    - Add `COLLECTION_BACKTEST_ORDERS = "backtest_orders"`
    - Add `COLLECTION_BACKTEST_TRADES = "backtest_trades"`
    - Rename `COLLECTION_OPTIMIZATION_RUNS` → `COLLECTION_BACKTEST_OPTIMIZATION_RUNS` (value `"backtest_optimization_runs"`)
  - `packages/pocketquant-backtest/src/pocketquant/backtest/persistence/backtest_repository.py`:
    - Remove embedded-array references in `save`/`get` (handled by entities.py change)
    - Add `delete_run_cascade()`
    - Update `delete_by_strategy` to cascade
  - `packages/pocketquant-backtest/src/pocketquant/backtest/persistence/optimization_repository.py`:
    - Switch to `COLLECTION_BACKTEST_OPTIMIZATION_RUNS`
  - `packages/pocketquant-backtest/src/pocketquant/backtest/persistence/__init__.py`:
    - Export `OrderRepository`, `TradeRepository`
  - `packages/pocketquant-backtest/src/pocketquant/backtest/domain/entities.py`:
    - `BacktestResult` drop `trades: list[Fill]`, `positions: list[Trade]`; add `open_positions: list[OpenLot]`
    - Update `to_mongo()`/`from_mongo()`
  - `packages/pocketquant-api/src/pocketquant/api/di/persistence.py`:
    - Add `OrderRepository`, `TradeRepository` to auto-resolved list (line 51 area)
  - App startup hook (search for current `ensure_indexes` callers):
    - Add `OrderRepository.ensure_indexes()` + `TradeRepository.ensure_indexes()` calls
- **Delete:** none

## Implementation Steps

1. Update `constants.py`: add 2 new, rename 1 existing constant. Grep project for all `optimization_runs` string usages — must zero out.
2. Create `order_repository.py` per spec above; copy index pattern from `backtest_repository.py:248-277`.
3. Create `trade_repository.py` similarly.
4. Modify `BacktestResult` dataclass in `entities.py`:
   - Remove `trades: list[TradeRecord]`, `positions: list[PositionRecord]` fields
   - Add `open_positions: list[OpenLot]`
   - Update `to_mongo`/`from_mongo`
5. Modify `BacktestRepository`:
   - Inject `OrderRepository` + `TradeRepository` via constructor (optional — could keep flat and rely on caller)
   - **Recommend:** keep `BacktestRepository` flat (no injection); cascade-delete logic lives in app-service or a small `BacktestUnitOfWork` helper. KISS.
   - Add `delete_run_cascade(run_id, order_repo, trade_repo)` static-style or just orchestrate in app-service
6. Update `OptimizationRepository` to use new constant.
7. Update `persistence/__init__.py` exports.
8. Update DI `persistence.py` provider to register new repos.
9. Update startup `ensure_indexes` chain (find via grep: `ensure_indexes` callers).
10. Verify with `python -m compileall packages/pocketquant-backtest/src packages/pocketquant-api/src`.
11. Run existing tests (`pytest packages/pocketquant-backtest/tests/`) — they may break because `BacktestResult` shape changed. Fix or defer to Phase 4.

## Decision Point — Unit of Work pattern

Cascade delete + atomic save of (run + orders + trades) raises consistency Q. Options:
- **A. App-service orchestrates** (no UoW; KISS) — Phase 4 result_collector calls 3 repos in sequence. Risk: partial failure leaves orphans.
- **B. BacktestUnitOfWork helper** — wraps the 3 writes in a session; Mongo transaction across collections.
- **C. Cleanup job** — out-of-band repair runs daily.

**Recommend A** for MVP. Single-run failures are rare; daily cleanup script can be added later if it matters. Document in run logs.

## Success Criteria

- [ ] 4 collections defined in `constants.py`; legacy `optimization_runs` removed; grep returns zero hits
- [ ] `OrderRepository` + `TradeRepository` created, each <200 lines
- [ ] `ensure_indexes()` of each new repo creates the documented indexes (verify via `db.collection.getIndexes()` after startup)
- [ ] `BacktestResult` no longer carries `trades`/`positions` arrays
- [ ] `OptimizationRepository` reads/writes `backtest_optimization_runs`
- [ ] DI `persistence.py` registers both new repos; container can resolve them at app boot
- [ ] `python -m compileall` of both packages succeeds

## Risk Assessment

- **Renaming `optimization_runs` breaks prod read path:** Migration (Phase 5) renames the existing collection. Until migration runs, code points to `backtest_optimization_runs` which doesn't exist. Mitigation: deploy migration FIRST, then code switch. **OR** keep dual-read for one release. **Recommend: deploy together; document deploy order in Phase 5.**
- **No transaction across collections:** Partial save (run saved but orders fail) leaves orphan run. Mitigation: write in order (orders first → trades → run); if run fails, orders/trades still useful for debugging. Accept; doc in code.
- **Index creation cost on prod:** Adding 4+5 new indexes on ~existing collections. New collections start empty so trivial. Acceptable.
- **DI auto-resolution requires `BaseRepository` inheritance:** Confirm `OrderRepository`/`TradeRepository` follow the BaseRepository pattern with the right constructor signature.
