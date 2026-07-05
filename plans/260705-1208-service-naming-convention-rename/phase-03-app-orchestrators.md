# Phase 3 — Application Orchestrators

**Priority:** P2 · **Risk:** med (một số qua DI) · **Status:** completed

## Overview
Kéo 4 orchestrator lệch chuẩn về `*AppService`. Đây là các stateful orchestrator/event-subscriber đang mang suffix sai (`Collector`/`Service`/`Manager`/`Sandbox`).

## Rename mapping
| Current class | New class | Current file | New file | refs |
|---|---|---|---|---|
| `BacktestResultCollector` | `BacktestResultAppService` | `backtest/engine/result_collector.py` | `backtest_result_app_service.py` | 6 |
| `StrategyReconcileService` | `StrategyReconcileAppService` | `engine/app_services/strategy_reconcile_service.py` | `strategy_reconcile_app_service.py` | 6 |
| `WsSubscriptionManager` | `WsSubscriptionAppService` | `app/market_data/app_services/ws_subscription_manager.py` | `ws_subscription_app_service.py` | 3 |
| `BacktestSandbox` | `BacktestSandboxAppService` | `backtest/engine/backtest_engine_sandbox.py` | `backtest_sandbox_app_service.py` | 2 |

## Implementation steps
1. Rename class + `git mv` file (4 cái).
2. Cập nhật DI provider nếu inject: kiểm tra `app/di/*.py` (`services.py`, `trading_services.py`, `backtest_worker.py`) — sửa provide return-hint + `FromDishka[…]` tại routes/consumers.
3. `BacktestResultCollector`: dùng bởi `backtest_app_service.py` (khởi tạo trực tiếp) + tests. `BacktestSandbox`: dùng bởi worker/tests.
4. `WsSubscriptionManager`: kiểm tra WS route + lifespan wiring.
5. `StrategyReconcileService`: reconcile loop (lifespan singleton) — cập nhật đăng ký event-handler + lifespan init.

## Gotchas
- **Overlap MAE/MFE plan**: `result_collector.py` + `backtest_engine_sandbox.py`. Rename trước để plan kia dùng tên mới.
- `StrategyReconcileService` là singleton khởi tạo trong lifespan (reconcile loop in-process) — không đổi thứ tự wiring, chỉ đổi tên.
- Event-handler registry (`registry.register_instance`) — cập nhật nếu tham chiếu class.

## Verify
- `just test` · `import-linter` · `pyright` → xanh.
- Commit: `refactor(naming): orchestrators → *AppService`

## Todo
- [x] BacktestResultCollector → BacktestResultAppService
- [x] StrategyReconcileService → StrategyReconcileAppService
- [x] WsSubscriptionManager → WsSubscriptionAppService
- [x] BacktestSandbox → BacktestSandboxAppService
- [x] Cập nhật DI provider + lifespan wiring + event-handler registry
- [x] pytest + import-linter + pyright xanh

## Success criteria
Test/lint/type xanh; reconcile loop + WS subscription + backtest run hoạt động; refs tên cũ = 0.
