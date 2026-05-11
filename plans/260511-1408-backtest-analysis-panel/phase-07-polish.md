---
phase: 7
title: "Polish"
status: pending
priority: P3
effort: "0.5d"
dependencies: [4, 5, 6]
---

# Phase 7: Polish

## Overview

Empty states, loading indicators, hover sync giữa table và chart, smoke test E2E, docs update.

## Requirements

- Functional:
  - Empty state messages cho: no backtest run, no positions, status=failed.
  - Loading spinner trong mỗi tab khi `isFetching && !data`.
  - Hover row trong positions table → tạm thời highlight position box trên chart (different style từ click selection).
  - Symbol mismatch warning: panel hidden khi user xem chart symbol ≠ sub.symbol, tooltip explain.
- Non-functional: smooth UX, no janky transitions.

## Architecture

### Empty states map

| Condition | Message |
|-----------|---------|
| `backtestDoc.status === 'pending'` | "Backtest queued..." |
| `backtestDoc.status === 'running'` | spinner + "Backtest in progress..." |
| `backtestDoc.status === 'failed'` | error icon + `error_message` |
| `positions.length === 0` (Positions tab) | "No positions in this backtest" |
| `equity_curve.length === 0` (Equity tab) | "No equity data" |

### Hover highlight (table ↔ chart)

Lift `hoveredPositionIdx` state similar to `highlightedPositionIdx` (Phase 5). Pass to `PositionBoxPrimitive` separately — render với dashed outline (different từ solid outline của click selection).

### Symbol mismatch

`routes/index.tsx`:
```typescript
const symbolMismatch = selectedSub && (
  selectedSub.symbol !== currentSymbol ||
  selectedSub.exchange !== currentExchange
)

{!symbolMismatch && backtestDoc?.status === 'completed' && (
  <BacktestPanel ... />
)}

{symbolMismatch && (
  <div className="symbol-mismatch-banner">
    Switch to {selectedSub.exchange}:{selectedSub.symbol} to view backtest
  </div>
)}
```

## Related Code Files

### Modify
- `packages/pocketquant-web/src/components/strategy/backtest-panel/index.tsx` — status-aware empty/loading states
- `packages/pocketquant-web/src/components/strategy/backtest-panel/positions-tab.tsx` — empty state, hover sync
- `packages/pocketquant-web/src/components/strategy/backtest-panel/equity-tab.tsx` — empty state
- `packages/pocketquant-web/src/components/strategy/backtest-panel/metrics-tab.tsx` — failed state
- `packages/pocketquant-web/src/components/chart/position-box-primitive.ts` — support `hoveredIdx` với dashed outline
- `packages/pocketquant-web/src/components/chart/trading-chart.tsx` — accept `hoveredPositionIdx` prop
- `packages/pocketquant-web/src/routes/index.tsx` — lift hover state, symbol mismatch banner
- `packages/pocketquant-web/src/index.css` — `.empty-state`, `.loading-spinner`, `.symbol-mismatch-banner` styles
- `docs/codebase-summary.md` — add section về BacktestPanel architecture
- `docs/project-changelog.md` — entry cho feature

## Implementation Steps

1. **Empty/loading states** mỗi tab — pattern: `if (failed) return errorView; if (loading) return spinner; if (empty) return emptyView; return mainView`.
2. **Hover state lift** — `setHoveredPositionIdx` qua table `onRowMouseEnter`/`onRowMouseLeave`.
3. **Dashed outline trong primitive** — separate render block cho hovered (dashed lineDash) vs highlighted (solid).
4. **Symbol mismatch banner** — compute trong `routes/index.tsx`, conditional render.
5. **E2E smoke test**:
   - Chọn sub completed → 3 tabs work.
   - Sub running → spinner.
   - Sub failed → error message.
   - Sub empty positions → empty state.
   - Symbol switch → mismatch banner, panel hidden.
   - Hover table row → dashed outline; click row → solid outline + zoom.
6. **Docs update**:
   - `codebase-summary.md`: BacktestPanel section ngắn (architecture, file map).
   - `project-changelog.md`: entry "Backtest Analysis Panel" với date.

## Success Criteria

- [ ] All status states render đúng message
- [ ] Loading spinner trong tabs khi data đang fetch
- [ ] Hover row → dashed outline trên chart
- [ ] Click row → solid outline + zoom (Phase 5 maintained)
- [ ] Symbol mismatch banner hiển thị + panel hidden
- [ ] Docs updated
- [ ] Full E2E smoke pass

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Hover spam re-render chart primitive | Memo primitive recreation gate by `hoveredIdx` only |
| Empty state UX không đẹp | Use existing dark theme tokens, simple icons |
| Symbol mismatch banner phá vỡ layout | Minimal banner, < 32px height |

## Notes

- Hover effect optional — nếu cảm thấy noisy có thể skip, giữ chỉ click selection.
- Docs update KHÔNG bắt buộc trong scope, nhưng helpful cho team.
