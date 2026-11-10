# Phase 03 report: hitnrun2 strategy with a cost filter

## Entry gate

- EG(1) `git status --porcelain -- src web deploy tests scripts docs .github`: empty.
- EG(2) HEAD equals origin/develop: `synced`.
- EG(3) `reports/phase-02-track-a-backtests.md` last line: `Result: PASS`.
- EG(4) `grep -c "^verdict: "` on the Phase 02 report: `2`.
- EG(5) `docker ps`: `docker-ok`.

## Task 03.1: the spec reaches the strategy

- `git grep -n "contract_spec="`: `backtest_execution_service.py:46`, `:118`, `:129`; `strategy_reconcile_app_service.py:177`.
- `git grep -c "contract_spec="`: `backtest_execution_service.py:3` and `strategy_reconcile_app_service.py:1`.
- `git grep -n "symbol_lookup=symbol_lookup"` in `app/di/services.py`: `services.py:171:` and `services.py:198:`.
- Trader test `test_reconcile_loads_a_contract_subscription_with_its_spec`: `1 passed, 1 warning in 0.66s`.
- No [ASK] was needed. The backtest path builds the strategy's `StrategyConfig` with `contract_spec=config.contract_spec` at `backtest_execution_service.py:118`.

## Task 03.2: unit tests first

- Expected red: `ERROR tests/core_test/unit/domain/strategy/test_hitnrun2.py`, `ModuleNotFoundError: No module named 'pocketquant.core.domain.strategy.services.hitnrun2_strategy_service'`. The Verify grep count printed `2`.
- Deviation from the Task 03.2 helper spec: `_fill` returns a frozen `_Fill` dataclass instead of `SimpleNamespace`. The pyright gate rejects `SimpleNamespace` against the `FilledOrder` Protocol (2 errors, `reportArgumentType`). kongming advised this fix; a cast was rejected because it silences the checker without conforming. `test_triple_screen.py` has the same pattern with 4 pre-existing pyright errors. It is outside this phase's file list and was left untouched.

## Task 03.3: the strategy and its registry entry

- `test_hitnrun2.py`: `17 passed, 1 warning in 0.20s`.
- Registry: `['hitnrun2', 'triple_screen']`.

## Task 03.4: backtest-path test

- `test_hitnrun2_backtest.py`: `2 passed, 2 warnings in 10.66s`.

## Task 03.5: CLOSE

- AGNOSTIC: `0`.
- lint-imports: `Contracts: 6 kept, 0 broken.`
- Ratchet: exit 0. No metric-ceiling commit.
- ruff check: `All checks passed!`
- pyright on `src` and the two new test files: `0 errors, 0 warnings, 0 informations` (after the `_Fill` fix; the first run gave `2 errors, 0 warnings, 0 informations`).
- FULLSUITE: `4 failed, 1371 passed, 1 skipped, 63 warnings, 4 errors in 172.84s (0:02:52)`; non-baseline FAILED/ERROR count `0`.
- Commit: `150ceb32d81fc023281f8895700b72997ab29eb5` `feat(strategy): add the hitnrun2 1m breakout strategy with a cost filter`.
- CI run `42646391531`: `completed success 150ceb32d81fc023281f8895700b72997ab29eb5`, equal to `git rev-parse HEAD`.

## Notes

- `ruff format --check src tests scripts` lists 14 pre-existing files that would be reformatted. None is a file of this phase, and format is not part of GATES.

Result: PASS
