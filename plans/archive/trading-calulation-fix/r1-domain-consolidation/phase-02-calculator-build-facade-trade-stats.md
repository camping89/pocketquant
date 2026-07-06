# Phase 02 — Move calculator + fold `build` facade + move `trade_stats` + xoá `metrics_builder`

**Priority:** P0 · **Status:** pending · **Depends:** P1
**Context:** [plan](plan.md) · nguồn `backtest/domain/services/*` + `backtest/engine/metrics_builder.py`

## Mục tiêu
Đưa metrics engine lên `core.domain.trading`: move `PerformanceCalculatorDomainService` (primitives, verbatim), **fold** `build_metrics`+`_avg_trade_duration` thành static `PerformanceCalculatorDomainService.build(...)`, move `trade_stats`, xoá `metrics_builder.py` + rewire consumer. Logic y hệt — chỉ đổi chỗ + gói namespace.

## Files
**Create**
- `core/domain/trading/performance_calculator_domain_service.py` — copy nguyên `PerformanceCalculatorDomainService` (numpy, consts `TRADING_DAYS_PER_YEAR`, `RISK_FREE_RATE`) **+ thêm** `@staticmethod build(...)` = body `build_metrics` (fold `_avg_trade_duration` thành module-private hoặc staticmethod). Signature **giữ nguyên kwargs** của `build_metrics`; return đổi type `BacktestMetrics`→`PerformanceMetrics`. Import `PerformanceMetrics, EquityPoint, Trade` từ `core.domain.trading.value_objects`.
- `core/domain/trading/trade_stats.py` — move nguyên `trade_stats_calculator.py` (dataclasses `HistogramBin/StreakStats/DirectionProfitFactor/DrawdownPeriod` + funcs `histogram/win_loss_streaks/profit_factor_by_direction/drawdown_periods`); `EquityPoint` import từ `.value_objects`.

**Modify**
- `core/domain/trading/__init__.py` — thêm export `PerformanceCalculatorDomainService` (+ trade_stats funcs nếu muốn expose; hoặc để consumer import từ submodule).
- `backtest/engine/backtest_result_app_service.py` — bỏ `from ...metrics_builder import build_metrics`; import `PerformanceCalculatorDomainService` từ `core.domain.trading`; dòng ~424 đổi `metrics = build_metrics(...)` → `metrics = PerformanceCalculatorDomainService.build(...)` (**cùng kwargs**); type `metrics: PerformanceMetrics`.
- `backtest/backtest_stats_service.py` — import trade_stats funcs từ `core.domain.trading.trade_stats`.

**Delete**
- `backtest/engine/metrics_builder.py`
- `backtest/domain/services/performance_calculator_domain_service.py`, `trade_stats_calculator.py`, `services/__init__.py`
- `backtest/domain/__init__.py` → cả thư mục `backtest/domain/` rỗng, xoá.

**Tests**
- `tests/backtest_test/domain/test_performance_calculator_annualization.py` → import từ `core.domain.trading`; cân nhắc chuyển `tests/core_test/unit/domain/trading/`.
- `tests/backtest_test/domain/test_trade_stats_calculator.py` → import `core.domain.trading.trade_stats`; chuyển tương tự.
- Nếu có test gọi `build_metrics` trực tiếp → đổi sang `PerformanceCalculatorDomainService.build`.

## Steps
1. Copy calculator → trading; verify numpy import + consts nguyên vẹn.
2. Fold `build_metrics` → `build` staticmethod (paste body, đổi return type `PerformanceMetrics`, chuyển `_avg_trade_duration` vào cùng module). Diff logic = 0.
3. Move `trade_stats.py`; fix EquityPoint import.
4. Rewire `backtest_result_app_service` (build call) + `backtest_stats_service` (trade_stats import).
5. Xoá metrics_builder + cả cây `backtest/domain/`.
6. Update tests (import + optional relocate).
7. Gates: `ruff && pyright && lint-imports && just test`.

## Success
- `grep -rn "metrics_builder\|backtest.domain.services\|build_metrics" src/` → rỗng.
- `PerformanceCalculatorDomainService.build(...)` trả `PerformanceMetrics`; `backtest_result_app_service` gọi nó; số backtest **không đổi** (so equity/metrics run `engulfing` trước-sau).
- `backtest/domain/` không còn tồn tại; 7 contracts + test xanh.

## Rủi ro
- `.build` giữ signature **backtest-specific** (initial_capital, current_equity, start_date, end_date, periods_per_year, returns_curve) — **cố ý**: tổng quát hoá source-agnostic là logic của R5, ngoài scope R1.
- Consumer R5 (`BacktestReportAppService`) sẽ thừa hưởng `.build` sạch → mục "xoá metrics_builder" của R5 thành đã-xong (ghi chú vào roadmap ở P5).
