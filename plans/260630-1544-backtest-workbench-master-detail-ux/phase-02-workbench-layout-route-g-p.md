---
phase: 2
title: "Workbench layout + route gộp"
status: completed
priority: P1
dependencies: [1]
---

# Phase 2: Workbench layout + route gộp

## Overview

Gộp list + detail vào 1 route `/backtest?run=<id>`, full viewport master-detail (clone `.strategies-layout`), lazy-load detail, error boundary, mobile 2-tab. Xóa hẳn route `/backtest/$runId` (validation Q3 — không redirect). Giữ `/backtest/compare`.

## Requirements

- Functional:
  - 1 route `/backtest` với `validateSearch({ run?: string })`. `run` set → detail pane lazy-fetch; null → empty state "Select a run".
  - Desktop ≥768px: grid `~400px 1fr`, `height: calc(100vh - 41px)`, 2 pane scroll độc lập, bỏ `maxWidth` cứng.
  - Mobile <768px: 2 tab `[List][Detail]`, chọn run → nhảy tab Detail.
  - `errorComponent` ở route → lỗi render pane không trắng app.
  - Route cũ `backtest_.$runId.tsx` XÓA hẳn (validation Q3) — `/backtest` là điểm vào duy nhất. Bookmark `/backtest/<id>` cũ → 404, đã chấp nhận (run ad-hoc ephemeral).
- Non-functional: dùng full viewport; chart trong detail re-init đúng width khi mount/đổi tab.

## Architecture

- **Route shell** `routes/backtest.tsx` viết lại:
  - `validateSearch: (s) => ({ run: typeof s.run === 'string' ? s.run : undefined })`.
  - `errorComponent` đơn giản (pane-level fallback "Failed to render this view").
  - Render `<BacktestWorkbench />`.
- **Component mới** `components/backtest/backtest-workbench.tsx` — orchestrator:
  - Đọc `run` từ `Route.useSearch()`, `navigate` cập nhật `?run=` khi chọn.
  - Desktop: `.backtest-layout` grid (list pane | detail pane). Detail = `BacktestDetailPane` (move logic từ `backtest_.$runId.tsx`: poll status, `BacktestResultView`, status badge).
  - Mobile: `.backtest-mobile` 2 tab (clone `.strategies-mobile`).
  - Lazy: `useBacktestRun(run)` với `enabled: !!run` (đã có) — detail chỉ fetch khi `run` set.
- **Detail pane** tách từ `backtest_.$runId.tsx` thành `BacktestDetailPane` (nhận `runId: string | null`), bỏ wrapper `maxWidth: 1080`.
- **Route cũ** `backtest_.$runId.tsx` → **XÓA hẳn** (validation Q3). `/backtest` là điểm vào duy nhất. Bookmark `/backtest/<id>` cũ → 404 (chấp nhận: run ad-hoc ephemeral, ít bookmark deep-link). KHÔNG dùng redirect/beforeLoad (tránh API chưa có tiền lệ repo). `backtest_.compare.tsx` GIỮ.
- **CSS** `index.css`: thêm `.backtest-layout` (clone `.strategies-layout`: `display:none` mobile, grid `400px 1fr` ≥768px, `height: calc(100vh - 41px)`, overflow per-pane) + `.backtest-mobile` + `.backtest-list-pane` / `.backtest-detail-pane`.

## Related Code Files

- Modify: `web/src/routes/backtest.tsx` (viết lại: validateSearch + errorComponent + render workbench)
- Delete: `web/src/routes/backtest_.$runId.tsx` (validation Q3 — xóa hẳn, không redirect)
- Create: `web/src/components/backtest/backtest-workbench.tsx` (orchestrator 2 pane + mobile tabs)
- Create: `web/src/components/backtest/backtest-detail-pane.tsx` (detail logic tách từ route cũ, bỏ maxWidth)
- Modify: `web/src/index.css` (`.backtest-layout`, `.backtest-mobile`, pane styles)
- Modify: `web/src/routeTree.gen.ts` (auto-regen bởi TanStack Router plugin khi dev — không sửa tay)

## Implementation Steps

1. `index.css`: thêm block `.backtest-layout` / `.backtest-mobile` / pane styles — clone từ `.strategies-layout` (dòng ~1441-1521), đổi grid cột `240px 1fr 360px` → `400px 1fr` (2 pane).
2. Tạo `backtest-detail-pane.tsx`: move JSX + logic từ `backtest_.$runId.tsx` (`useBacktestRun`, status badge, loading/failed/finished → `BacktestResultView`). Nhận `runId: string | null`; `null` → empty state. Bỏ wrapper `maxWidth`.
3. Tạo `backtest-workbench.tsx`:
   - `const { run } = Route.useSearch()` (import Route từ `routes/backtest`), `const navigate = useNavigate()`.
   - `onSelect(runId) → navigate({ to: '/backtest', search: { run: runId } })`.
   - Desktop `.backtest-layout`: `<RunHistoryRail selectedRun={run} onSelect={...} />` (P3 cập nhật signature) | `<BacktestDetailPane runId={run ?? null} />`.
   - Mobile `.backtest-mobile`: tab state, chọn run set tab='detail'.
4. Viết lại `routes/backtest.tsx`: `validateSearch` + `errorComponent` + `component: () => <BacktestWorkbench />`. (Tách `RunHistoryRail`/form ra khỏi route — chuyển vào workbench/P3.)
5. XÓA `backtest_.$runId.tsx` (di chuyển logic vào `backtest-detail-pane.tsx` ở bước 2).
6. Dev server tự regen `routeTree.gen.ts`. Verify `npm run build`.
7. Test thủ công (agent-browser): desktop full-width, click run → `?run=` + lazy fetch, reload giữ run, mobile 2 tab, ép lỗi render → chỉ pane hỏng.

## Success Criteria

- [ ] `/backtest` full viewport, list trái ~400px | detail 1fr, không cột trống.
- [ ] Click run → `?run=<id>`, detail lazy-fetch (Network), reload/back/forward giữ run.
- [ ] `backtest_.$runId.tsx` đã xóa; `routeTree.gen.ts` regen không còn route `/backtest/$runId`; build pass.
- [ ] Mobile <768px: 2 tab hoạt động, chọn run nhảy Detail.
- [ ] Lỗi render pane → errorComponent, không trắng app.
- [ ] `/backtest/compare` còn nguyên.
- [ ] `npm run build` pass.

## Risk Assessment

- **Chart resize khi mount/đổi tab:** `EquityDrawdownChart`/`HistogramChart` dùng `ResizeObserver` + cleanup (đã có). Detail pane mount lần đầu khi chọn run → chart init sau khi container có width. Mitigate: giữ cleanup effect; nếu chart 0-width, kiểm `ResizeObserver` fire sau layout (đã hoạt động ở strategies).
- **Rules of Hooks:** `BacktestDetailPane` gọi `useBacktestRun(runId)` unconditional, `enabled: !!runId` lo lazy — không early-return trước hook.
- **routeTree.gen.ts:** auto-gen, không sửa tay; nếu build lỗi search type, kiểm `validateSearch` trả đúng shape. Sau khi xóa route file, dev server regen — nếu chạy build tĩnh (không dev), chạy `npm run dev` 1 lần hoặc xóa entry route trong gen file thủ công rồi build.
- **404 bookmark cũ:** chấp nhận (validation Q3). Compare route giữ nên link compare không vỡ.
