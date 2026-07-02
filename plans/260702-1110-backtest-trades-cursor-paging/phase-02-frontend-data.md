# Phase 02 — Frontend data layer: api client + react-query infinite hooks + types

## Context

- `web/src/api/backtest-api.ts` — `fetchBacktestRun` currently does run doc + `GET /{runId}/trades` (all) + merges open_positions into `positions[]`. Types: `BacktestPosition`, `BacktestRunResult`.
- `web/src/api/api-client.ts` — `apiFetch<T>(path, params?)` builds URL + query params.
- `web/src/hooks/use-backtest-run.ts` — `useBacktestRun` (react-query), `useBacktestOrders` (lazy). `@tanstack/react-query ^5`.

## Design

Split the monolithic `fetchBacktestRun` so `positions[]` no longer carries all closed trades:

- Run doc fetch keeps: metrics, equity_curve, symbol/interval/end_date, verdict, **open_positions** (own list now, for the Open tab).
- Closed trades: new paged fetch, driven by `useInfiniteQuery`.
- Markers: separate lightweight fetch (all trades' entry/exit/direction) — feeds chart arrows.
- Stats: separate fetch — feeds histograms + drawdown table + streaks + PF.

## Files to modify

1. `web/src/api/backtest-api.ts`
   - Add types matching Phase-01 DTOs:
     - `TradeRow` (trade_id + BacktestPosition fields + duration_seconds).
     - `PagedTrades { items: TradeRow[]; next_cursor: string | null; has_more: boolean; total: number }`.
     - `TradeMarker { trade_id; entry_time; exit_time: string|null; direction }`.
     - `BacktestStats { pnl_histogram; duration_histogram; streaks; profit_factor_by_direction; drawdowns; profit_factor_all }` (bin/period shapes mirror BE).
     - `TradeSortKey`, `TradeSortDir`, `TradeFilterKey` unions.
   - `fetchBacktestTradesPage(runId, {cursor, limit, sortKey, sortDir, filter}) -> PagedTrades`.
   - `fetchBacktestMarkers(runId) -> TradeMarker[]`.
   - `fetchBacktestStats(runId) -> BacktestStats`.
   - Refactor `fetchBacktestRun`: keep run doc mapping; expose `open_positions` as `BacktestPosition[]` on the result (e.g. `open_positions` field); **remove** the all-trades fetch + merge. `positions` no longer used for the table/stats/markers — keep field only if still needed elsewhere (grep). Prefer renaming to `open_positions` to avoid stale consumers silently reading an empty array.

2. `web/src/hooks/use-backtest-run.ts`
   - `useBacktestTrades(runId, {sortKey, sortDir, filter})` → `useInfiniteQuery`:
     - `queryKey: ['backtest-trades', runId, sortKey, sortDir, filter]`.
     - `queryFn: ({pageParam}) => fetchBacktestTradesPage(runId, {cursor: pageParam, ...})`.
     - `getNextPageParam: (last) => last.has_more ? last.next_cursor : undefined`.
     - `initialPageParam: null`, `enabled: run finished`.
   - `useBacktestMarkers(runId, enabled)` → `useQuery` key `['backtest-markers', runId]`.
   - `useBacktestStats(runId, enabled)` → `useQuery` key `['backtest-stats', runId]`.
   - `useBacktestRun` stays (still polls until terminal), now returns slimmer result.

## Implementation steps

1. Grep every consumer of `run.positions` (backtest-result-view, positions-tab, pnl/duration histograms, stats-utils callers, trading-chart) — enumerate so Phase 03 rewires each.
2. Add DTO types + fetchers.
3. Add infinite + query hooks.
4. `tsc` compile clean for the data layer (UI wiring in Phase 03).

## Validation

- `npm run build` (tsc -b) passes after Phase 03 wiring; data layer types self-consistent here.

## Risks

- Contract mismatch with BE → keep field names identical to Phase-01 DTOs.
- Any stale reader of `run.positions` → resolved by rename + grep sweep.
