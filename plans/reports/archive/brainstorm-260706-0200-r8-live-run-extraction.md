# Brainstorm — R8 Live-Run Extraction + Live Trade Pipeline

> Scope chốt (session): **B** — structural extraction + live Trade collector (paper); **thin app driver**; relocation rộng (BrokerFactory + WsSubscription/QuoteAppService xuống engine). OKX emission giữ no-op (cần demo payload).

## Problem statement

R8 (roadmap `plans/trading-calulation-fix/roadmap.md`, track hybrid, dep R2 ✅). Title: *trích live-run orchestration từ app vào `engine/live/` framework-free; app giữ runtime driver*. Kèm nợ R4: OKX `subscribe_trades` no-op + live-value map (`subscription_id`→`Trade.run_id`).

**Reframe brutal (findings):**
1. **R2 đã tách ~80% cấu trúc.** `StrategyReconcileAppService` đã framework-free trong `engine/live`; chỉ còn task-lifecycle + DI construct ở app. Reconcile là **plain asyncio task, KHÔNG chạy scheduler** → "không kéo scheduler xuống" là non-issue (chưa từng coupling). Engine đã fastapi-clean.
2. **Giá trị thật = pipeline Trade/metrics của live — chưa tồn tại.** Live đọc *closed Positions* (`get_trades`→`position_repo.find_closed_by_subscription`), không `Trade` VO, không equity curve, không `PerformanceCalculatorDomainService.build`. Backtest thì có đủ. Đây là gap của vision "backtest & live = 2 driver, 1 engine + 1 metrics".
3. **Attribution R4 lo ngại đã giải sẵn:** `TradeClosedEvent` mang `subscription_id` + `symbol` (`position/events.py:49-50`); paper broker key position theo `f"{subscription_id}:{symbol}"`. Live collector attribute từng trade qua `event.subscription_id`.

## Boundary verdict (câu hỏi gốc)

**Litmus test:** unit thuộc `engine/live` iff dựng+chạy chỉ với (repos, engine services, event bus, asyncio loop) — không FastAPI object, không container, không scheduler handle.

| Mảnh | Nay | Verdict R8 |
|---|---|---|
| Reconcile control-loop (`run`/ensure/converge) | `engine/live/strategy_reconcile_app_service.py` | ✅ đã ở engine (R2) |
| `rehydrate_strategies_from_subscriptions` | `app/main_extensions.py:121` | 🔶 fold → `engine/live` (đổi chữ ký: nhận `sub_repo`+`strategy_service`, bỏ `AsyncContainer`); dedup với `_ensure_instances` |
| Task driver `start/stop_reconcile_loop` | `app/main_extensions.py:223` | ⛔ **ở app** (thin driver: `create_task`/cancel + `enable_jobs` gate) |
| WS feed / scheduler / DI / lifespan | app | ⛔ ở app |
| `BrokerFactory` | `app/di/broker_factory.py` | 🔶 move → `core/infra/brokers/broker_factory.py` (implements `IBrokerFactoryPort`, zero fastapi) |
| `QuoteAppService` + `WsSubscriptionAppService` | `app/market_data/app_services/` | 🔶 move → `engine/market_data/app_services/` (framework-free, cạnh `bar_app_service`) |
| **Live Trade collector** | KHÔNG có | 🆕 tạo `engine/live/` |
| OKX `subscribe_trades` | `okx:287` no-op | ⏸ giữ no-op (external dep: demo payload) |

**Cut app↔engine (thin app driver):** app lifespan chỉ `inject deps → svc.bootstrap() → create_task(svc.run()) → cancel on shutdown`. Engine expose service thuần. Không đảo ngược ownership event loop.

## Live Trade collector — thiết kế

Khác backtest collector (discrete run, `finalize()→CollectedResults`): live **continuous**, persist **incremental**, **N subscription share 1 paper broker**.

```
paper broker (shared, lazy)          engine/live/live_trade_collector.py       core.infra repo
  reduce_quantity → TradeClosedEvent ────────────────► on_trade(event)
     (carries subscription_id+symbol)                    build Trade(run_id=event.subscription_id,
                                                                      strategy_code=resolve(sub_id))
                                                          persist → trades collection (incremental)
                                                          update per-sub equity accumulator
GET /subscriptions/{id}/metrics ──► LiveMetricsQueryService.build(trades, equity) [on-demand, stateless]
```

**Wiring TradeClosedEvent → collector** (broker lazy+shared): route qua **EventBus** — `StrategyAppService` khi tạo broker gọi `broker.subscribe_trades(lambda e: bus.publish(e))`; collector là **EventBus subscriber** (`@event_handler(TradeClosedEvent)`), khớp design event-driven sẵn có của engine. Tránh collector phải biết thời điểm broker được tạo.

**subscriber-stamp (R4 pattern):** `run_id ← event.subscription_id`, `strategy_code ← sub_repo/config lookup theo subscription_id` (cache sub_id→code).

**Persistence:** `TradeRepository` (live) → collection `trades` (mirror `BacktestTradeRepository`/`backtest_trades`). Live orders KHÔNG duplicate (đã persist qua order path). Read path `get_trades` (closed positions) **giữ nguyên** — B không migrate (đó là C); thêm route metrics mới đọc `trades`.

### Fork còn lại — equity/metrics accounting model

Shared paper broker có **1 `_balance` portfolio-wide** cho mọi sub → `broker.get_balance()` không cho equity per-sub. 3 lựa chọn:

| Model | Cách | Metrics ra được | Churn | YAGNI |
|---|---|---|---|---|
| **M1 Relative-per-sub (KHUYẾN NGHỊ)** | equity curve per sub = cumsum(trade pnl) từ baseline (risk capital cấu hình / nominal). Collector giữ accumulator per sub. | Trade-derived FULL (win rate, profit factor, avg win/loss, expectancy, gross/net) + drawdown + Sharpe trên chuỗi trade-return. total_return% vs baseline cấu hình. | Nhỏ — chỉ collector + query svc | ✅ ~90% giá trị, không đụng broker model |
| **M2 Per-sub broker** | `_get_or_create_broker` key theo `sub.id` (không theo type); mỗi sub 1 `PaperBrokerAdapter` + initial_balance riêng. Collector đọc balance sub. | FULL parity y hệt backtest (kể cả account-based return/cagr) | Lớn — đổi broker lifecycle + SL/TP auto-fill routing + connect/disconnect per sub | ⚠ đúng nhất nhưng surgery; chưa có live trading |
| **M3 Portfolio-only** | 1 metrics cho cả account live, không per-sub | Metrics account tổng | Nhỏ nhất | ❌ mất per-sub — trái UX subscription hiện tại |

## Approaches (structural)

- **A structural-only** — chỉ fold rehydrate. Bỏ vì defer R4 lần 2 (user loại).
- **B (chọn)** — structural + live collector paper + relocation. OKX no-op.
- **C full parity** — B + OKX real emission + migrate read path. Loại: OKX cần demo payload (external), migrate read = risk build persistence chưa ai query.

## Related code files

**Move (pure, test giữ xanh):**
- `app/di/broker_factory.py` → `core/infra/brokers/broker_factory.py` (rewire `app/di/infrastructure.py`, `app/di/execution.py`)
- `app/market_data/app_services/quote_app_service.py` → `engine/market_data/app_services/quote_app_service.py`
- `app/market_data/app_services/ws_subscription_app_service.py` → `engine/market_data/app_services/ws_subscription_app_service.py` (rewire `app/di/market_data.py`, `app/main_extensions.py` import)

**Fold:**
- `rehydrate_strategies_from_subscriptions` (`main_extensions.py:121`) → method `bootstrap()`/`ensure_all` trên `StrategyReconcileAppService` (hoặc shared helper); app gọi `svc.bootstrap()` trước `create_task(svc.run())`.

**Create:**
- `engine/live/live_trade_collector.py` — `LiveTradeCollector` (EventBus subscriber → build Trade → persist)
- `engine/live/live_metrics_query_service.py` — `LiveMetricsQueryService.get_metrics(subscription_id)` (on-demand build)
- `core/infra/persistence/repositories/trade_repository.py` — `TradeRepository` (collection `trades`)
- route `GET /subscriptions/{id}/metrics` (`app/routes/strategy.py`)
- DI: provide collector (APP scope, start in lifespan) + query service + repo

**Touch:**
- `engine/strategy/strategy_app_service.py` — khi tạo broker, wire `subscribe_trades → bus.publish` (M1); nếu M2: đổi `_get_or_create_broker` key theo sub.id
- `app/main.py` / `main_extensions.py` — start collector (thin driver), fold rehydrate call
- `core/infra/brokers/okx/okx_broker_adapter.py` — giữ no-op, comment trỏ future R

## Invariants giữ

- import-linter 8 contract xanh: BrokerFactory ở `core.infra` (infra→domain OK); collector/query ở engine (engine→core OK); `fastapi only in app`. Move Quote/WsSubscription xuống engine phải KHÔNG kéo import app nào (verify trước move).
- Parity: paper khớp lệnh dùng chung PaperBrokerAdapter — M1 KHÔNG đụng; M2 đụng broker keying (cần re-verify backtest parity 560 test).
- `just test` + ruff + pyright + lint-imports xanh sau mỗi move (structure track: move thuần, test xanh liên tục).

## Risks

- **Move Quote/WsSubscription:** kiểm forward-ref circular (`ws_subscription` ref `QuoteAppService` qua string) + import app-only nào (nếu có → chặn move, giữ app). Verify bằng `lint-imports` + `pytest` ngay sau.
- **EventBus double-dispatch:** broker publish TradeClosedEvent lên bus — đảm bảo backtest (dùng subscribe_trades trực tiếp) KHÔNG bị ảnh hưởng (collector live subscribe bus; backtest collector subscribe broker callback — 2 kênh tách).
- **M1 baseline ambiguity:** total_return% cần baseline per-sub; nếu không cấu hình → chỉ report absolute pnl + trade-derived metrics (bỏ %-return), tránh số sai lệch.
- **Broker lazy-create timing:** collector-as-bus-subscriber né được; nếu chọn direct-subscribe phải hook lúc `_get_or_create_broker`.

## Success criteria

- `engine/live` chứa reconcile + bootstrap + live collector + metrics query; app lifespan chỉ inject+create_task+cancel.
- Live paper subscription đóng trade → `trades` collection có Trade doc (run_id=sub_id, pnl/commission đúng avg-cost).
- `GET /subscriptions/{id}/metrics` trả PerformanceMetrics (trade-derived + drawdown/Sharpe theo model chọn).
- 8 import-linter contract xanh; 560 parity test xanh; ruff/pyright xanh.
- BrokerFactory + Quote/WsSubscription ở engine/core, zero fastapi import trong engine.

## Decisions locked (session)

1. **Equity model = M1 relative-per-sub.** Collector giữ accumulator per sub; metrics = trade-derived FULL + drawdown + Sharpe trên chuỗi trade-return. KHÔNG đụng broker keying/parity.
2. **Metrics endpoint = có ngay.** `GET /subscriptions/{id}/metrics` đọc `trades` → `PerformanceCalculatorDomainService.build`. Live subscription có performance report như backtest.
3. **QuoteAppService + WsSubscription → `engine/market_data/app_services/`** (cạnh `bar_app_service`, đúng feature-area).
4. **OKX emission** giữ no-op (external dep: demo payload) — defer future R.

## Còn mở (giải trong plan)

- **total_return% baseline** (M1): baseline per-sub lấy từ risk capital cấu hình per-strategy; nếu không có → report absolute pnl + trade-derived + drawdown/Sharpe, BỎ %-return (tránh số sai). Chốt cụ thể khi làm phase collector/metrics.
