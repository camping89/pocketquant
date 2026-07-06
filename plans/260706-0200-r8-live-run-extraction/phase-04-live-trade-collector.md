# Phase 4 — LiveTradeCollector + broker→bus wiring

**Context:** [plan.md](./plan.md) · [phase-03](./phase-03-trade-repository.md)
**Priority:** P2 · **Status:** Done · **Track:** logic (core value)

## Overview

Live analog của `BacktestReportAppService` — nhưng **continuous + incremental + N-sub share 1 broker**. Collector là **EventBus subscriber**: `TradeClosedEvent` (mang `subscription_id`) → build `Trade` (`run_id←subscription_id`, `strategy_code←resolve`) → `TradeRepository.save_many([trade])`. Model M1: collector CHỈ persist Trade; equity/metrics derive on-demand ở Phase 5 (KISS — không giữ equity ledger).

## Key insights

- **Attribution giải sẵn:** `TradeClosedEvent.subscription_id` + `.symbol` có sẵn (`position/events.py:49-50`); paper broker key `f"{subscription_id}:{symbol}"`.
- **Wiring broker→bus:** `StrategyAppService._get_or_create_broker` (live path) — sau khi tạo broker, `await broker.subscribe_trades(self._forward_trade_to_bus)`. `_forward_trade_to_bus(event)` = `await self._event_bus.publish(event)`. Backtest dùng `inject_prepared_strategy` (bypass `_get_or_create_broker`) → **KHÔNG** wire bus → backtest collector (subscribe callback trực tiếp) không đổi. **2 kênh tách.**
- **Collector là bus subscriber:** `@event_handler(TradeClosedEvent) async def on_trade(...)`. `start()` gọi `registry.register_instance(self, event_bus)` (mirror `StrategyAppService.start`). Lifespan start collector (thin driver).
- **strategy_code resolve:** `StrategyAppService.get_config(sub_id).name` (in-memory, = `sub.strategy_code`; free, không Mongo). Inject `StrategyAppService` vào collector.
- **Trade build:** reuse mapping trong `BacktestReportAppService.on_trade:119-137` (cùng field từ `TradeClosedEvent`). Cân nhắc extract helper `trade_from_closed_event(event, run_id, strategy_code)` vào `core.domain.trading` (DRY giữa backtest + live) — YAGNI check: nếu chỉ 2 caller, extract đáng.

## Related code files

**Create:**
- `src/pocketquant/engine/live/live_trade_collector.py` — `class LiveTradeCollector`.

**Touch:**
- `src/pocketquant/engine/strategy/strategy_app_service.py` — `_get_or_create_broker` wire `subscribe_trades → bus`; thêm `_forward_trade_to_bus`.
- `src/pocketquant/app/di/execution.py` (hoặc live provider) — provide `LiveTradeCollector` (APP scope).
- `src/pocketquant/app/main_extensions.py` + `main.py` — `start_live_collector(container)` gọi `collector.start()` trong lifespan (sau bootstrap, quanh reconcile start).
- (option) `src/pocketquant/core/domain/trading/` — helper `trade_from_closed_event` nếu extract.

## Implementation steps

1. `LiveTradeCollector.__init__(event_bus, trade_repo, strategy_service)`. `start()` register `@event_handler` lên bus. `on_trade(event)`: resolve `strategy_code = strategy_service.get_config(event.subscription_id).name or ""`; build `Trade(trade_id=generate_id(), run_id=event.subscription_id, strategy_code=..., ...event fields)`; `await trade_repo.save_many([trade])`.
2. `StrategyAppService`: thêm `async def _forward_trade_to_bus(self, e): await self._event_bus.publish(e)`. Trong `_get_or_create_broker` sau khi `broker = self._broker_factory.create(...)`: `await broker.subscribe_trades(self._forward_trade_to_bus)`. (Chỉ live path — backtest bypass.)
3. DI provide `LiveTradeCollector`. Lifespan `start_live_collector` gọi `collector.start()` (unconditional hoặc gate enable_jobs? → gate `enable_jobs` giống reconcile: collector chỉ có ích khi runtime chạy; nhưng persist trade nên chạy nếu có live → GATE `enable_jobs` cho nhất quán với reconcile/feed).
4. Test: paper broker close position (round-trip) → collector persist Trade với `run_id`=sub_id, pnl/commission khớp `TradeClosedEvent`. Verify backtest collector KHÔNG nhận double event (bus vs callback tách).
5. Gate xanh.

## Todo

- [x] `LiveTradeCollector` (bus subscriber → build Trade → persist)
- [x] `_forward_trade_to_bus` + wire trong `_get_or_create_broker` (live-only)
- [x] DI provide + lifespan `start_live_collector` (gate enable_jobs)
- [x] (option) extract `trade_from_closed_event` helper nếu DRY đáng
- [x] Test: round-trip close → Trade persisted; backtest không double
- [x] Gate xanh

## Success criteria

- Live paper subscription đóng trade → 1 `Trade` doc trong `trades` (`run_id`=sub_id, pnl/commission avg-cost đúng).
- Backtest parity 560 test KHÔNG đổi (bus-forward chỉ ở live path).
- Gate xanh; engine không import fastapi.

## Risk assessment

- **Double-count backtest:** rủi ro chính. Bus-forward CHỈ ở `_get_or_create_broker` (live); backtest `inject_prepared_strategy` bypass → an toàn. **Test khóa:** chạy 1 backtest, assert số Trade không đổi.
- **Broker lazy-create timing:** collector-as-bus-subscriber né được (không cần biết lúc broker tạo). Bus publish sau khi broker có callback.
- **`await` trong publish:** `_forward_trade_to_bus` async; paper broker `_notify_trade_callbacks` await callback → OK (đã async). Đảm bảo không nằm trong lock broker (dispatch ngoài lock — R5 verified).
- **get_config None:** sub chưa load → `get_config` None → `strategy_code=""`. Chấp nhận (rare); Trade vẫn persist với run_id.

## Next steps

→ Phase 5 (metrics query đọc trades này + build).
