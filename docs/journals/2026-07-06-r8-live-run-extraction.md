# R8: Live-Run Extraction + Live Trade Pipeline

**Date**: 2026-07-06 08:55
**Severity**: Medium
**Component**: engine/live, engine/market_data, core/infra/brokers, live Trade pipeline, metrics route
**Status**: Completed

---

## What Happened

Last item in the `trading-calulation-fix` initiative (R1–R8 now **done**). Brainstorm reframe: R2 already extracted ~80% of the structure so R8 is no longer "extract a huge orchestration" — the real value is the **Trade/metrics pipeline for live** (previously live only read closed Positions, never had `Trade`/equity/metrics).

Two tracks:

**Structure (pure move, gates green throughout):**
- `BrokerFactory` `app/di/` → `core/infra/brokers/broker_factory.py` (framework-free, only imports core).
- `QuoteAppService` + `WsSubscriptionAppService` `app/market_data/` → `engine/market_data/app_services/`.
- Fold `rehydrate_strategies_from_subscriptions` → `StrategyReconcileAppService.bootstrap()` (reuse `_ensure_instances` → boot path and steady-state path don't drift). App lifespan is now a thin driver: `inject → bootstrap_live_instances → create_task(reconcile.run) → cancel`.

**Logic (M1 relative-per-sub, core value):**
- `TradeRepository` (`trades` collection, `run_id`=subscription_id) — mirror a small slice of the backtest repo, reuse `Trade.to_mongo/from_mongo`.
- `LiveTradeCollector` — EventBus subscriber (`_on_trade_closed`), builds `Trade` + persists. Broker→bus via `StrategyAppService._forward_trade_to_bus`, wired in `_get_or_create_broker` (**live-only** — backtest `inject_prepared_strategy` bypasses → no double-count).
- `LiveMetricsQueryService` + route `GET /api/v1/subscriptions/{id}/metrics` — on-demand, stateless, cumsum-pnl equity.
- OKX `subscribe_trades` kept as no-op (defer to a future R — needs a demo fill payload to verify snapshot-delta).

Gate: `just test` 571 pass (+9 R8 tests), ruff/pyright/lint-imports (8 contracts) clean.

---

## The Brutal Truth

**Two near-misses, caught by code-reviewer:**

1. **Sharpe inflated by hundreds of times (HIGH).** Initially I passed `periods_per_year = Interval.periods_per_year_for(sub.interval)` = bars/year (1m → 525,600) like backtest. But backtest annualizes on a **per-bar** curve (uniform mtm_curve); my live curve is **trade-keyed** (1 point/closure). Annualizing per-trade returns by √(bars/year) → Sharpe off by tens–hundreds×. Worse: this path was **untested** because both metrics tests don't seed the subscription doc → `sub=None` → `periods_per_year=None` → Sharpe=0 → hidden bug. KISS fix: a trade-keyed curve **cannot** be annualized by bar-freq → `periods_per_year=None` always (Sharpe=0, matching the "not annualizable" convention); also drop `sub_repo`, now a dead dependency. Added a test locking Sharpe=0.

2. **Collector missing error boundary (MEDIUM).** `save_many` unguarded — a transient Mongo error would propagate through `_forward_trade_to_bus` → paper broker `_notify_trade_callbacks` (`raise errors[0]`) → breaking the remaining `BarCompletedEvent` subscribers of that tick + losing the Trade. Every sibling bus handler wraps+logs; the collector must match. Fix: try/except + log `subscription_id`/`pnl` + swallow.

**Caught myself during implementation:** the plan wrote a handler named `on_trade`, but `EventRegistry.register_instance` only scans methods starting with **one** `_` (`startswith("_") and not "__"`) → must name it `_on_trade_closed` to be discovered. Following the plan literally, the collector would silently receive no events.

**Baseline drawdown decision:** the plan suggested `initial_capital = 0`, but `max_drawdown` divides by the running peak — baseline 0 with a losing first trade → `(neg)/0 = -inf` → `np.nan_to_num` by default turns `-inf` into `-1.79e308` (garbage drawdown, not nan). Anchor the curve at `paper_initial_balance` (positive, the real account number) → denominator always > 0 → finite drawdown. Still omit `total_return`/`cagr` (per-sub %-of-shared-account is misleading). Regression test locks it down.

---

## Lessons

- **Reuse ≠ blindly copying parameters.** `PerformanceCalculatorDomainService.build` is shared by backtest + live, but `periods_per_year` depends on the *curve shape* (per-bar vs trade-keyed) — not copied verbatim from another caller.
- **np.nan_to_num by default does NOT only handle nan** — it also turns ±inf into ±1.79e308. Div-by-zero on the equity curve produces inf, not nan → guard with a positive baseline instead of relying on nan_to_num.
- **register_instance scans the `_`-prefix** is a hidden trap for every new bus subscriber — a public handler (`on_x`) will never be registered.
- Separating the 2 Trade channels (backtest direct callback vs live bus-forward) is the key to avoiding double-count — verified by a backtest parity test + a broker→bus integration test.

---

## Unresolved

- Live Sharpe is currently = 0 (not annualized). If the product needs a real live Sharpe → add a per-bar equity sampler for live (out of R8 scope).
- OKX-backed subscription persists zero trades → `/metrics` returns zeros forever, no signal. Waiting for a future R to wire OKX position→Trade (needs a demo payload).
- Soft-coupling `260630-0031-backtest-mae-mfe-excursion`: appending `mae/mfe/r_multiple` to `Trade`+`TradeClosedEvent` → the live collector will leave excursion fields = None, a light rebase when that side lands.
