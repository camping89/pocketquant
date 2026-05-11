---
phase: 3
title: "Bottom Panel Skeleton"
status: pending
priority: P1
effort: "0.5d"
dependencies: [2]
---

# Phase 3: Bottom Panel Skeleton

## Overview

Collapsible bottom panel dưới `TradingChart`. Header với tabs (Metrics | Positions | Equity) + collapse/expand button + drag handle resize. Persist `{height, activeTab, collapsed}` ở `localStorage`. Mount conditionally khi có `selectedSubId` và backtest completed.

## Requirements

- Functional:
  - Panel mount khi `selectedSubId && backtestDoc?.status === 'completed'`.
  - Tab switch instant (KHÔNG refetch — same data).
  - Drag resize từ top edge, min 120px, max 60% viewport height.
  - Collapse toggle giấu nội dung, giữ header 32px.
  - State persist qua reload.
- Non-functional: < 200 LOC main file, separate concerns.

## Architecture

### Folder structure

```
components/strategy/backtest-panel/
├── index.tsx                  # main collapsible container, state, dispatch
├── backtest-panel-header.tsx  # tabs + collapse button
├── backtest-panel-tabs.ts     # tab id constants + types
├── use-panel-layout.ts        # localStorage persistence hook
├── metrics-tab.tsx            # Phase 4
├── positions-tab.tsx          # Phase 5
└── equity-tab.tsx             # Phase 6
```

### State

```typescript
interface PanelLayout {
  height: number       // px, persisted
  collapsed: boolean   // persisted
  activeTab: TabId     // persisted
}

type TabId = 'metrics' | 'positions' | 'equity'

const STORAGE_KEY = 'backtest-panel.layout'
const DEFAULT: PanelLayout = { height: 280, collapsed: false, activeTab: 'metrics' }
```

`use-panel-layout.ts`: `useState` + `useEffect` sync với localStorage.

### Layout integration

`routes/index.tsx`:
```tsx
<main className="chart-container">
  <TickerWidget ... />
  <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
    <TradingChart ... />  // takes flex: 1
    {backtestDoc?.status === 'completed' && (
      <BacktestPanel
        backtest={backtestDoc}
        subscription={selectedSub}
      />
    )}
  </div>
</main>
```

`<BacktestPanel>` self-managed height qua CSS `height: {layout.height}px`.

### Drag handle

```tsx
<div
  className="drag-handle"
  onMouseDown={startDrag}
  style={{ height: 4, cursor: 'row-resize', ... }}
/>
```

Drag logic: `mousemove` → `setHeight(clamp(viewport.height - e.clientY, 120, viewport.height * 0.6))`. Cleanup listeners on `mouseup`.

## Related Code Files

### Create
- `packages/pocketquant-web/src/components/strategy/backtest-panel/index.tsx`
- `packages/pocketquant-web/src/components/strategy/backtest-panel/backtest-panel-header.tsx`
- `packages/pocketquant-web/src/components/strategy/backtest-panel/backtest-panel-tabs.ts`
- `packages/pocketquant-web/src/components/strategy/backtest-panel/use-panel-layout.ts`
- `packages/pocketquant-web/src/components/strategy/backtest-panel/metrics-tab.tsx` — stub `<div>Metrics</div>`
- `packages/pocketquant-web/src/components/strategy/backtest-panel/positions-tab.tsx` — stub
- `packages/pocketquant-web/src/components/strategy/backtest-panel/equity-tab.tsx` — stub

### Modify
- `packages/pocketquant-web/src/routes/index.tsx` — mount `<BacktestPanel>` dưới `<TradingChart>`
- `packages/pocketquant-web/src/index.css` — add styles for drag handle + panel

## Implementation Steps

1. **Create `backtest-panel-tabs.ts`** — export `TabId` type + `TAB_IDS` array.
2. **Create `use-panel-layout.ts`** — hook trả `[layout, dispatch]` với localStorage sync.
3. **Create `backtest-panel-header.tsx`** — render 3 tabs (active highlight) + collapse button. Click tab → dispatch `{activeTab}`. Click collapse → dispatch `{collapsed}`.
4. **Create `index.tsx`** — main container:
   - Hook `usePanelLayout()`.
   - Drag logic for height resize.
   - Render header + content area (height = `collapsed ? 0 : height`).
   - Render active tab component (lazy switch).
   - Props: `backtest: SubscriptionBacktest`, `subscription: Subscription`.
5. **Stub tab components** — return `<div>Tab name placeholder</div>` để Phase 4-6 fill.
6. **Mount trong `routes/index.tsx`** — wrap chart + panel trong flex column container. Conditional mount theo brainstorm decision.
7. **CSS** — `.backtest-panel`, `.backtest-panel__header`, `.backtest-panel__drag-handle`, `.backtest-panel__tab--active`. Match existing dark theme (`#0d1117`-ish bg, subtle borders).
8. **Smoke test** — `pnpm dev`, chọn sub có completed backtest → panel xuất hiện; click tabs; drag resize; reload → state restored.

## Success Criteria

- [ ] Panel mount đúng condition
- [ ] 3 tabs switch instant, active highlight đúng
- [ ] Drag resize hoạt động, clamp 120-60%
- [ ] Collapse/expand toggle
- [ ] State persist qua reload
- [ ] No layout regression cho khi panel không mount
- [ ] tsc + lint pass

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Drag event leak khi rapid mouseup outside window | Cleanup listeners trong useEffect return |
| Chart resize không trigger khi panel resize | ResizeObserver trong TradingChart đã handle — verify |
| Panel chiếm chart space → chart shrink xấu | flex: 1 cho chart container, panel fixed height — chart tự handle |

## Notes

- Tab content lazy: chỉ render component của active tab, unmount khi switch (giảm GPU cost cho equity pane Phase 6).
- KISS: dùng inline styles cho dynamic height, classes cho static styling.
