---
phase: 3
title: "Track B: spec check, hitnrun2 rewrite with cost filter, tests, CI"
status: pending
priority: P2
effort: "1d"
dependencies: [2]
---

# Phase 03: Track B: spec check, hitnrun2 rewrite with cost filter, tests, CI

## Goal

`HitNRun2StrategyService` is back in the registry as `hitnrun2`, on the current contract with exactly one interval, with a `min_cost_multiple` filter that reads the round-trip cost from `config.contract_spec`, proven by 17 unit tests and a backtest-path test, with CI green on `develop`.

## Context

- D3, A3, A4 and the advice: keep the three lookbacks, `max_loss_pct`, `min_profit_pct` and `direction` as parameters; add one parameter `min_cost_multiple` (default 3.0); round-trip cost = `commission_per_contract * 2 + spread` from `config.contract_spec`; skip when the nearer of the TP and SL distances is under `min_cost_multiple` times that cost. Never a literal 0.15. For the seeded gold spec the multiplier is 1.0, so the per-contract fee is in price units and the formula is exact (plan.md Facts).
- Old code (`git show f3bb9e64^:src/pocketquant/core/domain/strategy/services/hitnrun2_strategy_service.py`): LONG when `close < min(previous entry window lows)`, `sl = max(min(previous SL window lows), close * (1 - max_loss_pct))`, `tp = max(max(previous TP window highs), close * (1 + min_profit_pct))`; SHORT mirrors (`:80-94`); windows exclude the current bar (`:60-70`); warm-up until the SL window is full (`:72-74`); one position at a time (`:76-78`); an opposite-side fill closes (`:98-104`); a rejection clears (`:106-107`).
- Signed distances: LONG `tp - close` and `close - sl`; SHORT `close - tp` and `sl - close`. When the close is also beyond the SL-window extreme, the SL sits on the wrong side and the nearer distance is `<= 0`, so the filter skips (plan.md Facts). The filter also skips `<= 0` when the spec cost is 0.
- Current contract (`src/pocketquant/core/domain/strategy/strategy_service_interface.py:16-48`): `DEFAULTS: ClassVar[dict]` is the parameter and type contract that `check_strategy_inputs` enforces (`services/__init__.py:49-71`); `restore_direction`; `snapshot` (optional, the engine tolerates `None`, `strategy_app_service.py:87-97`). The engine adds `bar["context"]` (`strategy_app_service.py:422-425`); a one-interval strategy never reads it. `Signal` fields as Triple Screen uses them (`triple_screen_strategy_service.py:182-202`). Style model: `triple_screen_strategy_service.py`.
- Spec wiring (plan.md Facts): backtest `backtest_execution_service.py:101-119`; trader `strategy_reconcile_app_service.py:154-177`, DI `app/di/services.py:159-171`. Existing trader test: `tests/engine_test/test_contract_spec_wiring.py:154` (`test_reconcile_loads_a_contract_subscription_with_its_spec`). The existing backtest test (`tests/backtest_test/test_backtest_dispatch_contract_spec.py:44-73`) checks the backtest config and broker, not the strategy, so this phase adds the strategy-level backtest test.
- Symbol lookups are cached per symbol for 60 s in a module-level cache (`src/pocketquant/core/infra/persistence/symbol_lookup_helper.py:15,25-38`), so the backtest test uses a different symbol per case.
- Test patterns: `tests/core_test/unit/domain/strategy/test_triple_screen.py` (helpers, `SimpleNamespace` fills); `tests/backtest_test/engine/test_triple_screen_backtest.py` (`_execution`, `_cmd_svc`, `_series`, seeding and cleanup); `database` fixture `tests/backtest_test/conftest.py:38-55`; `asyncio_mode = "auto"` (`pyproject.toml:63`).

## Entry gate

1. Conventions EG (1)-(3); the previous report is `reports/phase-02-track-a-backtests.md`.
2. `grep -c "^verdict: " plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md` prints `2` (Track A numbers exist before Track B code).
3. `docker ps > /dev/null 2>&1 && echo docker-ok` prints `docker-ok` (start Docker Desktop per FULLSUITE and retry once).

On a miss, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 03 after <UTC time>
```

## Files

- Create: `src/pocketquant/core/domain/strategy/services/hitnrun2_strategy_service.py`, `tests/core_test/unit/domain/strategy/test_hitnrun2.py`, `tests/backtest_test/engine/test_hitnrun2_backtest.py`, the phase report.
- Modify: `src/pocketquant/core/domain/strategy/services/__init__.py` (registry and `__all__` only).
- Delete: none. Docs: none (plan.md Docs impact).

## Tasks

### Task 03.1 — The spec reaches the strategy in both paths

**Goal:** confirm, before writing the filter, that `StrategyConfig.contract_spec` carries the symbol's spec in the backtest and the trader path.

**Target files and symbols:** `backtest_execution_service.py` (`BacktestExecutionService.run`), `strategy_reconcile_app_service.py`, `app/di/services.py` (`get_reconcile_service`).

**Steps:**
1. `git grep -n "contract_spec=" -- src/pocketquant/engine/backtest/backtest_execution_service.py src/pocketquant/engine/live/strategy_reconcile_app_service.py`; record it.
2. `git grep -n "symbol_lookup=symbol_lookup" -- src/pocketquant/app/di/services.py`; record it.
3. `uv run python -m pytest "tests/engine_test/test_contract_spec_wiring.py::test_reconcile_loads_a_contract_subscription_with_its_spec" -q 2>&1 | tail -1`; record it.
4. If a grep misses or the test fails, [ASK] (intent) "the strategy does not receive the symbol's contract_spec in <path>; fixing it needs an engine change in <file>; make that change in this plan?" `Recommended: yes, one line passing the spec`, reason: A4 cannot hold without it. A non-yes ends the phase with `NOT_YET`.

**Success criteria:** both paths pass the spec; the trader test passes.

**Verify:** `git grep -c "contract_spec=" -- src/pocketquant/engine/backtest/backtest_execution_service.py src/pocketquant/engine/live/strategy_reconcile_app_service.py` prints exactly the two lines `src/pocketquant/engine/backtest/backtest_execution_service.py:3` and `src/pocketquant/engine/live/strategy_reconcile_app_service.py:1`; step 2's output contains `services.py:171:`; step 3's line contains `1 passed`.

### Task 03.2 — Unit tests first

**Goal:** the strategy's rules are pinned before it exists.

**Target files and symbols:** `tests/core_test/unit/domain/strategy/test_hitnrun2.py`.

**Steps:**
1. Helpers (copy the style of `test_triple_screen.py`):
   - `GOLD = ContractSpec(multiplier=1.0, tick_size=0.001, commission_per_contract=0.035, spread=0.08)` with a `#` comment that it mirrors the seeded gold spec; `LINEAR_SPEC` from `pocketquant.core.domain.symbol`.
   - `_cfg(intervals=("1m",), spec=LINEAR_SPEC, **params)` returns `StrategyConfig(id="sub-1", name="hitnrun2", symbol="XAUUSD:EXNESS", intervals=list(intervals), parameters={"entry_lookback_bars": 2, "sl_lookback_bars": 8, "tp_lookback_bars": 3, **params}, contract_spec=spec)`.
   - `async def _strategy(spec=LINEAR_SPEC, **params)` builds `HitNRun2StrategyService(_cfg(spec=spec, **params))` and awaits `on_start()`.
   - `_bar(high, low, close, i)` returns `{"symbol": "XAUUSD:EXNESS", "interval": "1m", "open": close, "high": high, "low": low, "close": close, "volume": 1.0, "timestamp": _T0 + timedelta(minutes=i)}` with `_T0 = datetime(2026, 1, 5, tzinfo=UTC)`.
   - `async def _warm(s, deep=98.0, high3=None, high7=None)` feeds bars `i = 0..7` with `high=100.5, low=99.5, close=100.0`, except bar 3 has `low=deep` when `deep` is not None and `high=high3` when given, and bar 7 has `high=high7` when given. It asserts each returns `None`.
   - `_fill(side)` returns `SimpleNamespace(side=OrderSide[side])`.
   - `TRIGGER = (99.5, 98.9, 99.0)` (high, low, close) at `i=8`.
   - Unless a test says otherwise, it builds the strategy with `_strategy()` and calls `await _warm(s)` before the trigger; every test is `async def`.
2. Tests (names state the rule; expected values were derived from the rules in Context):
   - `test_more_than_one_interval_is_rejected`: `_cfg(intervals=("1m", "5m"))` raises `ValueError`.
   - `test_an_unknown_direction_is_rejected`: `direction="up"` raises `ValueError`.
   - `test_a_negative_cost_multiple_is_rejected`: `min_cost_multiple=-1.0` raises `ValueError`.
   - `test_check_strategy_inputs_accepts_one_interval_and_rejects_two`: `check_strategy_inputs("hitnrun2", ["1m"], {"min_cost_multiple": 2})` returns `HitNRun2StrategyService`; `["1m", "5m"]` raises `DomainError` with `error_code == "INVALID_PARAMETERS"`.
   - `test_the_sl_window_warms_up_first`: `_warm(s)`; after it `s.snapshot["decision"] == {"action": "skip", "reason": "warming up"}`.
   - `test_long_entry_on_a_close_below_the_previous_entry_window_low`: `_warm(s)`, then `TRIGGER` gives `Direction.LONG`, `entry_type == "market"`, `entry_price == 99.0`, `stop_loss_price == pytest.approx(98.01)`, `take_profit_price == pytest.approx(100.98)`, `entry_logic == "hitnrun2:breakdown"`. A `#` comment: the trigger's own low 98.9 is above its close, so a signal also proves the bar is not in its own window.
   - `test_short_entry_on_a_close_above_the_previous_entry_window_high`: `_warm(s, deep=None, high3=102.0)`, then bar `(101.2, 100.6, 101.0)` gives `Direction.SHORT`, `stop_loss_price == pytest.approx(102.0)`, `take_profit_price == pytest.approx(98.98)`, `entry_logic == "hitnrun2:breakup"`.
   - `test_the_sl_is_the_window_low_capped_at_max_loss_pct`: with `deep=50.0` the SL is `pytest.approx(98.01)`; a fresh strategy with `deep=98.7` gives `pytest.approx(98.7)`.
   - `test_the_tp_takes_the_window_high_above_the_min_profit`: `_warm(s, high7=105.0)`, then `TRIGGER` gives `take_profit_price == pytest.approx(105.0)`.
   - `test_direction_long_ignores_a_breakup`: `direction="long"`, `_warm(s, deep=None, high3=102.0)`, bar `(101.2, 100.6, 101.0)` returns `None` and `s.snapshot["decision"]["reason"] == "no breakout"`.
   - `test_one_position_until_the_opposite_fill`: `TRIGGER` gives LONG; `await s.on_order_filled(_fill("BUY"), 99.0)`; bar `(99.0, 98.5, 98.6)` at `i=9` returns `None` with reason `"position held"`; `await s.on_order_filled(_fill("SELL"), 98.6)`; bar `(98.6, 98.2, 98.3)` at `i=10` gives `Direction.LONG`.
   - `test_a_rejected_entry_clears_the_position`: `TRIGGER` gives LONG; `await s.on_order_rejected("zero position size")`; bar `(99.0, 98.5, 98.6)` at `i=9` gives `Direction.LONG`.
   - `test_a_restored_direction_blocks_an_entry`: `_warm(s)`; `s.restore_direction(Direction.SHORT)`; `TRIGGER` returns `None` with reason `"position held"`.
   - `test_an_entry_whose_nearer_exit_is_under_the_cost_multiple_is_skipped`: `spec=GOLD`, `_warm(s, deep=98.7)`; `TRIGGER` returns `None` and `s.snapshot["decision"] == {"action": "skip", "reason": "nearer exit under the cost multiple"}`. A `#` comment: the SL distance 0.3 is under 3 x 0.15.
   - `test_an_entry_whose_nearer_exit_covers_the_cost_multiple_is_taken`: `spec=GOLD`, `_warm(s, deep=98.0)`; `TRIGGER` gives `Direction.LONG` (nearer 0.99).
   - `test_the_cost_comes_from_the_contract_spec`: `deep=98.7` and `TRIGGER` give `Direction.LONG` with `spec=LINEAR_SPEC`, and also with `spec=GOLD, min_cost_multiple=1.0` (0.3 covers 0.15). Together with the skip test this shows the spec and the multiple decide, not a constant.
   - `test_an_entry_with_its_stop_on_the_wrong_side_is_skipped`: `spec=LINEAR_SPEC`, `_warm(s, deep=None)`; `TRIGGER` returns `None` with reason `"nearer exit under the cost multiple"` (the SL window low 99.5 is above the close 99.0).
3. Run `uv run python -m pytest tests/core_test/unit/domain/strategy/test_hitnrun2.py -q 2>&1 | tail -3`; expected red: an import error (the module does not exist). Record it.

**Success criteria:** the file holds 17 tests and fails only because the strategy is missing.

**Verify:** `uv run python -m pytest tests/core_test/unit/domain/strategy/test_hitnrun2.py -q 2>&1 | grep -c -E "ModuleNotFoundError|ImportError|cannot import"` prints a number `>= 1`.

### Task 03.3 — The strategy and its registry entry

**Goal:** `HitNRun2StrategyService` implements the rules and is registered as `hitnrun2`.

**Target files and symbols:** `hitnrun2_strategy_service.py` (`HitNRun2StrategyService`); `services/__init__.py` (`STRATEGY_REGISTRY`, `__all__`).

**Steps:**
1. Recover the old file as a starting point: `git show f3bb9e64^:src/pocketquant/core/domain/strategy/services/hitnrun2_strategy_service.py > src/pocketquant/core/domain/strategy/services/hitnrun2_strategy_service.py`.
2. Rewrite it to this shape (keep it about this short; no logging; no docstrings):
```python
from __future__ import annotations

from collections import deque
from typing import ClassVar

from pocketquant.core.domain.order import OrderSide
from pocketquant.core.domain.strategy.enums import Direction
from pocketquant.core.domain.strategy.strategy_service_interface import (
    FilledOrder,
    IStrategyService,
)
from pocketquant.core.domain.strategy.value_objects import Signal, StrategyConfig


class HitNRun2StrategyService(IStrategyService):
    DEFAULTS: ClassVar[dict] = {
        "entry_lookback_bars": 240,
        "sl_lookback_bars": 480,
        "tp_lookback_bars": 60,
        "max_loss_pct": 0.01,
        "min_profit_pct": 0.02,
        "direction": "both",
        "min_cost_multiple": 3.0,
    }

    def __init__(self, config: StrategyConfig) -> None:
        super().__init__(config)
        p = config.parameters or {}
        d = self.DEFAULTS
        self.entry_lookback_bars = p.get("entry_lookback_bars", d["entry_lookback_bars"])
        self.sl_lookback_bars = p.get("sl_lookback_bars", d["sl_lookback_bars"])
        self.tp_lookback_bars = p.get("tp_lookback_bars", d["tp_lookback_bars"])
        self.max_loss_pct = float(p.get("max_loss_pct", d["max_loss_pct"]))
        self.min_profit_pct = float(p.get("min_profit_pct", d["min_profit_pct"]))
        self.direction = p.get("direction", d["direction"])
        self.min_cost_multiple = float(p.get("min_cost_multiple", d["min_cost_multiple"]))
        lookbacks = (self.entry_lookback_bars, self.sl_lookback_bars, self.tp_lookback_bars)
        if len(config.intervals) != 1:
            raise ValueError("hitnrun2 decides on exactly one interval")
        if self.direction not in ("long", "short", "both"):
            raise ValueError(f"direction must be long|short|both, got {self.direction!r}")
        if any(n < 1 for n in lookbacks):
            raise ValueError("lookbacks must be >= 1")
        if self.max_loss_pct <= 0 or self.min_profit_pct < 0 or self.min_cost_multiple < 0:
            raise ValueError("max_loss_pct must be above 0; min_profit_pct, min_cost_multiple >= 0")
        spec = config.contract_spec
        # A fee on entry and on exit plus one spread, in price units on the seeded gold spec
        # (multiplier 1.0). A spec without a per-contract fee adds no commission here.
        self._round_trip = (spec.commission_per_contract or 0.0) * 2 + spec.spread
        self._highs: deque[float] = deque(maxlen=max(lookbacks))
        self._lows: deque[float] = deque(maxlen=max(lookbacks))

    async def on_start(self) -> None:
        await super().on_start()
        self._highs.clear()
        self._lows.clear()
        self._open_direction = None

    def _breakout(
        self, highs: list[float], lows: list[float], close: float
    ) -> tuple[Direction, float, float, str] | None:
        # LONG on a close below the entry-window low (SL below, TP above); SHORT mirrors.
        ...  # returns (direction, sl, tp, tag) with the old formulas, or None

    async def on_bar_completed(self, bar: dict) -> Signal | None:
        high, low, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
        # Read before the current bar joins, so a bar never breaks its own range.
        highs, lows = list(self._highs), list(self._lows)
        self._highs.append(high)
        self._lows.append(low)
        ...  # decide in this order: warming up -> position held -> no breakout ->
        ...  # cost filter -> enter; set self.snapshot; return the Signal or None
```
   Fill in the `...` parts exactly as follows:
   - `_breakout(highs: list[float], lows: list[float], close: float)`: if `self.direction != "short"` and `close < min(lows[-self.entry_lookback_bars:])`, return `(Direction.LONG, max(min(lows[-self.sl_lookback_bars:]), close * (1 - self.max_loss_pct)), max(max(highs[-self.tp_lookback_bars:]), close * (1 + self.min_profit_pct)), "breakdown")`; elif `self.direction != "long"` and `close > max(highs[-self.entry_lookback_bars:])`, return `(Direction.SHORT, min(max(highs[-self.sl_lookback_bars:]), close * (1 + self.max_loss_pct)), min(min(lows[-self.tp_lookback_bars:]), close * (1 - self.min_profit_pct)), "breakup")`; else `None`.
   - `on_bar_completed` decision: `len(lows) < self.sl_lookback_bars` -> `("skip", "warming up")`; `self._open_direction is not None` -> `("hold", "position held")`; `_breakout(...)` is `None` -> `("hold", "no breakout")`; else compute `nearer = min(tp - close, close - sl)` for LONG and `min(close - tp, sl - close)` for SHORT; with a `#` comment "A stop on the wrong side of the close gives a distance <= 0, which no cost covers.", if `nearer <= 0 or nearer < self.min_cost_multiple * self._round_trip` -> `("skip", "nearer exit under the cost multiple")`; else `("enter_long" | "enter_short", tag)`, set `self._open_direction = direction` and build `Signal(symbol=self.config.symbol, direction=direction, confidence=0.7, timestamp=bar["timestamp"], subscription_id=self.id, entry_price=close, stop_loss_price=sl, take_profit_price=tp, entry_logic=f"hitnrun2:{tag}")`. Always set `self.snapshot = {"readings": [], "decision": {"action": action, "reason": reason}}` before returning.
   - `on_order_filled(self, order: FilledOrder, fill_price: float)`: with the `#` comment "Broker SL/TP fills arrive as the opposite side, so an opposite-side fill is the close.", clear `_open_direction` when it is LONG and `order.side == OrderSide.SELL`, or SHORT and `order.side == OrderSide.BUY`.
   - `on_order_rejected(self, reason: str)`: with the `#` comment "Only market entries are sent, so a rejection means no position opened.", set `_open_direction = None`.
3. Registry in `services/__init__.py`: import `HitNRun2StrategyService` from `pocketquant.core.domain.strategy.services.hitnrun2_strategy_service`; `STRATEGY_REGISTRY = {"triple_screen": TripleScreenStrategyService, "hitnrun2": HitNRun2StrategyService}`; add `"HitNRun2StrategyService"` to `__all__` (sorted).
4. Delete nothing from the old file's behaviour except the `datetime.now` fallback for the timestamp (the engine always sets `bar["timestamp"]`, `strategy_app_service.py:73-83`).

**Success criteria:** every Task 03.2 test passes; the registry lists both strategies.

**Verify:** `uv run python -m pytest tests/core_test/unit/domain/strategy/test_hitnrun2.py -q 2>&1 | tail -1` contains `17 passed` and contains neither `failed` nor `error`; `uv run python -c "from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY; print(sorted(STRATEGY_REGISTRY))"` prints `['hitnrun2', 'triple_screen']`.

### Task 03.4 — Backtest-path test: the symbol's spec decides the filter

**Goal:** a real backtest over seeded Mongo hands the symbol's spec to hitnrun2: a free spec trades, a costly spec trades nothing (AC4).

**Target files and symbols:** `tests/backtest_test/engine/test_hitnrun2_backtest.py` (`test_the_backtest_filter_reads_the_symbol_spec`).

**Steps:**
1. Copy `_execution`, `_cmd_svc` and the `_reset_sim_time` fixture from `tests/backtest_test/engine/test_triple_screen_backtest.py:39-59`.
2. `_T0 = datetime(2026, 1, 1, tzinfo=UTC)`. `_series(symbol)` builds 2 days of 1m `Bar`s from `_T0` with `close_k = 100 + 10 * sin(2 * pi * k / 30)`, `open` = previous close, `high = max(open, close) + 0.2`, `low = min(open, close) - 0.2`, `volume=1.0`, `tick_count=1` (same shape as the Triple Screen `_series`). A `#` comment: a 30-bar sine keeps the previous trough inside the 40-bar SL window, so breakdowns have a stop on the right side.
3. Parametrize `(symbol, spec, any_trades)` over `("HNRFREE:BINANCE", ContractSpec(), True)` and `("HNRDEAR:BINANCE", ContractSpec(commission_per_contract=1.0), False)`. A `#` comment: the nearer exit is at most `max_loss_pct` of about 100, near 1.0, below 3 x 2.0, so the costly spec must skip every entry; distinct symbols avoid the 60 s symbol lookup cache.
4. Test body: delete `bars` and `symbols` documents for `symbol` (collections `COLLECTION_BARS`, `COLLECTION_SYMBOLS` from `pocketquant.core.common.constants`); `await SymbolRepository(database).upsert(Symbol.create(symbol, contract_spec=spec))`; insert `_series(symbol)`; run `RunBacktestCommand(strategy_id="hitnrun2", symbol=symbol, intervals=["1m"], start_date=_T0 + timedelta(days=1), end_date=_T0 + timedelta(days=2), slippage_bps=0, commission_bps=0, parameters={"entry_lookback_bars": 20, "sl_lookback_bars": 40, "tp_lookback_bars": 10, "min_profit_pct": 0.0})` through `_cmd_svc(database).run` and `_execution(database).execute_and_persist`; load the run with `BacktestRepository(database).get(run_id)`; assert `status == "finished"` and `metrics.total_trades >= 1` when `any_trades`, else `== 0`. Delete the same `bars` and `symbols` documents in a `finally`.
5. Run the file.

**Success criteria:** 2 cases pass.

**Verify:** `uv run python -m pytest tests/backtest_test/engine/test_hitnrun2_backtest.py -q 2>&1 | tail -1` contains `2 passed` and contains neither `failed` nor `error`.

### Task 03.5 — CLOSE

**Goal:** gates hold, one feature commit, CI green on `develop`.

**Target files and symbols:** all files of this phase.

**Steps:**
1. AGNOSTIC (plan.md Conventions) prints `0`.
2. GATES with pyright on `src tests/core_test/unit/domain/strategy/test_hitnrun2.py tests/backtest_test/engine/test_hitnrun2_backtest.py`; FULLSUITE. Record every tail line.
3. `git add` the four files; commit `feat(strategy): add the hitnrun2 1m breakout strategy with a cost filter`; push `develop`; run the CLOSE check.

**Success criteria:** CI `success` on `HEAD`.

**Verify:** `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 1 --json headSha,status,conclusion -q '.[0] | "\(.status) \(.conclusion) \(.headSha)"'` prints `completed success <sha>` with `<sha>` equal to `git rev-parse HEAD`.

## Rollback

`git revert <feature commit>` on `develop` and push. Nothing reaches prod before Phase 04.

## Report

`reports/phase-03-hitnrun2-strategy.md`: entry-gate outputs; the Task 03.1 greps and test line (and any [ASK] answer); the expected red; each Verify output; AGNOSTIC, GATES and FULLSUITE lines; any metric-ceiling commit; the commit sha and CI run id; then `Result: PASS`.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same
failure evidence to the user. Never continue by self-reasoning.

