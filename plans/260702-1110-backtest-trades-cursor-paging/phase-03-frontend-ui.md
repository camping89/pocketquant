# Phase 03 — Frontend UI: virtualized infinite table + chart selection by trade_id + BE stats + Open tab

## Context

- `web/src/components/backtest/backtest-result-view.tsx` — owns `highlightedIndex`/`hoveredIndex` (array index), tabs (overview/trades/risk/orders), passes `run.positions` to chart + PositionsTab + PnlHistogram + DurationHistogram + streaks/PF (via stats-utils).
- `web/src/components/chart/trading-chart.tsx` — markers from ALL `positions` (`:251-287`); box/info only for selected/hovered by **index** (`:325-381`); scroll-to-trade by index (`:385-411`).
- `web/src/components/strategy/backtest-panel/positions-tab.tsx` + `positions-table.tsx` + `positions-utils.ts` — client filter/sort, non-virtualized table, selection by index.
- Stats components: `pnl-histogram.tsx`, `duration-histogram.tsx`, `histogram-chart.tsx`, `drawdown-table.tsx`, `stats-utils.ts`.
- `web/package.json` — add `@tanstack/react-virtual`.

## Key design change: selection by trade_id, not index

Chart box/info must survive paging + server sort. Replace index-based selection with `trade_id`:

- `backtest-result-view` state: `highlightedTradeId: string | null`, `hoveredTradeId: string | null`.
- Chart receives the **selected/hovered trade objects** (or their id + a lookup) instead of an index into a full array. Chart draws box from the trade object's fields directly (entry/exit time+price, sl/tp, qty, pnl, commission, direction) — no `positions[]` indexing.
- Scroll-to-trade uses the selected trade object's entry/exit times.
- Markers come from `useBacktestMarkers` (all trades), independent of the paged table.

## Files to modify

1. `web/package.json` — add `@tanstack/react-virtual` (^3). Run `npm install`.

2. `web/src/components/chart/trading-chart.tsx`
   - Props: replace `positions?`, `highlightedPositionIndex`, `hoveredPositionIndex` with:
     - `markers?: TradeMarker[]` (drives BUY/SELL arrows — dedup logic unchanged, keyed on entry/exit time).
     - `highlightedTrade?: TradeRow | null`, `hoveredTrade?: TradeRow | null` (drive box/info + scroll).
   - Marker `useMemo` reads `markers` instead of `positions`.
   - Box effect: build `PositionData` from `highlightedTrade`/`hoveredTrade` objects directly; `index` field no longer meaningful → keep for primitive API but derive from a stable discriminator (e.g. 0 for highlight, 1 for hover) since primitive only needs to distinguish the two visually.
   - Scroll effect: use `highlightedTrade` object.
   - Verify `PositionBoxPrimitive` call site still gets what it needs (it took `highlightedPositionIndex/hoveredPositionIndex` to pick outline style — pass a small marker instead, e.g. which of the ≤2 boxes is the click vs hover).

3. `web/src/components/chart/position-box-primitive.ts`
   - Adjust constructor signature if it keyed outline style on index. Switch to an explicit `highlightKind` per box (`'click' | 'hover'`) so it no longer depends on array index. Keep visual behavior identical (solid outline for click, dashed for hover).

4. `web/src/components/strategy/backtest-panel/positions-tab.tsx`
   - Drop client `applyFilter`/`sortPositions`. Own `filter`, `sortKey`, `sortDir` state → pass to `useBacktestTrades`.
   - Flatten infinite pages → `rows: TradeRow[]`. Footer count/total PnL from BE (`total` + a summed pnl — if summed PnL of full filtered set is needed, add to `PagedTradesResponse` or compute from stats; keep footer meaningful without full client data).
   - Selection: `onRowClick(trade)` → `setHighlightedTradeId(trade.trade_id)`; hover → `setHoveredTradeId`.
   - `highlighted` row = `row.trade_id === highlightedTradeId`.

5. `web/src/components/strategy/backtest-panel/positions-table.tsx`
   - Virtualize rows with `@tanstack/react-virtual` (`useVirtualizer`, fixed row height, scroll container = table wrap). Render only visible `<tr>` + top/bottom spacer rows.
   - Infinite trigger: when last virtual item near end → call `fetchNextPage` (passed as prop `onReachEnd` + `isFetchingNextPage`).
   - Sort header click → `onSortChange(key)` (now drives server query).
   - Keep column set; `#` column = row ordinal within loaded set (display only; not a stable id).

6. `web/src/components/strategy/backtest-panel/positions-utils.ts`
   - Remove client `applyFilter`/`sortPositions`/`IndexedPosition` (now server-side). Keep formatters (`fmtDateTime`, `fmtDuration`, `fmtPnl`, `fmtPrice`, `aggregatePnl` if still used). Adjust `SortKey`/`FilterKey` unions to match BE enums (drop `index`, `entry_time` default; keep sortable set).

7. `web/src/components/backtest/backtest-result-view.tsx`
   - State → `highlightedTradeId`/`hoveredTradeId` (clear on run change).
   - Trades tab:
     - `useBacktestMarkers(runId, tab==='trades')` → chart `markers`.
     - `useBacktestStats(runId, tab==='trades')` → PnlHistogram/DurationHistogram/DrawdownTable/streaks/PF read BE stats.
     - Chart gets `highlightedTrade`/`hoveredTrade` resolved from loaded rows (the selected trade object is available since it was clicked from the table; keep a small map id→TradeRow from loaded pages, or pass the clicked object up directly).
   - Add **Open Positions** tab: renders `run.open_positions` in a simple (non-paged) table. Move open-position display out of the trades table.
   - Streaks/PF footer + histograms consume `useBacktestStats` data instead of `computeStreaks`/`profitFactorByDirection`/`histogram`.

8. Stats components
   - `pnl-histogram.tsx` / `duration-histogram.tsx`: accept `bins: HistogramBin[]` from BE stats instead of computing from positions.
   - `drawdown-table.tsx`: accept `periods` from BE stats instead of `topDrawdowns(equityCurve)`.
   - `histogram-chart.tsx`: unchanged (already takes bins).
   - `stats-utils.ts`: the compute fns (`histogram`, `computeStreaks`, `profitFactorByDirection`, `topDrawdowns`) become dead once BE supplies stats. Remove them + their tests (logic now lives + tested in BE). Keep `HistogramBin`/`DrawdownPeriod` types if reused for BE-shaped data, or re-declare from api types.

## Implementation steps

1. `npm install @tanstack/react-virtual`.
2. Rewire chart props (markers + selected trade objects) + primitive outline-kind.
3. Rewrite positions-tab/table for server filter/sort + virtualized infinite scroll.
4. Wire result-view: markers/stats hooks, trade_id selection, Open Positions tab.
5. Point histograms/drawdown at BE stats; delete dead client stats fns + test.
6. `npm run lint`, `npm run build`.

## Validation

- `npm run build` (tsc -b) + `npm run lint` clean.
- Manual: click trade on page 2 → box draws + chart scrolls; hover outlines; markers show for all trades; histograms/streaks/PF/drawdown render; Open tab shows open lots.

## Risks

- Selected trade object availability across pages → resolve by passing the clicked `TradeRow` up on click (it's in-hand at click time) and caching id→row for loaded pages.
- Footer "Total PnL of filtered set" needs full-set aggregate → source from BE (stats or paged response), not loaded pages only.
- Virtualizer + variable container height → fixed row height, measure container via ref.
