---
phase: 14
title: "Triple Screen strategy and tests"
status: completed
priority: P1
effort: 1d
dependencies: [9, 11]
---

# Phase 14: Triple Screen strategy and tests

<!-- Red team 2026-11-01: #15 -->
No open issue. AGNOSTIC is the plan.md Conventions check "Strategy-agnostic UI": `git grep -n -i -E "triple[ _-]?screen|force[ _-]?index|elder" -- web/src src/pocketquant/app src/pocketquant/engine | wc -l` prints `0`.

## Goal

Triple Screen is the first multi-timeframe consumer: one strategy file and one registry entry, with its own parameters choosing `entry_type` (market|stop) and `exit_mode` (sl_tp|strategy), and tests that include a leak test and the resting-stop and rejection rules.

## Context

- Inputs from earlier phases (not on HEAD): Phase 06 `StrategyConfig.intervals: list[str]`, `IStrategyService.DEFAULTS: ClassVar[dict]`, `check_strategy_inputs` (rejects keys not in `DEFAULTS`, type-checks values against their default, maps a constructor `ValueError` to `INVALID_PARAMETERS`), `RunBacktestCommand.intervals`; Phase 07 `bar["context"]` = `{interval: [Bar, ascending]}` for `intervals[1:]`, holding only bars with `datetime + step <= entry bar start`; Phase 09 `Signal.entry_type: Literal["market","stop"]` (a stop needs `entry_price` and LONG/SHORT), EXIT = cancel the pending stop then close; Phase 11 `self.snapshot` set by the strategy as `{"readings": [...], "decision": {...}}`. Phase 05 leaves `STRATEGY_REGISTRY` empty.
- <!-- Red team 2026-11-01: #1 --> Engine rules this strategy relies on (plan.md Design verdicts "Resting stop trigger order" and "Pending stop"): a resting stop never survives a stop, unload, edit or trader handover; takeover restores no resting stop and calls only `restore_direction` from the open position; an unchanged re-placed stop (same side and price) is kept, a moved one is cancelled and re-sent. So after any start the strategy holds no stop until it places one, and it must re-place its stop on every bar while the setup holds.
- <!-- Red team 2026-11-01: #2 --> EXIT is exempt from the stale and gap skips; an in-flight block rejects it, and the engine calls `on_order_rejected(reason)` (plan.md Design verdict "EXIT"). The engine also calls `on_order_rejected("warmup")` for every warm-up replay signal (`src/pocketquant/engine/strategy/strategy_app_service.py:265-266`) and then `restore_direction` from the open position (`:271`). The hook carries only the reason (`src/pocketquant/core/domain/strategy/strategy_service_interface.py:42-43`), so the strategy remembers what it last sent.
- C10: Triple Screen is the first consumer only; nothing Triple-Screen-specific goes into platform or UI code. Its names live only in its strategy file, its tests and the registry entry.
- Contract C7 snapshot shape: `readings[{interval, name, value, ok}]`, `decision{action, reason}`; the engine adds `bar_start`, `interval`, `outcome`, `pending`.
- Governance `docs/governance/no-look-ahead-rules.md:7-9,19-22`: read only HTF bars closed by the decision bar's close; check the first entry bar of each HTF bucket; compare indicator values, not only entry flags; warm up until every HTF indicator is defined.
- Style model on HEAD (deleted in Phase 05): `src/pocketquant/core/domain/strategy/services/hitnrun2_strategy_service.py:25-129` (`__init__` validation with `ValueError` `:36-38`, `on_order_filled` resets on the opposite side `:98-104`, `on_order_rejected` `:106-107`, `Signal` build `:118-129`). Base class `strategy_service_interface.py:16-43` (`_open_direction`, `restore_direction`). `Bar` fields `close`, `volume`, `datetime` (`src/pocketquant/core/domain/bar/entities.py:22-34`).
- No indicator library exists in `src` (`git grep -n -i "def ema\|macd" -- src` prints nothing); EMA and MACD are computed inline in the strategy file.
- <!-- Red team 2026-11-01: #15 --> Tests: this phase needs no strategy double. The shared `ScriptedStrategy` (`tests/strategy_doubles.py`, Phase 05) and the `probe_registry` fixture serve the engine tests. The one rubric degrees-of-freedom test is Phase 06's (`tests/scripts/rubric/test_static_audit.py`, over the probe); this phase adds no second rubric test and no registry-pinning test (A2 already checks the registry keys).
- Backtest test pattern on HEAD: `tests/backtest_test/test_backtest_single_run_direct_task.py:94-127` (`_seed_bars`, `_execution`, `_cmd_svc`, `_command`) and `:135-160` (`execute_and_persist`, status `finished`); fixture `database` `tests/backtest_test/conftest.py:38-50` (clears backtest collections, not bars).

**Rules fixed here.** Intervals: `entry = intervals[0]`, `middle = intervals[1]`, `top = intervals[2]`. Top screen (tide): MACD histogram `hist = (EMA_fast - EMA_slow) - EMA_signal(EMA_fast - EMA_slow)` over `context[top]` closes; tide is `up` when `hist[-1] > hist[-2]`, `down` when `<`, else `flat`; fewer than `macd_slow + macd_signal + 1` top bars is `skip` with reason `top interval warming up`. Middle screen (wave): `force = EMA(force_period)` of `(close - prev_close) * volume` over `context[middle]`; fewer than `force_period + 1` middle bars is `skip` with `middle interval warming up`. Long setup = tide up and `force < 0`; short setup = tide down and `force > 0`. Entry: keep the last `stop_lookback` entry bars including the current one; SL (long) = lowest low of them, (short) = highest high. `market` enters at the bar close; `stop` places a buy stop at the current entry bar's high (sell stop at its low) and sends it again on every bar while the setup holds (the engine keeps an unchanged stop and replaces a moved one). Risk = `|entry - SL|`; `risk <= 0` is `skip` with `no risk distance`. TP = `entry ± risk_reward * risk` only for `sl_tp`, else `None`. EXIT when a stop is armed and the setup is gone; in `strategy` mode also when a position is held and the tide turns against it (LONG with tide down, SHORT with tide up). A held position in `sl_tp` mode holds.

<!-- Red team 2026-11-01: #1, #2 -->
**State rules.** `_armed` is the side of the stop the strategy believes rests; it starts `None` after `on_start` (no stop survives a restart). A fill while flat sets `_open_direction` from the fill side (BUY → LONG, SELL → SHORT) and clears `_armed`, so a stop fill is recognised even when `_armed` was lost; an opposite-side fill while holding clears `_open_direction`. `on_order_rejected` undoes only what the rejected signal changed: a rejected market entry clears `_open_direction`; a rejected stop entry keeps `_armed` (a stop placed on an earlier bar may still rest; at worst the next EXIT is ignored by the engine); a rejected EXIT keeps `_open_direction` and restores the `_armed` value that EXIT cleared, so the next bar decides EXIT again.

## Entry gate

1. Conventions EG (1)-(3); the previous report is `reports/phase-13-*.md`.
2. `git grep -n "DEFAULTS: ClassVar" -- src/pocketquant/core/domain/strategy/strategy_service_interface.py | wc -l` prints `1`.
3. `git grep -n "entry_type" -- src/pocketquant/core/domain/strategy/value_objects.py | wc -l` prints a number `>= 1`.
4. `git grep -n "snapshot" -- src/pocketquant/core/domain/strategy/strategy_service_interface.py | wc -l` prints a number `>= 1`.
5. `git grep -n "\"context\"" -- src/pocketquant/engine/strategy/strategy_app_service.py | wc -l` prints a number `>= 1`.
6. `docker ps > /dev/null 2>&1 && echo docker-ok` prints `docker-ok` (start Docker Desktop per FULLSUITE and retry once).

On a miss, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261101-0843-stf-to-mtf-foundation --from 14 after <UTC time>
```

## Files

- Create: `src/pocketquant/core/domain/strategy/services/triple_screen_strategy_service.py`, `tests/core_test/unit/domain/strategy/test_triple_screen.py`, `tests/backtest_test/engine/test_triple_screen_backtest.py`.
- Modify: `src/pocketquant/core/domain/strategy/services/__init__.py`.
- Delete: none.

## Tasks

### Task 14.1 — Unit tests first (screens, settings, leak, snapshot, state)

**Goal:** the strategy's behaviour is pinned before it exists.

**Target files and symbols:** `tests/core_test/unit/domain/strategy/test_triple_screen.py`.

**Steps:**
1. Helpers in the test file: `_cfg(intervals=("15m","1h","4h"), **params)` builds `StrategyConfig(id="sub-1", name="triple_screen", symbol="XAUUSD:EXNESS", intervals=list(intervals), parameters=params)`; `_bars(interval, closes, volume=1.0, t0=datetime(2026, 1, 5, tzinfo=UTC))` builds ascending `Bar`s with `open=high=low=close`, stepped by `INTERVAL_SECONDS[interval]`; `_entry(high, low, close, ts)` builds the bar dict (`symbol, interval="15m", open, high, low, close, volume=1.0, timestamp=ts`) and sets `context`; `_fill(side)` is an object with `side=OrderSide.<side>`. Series: `TOP_UP = [100.0] * 58 + [101.0, 103.0]`, `TOP_DOWN = [100.0] * 58 + [99.0, 97.0]`, `TOP_FLAT = [100.0] * 60`, `MID_DIP = [100.0] * 10 + [99.0]` (force < 0), `MID_POP = [100.0] * 10 + [101.0]` (force > 0). Before the decision bar feed five entry bars whose context is `TOP_FLAT` + `MID_DIP` (no setup), so `stop_lookback=5` is full and nothing is sent early.
2. Tests (names state the rule):
   - `test_two_intervals_are_rejected` (`ValueError`), `test_an_unknown_entry_type_is_rejected`, `test_an_unknown_exit_mode_is_rejected`.
   - `test_the_top_interval_warming_up_skips`: 30 top bars, returns `None`, `snapshot["decision"]["action"] == "skip"`.
   - `test_market_long_when_the_tide_rises_and_force_is_below_zero`: `TOP_UP` + `MID_DIP` gives `Direction.LONG`, `entry_type == "market"`, `stop_loss_price < close < take_profit_price`.
   - `test_market_short_mirrors_the_long`: `TOP_DOWN` + `MID_POP` gives `Direction.SHORT`, `take_profit_price < close < stop_loss_price`.
   - `test_a_stop_entry_rests_at_the_entry_bar_high`: `entry_type="stop"` gives `entry_type == "stop"`, `entry_price == bar["high"]`.
   - `test_the_stop_is_sent_again_each_bar_while_the_setup_holds`: two consecutive decision bars with highs 101.2 then 101.0 give two stop signals with those prices; <!-- Red team 2026-11-01: #1 --> a third bar with the same high 101.0 sends the stop again (the engine, not the strategy, keeps an unchanged stop).
   - `test_exit_when_the_setup_is_gone_with_a_stop_armed`: after a stop signal, a bar with `TOP_FLAT` gives `Direction.EXIT`.
   - <!-- Red team 2026-11-01: #1 --> `test_a_fresh_start_holds_no_stop`: after `on_start`, a `TOP_FLAT` bar returns `None` with `decision["reason"] == "no setup"` (no EXIT for a stop that cannot exist), and a following `TOP_UP` + `MID_DIP` bar with `entry_type="stop"` sends the stop.
   - <!-- Red team 2026-11-01: #1 --> `test_a_fill_while_flat_takes_the_side_of_the_fill`: a fresh `entry_type="stop", exit_mode="strategy"` strategy with no armed stop gets `await s.on_order_filled(_fill("BUY"), 101.0)`; then a `TOP_DOWN` bar gives `Direction.EXIT`.
   - `test_strategy_mode_sets_no_take_profit_and_exits_on_a_tide_flip`: `exit_mode="strategy"`, `take_profit_price is None`; after `await s.on_order_filled(_fill("BUY"), 101.0)`, a `TOP_DOWN` bar gives `Direction.EXIT`.
   - `test_sl_tp_mode_holds_a_position_on_a_tide_flip`: same as above with `sl_tp`, returns `None` and `decision["action"] == "hold"`.
   - <!-- Red team 2026-11-01: #2 --> `test_a_rejected_exit_keeps_the_position_and_exits_again`: strategy mode, LONG after a BUY fill; a `TOP_DOWN` bar gives EXIT; `await s.on_order_rejected("inflight")`; the next `TOP_DOWN` bar gives EXIT again.
   - <!-- Red team 2026-11-01: #2 --> `test_a_rejected_setup_gone_exit_is_sent_again`: a stop signal, then a `TOP_FLAT` bar gives EXIT; `on_order_rejected("inflight")`; the next `TOP_FLAT` bar gives EXIT again.
   - <!-- Red team 2026-11-01: #2 --> `test_a_rejected_market_entry_clears_the_position`: a market LONG, then `on_order_rejected("zero position size")`; a `TOP_DOWN` bar in strategy mode gives no EXIT (`None` or a SHORT setup signal, never `Direction.EXIT`).
   - `test_the_snapshot_reports_three_readings_and_a_decision`: readings intervals are `["4h","1h","15m"]`, names `["macd_hist_slope","force_index","trigger"]`, each has `value` and `ok`; decision has `action` and `reason`.
   - `test_a_leaked_current_bucket_changes_the_decision` (leak test): entry bar at the first 15m of a new 4h bucket; context A = `TOP_UP` ending at the previous bucket gives LONG; context B = A plus one more 4h bar stamped at the current bucket start with close `90.0` gives no LONG. So a served partial bucket would change the decision; Phases 07 and 08 prove the engine never serves it.
   - `test_the_tide_reading_is_computed_from_the_given_bars_only`: with `TOP_FLAT` the `macd_hist_slope` value is exactly `0.0` (indicator value check, governance check 3).
3. Run `uv run python -m pytest tests/core_test/unit/domain/strategy/test_triple_screen.py -q 2>&1 | tail -1`; expected red: an import error or `failed` (the module does not exist).

**Success criteria:** the file exists and fails only because the strategy is missing.

**Verify:** no verification needed (Task 14.2's Verify runs this file).

### Task 14.2 — Strategy and registry entry

**Goal:** `TripleScreenStrategyService` implements the rules above and is registered as `"triple_screen"`.

**Target files and symbols:** `triple_screen_strategy_service.py` (`TripleScreenStrategyService`, module-level `_ema`); `services/__init__.py` (`STRATEGY_REGISTRY`, `__all__`).

**Steps:**
1. `class TripleScreenStrategyService(IStrategyService)` with `DEFAULTS: ClassVar[dict] = {"entry_type": "market", "exit_mode": "sl_tp", "macd_fast": 12, "macd_slow": 26, "macd_signal": 9, "force_period": 2, "stop_lookback": 5, "risk_reward": 2.0}` (no `direction`: the strategy trades both sides).
2. `__init__`: read each key with `p.get(key, self.DEFAULTS[key])`; raise `ValueError` unless `len(config.intervals) == 3`, `entry_type in ("market","stop")`, `exit_mode in ("sl_tp","strategy")`, every integer is `>= 1`, `macd_fast < macd_slow`, `risk_reward > 0`. State: `self._recent: deque[tuple[float, float]]` (high, low; `maxlen=stop_lookback`), `self._armed: Direction | None = None`, `self._sent: str | None = None` (`"market"`, `"stop"` or `"exit"`), `self._armed_before_exit: Direction | None = None`, `self.snapshot = None`. `on_start` clears them and `_open_direction`.
3. `_ema(values, period) -> list[float]` (seed with the first value, `k = 2 / (period + 1)`), one module-level function used for MACD, signal and force.
4. `on_bar_completed(bar)`: append `(high, low)`; compute tide and force from `bar["context"]` with the rules; build readings `[{interval: top, name: "macd_hist_slope", value: <hist[-1] - hist[-2], or None while the top interval warms up>, ok: tide != "flat"}, {interval: middle, name: "force_index", value: <force, or None while the middle interval warms up>, ok: <setup holds>}, {interval: entry, name: "trigger", value: <entry or stop price or None>, ok: <a signal is sent>}]` (a computed `0.0` stays `0.0`, never `None`: `test_the_tide_reading_is_computed_from_the_given_bars_only` asserts it) <!-- Consistency sweep 2026-11-01 -->; decide in this order: warming up -> `skip`; position held -> `exit` (strategy mode, tide against) or `hold`; setup holds -> `enter_long`/`enter_short` (market sets `_open_direction` at once, as the STF strategies did; stop sets `_armed`); setup gone with `_armed` -> `exit`, saving `_armed_before_exit = _armed` and clearing `_armed`; else `hold` with `no setup`. Set `_sent` to the kind of signal returned (or `None`). Set `self.snapshot = {"readings": readings, "decision": {"action": ..., "reason": ...}}` on every bar, then return the `Signal` (`timestamp=bar["timestamp"]`, `subscription_id=self.id`, `confidence=0.7`, `entry_logic="triple_screen:<action>"`) or `None`. An EXIT signal carries no prices.
5. <!-- Red team 2026-11-01: #1, #2 --> `on_order_filled(order, fill_price)` and `on_order_rejected(reason)` follow the State rules: a fill while `_open_direction is None` sets it from `order.side` and clears `_armed`; an opposite-side fill clears `_open_direction`; a rejection with `_sent == "market"` clears `_open_direction`, with `_sent == "exit"` restores `_armed = _armed_before_exit`, with `_sent == "stop"` changes nothing; every rejection then sets `_sent = None`.
6. Registry: `STRATEGY_REGISTRY = {"triple_screen": TripleScreenStrategyService}`, `__all__` lists both names.
7. Comments, no docstrings, no logging in the strategy: one `#` line above the stop rule (re-sent every bar while the setup holds, because no resting stop survives a restart and the engine keeps an unchanged one); one `#` line above `on_order_rejected` (a rejection undoes only what the rejected signal changed, so a rejected EXIT is retried on the next bar).

**Success criteria:** every Task 14.1 test passes.

**Verify:** `uv run python -m pytest tests/core_test/unit/domain/strategy/test_triple_screen.py -q 2>&1 | tail -1` contains `passed` and does not contain `failed` or `error`.

### Task 14.3 — Backtest over seeded Mongo

**Goal:** both parameter settings run end to end through the backtest path with real higher-timeframe context.

**Target files and symbols:** `tests/backtest_test/engine/test_triple_screen_backtest.py` (`test_triple_screen_backtest_finishes_with_trades`).

**Steps:**
1. Backtest test, parametrized over `{"entry_type": "market", "exit_mode": "sl_tp"}` and `{"entry_type": "stop", "exit_mode": "strategy"}`. Copy the helper pattern of `test_backtest_single_run_direct_task.py:94-127` (`_execution`, `_cmd_svc`) into this file. Seed `BTCUSDT:BINANCE` bars from `t0 = 2026-01-01T00:00Z` for 30 days, deleting the three intervals' bars for the symbol before seeding and in a `finally`: 4h close `100 + 10*sin(2*pi*i/30)`; 1h close `top(t) + 0.5*sin(2*pi*j/6)`; 15m close `100 + 10*sin(2*pi*k/480) + 0.3*sin(2*pi*k/7)`, `open` = previous close, `high = max(open, close) + 0.2`, `low = min(open, close) - 0.2`; volume `1.0`. Run `RunBacktestCommand(strategy_id="triple_screen", symbol="BTCUSDT:BINANCE", intervals=["15m","1h","4h"], start_date=t0 + 7 days, end_date=t0 + 30 days, slippage_bps=0, commission_bps=0, parameters=<setting>)`, then `execute_and_persist`. Assert the stored run has `status == "finished"` and `metrics.total_trades >= 1`.
2. <!-- Red team 2026-11-01: #15 --> No rubric test here (Phase 06 owns the one degrees-of-freedom test).
3. Run the file; it passes against Task 14.2's code (no expected red: it covers code that now exists). If the backtest test finds no trade, that is a failed Verify.

**Success criteria:** 2 backtest cases pass.

**Verify:** `uv run python -m pytest tests/backtest_test/engine/test_triple_screen_backtest.py -q 2>&1 | tail -1` contains `2 passed` and does not contain `failed` or `error`.

### Task 14.4 — CLOSE

**Goal:** gates, A2 and AGNOSTIC hold; one commit; CI green.

**Target files and symbols:** all files of this phase.

**Steps:**
1. A2: `git grep -n -E "hitnrun2|engulfing_pullback30|engulfing_detector|\"engulfing\"" -- src tests scripts | wc -l` prints `0`, and `uv run python -c "from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY; print(list(STRATEGY_REGISTRY))"` prints `['triple_screen']`.
2. AGNOSTIC prints `0`.
3. GATES and FULLSUITE (raise the metric ceiling in its own commit only if the ratchet alone fails).
4. Commit `feat(strategy): add the triple screen strategy`; push `develop`; run the CLOSE check.

**Success criteria:** CI `success` on HEAD.

**Verify:** `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 1 --json headSha,status,conclusion -q '.[0] | "\(.status) \(.conclusion) \(.headSha)"'` prints `completed success <sha>` with `<sha>` equal to `git rev-parse HEAD`.

## Rollback

`git revert <commit>` on `develop` and push; the registry is empty again. Nothing reaches prod before Phase 15.

## Report

`reports/phase-14-triple-screen.md`: entry-gate outputs; the expected red of Task 14.1; each Verify output; the A2 and AGNOSTIC outputs; GATES and FULLSUITE tail lines; any metric-ceiling commit; commit sha and CI run id; then `Result: PASS`.

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
