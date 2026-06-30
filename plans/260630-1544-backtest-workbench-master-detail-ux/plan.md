---
title: "Backtest Workbench master-detail UX"
description: "Refactor /backtest từ list+detail 2 route rời thành master-detail 1 trang full-viewport, lazy-load detail qua ?run=<id>, compact list, format số qty/price, error boundary, mobile tabs. Follow-up UX của workbench (260630-0031, đã completed)."
status: completed
priority: P2
branch: "develop"
tags: [backtest, web, ux, layout]
blockedBy: []
blocks: []
created: "2026-06-30T12:16:12.843Z"
createdBy: "ck:plan"
source: skill
---

# Backtest Workbench master-detail UX

## Overview

Trang `/backtest` (do plan `260630-0031-backtest-research-workbench` tạo, đã completed + merged) hiện UX kém: list + detail tách 2 route rời (`/backtest` ↔ `/backtest/$runId`), `maxWidth` cứng nhồi nội dung vào cột giữa bỏ phí ~430px mỗi bên trên desktop 1440px, số quantity/price không format gây tràn cột (content cutoff).

Refactor thành **master-detail 1 trang**: list trái compact ~400px | detail phải 1fr full viewport; click run → detail **lazy-fetch** qua `?run=<id>` (deep-link reload-safe); format số gọn; error boundary cô lập lỗi render từng pane; mobile 2-tab single-pane.

Đây là **follow-up UX**, không phải feature mới — tái dùng toàn bộ components workbench (`backtest-result-view`, `run-history-rail`, orders/verdict, các chart). Workbench đã completed nên chạy **riêng**, không gộp.

Brainstorm: [`../reports/brainstorm-260630-1544-backtest-workbench-master-detail-ux-report.md`](../reports/brainstorm-260630-1544-backtest-workbench-master-detail-ux-report.md)
Bằng chứng screenshot: [`../reports/assets/260630-1544-backtest-workbench-ux/`](../reports/assets/260630-1544-backtest-workbench-ux/)

## Decisions (đã chốt với user)

- **State/URL** = search param `/backtest?run=<id>` (`validateSearch`, giống `/compare`). Detail lazy: `useBacktestRun(run)` đã có `enabled: !!run`. Reload/back/forward/share giữ run.
- **List master** = compact card/row (KHÔNG table 9 cột) — hợp sidebar hẹp, không tràn. Checkbox compare (≤3) giữ nguyên.
- **Layout split** = cố định ~400px | 1fr (clone `.strategies-layout`), KHÔNG resizable.
- **Form "Run Backtest"** = nút "+ New run" mở drawer (tái dùng pattern `order-detail-drawer`).
- **Compare** = GIỮ route riêng `/backtest/compare?runs=a,b` — KHÔNG gộp inline.
- **Error boundary** = `errorComponent` ở route `/backtest` → lỗi render 1 pane không trắng cả app.
- **Mobile <768px** = 2 tab `[List][Detail]` single-pane (như `strategies-mobile`), chọn run nhảy tab Detail.
- **Format số** = áp toàn bộ qty/price tràn: orders-table, positions-table, order-detail-drawer, backtest-history-table.

## Đính chính vs workbench plan (260630-0031) — tránh red-team bắt lại

- **`number-format.ts` đặt ở `web/src/lib/`** — KHÔNG mâu thuẫn workbench red-team M6. M6 nói **API fetch module** phải ở `api/backtest-api.ts` (không `lib/`). `number-format` là **format util thuần**, đúng chỗ `lib/` cạnh `datetime.ts`, `symbol-format.ts`, `theme-colors.ts`. Đã có tiền lệ `fmtPrice`/`fmtPnl` trong `positions-utils.ts` (sẽ promote lên `lib/` + re-export để DRY).
- **Route file convention** — workbench chốt trailing-underscore (`backtest_.$runId.tsx`, `backtest_.compare.tsx`) khớp `monitor_.jobs.$jobId`. Plan này XÓA `backtest_.$runId.tsx` (gộp vào `/backtest`), GIỮ `backtest_.compare.tsx` đúng convention.
- **History default scope** — workbench validation Q5 chốt "rỗng đến khi chọn strategy", NHƯNG commit `76768d0` đã đổi sang "all strategies" (code đi xa hơn plan). Compact list theo **code hiện tại** (all strategies + narrow qua picker), KHÔNG theo plan Q5 cũ.

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Number format util](./phase-01-number-format-util.md) | Completed |
| 2 | [Workbench layout + route gộp](./phase-02-workbench-layout-route-g-p.md) | Completed |
| 3 | [Compact list + form drawer](./phase-03-compact-list-form-drawer.md) | Completed |

## Phase dependencies

```
P1 (number-format, độc lập) ──┐
                              ├─► P2 (route gộp + layout shell) ─► P3 (compact list + form drawer)
```

P1 thuần util + có unit test, độc lập, làm trước để P2/P3 dùng ngay. P2 dựng shell master-detail + route. P3 thay list render + form drawer trên shell P2.

## Acceptance criteria (toàn plan)

- [ ] Desktop ≥1280px: nội dung dùng full viewport, KHÔNG còn cột trống 2 bên (bỏ `maxWidth` cứng).
- [ ] Click run trong list → detail lazy-fetch (Network chỉ gọi `/backtest/{id}` khi chọn), URL có `?run=<id>`, reload/back/forward giữ run.
- [ ] QTY/price format gọn (qty ≤6-8 sig digits, price `109,169.14`), KHÔNG tràn cột ở orders/trades/drawer/history.
- [ ] Mobile <768px: 2 tab List/Detail hoạt động, KHÔNG tràn ngang.
- [ ] Lỗi render 1 pane (chart/detail throw) KHÔNG làm trắng cả app.
- [ ] Route cũ `backtest_.$runId.tsx` XÓA; `/backtest` là điểm vào duy nhất (bookmark `/backtest/<id>` cũ → 404, đã chấp nhận — validation).
- [ ] Compact list có dropdown sort (Newest/Return/Sharpe/...) — giữ power table cũ.
- [ ] Compare route `/backtest/compare` giữ nguyên hoạt động.
- [ ] FE `npm run lint && npm run build` pass; `npx vitest run` pass (gồm test mới `number-format`).

**Lệnh build FE (từ `web/`):** lint = `npm run lint`, types+build = `npm run build` (`tsc -b && vite build`), test = `npm run test` (`vitest run`).

## Non-negotiable constraints (CLAUDE.md)

- FE: thuần **CSS variables** (KHÔNG Tailwind), TanStack Router file-based + React Query, theme `data-theme`.
- Route dùng `createFileRoute` + `validateSearch` cho search param; KHÔNG đổi contract API (chỉ FE refactor).
- Charts lightweight-charts: giữ `ResizeObserver` + cleanup effect (`ro.disconnect()` + `chart.remove()`) — quan trọng khi pane mount/unmount.
- Rules of Hooks: hook `useBacktestRun`/`useBacktestOrders` gọi unconditional, lazy qua `enabled` flag (đã đúng).

## Risks

- **Resize chart trong pane ẩn/hiện** — lightweight-charts `ResizeObserver` riêng. Mobile chuyển tab hoặc detail mount/unmount phải re-init đúng width. Mitigate: giữ cleanup effect hiện có; test thủ công đổi tab + resize.
- **Xóa route cũ → 404 bookmark** — validation chốt XÓA `backtest_.$runId.tsx` (không redirect). Bookmark `/backtest/<id>` cũ sẽ 404. Đã chấp nhận: run ad-hoc ephemeral, ít ai bookmark deep-link runId. Compare route giữ.
- **`formatQty` làm tròn mất thông tin** — crypto qty rất nhỏ. Chốt `toPrecision(8)` (validation) — đủ giữ bậc cho lệnh nhỏ, không float noise.

## Validation Log

### Session 1 — 2026-06-30

**Verification Results**
- Claims checked: 6 · Verified: 5 · Failed: 0 · Unverified: 1 · Tier: Standard (3 phase)
- `BacktestHistoryTable` chỉ 1 callsite (`run-history-rail.tsx:79`) → xóa an toàn. VERIFIED
- `BacktestResultView`/`RunHistoryRail` callsites khớp plan. VERIFIED
- `validateSearch` dùng ở `index`/`monitor_.jobs.$jobId`/`backtest_.compare` → pattern OK. VERIFIED
- `errorComponent`/`redirect`/`beforeLoad` chưa có tiền lệ trong repo (API chuẩn TanStack Router v1). UNVERIFIED → resolved: dùng `errorComponent` (API chuẩn), KHÔNG cần redirect (xóa route cũ).

| # | Câu hỏi | Quyết định | Propagate |
|---|---------|-----------|-----------|
| 1 | formatQty precision | **`toPrecision(8)`** (8 sig digits) | P1 (đã khớp) |
| 2 | Compact list sort | **Dropdown sort gọn** (Newest/Return/Sharpe/...) trên đỉnh list | P3 |
| 3 | Redirect route cũ | **XÓA hẳn** `backtest_.$runId.tsx` (chấp nhận 404 bookmark cũ), KHÔNG redirect/beforeLoad | P2 |
| 4 | BacktestHistoryTable | **Xóa luôn** (1 callsite, compact thay hoàn toàn) — di chuyển sort logic sang rail trước | P3 |

### Whole-Plan Consistency Sweep
- Sửa P2 Overview: "Xóa route (redirect)" → "Xóa hẳn (không redirect)" khớp Q3. Bỏ mọi `beforeLoad`/`redirect-only` khỏi P2 (Architecture/Files/Steps/Risk/Criteria).
- P3 `BacktestHistoryTable`: thống nhất XÓA (bỏ "maybe delete"/"cân nhắc"), thêm bước di chuyển `SortKey`+`metricVal`+sort sang rail trước khi xóa → dropdown sort (Q2) tái dùng logic này, không mất power.
- Cross-plan: workbench `260630-0031` đã completed → plan này không blocking, không cần bidirectional update. `number-format.ts` ở `lib/` đã ghi rõ không mâu thuẫn M6.
- Không còn contradiction chưa giải quyết. Plan sẵn sàng cook.

## Dependencies

- Plan `260630-0031-backtest-research-workbench` (completed) — tạo trang + components plan này refactor. Không blocking (đã xong).
- Plan `260629-2132-web-claude-theme-ui-tweaks` (done) — theme tokens. Không blocking.
