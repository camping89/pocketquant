# Backtest Trades Paging + Server-Side Analytics

**Date**: 2026-07-02 22:07
**Severity**: High
**Component**: Backend / Web / Backtest Trades Tab
**Status**: Completed

## What Happened

Completed a feature refactor of the Trades tab on the backtest page (`/backtest?run=<id>`). Before: load all trades at once, compute stats client-side → UI lag + BE overload. After: server-side paging (keyset cursor, `.allow_disk_use(True)`), dedicated `BacktestStatsService`, infinite scroll + virtualized table, chart selection stable across paging. Commit `504e276` (code), CI/CD workflow + Playwright automation 5/5 pass on prod.

## The Brutal Truth

The Trades tab was the bottleneck: load 10K+ trades → FE parsing + compute histogram/streak/PF/drawdown → DOM render → every re-sort recalculates everything. On large runs (3-4K trades), this tab froze for 3-4 seconds. Chart selection broke when the user re-sorted/filtered because selection tracking used the array index (when paging changed, the index mismatched → clicking the wrong trade).

On top of that, dropping client-side stats without being sure the backend was perfect → had to code-review the keyset cursor logic, tie-break, datetime decode carefully (3 things easy to get wrong).

## Technical Details

**Backend changes (`src/pocketquant/backtest/backtest_stats_service.py`):**
- New `BacktestStatsService`: gathers all analytics queries + aggregation (paged + aggregate modes).
- Domain calculator `trade_stats_calculator.py`: histogram/streaks/profit-factor/max-drawdown (pure functions, testable separately).
- Repository extended: `list_by_run_paged(run_id, sort_by, direction, cursor, limit)` keyset cursor, tie-break `_id`; `count_by_run`, `sum_pnl_by_run`, `list_markers_by_run`.
- Endpoint changes:
  - `GET /{run_id}/trades`: `{trades: [...]}` → `{items, next_cursor, has_more, total, total_pnl}` (paged contract)
  - New `GET /{run_id}/trades/markers`: trades used to draw markers on the chart (trade_id, entry_exit signals)
  - New `GET /{run_id}/stats`: histogram/streaks/profit-factor/drawdown (top-level aggregate, not recomputed per page)
- Added index `ix_bttrades_run_pnl` to tie-break when sorting by `pnl`.
- Removed the `BacktestQueryService.list_trades` endpoint.

**Keyset cursor design:**
```
cursor = Base64Encode({v: "1", id: <trade_id>, <sort_field>: <value>})
```
- `v`: version (upgrade-safe)
- Opaque: client doesn't decode
- Tie-break `_id`: ordering deterministic when `pnl` (or another sort field) has duplicates
- Footer aggregate (total/total_pnl) computed only on the first page (`cursor is None`), skipped on later pages (optimization).

**Frontend changes:**
- Infinite scroll + `@tanstack/react-virtual` (row virtualization, 50-100 rows visible at a time).
- Filter/sort server-side → `useInfiniteQuery` from `@tanstack/react-query`.
- Selection from array index → **trade_id (UUIDv7)**: click a trade → highlight the row + draw box/info on the chart, durable across page changes.
- Removed `stats-utils.ts` (client-side histogram/streak/PF/drawdown) → consume the `GET /stats` endpoint.
- Open Positions tab separated (not mixed into the Trades tab).

**Verify scope:**
- Backend: 110 tests pass (trade_stats_calculator, repository keyset, service paging)
- Web: 32 tests pass (infinite scroll, cursor decode, selection stable)
- Lint: ruff/pyright/eslint/tsc all clean
- import-linter: 7/7 contracts KEPT
- OpenAPI + route snapshot regenerated
- Code-review (code-reviewer): keyset sound, stats parity exact
- Fix: `git rm -f stats-utils.ts` (zsh `-i` alias prompt swallowed in a non-interactive shell)
- Automation: Playwright 5/5 pass on prod (contract + UI + virtualization)

## What We Tried

1. **Offset pagination**: simple, but cursor-less paging = instability when the user sorts mid-scroll (rows added/removed).
   - Switched: keyset cursor (deterministic) ✓

2. **Client-side stats (histogram/streaks)**: no extra BE load, intuitive.
   - Problem: 10K+ items → O(n) recalc per filter/sort; UI freeze 3-4s on large runs.
   - Switched: server-side stats, cached in BE memory ✓

3. **Selection by array index**: simple, works when the table is static.
   - Problem: paging changes → index mismatch → clicking the wrong trade; chart selection lost.
   - Switched: stable UUID (trade_id) ✓

4. **MongoDB aggregate pipeline iterate (no `.allow_disk_use`)**: memory-efficient for small pipelines.
   - Problem: >32MB pipeline spill → memory OOM risk, abandon
   - Switched: `.allow_disk_use(True)` (MDB 3.2+) ✓

5. **Footer aggregate (total/total_pnl) per page**: consistency, user expects it
   - Problem: redundant calculation per cursor → wastes query time.
   - Switched: compute only the first page (that's what the user sees), skip on later pages ✓

## Root Cause Analysis

**Why the UI lagged:**
- FE loading 10K trades alone = parse JSON + DOM render (acceptable).
- But client-side stats (histogram binning, streak detect) = O(n) each time → the actual bottleneck.
- Virtualization without paging = memory in the DOM still large → React reconciliation slow.

**Why selection broke:**
- Table rendering without a stable key (using the array index) = React key warnings all around; swap/reorder rows → old key maps to a new item → selection stale.
- Keyset cursor paging = row order changes when sorting/filtering → the index no longer makes sense.

**Why the zsh `rm -i` prompt was hidden:**
- zsh aliases `rm` to `rm -i` (interactive) to prevent accidental deletion.
- But a non-interactive shell (CI, script) has stdin=null → what input does the prompt get? → the prompt defaults to cancel (the file isn't deleted).
- Tests only ran on dev (stdin=tty) so they passed, production wasn't tested, stats-utils.ts still existed.
- Fix: use `git rm -f` (always force-deletes a tracked file) instead of `rm`.

## Lessons Learned

1. **Keyset cursor = deterministic paging.** Offset is unstable when data changes mid-scan; keyset tie-break (`_id`) guarantees order + repeatability.

2. **Stable selection keys (UUID > index).** If the user can re-order/filter the table, selection must use a domain ID, not the array position.

3. **Virtualization must go with paging.** Row virtualization without paging = small DOM but huge data in memory. Improvement is slow if only handled on the FE.

4. **Stats centralization (BE > FE).** When stat logic is complex + recalculated per filter, BE takes charge. FE consumes the endpoint. DDD: encapsulate domain logic (`trade_stats_calculator`) in the domain layer, app-service exposes it.

5. **Non-interactive shell ≠ interactive dev.** The `rm -i` prompt works in a terminal (stdin=tty) but CI/script → input silently ignored. Git rm / bash set -e / explicit error check protect against this.

6. **PyMongo async pitfall: coroutine must be awaited before iterating.** `collection.aggregate(pipeline)` returns a coroutine; `async for doc in agg_coro` = error. Must `await` or use `async_command_cursor`.

## Next Steps

- [x] Code reviewed + fixed (keyset sound, stats exact, zsh rm issue gone)
- [x] Tests pass (backend 110, web 32)
- [x] Shipped & deployed (commit `504e276`, prod `/backtest?run=...`)
- [x] Automation verified (Playwright 5/5)
- [ ] **Monitor prod:** lag metric on tab Trades, cursor stability after sort/filter
- [ ] **Update docs:** keyset cursor pattern + stable selection guideline → `docs/code-standards.md` (reference for future pagination)
- [ ] **Optional:** if future tabs hit same paging + stats issue, reuse `BacktestStatsService` pattern (already modular)

**Owner**: Backend (stats service) + Web (infinite scroll). Ready production.

**Timeline**: Completed 2026-07-02 22:07. Code `504e276` shipped, CI/CD + live tests pass.
