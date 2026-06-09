---
phase: 5
title: "FE single-backtest poll"
status: pending
priority: P2
effort: "4h"
dependencies: [2]
---

# Phase 5: FE single-backtest poll

## Overview

Single backtest (`POST /api/v1/backtest/run`) đổi từ synchronous (FE await `BacktestResult`) sang async qua queue (Phase 2): enqueue → trả `{request_id}` → FE poll tới khi `done` → render chart. Đồng nhất với run_all đã poll. Cũng đổi FE proxy target sang bff (nếu cần local; prod đã qua bff service).

## Requirements

- Functional:
  - `runBacktest` (FE `backtest-api.ts:80`) đổi: POST `/backtest/run` trả `{request_id}` (không phải `BacktestResult`).
  - Thêm poll: `GET /api/v1/backtest/requests/{request_id}` trả `{status, result?}`; FE poll interval tới `done`/`failed`.
  - `use-backtest.ts` mutation đổi: trigger enqueue → bắt đầu poll → resolve khi có result → render chart như cũ.
  - UX: hiển thị trạng thái "running" giữa enqueue và done (spinner/skeleton). Fail → error overlay.
  - Vite proxy `/api` target đổi sang bff port (Phase 4 chốt bff port). Prod: web container đã trỏ app service → đổi sang bff service (Phase 6 compose).
- Non-functional:
  - Giữ shape `BacktestResponse` khi `done` để phần render chart/markers không phải sửa.
  - Poll có timeout + max attempts (tránh poll vô hạn nếu worker chết).

## Architecture

### Endpoint poll

Phase 2 chốt poll theo `request_id` (single backtest không gắn sub). bff thêm route `GET /backtest/requests/{request_id}` đọc `BacktestRequestRepository.get(id)` → trả status + embedded result khi done. Run_all giữ poll theo `/subscriptions/{id}/backtest` như cũ (không đổi).

### FE flow

```
user bấm Run
  → POST /backtest/run {config}        → {request_id}
  → poll GET /backtest/requests/{id}    (mỗi ~1s, max ~60 lần)
      status pending|running → tiếp tục
      status done            → lấy result.run → render chart + markers
      status failed          → error overlay
```

Tái dùng react-query: `useMutation` enqueue + `useQuery` poll với `refetchInterval` dừng khi terminal (pattern đã có ở `use-subscriptions.ts:21` refetchInterval conditional).

## Related Code Files

- Modify: `packages/pocketquant-web/src/api/backtest-api.ts` — `runBacktest` trả request_id; thêm `fetchBacktestRequest(id)`
- Modify: `packages/pocketquant-web/src/hooks/use-backtest.ts` — mutation→enqueue + poll query; expose result/loading/error
- Modify: component gọi use-backtest (backtest panel) — handle loading/running state nếu chưa có
- Modify: `packages/pocketquant-web/vite.config.ts` — proxy `/api` target → bff port (local)
- Create (bff, có thể thuộc Phase 2/4): route `GET /backtest/requests/{request_id}`
- Read context: `backtest-api.ts`, `use-backtest.ts`, `use-subscriptions.ts` (poll pattern), backtest panel component

## Implementation Steps

1. (bff) Thêm route `GET /backtest/requests/{request_id}` → `BacktestRequestRepository.get`. (Nếu chưa làm ở Phase 2.)
2. `backtest-api.ts`: `runBacktest` POST trả `{request_id}`; thêm `fetchBacktestRequest(id): Promise<{status, result?}>`.
3. `use-backtest.ts`: đổi `useMutation` → enqueue; lưu `request_id` state; `useQuery` poll `fetchBacktestRequest` với `refetchInterval` dừng khi `done`/`failed`; map `result.run` → BacktestResponse cũ.
4. Component: thêm running/loading UI (reuse spinner sẵn có).
5. `vite.config.ts`: target bff port (local dev).
6. `cd packages/pocketquant-web && npm run lint && npm run build` xanh.
7. Smoke: chạy app(worker)+bff+vite, bấm Run → poll → chart hiện markers. Fail case → overlay.

## Success Criteria

- [ ] Single backtest enqueue→poll→render hoạt động; chart + markers đúng như synchronous cũ.
- [ ] Running state hiển thị giữa enqueue và done; fail → error overlay.
- [ ] Poll có timeout/max attempts.
- [ ] run_all backtest poll không đổi (regression).
- [ ] Vite proxy trỏ bff; FE lint + build xanh.

## Risk Assessment

- **Worker chậm/chết → poll treo**: Mitigation: max attempts + timeout; báo lỗi rõ "backtest worker không phản hồi".
- **Result shape drift**: enqueue path phải embed cùng `BacktestResult` shape FE đang render. Mitigation: giữ `result.run` shape; test render với fixture.
- **Bruno/curl docs lỗi thời**: README sync smoke + `tests/http`/`tests/manual` dùng synchronous response. Cập nhật sang enqueue+poll (Phase 6 docs sweep hoặc đây).
- **bff port local chưa chốt**: phụ thuộc Phase 4. Mitigation: làm Phase 5 sau Phase 4 chốt port, hoặc dùng env var.
