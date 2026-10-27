# Phase 08 — Backtest chain 6 to 3 files

- Merge `backtest_execution_service.py` and `backtest_dispatch.py` into one runner.
- Inline the replay loop from `historical_replay_app_service.py` into `BacktestAppService.run`.
- Move `CollectedResults` into the report service.
- Drop `BacktestDispatchDeps`, `get_dispatch_deps`, `set_run_id` and the late bind, `persist_results`, write-only sandbox fields, unused parameters, and `replay_speed`.

Verify: all `tests/backtest_test` and `tests/app_test/integration/test_app_standalone_runtime.py`; the characterization tests keep identical stats.
