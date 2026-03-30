---
phase: 6
priority: P0
effort: S
status: complete
depends_on: [3]
---

# Phase 6: UI Controls

## Overview

Symbol selector dropdown, interval selector, indicator toggles. Wires user selections to chart data fetching.

## Context

- [plan.md](plan.md)
- Symbols from `GET /api/v1/market-data/symbols` — returns `{code, exchange, name, asset_type, is_active}`
- Intervals: `1, 3, 5, 15, 30, 45, 60, 120, 180, 240, 1D, 1W, 1M`
- Indicator types: SMA, EMA, RSI, MACD, Bollinger Bands

## Architecture

```
src/
├── components/
│   ├── controls/
│   │   ├── symbol-selector.tsx     # Dropdown with search
│   │   ├── interval-selector.tsx   # Button group for timeframes
│   │   └── indicator-toggles.tsx   # Checkbox/button toggles per indicator
│   └── layout/
│       ├── app-header.tsx          # Top bar with controls
│       └── app-layout.tsx          # Full page layout
└── App.tsx                          # State management, wiring
```

## Implementation Steps

1. Create `src/components/controls/symbol-selector.tsx`:
   - Uses `useSymbols()` hook
   - Filterable dropdown (input + options list)
   - Shows `{exchange}:{code}` format
   - Default: first active symbol
   ```typescript
   function SymbolSelector({ value, onChange }: {
     value: { exchange: string; symbol: string };
     onChange: (v: { exchange: string; symbol: string }) => void;
   }) { ... }
   ```

2. Create `src/components/controls/interval-selector.tsx`:
   - Button group, one active at a time
   - Groups: `1m 3m 5m 15m 30m 45m | 1h 2h 3h 4h | 1D 1W 1M`
   - Compact horizontal layout
   ```typescript
   const INTERVALS = [
     { label: '1m', value: '1' },
     { label: '5m', value: '5' },
     { label: '15m', value: '15' },
     { label: '1h', value: '60' },
     { label: '4h', value: '240' },
     { label: '1D', value: '1D' },
     { label: '1W', value: '1W' },
     { label: '1M', value: '1M' },
   ];
   ```

3. Create `src/components/controls/indicator-toggles.tsx`:
   - Toggle buttons for each indicator type
   - Active state = colored, inactive = dimmed
   ```typescript
   type IndicatorConfig = {
     sma: boolean;
     ema: boolean;
     rsi: boolean;
     macd: boolean;
     bollinger: boolean;
   };
   ```

4. Create `src/components/layout/app-header.tsx`:
   - Horizontal bar: `[Symbol Selector] [Interval Selector] [spacer] [Indicator Toggles]`
   - Dark theme, sticky top

5. Create `src/components/layout/app-layout.tsx`:
   - Header (fixed top) + Chart (fills remaining viewport)
   - `height: 100vh`, `display: flex`, `flex-direction: column`

6. Update `src/App.tsx`:
   - State: `selectedSymbol`, `selectedInterval`, `activeIndicators`
   - Pass to `<TradingChart>` + `<AppHeader>`
   - On change: TanStack Query auto-refetches via key change

## Styling Approach

Pure CSS (no framework). CSS modules or plain CSS with BEM-like naming.

```css
.app-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  background: #16213e;
  border-bottom: 1px solid #2B2B43;
}

.interval-btn {
  padding: 4px 8px;
  background: transparent;
  color: #8b8b9a;
  border: 1px solid #2B2B43;
  cursor: pointer;
}
.interval-btn.active {
  background: #1a1a2e;
  color: #d1d4dc;
  border-color: #26a69a;
}
```

## Related Code Files

- **Create:** `src/components/controls/*.tsx`, `src/components/layout/*.tsx`
- **Modify:** `src/App.tsx` (add state, wire controls to chart)

## Todo

- [x] Symbol selector with search/filter
- [x] Interval selector button group
- [x] Indicator toggle buttons
- [x] App header layout
- [x] App layout (header + chart)
- [x] Wire state in App.tsx
- [x] Verify symbol/interval changes refetch data

## Success Criteria

- Symbol dropdown loads from API, filterable
- Interval buttons switch chart timeframe
- Indicator toggles show/hide indicator series
- Layout: header sticky, chart fills viewport
- Dark theme consistent across all controls
