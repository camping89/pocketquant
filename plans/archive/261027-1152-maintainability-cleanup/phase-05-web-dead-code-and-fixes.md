# Phase 05 — Web dead code and small fixes

- Delete `components/chart/position-box-info-card.ts`, `components/strategy/backtest-panel/metrics-tab.tsx`, `fetchOHLCV`, `fetchCurrentBar`, `useDeleteStrategyById` and `deleteStrategy`, and the `components/monitor/format-helpers.ts` re-exports.
- Fix the crosshair unsubscribe leak in `trading-chart.tsx`.
- Add `'1w'` to `constants/active-intervals.ts`.
- Declare `fancy-canvas` in `package.json`.
- Translate the Vietnamese strings.

Verify: `npm run lint`, `npx tsc -b`, `npx vitest run`, `npm run build` in `web/`.
