# R1 Domain Consolidation — Code Review (structure-only, zero-drift verification)

**Verdict: CLEAN PURE-MOVE. Zero behavioral drift. No blocking defects.**

Scope: verify moves/renames of domain VOs + calculator fold introduced NO logic change and NO DB-shape change. Method: `git show HEAD:` vs new files (byte diff), import smoke test, import-linter, targeted test run (incl. real-Mongo roundtrips).

## Criteria results

### 1. DB compat (HIGHEST) — PASS
`to_mongo`/`from_mongo` field shape byte-identical vs HEAD for all moved classes:
- Trade, Fill, EquityPoint, PerformanceMetrics (ex-BacktestMetrics): trading/value_objects.py bodies verbatim vs old backtest/value_objects.py (only class name BacktestMetrics→PerformanceMetrics; `.empty()`/`to_dict()`/`from_mongo` unchanged).
- OrderRecord (ex-Order): order/records.py to_mongo/from_mongo verbatim vs old Order (keys `_id, run_id, strategy_code, symbol, side, order_type, quantity, price, sl_price, tp_price, status, submitted_at, last_updated_at, events, fills, resulting_trade_id` identical; embedded-fill `order_id`-drop preserved).
- OpenLot: stayed in backtest/value_objects.py, unchanged.
- BacktestResult.metrics embeds PerformanceMetrics — same on-disk shape (`avg_trade_duration_seconds` etc).
- Real-Mongo testcontainer roundtrips pass (test_order_repository, test_trade_repository, test_backtest_repository_slimmed).

### 2. `.build` fold — PASS
New `PerformanceCalculatorDomainService.build` (staticmethod) is line-for-line identical to DELETED `metrics_builder.build_metrics`: same 9 kwargs, same order, same math (equity_values/returns_source/days/sharpe/sortino/pnl_list/gross_profit/gross_loss/avg_duration), same `_avg_trade_duration` helper (now module-level in same file, `>0` filter preserved), only return type BacktestMetrics→PerformanceMetrics. Call site backtest_result_app_service.py:421 passes all kwargs correctly.

### 3. Calculator + trade_stats math — PASS
- performance_calculator body (methods lines 1–245: TRADING_DAYS_PER_YEAR/RISK_FREE_RATE, sharpe/sortino/total_return/cagr/max_drawdown/win_rate/profit_factor/average_win_loss) UNCHANGED — diff shows only ADDED lines (future import, datetime import, trading import, `.build`, `_avg_trade_duration`); nothing deleted/modified.
- trade_stats.py identical to old trade_stats_calculator.py except ONE line: EquityPoint import path backtest→trading. All 4 funcs (histogram, win_loss_streaks, profit_factor_by_direction, drawdown_periods) verbatim.

### 4. Import cycle — PASS
records.py imports Fill only under TYPE_CHECKING + lazily inside `from_mongo` (runtime). Module-level imports = order.enums + brokers.events (brokers.events imports only order.enums, a leaf → no back-edge). Smoke test importing order pkg FIRST (worst case) succeeds; OrderRecord.from_mongo resolves Fill at runtime. No new cycles.

### 5. Rename completeness — PASS
Zero leftovers in src/ and tests/ for: BacktestMetrics, build_metrics, metrics_builder, backtest.models, backtest.domain.services, trade_stats_calculator. All bare-`Order` matches are English-word comments or `order` locals — none reference the moved class. Deleted trees confirmed gone. `__init__` exports correctly re-homed (trading: EquityPoint/Fill/PerformanceMetrics/Trade/PerformanceCalculatorDomainService; order: +OrderRecord; backtest: BacktestConfig/BacktestResult/OpenLot).

### 6. import-linter — PASS
7 kept / 0 broken (225 files, 870 deps). Cross-imports within core.domain (trading↔backtest↔order) allowed; numpy in core.domain.trading fine.

## Non-blocking nits (trivial, optional)
- backtest_query_service.py:69 docstring says "not via `Order.to_mongo()`" — file NOT modified by R1, so this is a pre-existing doc reference now conceptually stale (Order→OrderRecord). Cosmetic only.
- BacktestConfig moved backtest/models/backtest_config.py → core/domain/backtest/config.py: `diff` reports IDENTICAL.

## Other checks
- collected_results.py, backtest_app_service.py, historical_replay_app_service.py, backtest_strategy_loader.py, backtest_dispatch.py, backtest_stats_service.py, entities.py, both repos: diffs are import-repath + type-annotation rename ONLY, no logic drift.
- Targeted suite: 69 passed (roundtrip, uuid-id, ann­ualization, trade_stats, order/trade repos).

## Unresolved questions
- None.
