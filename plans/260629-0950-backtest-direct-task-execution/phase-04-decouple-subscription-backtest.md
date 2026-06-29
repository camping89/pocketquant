---
phase: 4
title: "Decouple subscription backtest"
status: done
effort: ""
---

# Phase 4: Decouple subscription backtest

## Overview

Biến subscription thành THUẦN forward-testing: gỡ toàn bộ backtest cache + endpoints khỏi subscription (backend + FE), xóa `run_subscription` + `BacktestRequestRepository` (sau khi gỡ C3 dep). KHÔNG động start/stop/positions/trades/reconcile (forward-testing giữ nguyên).

## Requirements

- Functional: `/subscriptions/{id}/backtest` + `run-all-backtests` route xóa.
- Functional (C3): `StrategyCommandService` gỡ dep `BacktestRequestRepository` + cascade-delete calls → app boot OK.
- Functional: subscription card FE bỏ backtest panel/badge/equity/positions-from-backtest; chỉ còn forward-testing (positions/trades live).
- Non-functional: forward-testing path (start/stop/positions/trades/reconcile) KHÔNG đổi hành vi.
- Constraint (C6): grep FE chỉ sửa backtest-status consumers; KHÔNG đụng job-history/sync/forward-status badge dùng chung literal.

## Architecture

### Backend remove
- Route `run-all-backtests` (`routes/backtest.py:155` / `strategy.py`) + `RunAllBacktestsCommand` + `BacktestCommandService.run_all`.
- `run_subscription()` (`backtest_dispatch.py:142`) — H2 moot (xóa hẳn, không fix persist flag).
- Route `get_subscription_backtest` (`strategy.py:148`) + `GetSubscriptionBacktestQuery` + query method.
- Subscription backtest cache trong `backtest_repository.py`: `save_for_subscription`, `find_by_subscription`, `_upsert_cache_slot`, `upsert_status`, `get_subscription_status(es)`, `find_doc_by_subscription`, `delete_by_subscription`, `ensure_subscription_cache_unique_index`.

### C3 — StrategyCommandService decouple
`engine/strategy_command_service.py` constructor nhận `BacktestRequestRepository` (`:70,:75`), gọi `delete_by_subscription` (`:143`) + `delete_by_strategy_code` (`:155`) trong cascade-delete. GỠ: bỏ constructor arg + 2 call (orphan cleanup không cần vì collection bị drop). Update DI `trading_services.py:15` wiring. Rồi mới xóa `BacktestRequestRepository` file + provider + `COLLECTION_BACKTEST_REQUESTS`.

### FE remove (subscription card → forward only)
- `dashboard-column.tsx`: bỏ `useSubscriptionBacktest`, MetricsTab/PositionsTab from-backtest, equity từ backtest. Giữ live trades/positions.
- `subscription-panel.tsx`, `strategy-card.tsx`, `backtest-panel/*`: gỡ backtest panel khỏi subscription. (backtest-panel components có thể tái dùng cho UI single-run phase 5 — KHÔNG xóa vội, đánh dấu để phase 5 dùng lại.)
- `use-subscriptions.ts`: bỏ poll backtest-status (`:23,:36` keyed `'running'`); subscription poll chỉ còn forward state nếu có.
- `backtest-api.ts`: `SubscriptionBacktest` + `useSubscriptionBacktest` xóa; `BacktestStatus` chuyển dùng cho single-run (phase 5).
- C6: chỉ sửa backtest consumers. KHÔNG đụng `forward-status-badge.tsx`, `status-dot.tsx`, `job-history.ts`, `market-data.ts`, `use-available-intervals.ts`.

## Related Code Files

- Modify: `app/routes/backtest.py` — xóa `run_all_backtests` route.
- Modify: `app/routes/strategy.py` — xóa `get_subscription_backtest` route (`:148`).
- Modify: `backtest/backtest_command_service.py` — xóa `run_all`, `RunAllBacktestsCommand`.
- Modify: `backtest/backtest_query_service.py` — xóa `get_subscription_backtest` + `GetSubscriptionBacktestQuery`.
- Modify: `backtest/workers/backtest_dispatch.py` — xóa `run_subscription` + deps không dùng (subscription_repo nếu chỉ run_subscription dùng).
- Modify: `core/infra/persistence/repositories/backtest_repository.py` — xóa subscription cache methods.
- Modify: `engine/strategy_command_service.py` — gỡ `BacktestRequestRepository` dep + 2 cascade-delete call (C3).
- Modify: `app/di/trading_services.py` — update StrategyCommandService wiring.
- Delete: `repositories/backtest_request_repository.py` (sau C3 gỡ); `core/domain/backtest/request.py`.
- Modify: `app/di/persistence.py` — xóa `backtest_request_repository` provider.
- Modify: `core/common/constants.py` — xóa `COLLECTION_BACKTEST_REQUESTS`.
- Modify: `core/domain/backtest/__init__.py` — xóa export `BacktestRequest`.
- Modify (FE): `web/src/components/strategies/dashboard-column.tsx`, `web/src/components/strategy/subscription-panel.tsx`, `web/src/components/strategies/strategy-card.tsx`, `web/src/hooks/use-subscriptions.ts`, `web/src/api/backtest-api.ts`, `web/src/api/strategy-api.ts`.
- Read (không sửa, C6 guard): `forward-status-badge.tsx`, `status-dot.tsx`, `types/job-history.ts`, `types/market-data.ts`, `hooks/use-available-intervals.ts`.

## Implementation Steps

1. Backend: xóa `run-all-backtests` route + command. Test.
2. C3: gỡ `BacktestRequestRepository` dep khỏi `StrategyCommandService` + cascade calls; update DI. Boot test.
3. Xóa `run_subscription`, `get_subscription_backtest` route/query, subscription cache methods repo.
4. Xóa `BacktestRequestRepository` + `request.py` + provider + const + export. `lint-imports` + grep sạch `backtest_request`.
5. FE: gỡ backtest khỏi subscription card (dashboard-column, subscription-panel, strategy-card, use-subscriptions, api). Giữ forward.
6. C6 verify: `grep -rn "'running'\|'completed'" web/src` → các match còn lại CHỈ thuộc forward/job/sync domain (không đụng).
7. `pytest` + `cd web && npm run lint && npm run build` → xanh.
8. Manual: subscription card chỉ hiện forward-testing; start/stop/positions/trades vẫn hoạt động.

## Success Criteria

- [x] `/subscriptions/{id}/backtest` + `run-all-backtests` xóa (snapshot regen confirm); subscription thuần forward.
- [x] C3: `StrategyCommandService` gỡ `BacktestRequestRepository` dep + cascade; `BacktestRequestRepository`/`request.py`/`COLLECTION_BACKTEST_REQUESTS` xóa; app boot OK (48 routes).
- [x] Forward-testing (start/stop/positions/trades/reconcile) KHÔNG đổi code — `strategy_command_service.start/stop/add_symbol` + reconcile nguyên vẹn.
- [x] FE subscription card không còn backtest panel/badge; `strategy-card` + `dashboard-column` chuyển sang forward state; `npm run build` xanh.
- [x] C6: `forward-status-badge`/`status-dot`/`job-history`/`market-data`/`use-available-intervals` KHÔNG đổi (git status trống); chỉ backtest consumers sửa.
- [x] `lint-imports`(7)/`pytest`(594 passed)/`npm run lint`(0 errors)/`npm run build` xanh.

## Risk Assessment

- **Risk (C3)**: xóa repo trước khi gỡ dep → boot fail. Mitigation: thứ tự step 2 trước step 4.
- **Risk**: `run_subscription` xóa nhưng dispatch deps (subscription_repo) còn ref nơi khác. Mitigation: grep refs trước xóa.
- **Risk (C6)**: gỡ backtest FE đụng forward state dùng chung component. Mitigation: forward-status-badge tách riêng (đã verify); chỉ sửa backtest consumers.
- **Risk**: backtest-panel components xóa nhầm (phase 5 cần). Mitigation: KHÔNG xóa backtest-panel/*, chỉ gỡ khỏi subscription mount; phase 5 tái dùng.
- **Risk**: forward-testing regression. Mitigation: KHÔNG động code forward; manual smoke start/stop.
