---
name: pocketquant-package-cycle-topology
description: Exact backtest<->trading import edges and cycle composition as of 2026-05-31, used to assess whether a separate execution package is justified.
metadata:
  type: project
---

Verified import edges between backtest and trading (grep over packages/*/src, 2026-05-31):

- backtest -> trading: ONE real edge — `backtest/handlers/run/handler.py:14` imports `trading.app_services.strategy_app_service.StrategyAppService`. (Other hit is a docstring mention, not an import.)
- trading -> backtest: orchestration jobs (`trading/jobs/backtest_jobs.py:63-64`, `backtest_strategy_loader.py:10`) + 4 result-reader handlers importing `backtest.persistence.backtest_repository.BacktestRepository` (list_symbols, get_subscription_backtest, delete, remove_symbol).

**Why:** The 6-package plan's central justification is "break the backtest<->trading cycle" by extracting a separate `execution` package. But the cycle dissolves once orchestration moves to backtest and BacktestRepository moves to infra (both already in the plan) — leaving only backtest->trading, a legal one-directional sibling edge. The execution package is a purity goal (true siblings), not forced.

**How to apply:** When reviewing this plan or follow-ups, treat the separate execution package and the "all repos in infra / promote all entities to core" decisions as YAGNI-suspect, not load-bearing. Engine = ~857 LOC (StrategyAppService 343, OrderAppService 217, PositionAppService 161, RiskCheckHandler 136). Backtest domain promoted to core = ~602 LOC.

Other verified facts:
- `lint-imports` currently HARD-CRASHES (missing `include_external_packages=True` with bson forbidden contract) — so all 4 contracts are dead today. Phase 1 fix is legit.
- sync-status bump-vs-reset DECISION already lives in `api/.../sync/sync_one/handler.py:95-104`; repo `bump_empty_fetch`/`reset_empty_fetch` are already pure atomic `$inc`/`$set`. Phase 8's premise (rule is in the repo) is false.
- 3 private-hack sites confirmed: `backtest/handlers/run/handler.py:101-104`, `trading/jobs/backtest_strategy_loader.py:119-122`, `trading/jobs/backtest_jobs.py:101`. The two injection sites also do `broker.connect()` + `strategy.on_start()` inside the SAME lock — proposed `inject_prepared_strategy` (dict-only) doesn't cover that critical section.
