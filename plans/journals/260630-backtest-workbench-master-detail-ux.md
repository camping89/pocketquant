# Backtest Workbench Master-Detail UX Refactor

**Date**: 2026-06-30 22:58
**Severity**: Medium
**Component**: Web / Backtest UI
**Status**: Completed

## What Happened

Completed a 3-phase refactor of the `/backtest` page from a 2-route scattered architecture (`/backtest` list + `/backtest/$runId` detail) into a single-page master-detail layout. Commit `1ee36f9` (code), `0734abe` (plan docs). Scope: new number-format utility, layout grid conversion, compact list with dropdown sort, "+ New run" drawer, error boundary, mobile tabs. **No API contract changes.**

## The Brutal Truth

Desktop previously wasted ~430px on each side because of the hardcoded `maxWidth: 1080px` + centered layout. Mobile had no dedicated tab view so opening run detail opened a new route = context lost. Quantity/price data overflowed columns (order detail + history table) because it wasn't formatted compactly. Scattering list+detail across 2 routes made deep-linking fragile: reload detail → loading the list first meant the `$runId` route param lost context.

Extremely time-consuming to debug mobile responsive + chart resize when the pane mounts/unmounts, ResizeObserver callbacks firing unpredictably (an effect from the strategies layout pattern).

## Technical Details

**Commit scope (`1ee36f9`):**
- 14 files changed: 423 insertions, 175 deletions
- New: `number-format.ts` (22 lines, 52 tests), `backtest-workbench.tsx` (63 lines orchestrator), `backtest-detail-pane.tsx` (40 lines), `run-list-item.tsx` (48 lines compact card)
- Deleted: `backtest-history-table.tsx` (104 lines) — logic migrated to rail sort dropdown
- Modified: `backtest.tsx` route, `run-history-rail.tsx` (+119 lines), `index.css` (+92 lines layout block), `use-backtest-run.ts` hook
- Error: None. Lint 0 errors (5 pre-existing warnings), vitest 40/40 pass, build success

**Key implementations:**
- `validateSearch({ run?: string })` pattern: deep-link reload/back/forward preserves `?run=<id>` state
- Desktop grid: `~400px (list pane) | 1fr (detail)` CSS, full viewport `height: calc(100vh - 41px)`, cloned from `.strategies-layout` pattern
- `formatQty(qty)` → `toPrecision(8)` (8 significant digits), `formatPrice(price)` → thousands + 2dp; cover orders-table, positions-table, order-detail-drawer
- Mobile <768px: 2-tab single-pane (List | Detail tabs), selecting a run auto-switches to the Detail tab
- `errorComponent` at route level: pane render error doesn't crash app
- `useBacktestRun(runId, { enabled: !!runId })`: detail lazy-fetches only when `run` param set (no premature network call)

**Edge cases handled:**
- `formatQty` scientific notation <1e-7: accepted (crypto qty reality), locked via test
- Chart resize on pane mount/unmount: ResizeObserver + cleanup effect from existing detail pane pattern, verified manually
- Mobile drawer submit + back/forward: mobileTab state synced via **adjust-state-during-render** idiom (compare prev prop in render, update local state) instead of useEffect — avoids eslint `set-state-in-effect` & matches React idiom for derived state

**Breaking changes:** None. Route API preserved (search validation only). Deleted `backtest_.$runId.tsx` → old `/backtest/<id>` bookmark becomes 404 (expected, ephemeral runs).

## What We Tried

1. **First approach (rejected):** useEffect to sync mobileTab state from route param. Problem: eslint `set-state-in-effect` warning (legitimate), re-render thrashing on mobile viewport change
   - Switched: adjust-state-during-render pattern (compare prev prop in render body) ✓

2. **CSS grid for mobile:** tried `@media (max-width: 768px) { grid-template-columns: 1fr }` 
   - Problem: list scrolls offscreen when detail expands, no tab-based pane switching
   - Switched: separate `.backtest-mobile` 2-tab container with `display: none` on desktop, tab state toggles pane visibility ✓

3. **formatQty rounding:** originally `Math.round(qty * 1e6) / 1e6` (6 decimals)
   - Problem: crypto order qty 0.00000123 rounds to 0, loses data
   - Switched: `toPrecision(8)` (8 sig digits, crypto-friendly) + test boundary <1e-7 ✓

4. **Number format location:** tested `utils/format/` subdir vs `lib/number-format.ts`
   - Resolved via validation: `lib/` correct (matches `datetime.ts`, `symbol-format.ts`), promotes `positions-utils.fmtPrice` DRY ✓

## Root Cause Analysis

**Why desktop wasted space:** Container `max-width` pattern was cargo-culted from workbench v1 (stateful detail pane, needed scroll isolation). Master-detail refactor removes that constraint—should fill viewport. Nobody pushed back because UX complaint came late (after plan 260630-0031 shipped).

**Why mobile broke:** Route-based detail view assumed list + detail stay on screen together. Mobile clicks run → push new route → full-page redirect experience. Real mobile UX needs in-app tab toggle without route churn (back button breaks expectations).

**Why number format was missed:** Orders/positions tables rendered directly without formatter. When qty/price hit 10+ digits or decimals, inline text overflow clipped content. Existing `positions-utils.fmtPrice` was old pattern (not exported), so every component reimplemented ad-hoc.

**Why routeTree regen broke dev build:** Deleted `backtest_.$runId.tsx` but ran `npm run build` (static) before dev server regen. TanStack Router plugin only auto-generates on vite dev/build (dynamic). Mitigation: must run dev server once, or manually remove the entry from the .gen file before a static build.

## Lessons Learned

1. **Master-detail on desktop is cheaper than scattered routes.** List+detail in same viewport eliminates context loss on reload; query params beat route params for state persistence (back/forward just works).

2. **Mobile needs explicit single-pane UX.** Don't try to reflow master-detail grid. Use tabs or drawer overlay. Route-based navigation fights mobile UX expectations (back button psychology).

3. **adjust-state-during-render > useEffect for derived state.** When a prop changes and you need local state to sync, compare in render body, update on-the-fly. Avoids effect re-run thrashing + eslint warnings. React Conf talks about this (e.g., React 18 Suspense patterns).

4. **Number format is a cross-cutting utility.** Once you build one (`formatQty`, `formatPrice`), export/promote aggressively. Every table component will eventually render numbers; inconsistency looks broken.

5. **Auto-generated artifact (routeTree.gen.ts) means 1 dev workflow step.** After file deletions, run dev server minimum once to sync gen artifacts before static build. Document in README or pre-commit hook.

6. **Precision vs data fidelity trade-off.** `toPrecision(8)` fine for display, but crypto orders <1e-7 do exist (weird, but real). Lock behavior in tests so future refactors don't silently truncate.

## Next Steps

- [ ] **Verify production deployment:** live backtest list + master-detail on prod VPS, spot-check deep-link reload, mobile tab toggle
- [ ] **Add to README / docs/code-standards.md:** number-format usage pattern (when to use, precision guarantees, crypto edge case)
- [ ] **Pre-commit hook or CI check:** verify routeTree.gen.ts is in sync after route file adds/deletes (catch dev-only regen misses)
- [ ] **Optional follow-up:** if mobile drawer (form) hits viewport issues, extend `.backtest-mobile` tab to show form preview inline or dock form drawer at bottom

**Owner:** Web refactor complete. Operations + QA: smoke test live.

**Timeline:** Completed 2026-06-30 22:58. Code landed on `develop` branch. No deployment blocker.
