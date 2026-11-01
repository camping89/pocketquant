---
phase: 5
title: "Delete STF code, tests, docs, web comments; shared test doubles"
status: pending
priority: P1
effort: 1d
dependencies: [4]
---

# Phase 05: Delete STF code, tests, docs, web comments; shared test doubles

## Goal

No single-timeframe strategy code, test, doc or comment remains, `STRATEGY_REGISTRY` is empty, and the tests that needed a real strategy use the one shared double, `ScriptedStrategy`, from `tests/strategy_doubles.py`.

## Context

- C1: delete hitnrun2, engulfing, engulfing_pullback30_touch, `engulfing_detector.py`, the registry entries and their tests; no compatibility, no deprecate-and-keep. C2: keep the web Engulf overlay; its golden fixture becomes web-owned; rewrite the comments that name the Python detector.
- Registry `src/pocketquant/core/domain/strategy/services/__init__.py:1-22` (three imports, `STRATEGY_REGISTRY` `:11-15`, `__all__` `:17-22`). Package `src/pocketquant/core/domain/strategy/patterns/` (`__init__.py`, `engulfing_detector.py`) is imported only by the deleted strategy and its test. Nothing in `src` outside `core/domain/strategy` names an STF code (scout-backend §2).
- `IStrategyService` (`src/pocketquant/core/domain/strategy/strategy_service_interface.py:16-43`) holds `_open_direction`; `load_strategy(config, strategy_class=None)` builds the class directly (`engine/strategy/strategy_app_service.py:188-215`); a warm-up replay signal is answered with `on_order_rejected("warmup")` (`:265-266`).
- <!-- Red team 2026-11-01: #15 --> Test doubles (plan.md verdict): `tests/strategy_doubles.py` holds one strategy double, `ScriptedStrategy`, created here with its fixed rule only (no per-bar script yet: no test needs one in this phase). Later phases extend this class; they add no second strategy double. The registry key stays `"probe"` and the fixture stays `probe_registry`, the names later phases use.
- Registry lookups a test can reach: `StrategyReconcileAppService._ensure_instances` (`engine/live/strategy_reconcile_app_service.py:121`), `StrategyCommandService.add_symbol` (`engine/strategy/strategy_command_service.py:58`), `BacktestExecutionService.run` (`engine/backtest/backtest_execution_service.py:103-108`), and direct `STRATEGY_REGISTRY[...]`. A test that reaches one of them needs the probe registered.
- Tests import from the `tests` package (`tests/conftest.py:14-22` puts the workspace root on `sys.path`; precedent `tests/app_test/integration/test_safeguards_api.py:18`). `NoStoredBars` and `Continuous24x7CalendarFactory` stay where they are in this phase; Phase 08 moves them into `tests/strategy_doubles.py`.
- The two hitnrun2-named tests get behaviour names: `test_hitnrun2_signals_on_the_first_live_bar_after_481_stored_bars` (`tests/engine_test/test_strategy_warm_up.py:156`) and `test_hitnrun2_on_order_rejected_clears_open_direction` (`tests/engine_test/test_strategy_reject_delivery.py:126`).
- Rubric: `scripts/rubric/static_audit.py` stays (generic over the registry); `tests/scripts/rubric/test_static_audit.py:7-36` parametrizes the STF codes; only `test_unknown_strategy_falls_back_not_raises` (`:39-44`) survives. The DEFAULTS rewrite of the audit is Phase 06.
- Web: `web/src/lib/indicators/engulfing.ts:4-6` (mirror comment) and `:63-65` (threshold comment with the doc link); `engulfing.test.ts:4-5`; the fixture `_doc` string in `web/src/lib/indicators/__fixtures__/engulfing_golden_fixture.json:2` names the Python detector and old phases. The test reads only `cases` (`engulfing.test.ts:20`).
- Docs: `docs/swing-pivot-key-level.md` (16 lines, all about the engulfing strategy; only inbound link `engulfing.ts:65`); `docs/system-architecture.md:34` ends with the stale sentence "No current strategy adds; each holds at most one position."
- Manual files: `tests/http/backtest/run-backtest.bru:14-28`, `tests/http/backtest/list-results.bru:13`, `tests/manual/api-test.http:113,119,131`. The `/backtest/optimize` request at `api-test.http:117-119` has no route in `src` (`git grep -n "parameter_grid" -- src` prints nothing).
- `test_admin_token_guard.py:46` stays `17` here (no route change).

## Entry gate

Run from `D:/w/_me/algotrading/pocketquant`:

1. `git fetch -q origin && echo "dirty=$(git status --porcelain -- src web deploy tests scripts docs .github | wc -l | tr -d ' ') synced=$(test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo yes || echo no)"` prints `dirty=0 synced=yes`. On a resume, `dirty` may count only files from this phase's Files list, and `synced=no` passes only when `git rev-list --count HEAD..origin/develop` prints `0`.
2. `tail -1 plans/261101-0843-stf-to-mtf-foundation/reports/phase-04-web-gate.md` prints `Result: PASS`.
3. `cd web && npx tsc -b > /dev/null 2>&1; echo tsc=$?` prints `tsc=0`.
4. `docker ps > /dev/null 2>&1 && echo docker-ok` prints `docker-ok`.

On a miss, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261101-0843-stf-to-mtf-foundation --from 05 after <UTC time>
```

## Files

- Create: `tests/strategy_doubles.py`.
- Delete: `src/pocketquant/core/domain/strategy/services/hitnrun2_strategy_service.py`, `.../engulfing_strategy_service.py`, `.../engulfing_pullback30_touch_strategy_service.py`, `src/pocketquant/core/domain/strategy/patterns/` (whole package); `tests/core_test/unit/domain/strategy/test_hitnrun2.py`, `test_engulfing.py`, `test_engulfing_pullback30_touch.py`, `tests/core_test/unit/domain/strategy/patterns/` (test and Python fixture copy); `tests/backtest_test/engine/test_hitnrun2_backtest.py`, `test_engulfing_backtest.py`, `test_engulfing_pullback30_touch_backtest.py`; `docs/swing-pivot-key-level.md`.
- Modify src: `src/pocketquant/core/domain/strategy/services/__init__.py`.
- Modify tests: `tests/conftest.py`; the files listed in Tasks 05.2-05.3.
- Modify web and docs: `web/src/lib/indicators/engulfing.ts`, `engulfing.test.ts`, `__fixtures__/engulfing_golden_fixture.json` (`_doc` only), `docs/system-architecture.md` (`:34` only).
- Modify manual files: `tests/http/backtest/run-backtest.bru`, `tests/http/backtest/list-results.bru`, `tests/manual/api-test.http`.

## Tasks

### Task 05.1 — The shared strategy double and its fixture
<!-- Red team 2026-11-01: #15 -->

**Goal:** one strategy double, `ScriptedStrategy`, replaces every STF class the tests used.

**Target files and symbols:** new `tests/strategy_doubles.py` (`ScriptedStrategy`); `tests/conftest.py` (fixture `probe_registry`).

**Steps:**
1. `ScriptedStrategy(IStrategyService)`: `__init__` reads `self.min_bars = int((config.parameters or {}).get("min_bars", 0))` and sets `self.bars: list[dict] = []`; `on_start` calls `super().on_start()`, clears `bars`, sets `_open_direction = None`; `on_bar_completed` appends the bar, returns `None` while `len(self.bars) <= self.min_bars` or `_open_direction is not None`, else sets `_open_direction = Direction.LONG` and returns `Signal(symbol=self.config.symbol, direction=Direction.LONG, confidence=1.0, timestamp=bar["timestamp"], subscription_id=self.id, entry_price=close, stop_loss_price=close * 0.99, take_profit_price=close * 1.01)`; `on_order_filled` clears `_open_direction` on an opposite-side fill (a SELL while LONG); `on_order_rejected` clears it. One `#` comment above the class: it signals LONG with a 1% stop and target on every bar after `min_bars` bars while flat.
2. In `tests/conftest.py`: fixture `probe_registry(monkeypatch)` that runs `monkeypatch.setitem(STRATEGY_REGISTRY, "probe", ScriptedStrategy)` (import `ScriptedStrategy` from `tests.strategy_doubles`). Modules that need it declare `pytestmark = pytest.mark.usefixtures("probe_registry")` (add to an existing `pytestmark` list where one exists).

**Success criteria:** the module imports; the fixture registers `"probe"`.

**Verify:** `uv run python -c "from tests.strategy_doubles import ScriptedStrategy; print(ScriptedStrategy.__name__)"` prints `ScriptedStrategy`.

### Task 05.2 — Repoint the tests that need a real strategy

**Goal:** no test imports an STF class or resolves an STF code.

**Target files and symbols:**
- Class importers: `tests/engine_test/test_strategy_warm_up.py` (`:17-18`, `:156-187`), `tests/engine_test/test_strategy_reject_delivery.py` (`:1-2`, `:22-23`, `:116-133`), `tests/backtest_test/test_backtest_single_run_direct_task.py` (`_engulfing_bars` `:76`, `_command` `:118-130`, `:255-300`).
- Registry users (code `"probe"` plus the fixture): `tests/engine_test/test_live_trade_collector_integration.py:38`, `tests/engine_test/test_reconcile_restart_resume_integration.py:43`, `tests/engine_test/test_strategy_reconcile_service.py:20`, `tests/engine_test/test_strategy_service.py:140,165,169,182,261`, `tests/app_test/integration/test_app_standalone_runtime.py:30`, `tests/backtest_test/test_backtest_dispatch_contract_spec.py:57`, `tests/engine_test/test_contract_spec_wiring.py:161,241`, `tests/engine_test/test_subscription_broker_selection.py:34`. `tests/app_test/integration/test_trader_lifespan_handover.py:139,151` registers its own `_AlwaysLong`; change only the key to `"probe"`.

**Steps:**
1. Warm-up: `_engine(...)` gains `parameters: dict | None = None` passed to its `StrategyConfig`. Rename the `:156` test to `test_a_strategy_signals_on_the_first_live_bar_after_its_warm_up`: `ScriptedStrategy` with `min_bars=481` over 481 stored bars; `len(strategy.bars) == 481`, no fills; the live bar at close 90 gives exactly one BUY fill. `test_a_replayed_signal_sends_nothing` uses 482 stored bars with `min_bars=481`: no fills, `_open_direction is None`. `test_a_long_mirror_row_restores_direction_long` uses `ScriptedStrategy`.
2. Reject delivery: the header becomes `# A strategy arms _open_direction when it emits a signal and clears it only on an opposite` / `# fill, so a signal that never filled used to silence it for good.`; `_armed` loads `ScriptedStrategy`; rename `:126` to `test_on_order_rejected_clears_open_direction` (a `ScriptedStrategy` with `_open_direction = SHORT` is cleared by `on_order_rejected("x")`).
3. Single run: rename `_engulfing_bars` to `_cycle_bars`; codes become `"probe"`; every `parameters` becomes `{}`; the live engine builds `ScriptedStrategy(live_cfg)` with `id="probe-live", name="probe"`; add the module `pytestmark`.
4. Registry users: replace the STF code with `"probe"` and add the module `pytestmark`; fix any comment that names an STF code (for example `# must be in STRATEGY_REGISTRY` stays true).

**Success criteria:** these files pass against the current registry plus the probe.

**Verify:** `uv run python -m pytest tests/engine_test/test_strategy_warm_up.py tests/engine_test/test_strategy_reject_delivery.py tests/backtest_test/test_backtest_single_run_direct_task.py tests/engine_test/test_live_trade_collector_integration.py tests/engine_test/test_reconcile_restart_resume_integration.py tests/engine_test/test_strategy_reconcile_service.py tests/engine_test/test_strategy_service.py tests/app_test/integration/test_app_standalone_runtime.py tests/app_test/integration/test_trader_lifespan_handover.py tests/backtest_test/test_backtest_dispatch_contract_spec.py tests/engine_test/test_contract_spec_wiring.py tests/engine_test/test_subscription_broker_selection.py -q 2>&1 | tail -1` contains `passed` and not `failed` or `error`.

### Task 05.3 — Opaque codes, rubric tests, layout contract, manual files

**Goal:** every remaining STF name in `tests/` and the manual files is gone.

**Target files and symbols:** `tests/app_test/integration/test_admin_token_guard.py:27`, `test_backtest_name_api.py:18`, `test_backtest_orders_api.py:47,87`, `test_backtest_verdict_api.py:18`, `test_declarative_subscription_state_api.py:23`, `tests/backtest_test/test_backtest_result_verdict.py:5`, `tests/core_test/infra/brokers/test_paper_broker_spread.py:119`, `tests/core_test/unit/domain/subscription/test_subscription_desired_actual_state.py:21,45,78,91,94`, `tests/engine_test/market_data/test_tracked_symbols_service.py:109`, `tests/scripts/rubric/test_persist_shape.py:16`; two-code files `tests/core_test/infra/persistence/backtest/test_backtest_repository_slimmed.py:88-106`, `tests/scripts/rubric/test_dedup.py`, `tests/scripts/rubric/test_renderers.py:82-135`; `tests/scripts/rubric/test_static_audit.py`; `tests/core_test/test_core_layout_contract.py:11`; the three manual files.

**Steps:**
1. Single-code files: replace the code with `"probe"`. Two-code files: `hitnrun2` becomes `"breakout"` and `engulfing` becomes `"reversal"`, keeping every assertion's logic (for example `md.index("reversal") < md.index("breakout")`).
2. `test_static_audit.py`: delete `_STRATEGIES` and every test except `test_unknown_strategy_falls_back_not_raises`.
3. `test_core_layout_contract.py`: delete the `NEW_MODULES` line `:11`.
4. `run-backtest.bru`: body `{"strategy_id": "triple_screen", "symbol": "XAUUSD:EXNESS", "intervals": ["15m", "1h", "4h"], "start_date": "2026-01-01", "end_date": "2026-03-30", "initial_capital": 10000, "parameters": {}}`; `list-results.bru`: `strategy_id: triple_screen`. `api-test.http`: the `:113` body gets the same values; delete the `/backtest/optimize` request (`:115-119`, no route); line `:131` becomes `# 5. Choose triple_screen and verify backtest markers appear`.

**Success criteria:** no STF name in `tests/` outside the files Task 05.4 deletes.

**Verify:** `git grep -n -i -E "hitnrun|engulfing" -- tests ':!tests/core_test/unit/domain/strategy' ':!tests/backtest_test/engine/test_hitnrun2_backtest.py' ':!tests/backtest_test/engine/test_engulfing_backtest.py' ':!tests/backtest_test/engine/test_engulfing_pullback30_touch_backtest.py' | wc -l` prints `0`.

### Task 05.4 — Delete the STF source and its tests

**Goal:** the strategies, the detector and their tests are gone; the registry is empty.

**Target files and symbols:** the Delete list; `services/__init__.py`.

**Steps:**
1. `git rm -r` every path in the Delete list except the doc (Task 05.5).
2. `services/__init__.py` becomes `STRATEGY_REGISTRY: dict[str, type] = {}` and `__all__ = ["STRATEGY_REGISTRY"]`, with no imports.
3. Run the Task 05.2 test command plus `tests/scripts tests/core_test/test_core_layout_contract.py`; any test that now fails with an unknown code (`not found in registry`, `reconcile.unknown_template`, `KeyError: 'probe'`) gets the module `pytestmark` from Task 05.1 and nothing else.

**Success criteria:** no STF name in `src`, `tests` or `scripts`; the registry has no keys.

**Verify:** `echo "names=$(git grep -n -i -E "hitnrun|engulfing" -- src tests scripts | wc -l | tr -d ' ') keys=$(uv run python -c "from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY; print(len(STRATEGY_REGISTRY))")"` prints `names=0 keys=0`.

### Task 05.5 — Web comments, fixture note, docs

**Goal:** the web overlay and its fixture stand alone, and no doc describes a deleted strategy.

**Target files and symbols:** `engulfing.ts:4-6,63-65`, `engulfing.test.ts:4-5`, `engulfing_golden_fixture.json` `_doc`, `docs/swing-pivot-key-level.md`, `docs/system-architecture.md:34`.

**Steps:**
1. `engulfing.ts:4-6` becomes `// Chart overlay only; no strategy trades on it. Locked by its golden fixture (engulfing.test.ts).`; `:63-65` becomes `// Visual aid only: a fixed display threshold for strong/weak coloring.`
2. `engulfing.test.ts:4-5` becomes `// The web owns this golden fixture; detectEngulfing and the fixture change together.`
3. The fixture `_doc` becomes `"Golden fixture for detectEngulfing (web/src/lib/indicators/engulfing.ts). rejection_wick_pct is ALWAYS a float (sentinel 1.0 for non-engulfing or zero-range)."`; `cases` unchanged.
4. `git rm docs/swing-pivot-key-level.md`; delete the sentence "No current strategy adds; each holds at most one position." from `docs/system-architecture.md:34`, keeping the sentence before it.
5. In `web/`: `npx tsc -b` exits 0, `npm run lint` reports `0 errors`, `npx vitest run` exits 0.

**Success criteria:** no web or doc line names the Python detector, the swing doc or `max_rejection_wick`.

**Verify:** `git grep -n -i -E "python detector|swing-pivot|engulfing_detector|max_rejection_wick|current strategy adds" -- web/src docs README.md CLAUDE.md ':!docs/journals' | wc -l` prints `0`.

### Task 05.6 — CLOSE

**Goal:** the deletion is on `develop` with green gates and CI.

**Target files and symbols:** all files of this phase.

**Steps:**
1. GATES (plan.md Conventions), including the web part; FULLSUITE.
2. `git add -A src tests scripts web docs && git commit -m "refactor(strategy): remove the single-timeframe strategies"`; push with the Ops recipe; wait for CI.

**Success criteria:** CI on HEAD concludes `success`, both the `tests` and the `web` jobs.

**Verify:** `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 1 --json headSha,status,conclusion -q '.[0] | "\(.status) \(.conclusion) \(.headSha)"'` prints `completed success <sha>` with `<sha>` equal to `git rev-parse HEAD` (poll until `completed`).

## Rollback

`git revert <sha>` and push. Nothing reached prod: prod still runs the D-1 image with the STF registry until Phase 15.

## Report

`reports/phase-05-delete-stf-code.md`: the deleted file list (`git show --stat HEAD`); the Verify outputs of Tasks 05.2-05.5; GATES and FULLSUITE tail lines; the CI run id; any ratchet raise. Last line `Result: PASS`.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same failure evidence to the user. Never continue by self-reasoning.
