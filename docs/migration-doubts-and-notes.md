# Monorepo Migration — Notes

**Date:** 2026-03-21 | **Last reviewed:** 2026-05-25 | **Status:** All migration items resolved; 2 deferred YAGNI notes remain

All 7 migration concerns resolved during cleanup. See git history for details.

## Remaining Notes (Deferred — YAGNI)

- Strategy YAML path resolution uses CWD-relative — may need project-root resolution for Docker/production.

- **`Bar.tick_count` semantics inconsistent across data sources** (decided 2026-05-07: defer per YAGNI; still deferred as of 2026-05-25).
  Three shapes coexist in the `bars` collection:
  | Source | `tick_count` written | Where |
  |---|---|---|
  | TV historical fetch | `0` (default; not set) | `tradingview_client.py:138-150` |
  | Live tick aggregation | `N` ticks ingested | `bar_builder.py:82` (`+= 1` per quote tick) |
  | Binance backfill (one-off, 2026-05-07) | `N` trades from kline index 8 | `scripts/backfill_1m_from_binance.py` |
  Side effects: `Bar.is_complete` (= `tick_count > 0`) returns `False` for completed TV-historical bars; UI/aggregations reading `tick_count` see a discontinuity at 2026-04-30 where the data source shifts. Not actionable until a feature actually depends on cross-row comparability — at which point pick a single semantic (e.g. add `trade_count`, leave `tick_count` for in-flight tick counter) and migrate.
