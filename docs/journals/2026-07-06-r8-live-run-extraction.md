# R8: Live-Run Extraction + Live Trade Pipeline

**Date**: 2026-07-06 08:55
**Severity**: Medium
**Component**: engine/live, engine/market_data, core/infra/brokers, live Trade pipeline, metrics route
**Status**: Completed

---

## What Happened

Hàng cuối initiative `trading-calulation-fix` (R1–R8 giờ **done**). Brainstorm reframe: R2 đã tách ~80% structure nên R8 không còn là "trích orchestration khổng lồ" — giá trị thật là **pipeline Trade/metrics cho live** (trước đây live chỉ đọc closed Positions, chưa từng có `Trade`/equity/metrics).

Hai track:

**Structure (move thuần, gate xanh liên tục):**
- `BrokerFactory` `app/di/` → `core/infra/brokers/broker_factory.py` (framework-free, chỉ import core).
- `QuoteAppService` + `WsSubscriptionAppService` `app/market_data/` → `engine/market_data/app_services/`.
- Fold `rehydrate_strategies_from_subscriptions` → `StrategyReconcileAppService.bootstrap()` (reuse `_ensure_instances` → boot path và steady-state path không drift). App lifespan giờ thin driver: `inject → bootstrap_live_instances → create_task(reconcile.run) → cancel`.

**Logic (M1 relative-per-sub, giá trị lõi):**
- `TradeRepository` (`trades` collection, `run_id`=subscription_id) — mirror mảnh nhỏ backtest repo, reuse `Trade.to_mongo/from_mongo`.
- `LiveTradeCollector` — EventBus subscriber (`_on_trade_closed`), build `Trade` + persist. Broker→bus qua `StrategyAppService._forward_trade_to_bus`, wire trong `_get_or_create_broker` (**live-only** — backtest `inject_prepared_strategy` bypass → không double-count).
- `LiveMetricsQueryService` + route `GET /api/v1/subscriptions/{id}/metrics` — on-demand, stateless, cumsum-pnl equity.
- OKX `subscribe_trades` giữ no-op (defer future R — cần demo fill payload verify snapshot-delta).

Gate: `just test` 571 pass (+9 test R8), ruff/pyright/lint-imports (8 contract) sạch.

---

## The Brutal Truth

**Hai chỗ suýt sai, code-reviewer bắt được:**

1. **Sharpe phóng đại hàng trăm lần (HIGH).** Ban đầu tôi truyền `periods_per_year = Interval.periods_per_year_for(sub.interval)` = bars/năm (1m → 525,600) như backtest. Nhưng backtest annualize trên curve **per-bar** (mtm_curve đều); live curve của tôi là **trade-keyed** (1 điểm/closure). Annualize per-trade returns bằng √(bars/năm) → Sharpe sai lệch tens–hundreds×. Tệ hơn: path này **chưa được test** vì cả 2 test metrics đều không seed subscription doc → `sub=None` → `periods_per_year=None` → Sharpe=0 → bug ẩn. Fix KISS: trade-keyed curve **không** annualize được bằng bar-freq → `periods_per_year=None` luôn (Sharpe=0, đúng convention "not annualizable"); bỏ luôn `sub_repo` giờ thành dead dependency. Thêm test khoá Sharpe=0.

2. **Collector thiếu error boundary (MEDIUM).** `save_many` unguarded — Mongo lỗi transient sẽ propagate qua `_forward_trade_to_bus` → paper broker `_notify_trade_callbacks` (`raise errors[0]`) → làm hỏng các subscriber `BarCompletedEvent` còn lại của tick đó + mất Trade. Mọi sibling bus handler đều wrap+log; collector phải khớp. Fix: try/except + log `subscription_id`/`pnl` + swallow.

**Chỗ tự bắt được lúc implement:** plan viết handler tên `on_trade`, nhưng `EventRegistry.register_instance` chỉ quét method bắt đầu bằng **một** `_` (`startswith("_") and not "__"`) → phải đặt `_on_trade_closed` mới discover được. Nếu theo plan literal thì collector sẽ câm lặng không nhận event nào.

**Quyết định baseline drawdown:** plan gợi ý `initial_capital = 0`, nhưng `max_drawdown` chia cho running peak — baseline 0 với trade đầu thua → `(neg)/0 = -inf` → `np.nan_to_num` mặc định biến `-inf` thành `-1.79e308` (drawdown rác, không phải nan). Neo curve tại `paper_initial_balance` (dương, số account thật) → mẫu số luôn > 0 → drawdown hữu hạn. Vẫn omit `total_return`/`cagr` (per-sub %-of-shared-account gây hiểu lầm). Regression test khoá lại.

---

## Lessons

- **Reuse ≠ copy tham số một cách mù quáng.** `PerformanceCalculatorDomainService.build` dùng chung backtest + live, nhưng `periods_per_year` phụ thuộc *hình dạng curve* (per-bar vs trade-keyed) — không phải copy nguyên si từ caller khác.
- **np.nan_to_num mặc định KHÔNG chỉ xử nan** — nó cũng biến ±inf thành ±1.79e308. Div-by-zero trên equity curve tạo inf, không phải nan → guard bằng baseline dương thay vì trông chờ nan_to_num.
- **register_instance scan `_`-prefix** là một cái bẫy ngầm cho mọi bus subscriber mới — handler public (`on_x`) sẽ không bao giờ được đăng ký.
- Tách 2 kênh Trade (backtest callback trực tiếp vs live bus-forward) là chìa khoá tránh double-count — verified bằng test chạy backtest parity + integration test broker→bus.

---

## Unresolved

- Live Sharpe hiện = 0 (không annualize). Nếu product cần Sharpe live thật → thêm per-bar equity sampler cho live (ngoài scope R8).
- OKX-backed subscription persist zero trade → `/metrics` trả zeros mãi, không tín hiệu. Chờ R tương lai wire OKX position→Trade (cần demo payload).
- Soft-coupling `260630-0031-backtest-mae-mfe-excursion`: append `mae/mfe/r_multiple` vào `Trade`+`TradeClosedEvent` → live collector sẽ để field excursion = None, rebase nhẹ khi bên đó land.
