# Phase 5 — LiveMetricsQueryService + metrics route

**Context:** [plan.md](./plan.md) · [phase-04](./phase-04-live-trade-collector.md)
**Priority:** P2 · **Status:** Done · **Track:** logic (M1 read side)

## Overview

On-demand metrics per subscription. Đọc `Trade` từ `TradeRepository.list_by_subscription`, dựng **relative equity curve** (M1: cumsum pnl), gọi `PerformanceCalculatorDomainService.build`, trả `PerformanceMetrics` DTO. Route `GET /subscriptions/{id}/metrics`. Stateless — không giữ state ở collector.

## Key insights

- `PerformanceCalculatorDomainService.build(closed_trades, equity_curve, initial_capital, current_equity, total_commission, start_date, end_date, periods_per_year, returns_curve)` — xem `backtest_report_app_service.finalize:379`.
- **M1 equity curve:** từ trades sort `entry_time`, cumsum `pnl` → `EquityPoint(timestamp=trade.exit_time, equity=baseline+cum_pnl)`. Drawdown recompute (mirror `_with_drawdown`).
- **baseline (còn mở → chốt ở đây):** live subs share account, không có per-sub initial thật.
  - Nếu strategy config có risk capital per-sub → dùng làm `initial_capital`.
  - Nếu KHÔNG → set `initial_capital = 0` + BỎ các metric %-relative (total_return/cagr = None/omit), GIỮ absolute pnl + trade-derived (win rate/profit factor/expectancy/avg win-loss) + drawdown (absolute $) + Sharpe (trên trade-return series). Tránh trả %-return sai lệch.
  - Quyết định KISS: **absolute + trade-derived + drawdown/Sharpe; omit %-return khi thiếu baseline.** Document rõ trong DTO (field null).
- `periods_per_year`: live không có interval cố định như backtest run → dùng `sub.interval` (`Interval.periods_per_year_for`) cho annualize Sharpe; None → skip annualize (warn) như backtest.
- `current_equity` = baseline + tổng pnl; `total_commission` = sum `trade.commission`.

## Related code files

**Create:**
- `src/pocketquant/engine/live/live_metrics_query_service.py` — `class LiveMetricsQueryService`.

**Touch:**
- `src/pocketquant/app/routes/strategy.py` — thêm `GET /subscriptions/{sub_id}/metrics` (DishkaRoute, `FromDishka[LiveMetricsQueryService]`).
- `src/pocketquant/app/di/` (execution/trading provider) — provide `LiveMetricsQueryService` (deps: `TradeRepository`, `SubscriptionRepository` để lấy `interval`/baseline).

## Implementation steps

1. `LiveMetricsQueryService.__init__(trade_repo, sub_repo)`. `async def get_metrics(subscription_id) -> dict`:
   - `trades = await trade_repo.list_by_subscription(sub_id)`; rỗng → trả metrics zero/empty (không lỗi).
   - `sub = await sub_repo.get(sub_id)` → `interval`, baseline (risk capital nếu có).
   - Build equity curve (cumsum pnl). `periods_per_year = Interval.periods_per_year_for(sub.interval)`.
   - `metrics = PerformanceCalculatorDomainService.build(...)`. Serialize DTO (mirror backtest metrics serialize; %-return field = None khi thiếu baseline).
2. Route `GET /subscriptions/{sub_id}/metrics` → `query_svc.get_metrics(sub_id)`.
3. DI provide query service.
4. Test: seed vài Trade cho 1 sub → route trả win rate/profit factor/drawdown đúng; sub rỗng → metrics rỗng không crash.
5. Gate xanh.

## Todo

- [x] `LiveMetricsQueryService.get_metrics` (relative equity M1, omit %-return khi thiếu baseline)
- [x] Route `GET /subscriptions/{id}/metrics`
- [x] DI provide
- [x] Test: trades→metrics đúng; empty→no crash; OpenAPI snapshot cập nhật nếu có
- [x] Gate xanh

## Success criteria

- Route trả `PerformanceMetrics` (trade-derived + drawdown/Sharpe; %-return null khi thiếu baseline).
- Empty subscription → metrics rỗng, HTTP 200.
- Gate xanh; engine không import fastapi (query service ở engine, route ở app).

## Risk assessment

- **%-return sai:** không có baseline thật → OMIT (null), không đoán. Rõ ràng hơn số sai.
- **OpenAPI snapshot:** thêm route → cập nhật snapshot baseline nếu test khóa OpenAPI (README nhắc snapshot). Chạy test phát hiện.
- **Sharpe trên ít trade:** <2 trade → annualize vô nghĩa; build đã guard (mirror backtest) → trả 0/None an toàn.

## Next steps

→ Phase 6 (closeout: OKX no-op confirm + docs/roadmap).
