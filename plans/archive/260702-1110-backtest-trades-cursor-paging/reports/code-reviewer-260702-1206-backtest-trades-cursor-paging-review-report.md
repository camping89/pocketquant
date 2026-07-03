# Code Review — Backtest Trades Cursor Paging + Server-side Stats

Scope: BE `BacktestStatsService` + `trade_stats_calculator` + `BacktestTradeRepository` keyset paging + route contract change; FE paged/virtualized trades table, chart selection by `trade_id`, BE-driven histograms/streaks/PF/drawdown, Open Positions tab.

Verification run: 27 new BE tests pass · full backtest+persistence suite 101 pass · baseline snapshots 9 pass · web 40 tests pass · web `lint` 0 errors (6 pre-existing warnings) · `tsc -b && vite build` clean · pyright 0 errors on changed BE files · import-linter 7/7 KEPT.

## Summary

Implementation is largely correct and well-tested. Keyset cursor is sound (total ordering with `_id` tie-break, correct sort/cursor coupling, type-aware datetime decode). Stats parity with the deleted FE oracle is exact for histogram, streaks, PF, and drawdown. Public contract change is intentional and propagated; snapshots regenerated. **One blocker: the FE `stats-utils.ts` + its test were NOT actually deleted** — they remain on disk, tracked, and dead. Two performance findings and a few nits below.

---

## Blocker

### B1 — `stats-utils.ts` + `stats-utils.test.ts` still present (dead code + phantom test)
The task states "client `stats-utils.ts` + its test deleted." Both files still exist, are git-tracked, and unchanged from HEAD:
- `web/src/components/backtest/stats-utils.ts`
- `web/src/components/backtest/stats-utils.test.ts`

No production module imports `stats-utils` (grep: only the test imports it). Consequences:
1. Acceptance claim is false — deletion never happened.
2. `stats-utils.test.ts` runs as part of the 40 passing web tests but validates a module no longer wired into the app — a phantom test that will silently drift from the BE calculator (the new source of truth), defeating the centralization.
3. Dead code invites future edits against the wrong implementation.

Fix: `git rm web/src/components/backtest/stats-utils.ts web/src/components/backtest/stats-utils.test.ts`, re-run `npm run build && npm run test`.

---

## High

### H1 — `count_by_run` + `sum_pnl_by_run` recomputed on every page fetch
`BacktestStatsService.list_trades_paged` issues `count_documents` + `$sum` aggregation on **every** page (`backtest_stats_service.py:216-217`). The FE only reads `total`/`total_pnl` from `pages[0]` (`positions-tab.tsx:30-31`), so for every `fetchNextPage` beyond the first, both full-collection scans run and are discarded. For a filtered run with N pages this is N redundant count+sum passes.

Impact: bounded but real; scales with page count × trade count. Options: (a) accept (runs are operator-scale) and document; (b) compute totals only when `cursor is None` (first page) and return `total=-1`/`total_pnl=0.0` sentinels on later pages that the FE ignores; (c) FE stops re-reading. Recommend (b) or documenting (a) as accepted.

### H2 — Non-indexed sort keys trigger in-memory sort (32MB cap risk)
Compound indexes exist only for `(run_id, entry_time)` and `(run_id, pnl)`. Sorting by `quantity`, `entry_price`, `exit_price`, `commission`, `direction`, or `status`(→`exit_time`) filters on `run_id` (`ix_bttrades_run_id`) then does a blocking in-memory sort on `(field, _id)`. Mongo aborts non-indexed sorts exceeding 32MB. A large run (thousands of trades) sorted by one of these columns can fail the query outright.

Impact: correctness failure (500) under scale on the less-common sort columns. Options: accept for operator-scale runs (document the limit), or add `allowDiskUse` on the find (PyMongo `find(...).allow_disk_use(True)`), or index the remaining sort columns. Recommend documenting the accepted scale ceiling if runs stay small; otherwise `allow_disk_use(True)`.

---

## Medium

### M1 — Duration histogram drops the FE's `h >= 0 && isFinite` guard
Old FE `DurationHistogram` filtered `hours.filter(h => isFinite(h) && h >= 0)`; BE `get_stats` passes `t.duration_seconds / 3600` straight through with no guard (`backtest_stats_service.py:248`). Verified `duration_seconds = (exit_time - entry_time).total_seconds()` at trade creation (`result_collector.py:262`), and backtest replay is chronological so durations are always non-negative and finite. Parity holds in practice; the missing guard is only a latent divergence if a malformed/negative `duration_seconds` ever lands in storage. Low real risk — noting for awareness, not a required fix.

---

## Low / Nit

- **N1** — `get_stats` fetches the full closed-trade list into memory (`list_by_run`) to compute PnL/duration/streak/PF. Fine at operator scale; if runs grow large this is the same unbounded-load pattern the paging change set out to avoid on the read side. Streaks/PF are inherently sequential so this is hard to avoid, but histograms + PF could be pushed to an aggregation pipeline later if needed. Not required now.
- **N2** — `TradeDto.exit_time: str | None` and `TradeMarkerDto.exit_time: str | None` are nullable, but `Trade.exit_time` is a non-nullable `datetime` (closed trades only). The nullable typing is harmless (always populated) and lets the FE `TradeRow`/`fmtDuration` "Open" branch stay generic, but it slightly overstates the contract. Cosmetic.
- **N3** — `positions-table.tsx` renders the sortable "Status" column showing "Closed"/"Open" (`t.exit_time ? 'Closed' : 'Open'`), but the paged endpoint only ever returns closed trades, so it is always "Closed". Harmless; the `status` sort key sorts by `exit_time`, which is a reasonable proxy. Consider dropping the column or the sort affordance if it confuses.
- **N4** — `open-positions-tab.tsx` uses array index as React `key` (`key={i}`). Open lots are a small static run-end list (no reorder/paging), so acceptable, but a stable key (e.g. `entry_order_id`) would be cleaner.

---

## Acceptance Criteria Verdict

| Criterion | Status |
|---|---|
| Trades page via keyset cursor, infinite scroll, virtualized | MET — `useVirtualizer` + `useInfiniteQuery`, only visible rows in DOM, `onReachEnd` drives `fetchNextPage` |
| Filter/sort apply to FULL dataset server-side | MET — filter→`pnl_filter` clause, sort→`_SORT_FIELDS`, query keyed by sort/filter so change restarts keyset walk |
| Click trade on any page → box + scroll; hover → outline; via stable `trade_id` | MET — selection is `TradeRow` object, box drawn only for click/hover, scroll driven by highlight only, `highlightKind` replaces index |
| Markers (BUY/SELL) for EVERY trade from `/trade-markers` | MET — `useBacktestMarkers` → `list_markers_by_run` (all trades), deduped per candle time |
| Histograms/streaks/PF/drawdown from BE stats, parity with FE | MET — exact parity (see below); consumers switched to `HistogramBin[]`/`DrawdownPeriod[]` props |
| Open positions in own tab | MET — `OpenPositionsTab`, `open` filter chip removed |
| No regression: overview/risk/orders/verdict/history/poll | MET — `run-compare-view` untouched by shape change, verdict PATCH + poll-until-finished intact |

## Stats Parity (BE calculator vs deleted FE oracle) — EXACT

- **histogram**: empty→[], degenerate (min==max)→single bin, top-edge clamp `min(bin_count-1, int/floor((v-lo)/width))`. `int()`==`Math.floor` here since `v-lo >= 0` always. Match.
- **streaks**: `>0` win / `<0` loss / `==0` reset both. FE skipped open positions (`exit_time==null`) which were appended after closed trades; BE reads only closed trades in `entry_time ASC` — equivalent stream. Match.
- **profit_factor_by_direction**: `pnl>=0`→profit, else `abs`→loss; `loss>0 ? profit/loss : None`. Match.
- **drawdown_periods**: open on `<0`, track deepest, close on `>=0` with recovery=that point, unrecovered tail→`recovery_time=None`, sort by depth ascending (deepest first), top-N. Match. FE fed closed trades in same order.

Note: FE fed streaks/PF over `entry_time ASC` closed trades (old `/trades`→`list_by_run` ASC, opens appended+skipped). BE `get_stats` reads `list_by_run` (ASC). Order-equivalent.

## Keyset Cursor Correctness — SOUND

- Total ordering: sort `[(field, dir), ("_id", dir)]`; cursor predicate `(field op v) OR (field==v AND _id op id)`. No drop/dup on ties (repo tests `test_paged_walks_all_trades_without_gaps`, `test_paged_keyset_stable_on_equal_sort_value` confirm).
- Sort/cursor coupling: `_encode_cursor(trades[-1], sort_key)` always uses the active sort key; `_sort_value` maps `status`→`exit_time` matching repo `_SORT_FIELDS`. Correct.
- Type safety: datetime keys (`entry_time`, `status`→`exit_time`) encoded ISO / decoded via `fromisoformat`; numeric/string keys pass through JSON untouched. `_DATETIME_SORT_KEYS={"entry_time","status"}` correct. No int/float mismatch (domain fields are float).
- Precision: cursor built from round-tripped (Mongo millis-truncated) trade, so no microsecond drift vs stored value.
- `_id` compared as UUIDv7 **string** (lexicographic) consistently in both sort and predicate.
- `next_cursor` emitted only when `has_more and trades`; FE `getNextPageParam` stops on `has_more=false`. No phantom empty page at exact `total % limit == 0` boundary.

## Contract / Propagation — OK

- `/trades` `{trades:[...]}`→`{items,next_cursor,has_more,total,total_pnl}`: intentional, only consumer was `backtest-api.ts` (verified; `run-compare-view` untouched).
- `run.positions`→`run.open_positions`: only closed-trade join removed; opens still inline. No other consumer.
- New `/trade-markers`, `/stats` in route inventory snapshot; OpenAPI snapshot regenerated (+177 lines; routes return `dict` so body schema not detailed — pre-existing style). Baseline tests pass.
- `BacktestQueryService.list_trades` removed; no callers remain; ctor arg drop is DI-autowired (no manual call sites).

## Unresolved Questions

1. H1/H2: are backtest runs bounded small enough (few hundred trades) that recomputed totals-per-page and non-indexed in-memory sorts are acceptable? If runs can reach thousands, H2 becomes a correctness failure on 6 of 9 sort columns.
2. Was omitting the FE `stats-utils` deletion intentional (kept for reference) or an oversight? If reference, it should at least be un-imported-from-tests and marked, but the cleaner move is deletion (B1).

---

Status: DONE_WITH_CONCERNS
Summary: Feature is correct and fully tested (keyset + stats parity verified, all gates green), but the FE `stats-utils.ts`/test deletion was never performed (blocker: dead code + phantom test), plus two scale-dependent performance findings.
