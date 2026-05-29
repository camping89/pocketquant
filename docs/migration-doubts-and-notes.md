# Monorepo Migration — Notes

**Date:** 2026-03-21 | **Last reviewed:** 2026-05-29 | **Status:** All migration items resolved; boot migration for strategy_id refactor shipped 2026-05-26; 1 deferred YAGNI note remains

All 7 migration concerns resolved during cleanup. See git history for details.

## Migration Complete (2026-05-26)

**Strategy ID Refactor:** 7 commits (95c64f8..c68c02c) shipped. Mongo collection renamed `strategy_subscriptions` → `subscriptions`, fields `strategy_id` → `strategy_code` (subscriptions) and `strategy_id` → `subscription_id` (orders/positions). Boot migration `migrate_strategy_id_fields()` idempotent at startup (before `ensure_all_indexes`). Subscription hash deterministic IDs stable (no change). See `docs/code-standards.md` → "Strategy ID Disambiguation" and `docs/strategy-lifecycle.md` for field mapping tables.

## Resolved (2026-05-29)

- Strategy YAML path resolution — resolved by deleting unused YAML strategy loader + `POST /strategies/load` endpoint + `pyyaml` dep (plan: `260529-1700-delete-yaml-strategy-loader`). Strategy init now flows exclusively via `STRATEGY_REGISTRY` + subscription record.

## Remaining Notes (Deferred — YAGNI)

- **`Bar.tick_count` semantics inconsistent across data sources** (decided 2026-05-07: defer per YAGNI; still deferred as of 2026-05-25).
  Three shapes coexist in the `bars` collection:
  | Source | `tick_count` written | Where |
  |---|---|---|
  | TV historical fetch | `0` (default; not set) | `tradingview_client.py:138-150` |
  | Live tick aggregation | `N` ticks ingested | `bar_builder.py:82` (`+= 1` per quote tick) |
  | Binance backfill (one-off, 2026-05-07) | `N` trades from kline index 8 | `scripts/backfill_1m_from_binance.py` |
  Side effects: `Bar.is_complete` (= `tick_count > 0`) returns `False` for completed TV-historical bars; UI/aggregations reading `tick_count` see a discontinuity at 2026-04-30 where the data source shifts. Not actionable until a feature actually depends on cross-row comparability — at which point pick a single semantic (e.g. add `trade_count`, leave `tick_count` for in-flight tick counter) and migrate.
