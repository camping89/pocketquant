---
phase: 5
title: "One-time idempotent migration script"
status: pending
priority: P2
effort: "0.5d"
dependencies: [3]
---

# Phase 5: One-time idempotent migration script

## Overview

Write one-time idempotent migration script that:
1. **Backups** legacy `backtest_runs` and `optimization_runs` to `*_backup_YYMMDD` collections (pre-migration safety net)
2. **Reconstructs** `backtest_orders` documents from each old run's embedded `trades[]` array (those are fills under old naming)
3. **Reconstructs** `backtest_trades` documents from each old run's embedded `positions[]` array (round-trips with exit_time != null)
4. **Slims** `backtest_runs` documents: remove `trades[]` + `positions[]`; add `open_positions[]` from old `positions[]` where exit_time is null
5. **Renames** collection `optimization_runs` → `backtest_optimization_runs` (Mongo rename + ensure_indexes on new name)
6. **Verifies** post-run with `residual_count`: legacy fields gone, doc counts match expectations

Follow proven pattern from commit `9213c1e` script (`scripts/one_time_consolidate_config_snapshot_symbol.py`).

## Requirements

- Functional: Idempotent — re-run is no-op (skip-flag check before each per-doc operation)
- Functional: Dry-run flag — print plan, don't write
- Functional: Backup before write; backup retention is operator concern
- Functional: Two phases per run document: (a) extract orders+trades into new collections, (b) slim run doc
- Functional: Rename `optimization_runs` only if non-empty; if empty, just drop+create
- Non-functional: Batch writes (bulk_write 500-1000 ops)
- Non-functional: Logging — `migration_starting`, `run_processed`, `orders_extracted`, `trades_extracted`, `slimmed`, `done`, `residual_check` events
- Non-functional: Script ships in Docker image (Dockerfile already COPYs `scripts/` per commit `dfd873d`)

## Architecture

### Reconstruction rules

**Old `trades[]` (fills) → reconstruct `backtest_orders`:**
- Old `TradeRecord` shape: `{order_id, symbol, side: "BUY"|"SELL", quantity, price, commission, pnl, timestamp, sl_price?, tp_price?}`
- For each, create one `backtest_orders` doc with:
  - `_id = order_id` (use existing)
  - `run_id = run._id`
  - `strategy_id = run.strategy_id`
  - `symbol = run.config_snapshot.symbol`
  - `side = fill.side`
  - `order_type = "MARKET"` — assumption (old strategies were MARKET-only). Document this assumption.
  - `quantity = fill.quantity`
  - `price = null` (MARKET orders don't carry limit price)
  - `sl_price = fill.sl_price`, `tp_price = fill.tp_price`
  - `status = "FILLED"`
  - `submitted_at = fill.timestamp`, `last_updated_at = fill.timestamp`
  - `events = [{timestamp: fill.timestamp, from_status: null, to_status: "SUBMITTED", reason: "migrated"}, {timestamp: fill.timestamp, from_status: "SUBMITTED", to_status: "FILLED", reason: "migrated"}]`
  - `fills = [{fill_id: generated, timestamp: fill.timestamp, qty: fill.quantity, price: fill.price, commission: fill.commission, slippage: 0}]`
  - `resulting_trade_id = null` (linked later if matched)

**Old `positions[]` → reconstruct `backtest_trades` (closed) + `open_positions` (still open):**
- Old `PositionRecord` shape: `{symbol, direction, entry_price, entry_time, quantity, sl_price?, tp_price?, exit_price?, exit_time?, pnl, commission, direction?}`
- IF `exit_price != null` AND `exit_time != null` → CLOSED → create `backtest_trades` doc:
  - `_id = generated`
  - `run_id, strategy_id, symbol, direction`
  - `entry_order_id = null` — cannot reconstruct order ID from PositionRecord (no field); backfill nullable. Document this loss of information.
  - `entry_price, entry_time, quantity`
  - `exit_order_id = null` — same
  - `exit_price, exit_time`
  - `sl_price, tp_price`
  - `pnl, commission`
  - `duration_seconds = (exit_time - entry_time).total_seconds()`
- IF `exit_price == null` → OPEN → keep in slimmed run doc's `open_positions[]`:
  - `OpenLot` shape: `{symbol, direction, entry_price, entry_time, quantity, sl_price, tp_price, entry_order_id: null, entry_commission_portion: commission}`

**Slim `backtest_runs` doc:**
- Remove fields: `trades`, `positions`
- Add field: `open_positions` (list of OpenLot from above)

### Idempotency markers

Approach: doc-level marker on run document, e.g.:
```js
{ "_migration": { "v2_storage_split": { "completed_at": ISODate, "orders_extracted": 12, "trades_extracted": 6, "open_positions": 1 } } }
```
At each run-doc visit:
1. If marker present + completed → skip
2. Else if marker present + partial → resume from where it left off (re-extract orders if not done, etc.)
3. Else → fresh run

For collection rename (`optimization_runs` → `backtest_optimization_runs`):
- Check destination existence; if non-empty → skip (already migrated)
- Else execute Mongo `renameCollection` (atomic in same DB)

### Backup strategy

```python
async def _backup_collection(src: str, dst: str) -> int:
    """Copy src to dst (drops dst if exists; warn if dst non-empty)."""
    db = self._db
    if await db[dst].count_documents({}) > 0:
        logger.warning("backup_dst_non_empty", dst=dst)
        return 0
    docs = []
    async for doc in db[src].find({}):
        docs.append(doc)
    if docs:
        await db[dst].insert_many(docs)
    return len(docs)
```

`dst` name: `f"{src}_backup_{datetime.utcnow():%y%m%d}"`. E.g., `backtest_runs_backup_260524`.

### Migration entrypoint

```python
# scripts/one_time_split_backtest_collections.py

async def main(dry_run: bool = False, batch_size: int = 100):
    settings = Settings()
    db = await connect_database(settings)

    logger.info("migration_starting", dry_run=dry_run)

    # 1. Backup
    if not dry_run:
        backed_up = await _backup_collection(db, "backtest_runs", f"backtest_runs_backup_{today_yymmdd()}")
        logger.info("backup_complete", source="backtest_runs", count=backed_up)
        backed_up_opt = await _backup_collection(db, "optimization_runs", f"optimization_runs_backup_{today_yymmdd()}")
        logger.info("backup_complete", source="optimization_runs", count=backed_up_opt)

    # 2. Per-run extraction + slim
    cursor = db["backtest_runs"].find({"_migration.v2_storage_split.completed_at": {"$exists": False}})
    processed = 0
    async for run_doc in cursor:
        await _migrate_run(db, run_doc, dry_run)
        processed += 1
        if processed % 10 == 0:
            logger.info("progress", processed=processed)

    # 3. Optimization rename
    if not dry_run:
        await _rename_optimization_collection(db)

    # 4. Residual verification
    residuals = await _verify(db)
    logger.info("migration_done", processed=processed, residuals=residuals)
    if residuals["legacy_field_count"] > 0:
        logger.error("migration_residual_nonzero")
        sys.exit(1)
```

### Per-run extraction

```python
async def _migrate_run(db, run_doc, dry_run):
    run_id = run_doc["_id"]
    if run_doc.get("_migration", {}).get("v2_storage_split", {}).get("completed_at"):
        return  # idempotent skip
    fills_to_orders = _convert_fills(run_doc.get("trades", []), run_doc)
    closed_trades, open_lots = _convert_positions(run_doc.get("positions", []), run_doc)
    if dry_run:
        logger.info("would_migrate", run_id=run_id, orders=len(fills_to_orders), trades=len(closed_trades), open=len(open_lots))
        return
    # Idempotent collection insert: ordered=False so duplicates skip (orders/trades may already exist if partial)
    if fills_to_orders:
        try: await db["backtest_orders"].insert_many(fills_to_orders, ordered=False)
        except BulkWriteError as e: logger.warning("partial_order_insert", run_id=run_id, errors=len(e.details))
    if closed_trades:
        try: await db["backtest_trades"].insert_many(closed_trades, ordered=False)
        except BulkWriteError as e: logger.warning("partial_trade_insert", run_id=run_id, errors=len(e.details))
    # Slim run doc
    await db["backtest_runs"].update_one(
        {"_id": run_id},
        {
            "$set": {
                "open_positions": open_lots,
                "_migration.v2_storage_split": {
                    "completed_at": datetime.utcnow(),
                    "orders_extracted": len(fills_to_orders),
                    "trades_extracted": len(closed_trades),
                    "open_positions": len(open_lots),
                }
            },
            "$unset": {"trades": "", "positions": ""}
        }
    )
```

### Residual verification

```python
async def _verify(db) -> dict:
    return {
        "legacy_field_count": await db["backtest_runs"].count_documents({"$or": [{"trades": {"$exists": True}}, {"positions": {"$exists": True}}]}),
        "unmigrated_count": await db["backtest_runs"].count_documents({"_migration.v2_storage_split.completed_at": {"$exists": False}}),
        "orders_count": await db["backtest_orders"].count_documents({}),
        "trades_count": await db["backtest_trades"].count_documents({}),
        "optimization_legacy_exists": "optimization_runs" in await db.list_collection_names(),
    }
```

## Related Code Files

- **Create:**
  - `scripts/one_time_split_backtest_collections.py`
  - `scripts/tests/test_one_time_split_backtest_collections.py`
- **Modify:**
  - `scripts/README.md` (if exists) — add invocation instructions
  - Production runbook reference — add deploy step (depends on team process; ack with user)
- **Delete:** none

## Implementation Steps

1. Read reference migration `scripts/one_time_consolidate_config_snapshot_symbol.py` (180 lines) — mimic shape: CLI args (`--dry-run`, `--batch-size`), `Settings` load, logger, connect, main loop.
2. Implement `_convert_fills(old_trades, run_doc) -> list[order_doc]`.
3. Implement `_convert_positions(old_positions, run_doc) -> (closed_trade_docs, open_lots)`.
4. Implement `_migrate_run` per-doc handler with idempotency marker.
5. Implement `_backup_collection`.
6. Implement `_rename_optimization_collection`:
   - If `optimization_runs` exists and `backtest_optimization_runs` doesn't: `await db.command({"renameCollection": "your_db.optimization_runs", "to": "your_db.backtest_optimization_runs"})` (admin DB cmd)
   - Then call `OptimizationRepository.ensure_indexes()` to rebuild
7. Implement `_verify` post-check.
8. Write test in `scripts/tests/`: spin testcontainers MongoDB → seed 3 fixture old-shape `backtest_runs` docs → run migration → assert counts, fields removed, marker added, re-run is no-op.
9. Add `--validate-only` flag that runs `_verify` against current DB without changes (useful for monitoring).
10. Manual verify on staging: dry-run → real-run → re-run (must be no-op) → verify residuals=0.

## Deploy order

Per Phase 3 risk note: code switch + migration must coordinate. Recommend:
1. **Deploy code with feature flag** — new repos exist, but reads still tolerate old shape (transitional read path in `BacktestRepository.get`/`find_doc_by_subscription` for `trades`/`positions` fallback).
2. **Run migration in dry-run** on prod connection → review log output.
3. **Run migration for real** → verify residuals=0.
4. **Drop feature flag** in next deploy → reads strict-new.

Alternative (simpler): hard cutover deploy. Backup gives rollback if catastrophic. Recommend hard cutover for 22 docs — minimal downside.

## Success Criteria

- [ ] Migration script created at `scripts/one_time_split_backtest_collections.py`
- [ ] Test in `scripts/tests/test_one_time_split_backtest_collections.py`: 3 fixture runs migrated → counts correct; re-run is no-op
- [ ] Dry-run on prod logs all 22 runs as "would_migrate" with no DB writes
- [ ] Real run on prod: residuals=0; backup collections created; markers set; `optimization_runs` renamed
- [ ] Re-run of script on prod: zero changes (idempotent confirmed)
- [ ] `db.backtest_runs.findOne({})` shows no `trades` / `positions` arrays; only `open_positions` if any
- [ ] `db.backtest_orders.estimatedDocumentCount()` matches sum of old `trades.length` across all runs
- [ ] `db.backtest_trades.estimatedDocumentCount()` matches sum of CLOSED `positions` across all runs

## Risk Assessment

- **Backup collection grows DB size:** 22 docs × ~50KB ≈ 1.1MB. Trivial.
- **Reconstruction lossy on order_id linkage:** Old PositionRecord has no order_id reference; `backtest_trades.entry_order_id` and `exit_order_id` will be `null` for migrated docs. Document loud in commit message + migration log. New runs post-deploy have full linkage.
- **Migration run during active backtest:** If a `running` status doc is touched mid-extraction, partial state. Mitigation: `--exclude-running` flag (default true); only migrate `completed`/`failed` docs.
- **renameCollection requires admin perms:** Verify Mongo user has rights. Mitigation: if not, fall back to copy-then-drop.
- **Index re-creation after rename:** New `backtest_optimization_runs` needs `ensure_indexes()` re-run. Migration script must do this explicitly.
- **Lost subscription-scoped status docs:** Subscription cache docs in `backtest_runs` (with `_id = subscription_id`) lack `config_snapshot.parameters` etc. Mitigation: detect "status-only" docs (no `trades`/`positions` fields) and only set marker, don't extract.
