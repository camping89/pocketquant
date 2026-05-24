# scripts/

One-off operational scripts. Run from repository root.

## one_time_consolidate_exchange_into_symbol.py

One-time migration: consolidate the legacy `(symbol, exchange)` field pair into a single composite `symbol` field (`{CODE}:{EXCHANGE}`, e.g. `BTCUSDT:BINANCE`) across all collections.

Idempotent: re-running on already-migrated data is a no-op. Drops legacy compound indexes that reference `exchange`, creates new indexes on composite `symbol`.

### Usage

```bash
# Dry-run against all collections (safe; read-only)
uv run python scripts/one_time_consolidate_exchange_into_symbol.py --dry-run

# Migrate a single collection (real write)
uv run python scripts/one_time_consolidate_exchange_into_symbol.py --collection bars

# Tune batch size for large collections
uv run python scripts/one_time_consolidate_exchange_into_symbol.py --batch-size 2000

# Override connection details
uv run python scripts/one_time_consolidate_exchange_into_symbol.py \
    --mongo-uri mongodb://localhost:27017 --db-name pocketquant
```

Defaults pull `MONGO_URI` + `MONGO_DB` from environment.

### Recommended run order (production)

1. **Snapshot DB** (mongodump or volume snapshot).
2. **Stop FE deploy** so no new pre-migration writes arrive after the cut.
3. **Dry-run all** — confirm doc counts + intended changes:
   ```
   uv run python scripts/one_time_consolidate_exchange_into_symbol.py --dry-run
   ```
4. **Real run small collections first** (validates logic, fast):
   ```
   uv run python scripts/one_time_consolidate_exchange_into_symbol.py --collection symbols
   uv run python scripts/one_time_consolidate_exchange_into_symbol.py --collection tracked_symbols
   uv run python scripts/one_time_consolidate_exchange_into_symbol.py --collection sync_status
   uv run python scripts/one_time_consolidate_exchange_into_symbol.py --collection strategy_subscriptions
   uv run python scripts/one_time_consolidate_exchange_into_symbol.py --collection orders
   uv run python scripts/one_time_consolidate_exchange_into_symbol.py --collection positions
   uv run python scripts/one_time_consolidate_exchange_into_symbol.py --collection strategies
   uv run python scripts/one_time_consolidate_exchange_into_symbol.py --collection backtest_runs
   uv run python scripts/one_time_consolidate_exchange_into_symbol.py --collection optimization_runs
   ```
5. **Real run bars last** (largest):
   ```
   uv run python scripts/one_time_consolidate_exchange_into_symbol.py --collection bars
   ```
6. **Verify zero residuals**: per-collection log line `residual=0` (no docs with legacy `exchange` field).
7. **Deploy FE**.

### Safety notes

- Run from a secure ops host; never a laptop.
- Script uses unordered bulk writes — partial failures don't abort the batch.
- Script ignores docs without both legacy fields (logs `WARN` and skips) — re-run after debugging incomplete records.
- Cursor uses `no_cursor_timeout=True` — large collections complete without server-side cursor death; ensure connection stays alive.

## Other scripts

- `audit_bar_quality.py` — diagnostic, no writes.
- `backfill_1m_from_binance.py` — backfill missing 1m bars.
- `backfill_regression_window.py` — backfill specific date ranges.
- `check_env.py` — environment sanity check.
- `resync_2y_from_binance.py` — resync 2-year history per symbol.
