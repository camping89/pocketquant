---
phase: 2
title: "FE deep-link routing"
status: completed
priority: P1
dependencies: [1]
---

# Phase 2: FE deep-link routing

## Overview

Refactor `/backtest` từ single-page `activeRunId` local state sang **URL-driven master-detail** (TanStack Router): `/backtest` (shell + form + slot history), `/backtest/$runId` (detail reload-safe), `/backtest/compare?runs=a,b,c`. Nền cho toàn FE — giải quyết "reload là mất run" + shareable deep-link. Tái dùng thiết kế C1 slice-3.

## Requirements

- Functional:
  - `/backtest/$runId` param-driven, `useBacktestRun(runId)` poll khi `started`, reload giữ run, back/forward, copy URL.
  - `/backtest/compare?runs=a,b,c` search param (2–3 run).
  - `/backtest` index: `BacktestForm` (giữ) + slot history rail (P4).
  - `POST /run` thành công → navigate `/backtest/$runId`.
- Non-functional: giữ `useBacktestRun` refetchInterval (poll 1500ms khi `started`); thuần CSS variables; module API = `web/src/api/backtest-api.ts`.

## Architecture

```
/backtest (shell)
├─ index: <BacktestForm> + <div slot history (P4)> + empty state
├─ $runId: <BacktestResultView runId> — useBacktestRun(runId)
└─ compare?runs=a,b,c: <RunCompareView> (stub, P4 fill)
```

**404-race (red-team F6 — refuted nhưng ghi invariant):** `cmd_svc.run` await `save(BacktestResult.started(...))` TRƯỚC khi route trả 202 (`backtest_command_service.py:71`, `backtest.py:57-62`). Nên navigate→GET `$runId` luôn thấy doc `started`, không race. **Invariant phải giữ:** started-doc persist đồng bộ trước 202 — không được chuyển save vào spawned task (sẽ tái lập race `NotFoundError`). Ghi chú trong code.

**Cleanup (red-team F6):** `backtest.tsx:19` hiện đọc `run?.error_message ?? run?.error_msg` — `error_msg` là field chết (BE chỉ emit `error_message`). Khi move component → **bỏ fallback `error_msg`**, không mang theo.

## Related Code Files

- Modify: `web/src/routes/backtest.tsx` — bỏ `activeRunId`; shell + index (form + slot).
- Create: `web/src/routes/backtest.$runId.tsx` — param route → `BacktestResultView`.
- Create: `web/src/routes/backtest.compare.tsx` — search param stub.
- Modify: `web/src/hooks/use-backtest-run.ts` — `useRunBacktest` onSuccess navigate; giữ poll.
- Modify: `web/src/components/backtest/backtest-result-view.tsx` — nhận `runId`; bỏ `error_msg` fallback.
- Reference: `web/src/api/backtest-api.ts` (module đúng), `web/src/routes/__root.tsx` (nav).

## Implementation Steps

1. `backtest.$runId.tsx`: `Route.useParams().runId` → `useBacktestRun(runId)` → `BacktestResultView`. Loading/empty/error.
2. Refactor `backtest.tsx`: bỏ `activeRunId`; index = `BacktestForm` + slot `<div>` history (P4).
3. `use-backtest-run.ts`: `useRunBacktest` `onSuccess: (d) => navigate({to:'/backtest/$runId', params:{runId:d.request_id}})`.
4. `backtest.compare.tsx` stub: parse `?runs=`, placeholder.
5. Bỏ `error_msg` fallback khi move.
6. Verify TanStack Router regen `routeTree.gen.ts`.
7. `npm run lint && npm run build`.

## Success Criteria

- [x] Chạy backtest → URL `/backtest/$runId`; reload giữ; back/forward; copy link mở đúng.
- [x] Poll-while-started vẫn chạy (started→poll→finished dừng).
- [x] `/backtest/compare?runs=a,b` resolve (stub OK).
- [x] `error_msg` fallback đã bỏ.
- [x] `npm run lint && npm run build` pass.

## Risk Assessment

- **Refactor vỡ poll:** giữ `useBacktestRun` refetchInterval; chỉ đổi nguồn `runId` (param). Test thủ công poll→terminal.
- **404-race (refuted):** an toàn nhờ started-doc sync; ghi invariant code để không tái lập.
- **Route tree regen:** chạy dev/build generate `routeTree.gen.ts`; commit.
- **Compare ≤3:** clamp + empty state khi `runs` rỗng/thừa.
