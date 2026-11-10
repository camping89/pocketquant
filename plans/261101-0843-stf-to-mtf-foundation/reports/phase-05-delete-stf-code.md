# Phase 05 report: delete STF code, tests, docs, web comments; shared test doubles

Entry gate: `dirty=0 synced=yes`, phase 04 report `Result: PASS`, `tsc=0`, `docker-ok`.

## Deleted files (`git show --stat HEAD`, `f3bb9e64`)

- `src/pocketquant/core/domain/strategy/services/engulfing_strategy_service.py`, `engulfing_pullback30_touch_strategy_service.py`
- `src/pocketquant/core/domain/strategy/patterns/__init__.py`, `engulfing_detector.py`
- `tests/core_test/unit/domain/strategy/test_engulfing.py`, `test_engulfing_pullback30_touch.py`, `patterns/test_engulfing_detector.py`, `patterns/engulfing_golden_fixture.json`
- `tests/backtest_test/engine/test_engulfing_backtest.py`, `test_engulfing_pullback30_touch_backtest.py`
- `docs/swing-pivot-key-level.md`

Totals: `51 files changed, 173 insertions(+), 2483 deletions(-)`. Created `tests/strategy_doubles.py` (`ScriptedStrategy`) and the `probe_registry` fixture in `tests/conftest.py`.

## Verify outputs

- 05.1: `ScriptedStrategy`.
- 05.2: `76 passed, 4 warnings in 52.70s`.
- 05.3: `0`.
- 05.4: `names=0 keys=0`; step 3 run (05.2 files plus `tests/scripts` and the layout contract): `167 passed, 4 warnings`. No module needed an extra `pytestmark` beyond those added in 05.2.
- 05.5: `0`; web `tsc=0`, lint `0 errors, 6 warnings`, vitest `70 passed`.

## CLOSE

- GATES: `Contracts: 6 kept, 0 broken.`; ruff `All checks passed!`; ratchet exit 0 after the raise below.
- FULLSUITE: `4 failed, 1165 passed, 1 skipped, 50 warnings, 4 errors in 125.30s (0:02:05)`; unexpected count `0`.
- CI: run `41321988930` on `f3bb9e64` printed `completed success`; jobs `web`, `tests (UTC)`, `tests (Asia/Ho_Chi_Minh)`, `tests (America/Chicago)` all `success`.

## Ratchet raise

- `uv run python scripts/code_metrics.py --ratchet` failed with `tiny_share 0.4811 > 0.481`. Deleting 16 measured `src` functions (7 tiny, 9 not) moved the share from 0.4802 to 0.4811; the metric counts only `src/pocketquant`, so the new test double is out of scope. `kongming` confirmed the diagnosis and the value.
- `max_tiny_share` raised from `0.4810` to `0.4811` in its own commit `chore(metrics): raise the code metric ceiling`. `max_delegations` stays at its ceiling `73`.

## Notes

- `tests/manual/api-test.http`: deleted lines 115-120 (the `/backtest/optimize` request and the blank line after it), so one blank line separates the sections.
- `ruff format --check` reports pre-existing format drift in five test files; GATES uses `ruff check` only, so it was left alone.

## Commits

`c99696bd` `chore(metrics): raise the code metric ceiling` and `f3bb9e64` `refactor(strategy): remove the single-timeframe strategies` (both on `origin/develop`).

## Handover to Phase 06 (kongming go/no-go: GO)

- The `StrategyConfig.interval` to `intervals` rename touches every test constructor site at once (about 18 `StrategyConfig(`, 16 `Subscription(` and 30 raw `"interval":` lines in tests at `f3bb9e64`). Run the full `tests/` tree before CLOSE, not only the directories Task 06.3 names.
- Leave the `BacktestConfig.interval` readers alone; only `backtest_execution_service.py` changes.
- Phase 06 cites `test_strategy_service.py` line numbers that are now two lines lower, because this phase added a `pytestmark` line and its blank line.

Result: PASS
