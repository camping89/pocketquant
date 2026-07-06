# R8 Live-Run Extraction — Code Review

**Reviewer:** code-reviewer · **Date:** 2026-07-06 · **Branch:** develop (uncommitted)
**Scope:** structure moves + live Trade pipeline (broker→bus→collector→trades, on-demand metrics)
**Gates re-run by reviewer:** ruff (R8 files) clean · `lint-imports` 8/8 kept · R8 tests 9 passed

## Verdict

Wiring, DI, and the four risky concurrency/attribution invariants are **correct**. No blocking
(critical) defect. Two functional gaps worth addressing before this is trusted as a live metric
surface: a Sharpe/Sortino annualization mismatch (High) and a missing error boundary in the live
collector (Medium).

## Invariants verified (all PASS)

1. **No backtest double-count** — CONFIRMED. Backtest runs in an isolated sandbox
   (`backtest_sandbox_app_service.py`): fresh `EventBus()`, fresh `StrategyAppService`, fresh
   `PaperBrokerAdapter`, `engine.start(registry=EventRegistry())` (local registry). It uses
   `inject_prepared_strategy` (never `_get_or_create_broker`) and wires `collector.on_trade`
   directly onto its own broker. `TradeClosedEvent` is *never* bus-published by any broker — only
   `_forward_trade_to_bus` publishes it, and that is wired only on the live path. The global
   `LiveTradeCollector` cannot see a backtest closure.
2. **1 forward per shared broker** — CONFIRMED. `_get_or_create_broker` (strategy_app_service.py:421)
   returns via the reuse loop *before* the `subscribe_trades(self._forward_trade_to_bus)` call at
   :431, so the callback is appended exactly once per newly-created broker instance. N subs sharing
   one paper broker → 1 forward. Per-sub attribution rides on `event.subscription_id` (from
   `position.subscription_id`), not the broker, so a shared broker attributes correctly.
3. **Handler discovery** — CONFIRMED. `_on_trade_closed` is single-underscore + `@event_handler(
   TradeClosedEvent)`. `EventRegistry.register_instance` scans `startswith("_") and not
   startswith("__")` for `_event_types` → discovered. Verified live by
   `test_collector_persists_event_with_fallback_strategy_code` (publishes on bus, doc persists).
4. **await/lock safety** — CONFIRMED. Paper broker calls `_notify_trade_callbacks` *outside*
   `async with self._lock` in all three fill paths (`_fill_pending_on_bar` :764, `_fire_synthetic_exit`
   :824, submit). `_forward_trade_to_bus` publishes with no lock held. Nested publish
   (BarCompletedEvent → broker handler → TradeClosedEvent → collector) is reentrancy-safe: different
   handler lists, deque append only.

Plus: DI single-registration (TradeRepository, LiveTradeCollector, LiveMetricsQueryService,
StrategyReconcileAppService each provided exactly once — no dishka silent last-wins). Lifespan
ordering safe (collector subscribes before reconcile starts strategies; brokers don't subscribe to
the bus until `start_strategy`→`connect`, so no closure can precede the handler). Metrics
baseline/drawdown reasoning is sound — positive baseline avoids the `(-value)/0 → -inf →
nan_to_num → -1.79e308` garbage; regression-tested by `test_drawdown_finite_when_first_trade_loses`.

## Findings (ranked)

### High — Sharpe/Sortino annualized by bar-frequency against a trade-keyed curve

`LiveMetricsQueryService.get_metrics` (live_metrics_query_service.py:57,63-72) builds a
**trade-keyed** equity curve (one point per trade closure, `_equity_curve`) but passes
`periods_per_year = Interval.periods_per_year_for(sub.interval.value)` — **bars per year** (1m →
525,600). `build()` has no `returns_curve`, so `sharpe_ratio`/`sortino_ratio` compute per-*trade*
returns and annualize them by √(bars/year). Result overstates Sharpe by ~√(bars_per_year /
trades_per_year) — tens to hundreds× for realistic trade counts. The returned `sharpe_ratio` is
decision-relevant and will be materially wrong once a subscription doc exists.

Untested: both metric tests seed trades but no subscription doc, so `sub is None` →
`periods_per_year=None` → Sharpe=0. The buggy path (real interval) is never exercised.

Fix options: (a) simplest/KISS — pass `periods_per_year=None` for the trade-keyed curve so
Sharpe/Sortino stay raw/un-annualized (mirrors the existing unknown-interval handling); or
(b) annualize by trade frequency derived from trade timestamps; or (c) record a per-bar MTM curve
for live (heavier, not YAGNI for M1). Recommend (a) for now + doc the choice.

### Medium — `LiveTradeCollector._on_trade_closed` has no error boundary around persistence

`_on_trade_closed` (live_trade_collector.py:54-79) calls `await self._trade_repo.save_many([trade])`
with no try/except. A transient Mongo failure propagates: save_many → `_on_trade_closed` →
`bus.publish(TradeClosedEvent)` → broker `_notify_trade_callbacks` (re-raises `errors[0]`) →
`broker._on_bar_completed` → `bus.publish(BarCompletedEvent)`. Two consequences: (1) the closed
Trade is **lost** — no retry/replay, broker RAM state already advanced; (2) the exception halts the
remaining `BarCompletedEvent` subscribers for that tick and skips `_history.append`. Sibling bus
handlers (`StrategyAppService._on_bar_completed/_on_quote_received/_on_order_filled`) all wrap the
body in try/except + log; the collector should match that resilience pattern (catch, log with
`subscription_id`+`pnl`, swallow) so a DB hiccup neither loses a trade nor disrupts bar processing.

### Low — `max_drawdown` reported but distorted by the shared-account baseline

`total_return`/`cagr` are nulled because dividing a single sub's PnL by the whole shared account
(baseline=10k) understates the figure. `max_drawdown` is computed against the *same* baseline-anchored
peak (~account nominal), so it is understated by the same factor, yet it *is* reported. Either
document why account-relative drawdown is still meaningful (account-level risk contribution) or treat
it consistently with the nulled %-returns. Non-blocking; judgment call.

### Low — test gap: "1 forward per shared broker" unverified

Code is correct, but no test loads 2 paper subs and asserts `broker._trade_callbacks` contains a
single `_forward_trade_to_bus` (→ 1 Trade per closure, not 2). Add a 2-sub test to lock the
double-count-via-double-forward path.

### Info

- OKX `subscribe_trades` is a documented no-op (deferred). Live subs on an OKX broker persist zero
  Trades, so `GET /subscriptions/{id}/metrics` returns zeroed metrics forever for OKX-backed subs.
  Expected per scope, but the endpoint gives no signal that it is OKX-blind.
- `LiveTradeCollector` never unsubscribes on shutdown (no `stop()`); harmless in the single-process
  model (process exit tears down the bus). Noted for completeness.
- `TradeRepository.save_many` uses `replace_one({"_id": str(trade_id)}, trade.to_mongo(), upsert=True)`
  where `to_mongo()` also emits `_id` = same value — consistent, no immutable-`_id` conflict. Fine.
- Structure track (BrokerFactory → core/infra/brokers; Quote/WsSubscription → engine/market_data;
  rehydrate → reconcile.bootstrap) is a clean move: relocated `broker_factory.py` imports only
  core-level symbols; test diffs are pure import-path updates. `lint-imports` 8/8 kept.

## Unresolved questions

1. For M1, is a raw (un-annualized) live Sharpe acceptable, or is a trade-frequency annualization
   expected? Drives the High-finding fix choice.
2. Should `max_drawdown` be nulled/relabeled alongside `total_return`/`cagr`, or is account-relative
   drawdown intentionally retained?
