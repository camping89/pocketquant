# Service Naming Convention Rename — All Phases Completed

**Date:** 2026-07-05 17:22
**Severity:** Low (cosmetic, behavior-preserving)
**Component:** Core, Engine, Backtest, App — naming/conventions
**Status:** Resolved

## What Happened

Executed complete Service Naming Convention Rename across codebase: ~24 class + file renames across 5 phases to encode layer/role directly in class/file name. Convention: `*DomainService`, `*StrategyService`, `*AppService`, `I{Concept}Port`, `{Source}[{Type}]Adapter`, `*Helper`. All tests pass, all linter contracts kept.

9 commits: docs convention → domain services (PositionSizer, BarBuilder, PerformanceCalculator, TradeStatsCalculator, SyncProgressTracker, LotTracker→LotTrackingHelper) → strategy (IStrategy→IStrategyService, EngulfingStrategy→EngulfingStrategyService, HitNRun2Strategy→HitNRun2StrategyService) → app orchestrators (BacktestResultCollector→BacktestResultAppService, StrategyReconcileService→StrategyReconcileAppService, WsSubscriptionManager→WsSubscriptionAppService, BacktestSandbox→BacktestSandboxAppService) → market_data ports (IBroker/IBrokerFactory split into I*Port files; IDataProvider→IDataProviderPort, IRealtimeQuoteProvider→IRealtimeQuoteProviderPort) → broker ports (IBrokerPort, IBrokerFactoryPort split to *_port.py) + adapters (PaperBroker→PaperBrokerAdapter, OKXBroker→OKXBrokerAdapter, OkxWebSocketClient→OKXWebSocketAdapter, BinanceClient→BinanceAdapter) → BinanceWebSocketClient→BinanceWebSocketAdapter follow-up → docs sync.

## The Brutal Truth

Cosmetic rename that detonated DI resolution. Every type-hint, every import, every Dishka provider needed updating. Hit line-length limits (100) hard: ruff auto-fixed imports, then manual wrapping for usage lines. One misplaced reference would silently break because Python imports are lazy. The paranoia was justified — linter + tests + pyright were the only circuit breaker.

Most painful part: splitting `interfaces.py` files (market_data, brokers) into separate *_port.py files = chasing import chains everywhere. Exhausting but necessary for clarity.

## Technical Details

**Tests:** 552 passed, 1 skipped (pre-existing). 553 total collected.

**Import-linter:** All 7 contracts kept (Layered architecture — app top tier, Core domain free of infra adapters, Core imports clean, Engine clean, Backtest clean, fastapi only in app, UUID7-only).

**Pyright:** 1 error pre-existing (`tests/core_test/domain/strategies/test_engulfing.py`, unrelated to rename).

**Ruff:** 0 errors post-fix (E501 + I001 auto-fixed by ruff --fix, remaining imports manually wrapped).

**Behavior preserved:** STRATEGY_REGISTRY keys ("engulfing", "hitnrun2") unchanged (DB identifiers); log event keys ("ws_subscription_manager.*") unchanged (observability contracts); broker `.name`/`broker_type` literals unchanged (Binance/OKX API contracts).

**File operations:** 2 interfaces.py split → 4 new *_port.py files (data_provider_port.py, realtime_quote_provider_port.py, broker_port.py, broker_factory_port.py). All git mv (preserves history).

## What We Tried

1. Phase-by-phase approach (phase 0 docs → phase 1-5 impl) — isolated risk, tested after each.
2. `git mv` instead of delete/create — preserved file history.
3. `ruff --fix` for bulk import sorting — handled 80% of line-length violations.
4. Manual wrapping for edge cases — remaining long imports in provider/service files.
5. Spot-check Dishka type-hints during phase — caught mismatches early.

## Root Cause Analysis

Service naming had ZERO layer encoding — LotTracker could be domain, helper, or domain helper (actual state: helper). Broker, Factory, Client, Provider = generic crud suffix → unclear role. Class name read like "JPEG without metadata tags."

Convention fixes it cosmetically but semantically: developer reads `LotTrackingHelper` and knows layer + role without folder path.

## Lessons Learned

1. **Cosmetic refactors = same rigor as features.** DI touching is high-risk even when purely name-based.
2. **Behavior-preservation requires documentation.** Enum keys, log strings, broker literals are fragile contracts — note them before rename.
3. **Split large interface files early.** Monolithic interfaces.py = import nightmare when extracting. Future: 1 port = 1 file from the start.
4. **Test file names can lag without breaking tests.** File renames cosmetic; class renames inside test files critical. Left test_lot_tracker.py, test_trade_stats_calculator.py as-is — tests still pass because imports inside updated.

## Next Steps

1. **Optional cosmetic:** Rename test files (test_lot_tracker.py → test_lot_tracking_helper.py, etc.) to match class names. Accepted lag for v1 — not blocking.
2. **Optional:** Update DI provider method names (get_ws_subscription_manager → get_ws_subscription_app_service). Currently returns WsSubscriptionAppService but name is old. Low priority.
3. **Documentation:** New code follows convention via updated docs/code-standards.md (completed with phase-00).

**Unresolved cosmetic issues (follow-up):**
- Test file names: 5 files (test_lot_tracker.py, test_trade_stats_calculator.py, test_performance_calculator_annualization.py, test_bar_builder.py, sync_progress_tracker_test.py)
- DI provider method: get_ws_subscription_manager() + get_backtest_result_collector()
