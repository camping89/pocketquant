---
phase: 6
title: "Strategy runtime and restart state: guards, signal tasks, latency, warm-up, paper restore"
status: pending
priority: P1
effort: 1.5d code + deploy D-3 + 2 h watch
dependencies: [5]
---

# Phase 06 — Strategy runtime and restart state (deploy D-3)

## Goal

The strategy engine refuses entries on stale or gapped bars (exits always run), never sends two entries for one subscription, keeps venue orders out of the bar handler, logs one latency line per live signal, and has the single `trading_until` switch Phase 07 drives. A started strategy warms up from stored bars and gets its open direction back; a restart rebuilds paper brokers (balance and SL/TP positions) instead of deleting paper rows. `take_over()` exists and runs once at boot; Phase 07 only moves the call. For Phase 07 the engine also counts its running bar handlers, cancels signal tasks that have not reached the broker (`cancel_pending_signals()`), stops with a bounded wait (`stop(timeout_s)`), logs lease and drain discards at INFO, and passes `trading_until` to the broker as the order deadline. <!-- Red team 2026-10-28: #4 #5 --> Phases 04-06 then deploy together as D-3 (live stays off).

## Context

Line numbers are from `develop` @ 453e8e90; Phases 03-05 may shift them, so locate targets by symbol first.

- `StrategyAppService` (`src/pocketquant/engine/strategy/strategy_app_service.py`): `__init__` `:42-66`, `stop` `:88-99`, `start_strategy` `:139-154` (connects the broker, then `on_start`), `unload_strategy` `:167-195`, `_on_bar_completed` `:241-270` (computes the signal and awaits `_process_signal` inline, inside the bus publish), `_process_signal` `:323-390`, `_get_or_create_broker` `:421-442`. `fills_async` is `False` on the port (`core/domain/brokers/broker_port.py:23`) and `True` on Exness (`core/infra/brokers/exness/exness_broker_adapter.py:96`). Paper forbids concurrent calls (`core/infra/brokers/paper/paper_broker_adapter.py:81-83`), so paper stays inline (A6).
- The backtest sandbox today builds the same engine without repositories (`engine/backtest/backtest_sandbox_app_service.py:136-142`) and registers strategies through `inject_prepared_strategy` (`strategy_app_service.py:197-219`, called from `engine/backtest/backtest_execution_service.py:131`), never `start_strategy` or `take_over`; backtest events carry no `bar_end` (Phase 05 default), so no guard fires there.
<!-- Red team 2026-10-28: #14 -->
- `StrategyAppService(` is built at two `src` sites (`app/di/services.py:145`, `engine/backtest/backtest_sandbox_app_service.py:136`) and 14 test sites: `tests/backtest_test/engine/test_engulfing_backtest.py:183`, `tests/backtest_test/engine/test_engulfing_pullback30_touch_backtest.py:208`, `tests/backtest_test/engine/test_hitnrun2_backtest.py:238`, `tests/backtest_test/test_backtest_single_run_direct_task.py:254`, `tests/engine_test/strategy_injection_roundtrip_characterization_test.py:81`, `tests/engine_test/test_async_broker_fill_wiring.py:112`, `tests/engine_test/test_contract_spec_wiring.py:64,254`, `tests/engine_test/test_live_trade_collector_integration.py:81`, `tests/engine_test/test_order_filled_event_routing.py:63`, `tests/engine_test/test_paper_position_lifecycle.py:62`, `tests/engine_test/test_reconcile_restart_resume_integration.py:67`, `tests/engine_test/test_strategy_reject_delivery.py:100`, `tests/engine_test/test_subscription_broker_selection.py:106` (re-list with `git grep -n "StrategyAppService(" -- src tests`).
<!-- Red team 2026-10-28: #4 -->
- `engine.stop()` callers: `app/di/services.py:160` (the provider finalizer), `tests/app_test/integration/test_app_standalone_runtime.py:109`, `tests/engine_test/test_reconcile_restart_resume_integration.py:173`. `EventBus.publish` awaits each handler in turn (`core/common/messaging/event_bus.py:26-42`), so the paper fill of an inline signal runs inside `_on_bar_completed`.
<!-- Red team 2026-10-28: #10 -->
- `_process_signal` callers today: `strategy_app_service.py:261`; tests `tests/engine_test/test_contract_spec_wiring.py:120,304` (prices 4500.0 and 7800.0), `tests/engine_test/test_strategy_reject_delivery.py:137,154,166` (100.0); Phase 04 adds one in `tests/engine_test/test_paper_position_lifecycle.py`.
<!-- Red team 2026-10-28: #9 -->
- Prod logs are console lines with ANSI colours (`LOG_FORMAT=console`): `<ts> [info     ] live.signal_latency  closed_by=timer t0_bar_end=2026-…`. Strip the colours with `sed 's/\x1b\[[0-9;]*m//g'` and read `key=value` pairs; never parse JSON.
- Every strategy resets `_open_direction` in `on_start` (`hitnrun2_strategy_service.py:68-73`, `engulfing_strategy_service.py:74-79`, `engulfing_pullback30_touch_strategy_service.py:88-93`) and declares it in its own `__init__` (`:66`, `:72`, `:85`); the base class has no direction (`core/domain/strategy/strategy_service_interface.py:35-38`). hitnrun2 sets the direction when it signals and clears it in `on_order_rejected` (`hitnrun2_strategy_service.py:97-132`); it needs 480 prior bars (`:35-36,60-62`, buffer 481).
- `BarRepository.find(symbol, interval, start_date, end_date, limit)` returns bars newest first (`core/infra/persistence/repositories/bar_repository.py:146-174`).
- Paper rows are deleted at boot: `get_position_tracker` passes paper ids (`app/di/services.py:122-133`) to `PositionAppService.start` -> `load_open_positions` (`engine/execution/position_app_service.py:31-53`). The mirror opens without SL/TP (`:73-80`) because `OrderFilledEvent` has none (`core/domain/order/events.py:21-30`); producers `engine/execution/order_app_service.py:87-96,160-169`. `PositionAggregate.to_mongo` stores `sl_price`, `tp_price`, `opened_at`, `multiplier` but not `entry_commission` (`core/domain/position/entities.py:247-264`).
- Paper cash: an open debits the entry commission; a reduce credits the realized PnL and debits the exit commission (`paper_broker_adapter.py:433-464`). `TradeClosedEvent.pnl` is the gross realized PnL and `commission` is entry share plus exit (`core/domain/position/entities.py:152-154,165-181`); `LiveTradeCollector` copies both into `Trade` with `run_id = subscription_id` (`engine/live/live_trade_collector.py:53-75`). So the pre-restart cash is `initial + sum(pnl - commission) over closed trades - entry commission of the open positions`. Read `entities.py:131-198` once to confirm before Task 6.6 (the plan's open item "pnl net or gross" is answered: gross).
- Boot order: `bootstrap_live_instances` (`app/main.py:63`) loads and starts every subscription, then `register_health_checks`, then `start_quote_feed` (`:65`); bars only flow after the feed starts, so `take_over()` inserted right after `:63` runs before any bar.
- D26 stale budgets (s): 1m 10, 5m 30, 15m 60, 1h 120, 4h 300, 1d 600, 1w 600. Every interval closes on the timer at its end (D35, Phase 05), so a 4h/1d/1w bar whose market closed early (Friday's last bar) is published at its bucket end and is not stale. <!-- Validation 2026-10-28: D35 -->
- Successor rule (A16, Phase 05 note): a live bar is not the successor of the strategy's last bar when `calendar.trading_minutes(last_bar_start + interval, event.bar_start)` is non-empty. This one check covers skipped buckets and the warm-up seam.

## Entry gate

Run each command from `D:/w/_me/algotrading/pocketquant`:

1. `git fetch -q origin && echo "branch=$(git rev-parse --abbrev-ref HEAD) dirty=$(git status --porcelain -- src web deploy tests scripts docs | wc -l | tr -d ' ') synced=$(test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo yes || echo no)"` prints `branch=develop dirty=0 synced=yes`.
2. `git grep -n -E "flush_all_bars|_seed_builder_from_mongo" -- src | wc -l | tr -d ' '; grep -c "second=12" src/pocketquant/engine/market_data/app_services/sync_jobs.py` prints `0` then `1` (Phase 05 merged). <!-- Red team 2026-10-28: #10 -->
3. `export GH_TOKEN=$(gh auth token --user camping89); gh run list --workflow cicd.yml --branch develop --limit 5 --json headSha,conclusion -q ".[] | select(.headSha==\"$(git rev-parse HEAD)\") | .conclusion" | head -1` prints `success`.
4. NTP gate (D20): `mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key; HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'timedatectl show -p NTPSynchronized --value'` prints `yes`.
5. `docker ps > /dev/null 2>&1 && echo docker-ok` prints `docker-ok` (if not, start `"/c/Program Files/Docker/Docker/Docker Desktop.exe" &`, wait 10 s, re-run once).

On any miss: run `rm -f .cache/ssh/vps_key`, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <which gate line failed and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261028-0652-exness-only-parallel-runtime --from 06 after <UTC time>
```

**Resumed run.** Before each task, run its Verify; when it already meets its pass condition, mark the task done and go to the next one. After this phase's own unpushed commits, line 1 may print `synced=no`; that passes when `git rev-list --count HEAD..origin/develop` prints `0`, and line 3 then checks `origin/develop` instead of `HEAD`. A resume after the D-3 deploy (Task 6.9 waits) meets lines 1-3 as written, because Task 6.7 pushed `HEAD`.

## Files to create/modify

- Modify: `src/pocketquant/engine/strategy/strategy_app_service.py`, `src/pocketquant/core/domain/strategy/strategy_service_interface.py`, `src/pocketquant/core/domain/strategy/services/hitnrun2_strategy_service.py`, `.../engulfing_strategy_service.py`, `.../engulfing_pullback30_touch_strategy_service.py` (one `__init__` line each), `src/pocketquant/core/domain/order/events.py`, `src/pocketquant/engine/execution/order_app_service.py`, `src/pocketquant/engine/execution/position_app_service.py`, `src/pocketquant/core/infra/brokers/paper/paper_broker_adapter.py`, `src/pocketquant/core/infra/persistence/repositories/trade_repository.py`, `src/pocketquant/app/di/services.py`, `src/pocketquant/app/main.py`, `src/pocketquant/engine/backtest/backtest_sandbox_app_service.py` (explicit no-op live dependencies, #14).
- Modify tests: `tests/engine_test/test_paper_position_lifecycle.py`, `tests/engine_test/test_order_filled_event_routing.py`, `tests/core_test/infra/persistence/test_trade_repository.py`; the `_process_signal` callers `tests/engine_test/test_strategy_reject_delivery.py` and `tests/engine_test/test_contract_spec_wiring.py` (#10); the 14 `StrategyAppService(` test constructors listed in Context (#14); the `engine.stop()` callers `tests/app_test/integration/test_app_standalone_runtime.py` and `tests/engine_test/test_reconcile_restart_resume_integration.py` (#4). <!-- Red team 2026-10-28: #4 #10 #14 -->
- Create tests: `tests/engine_test/test_strategy_entry_guards.py`, `tests/engine_test/test_concurrent_opens.py`, `tests/engine_test/test_strategy_warm_up.py`, `tests/engine_test/test_paper_restore.py`.
- Create report: `plans/261028-0652-exness-only-parallel-runtime/reports/strategy-runtime-deploy.md`.

## Tasks

### Task 6.1 — Live-only dependencies and the trading switch

**Goal:** every engine gets the bar, calendar and trade dependencies as required parameters (the sandbox passes explicit no-ops and behaves as today), one `trading_until` field, the bookkeeping Phase 07's drain reads, and a bounded `stop`. <!-- Red team 2026-10-28: #4 #14 -->

**Target files and symbols:** `StrategyAppService.__init__`, `stop`, `unload_strategy`; `ServicesProvider.get_strategy_engine` (`app/di/services.py:135-160`); `build_backtest_sandbox` (`backtest_sandbox_app_service.py:132-144`); the 14 test constructors and two `stop()` test callers in Context.

**Steps:**
1. `__init__` gains required keyword parameters `bar_repository: BarRepository`, `calendar_factory: TradingCalendarFactory`, `trade_repository: TradeRepository` (no defaults; imports under `TYPE_CHECKING`), stored as `self._bar_repository`, `self._calendar_factory`, `self._trade_repository`. No branch in the engine checks them for `None`. Docstring line: "Warm-up reads the bar repository, the successor check the calendar, the paper restore the trade repository; the backtest sandbox passes no-op versions." <!-- Red team 2026-10-28: #14 -->
1a. `backtest_sandbox_app_service.py`: three small public classes next to `_InMemoryOrderRepo`: `NoStoredBars` (`async def find(self, *args, **kwargs) -> list[Bar]: return []`), `NoClosedTrades` (`async def realized_net(self, run_ids: list[str]) -> float: return 0.0`) and `Continuous24x7CalendarFactory` (`async def for_symbol(self, symbol: str) -> ITradingCalendarPort: return Continuous24x7Calendar()`), with one docstring line each ("A backtest has no stored bars/closed live trades/session calendar."). `build_backtest_sandbox` passes `bar_repository=NoStoredBars()`, `calendar_factory=Continuous24x7CalendarFactory()`, `trade_repository=NoClosedTrades()` (with the file's existing `# type: ignore[arg-type]` pattern). The sandbox never calls `start_strategy` or `take_over`, so they are never awaited in a backtest. The 14 test constructors pass the same three objects (import them from `pocketquant.engine.backtest.backtest_sandbox_app_service`); a test that needs real stored bars or trades passes its own fake. <!-- Red team 2026-10-28: #14 -->
2. New state (engine lifetime: one per process in live, one per run in the sandbox): `self.trading_until: datetime | None = datetime.max.replace(tzinfo=UTC)` with the comment "None = no new entry (standby, drained or lease lost): signals are discarded. Before roles exist every engine trades."; <!-- Red team 2026-10-28: #4 --> `self._signal_tasks: dict[str, asyncio.Task[None]] = {}`; `self._last_bar_start: dict[str, datetime] = {}`. <!-- Red team 2026-10-28: #4 #5 --> Also: `self._running_bar_handlers = 0` ("`_on_bar_completed` calls still running, inline paper fills included; the trader hands over at 0"); `self._sending: set[str] = set()` ("subscriptions whose signal reached the broker call; a lost lease never cancels those"); `self._discard_reason = "standby"` ("why a None switch discards: standby before `take_over()`, drain after it, lease after `cancel_pending_signals()`").
3. `stop(self, timeout_s: float)` (required): before stopping strategies and disconnecting brokers, `pending = [t for t in self._signal_tasks.values() if not t.done()]`; when any, `_, late = await asyncio.wait(pending, timeout=max(timeout_s, 0.0))` so an in-flight open finishes its ACK within the caller's remaining grace; each task still in `late` is cancelled and one ERROR `strategy_engine.stop_timeout pending=<len(late)>` is logged. Docstring: "Waits at most ``timeout_s`` for signal tasks: the caller passes what is left of its shutdown grace." Callers: `get_strategy_engine`'s finalizer `await engine.stop(timeout_s=5.0)` (comment: "a drained trader has no task left; this bounds every other shutdown"), `test_app_standalone_runtime.py:109` and `test_reconcile_restart_resume_integration.py:173` pass `timeout_s=5.0`. `unload_strategy`: `self._last_bar_start.pop(strategy_id, None)`. <!-- Red team 2026-10-28: #4 -->
4. `get_strategy_engine` takes `bar_repository: BarRepository`, `calendar_factory: TradingCalendarFactory`, `trade_repository: TradeRepository` and passes them.

**Success criteria:** backtests are unchanged; the engine builds in DI; `git grep -n -E "(bar_repository|calendar_factory|trade_repository): [A-Za-z]+ \| None = None" -- src/pocketquant/engine/strategy/strategy_app_service.py` prints nothing. <!-- Red team 2026-10-28: #14 -->

**Verify:** `uv run python -m pytest tests/backtest_test tests/engine_test tests/app_test/integration/test_app_standalone_runtime.py -q > /dev/null 2>&1; echo "exit=$?"` prints `exit=0`. <!-- Red team 2026-10-28: #4 #14 -->

### Task 6.2 — Entry guards, dedup, lease fence and the latency line

**Goal:** an entry on a stale bar (D26), a gapped bar or a non-successor bar is skipped with exactly one WARNING `strategy.entry_skipped`; exits still run; a bar already seen is ignored; no entry leaves while `trading_until` is `None` or past; every live signal logs one `live.signal_latency`.

**Target files and symbols:** `StrategyAppService._on_bar_completed`, `_process_signal`; module constant `_STALE_AFTER_S`.

**Steps:**
1. Tests first, new file `tests/engine_test/test_strategy_entry_guards.py`. Harness: the `_Factory`/`_Repo` pattern of `tests/engine_test/test_paper_position_lifecycle.py` (paper broker on a real `EventBus`), a calendar factory stub whose `for_symbol` returns `Continuous24x7Calendar()`, a strategy class `_AlwaysLong(IStrategyService)` whose `on_bar_completed` returns a LONG `Signal` with `stop_loss_price = close * 0.95`, `structlog.testing.capture_logs()`, and `set_simulation_time` as the clock. Events are `BarCompletedEvent` with `bar_end = bar_start + interval` unless stated.
   - `test_stale_budget` parametrized over `("1m",10)`, `("5m",30)`, `("15m",60)`, `("1h",120)`, `("4h",300)`, `("1d",600)`, `("1w",600)` and an offset of `0` or `1`: at `bar_end + budget` an order is filled (paper position exists); at `bar_end + budget + 1` no position, exactly one log with `event == "strategy.entry_skipped"` and `reason == "stale"`.
   - `test_a_gap_flagged_bar_skips_the_entry`: `gap=True`, fresh; one `reason == "gap"`, no position.
   - `test_a_non_successor_bar_skips_the_entry`: 1m events at 12:00 then 12:02; the second gives one `reason == "gap"`.
   - `test_paper_sl_still_fills_on_a_stale_bar`: an open paper LONG with SL 95 for another subscription on the same symbol; a stale bar with `low=90` closes it (broker has no position after the publish) while the entry is skipped.
   - `test_a_backtest_event_never_skips`: `bar_end=None`, clock one day later; the order fills.
   - `test_a_seen_bar_is_ignored`: the same event published twice; `on_bar_completed` ran once.
   - `test_standby_discards_the_signal`: `engine.trading_until = None`; no position, no `strategy.entry_skipped` log, one `strategy.signal_discarded` with `reason == "standby"` and `log_level == "debug"`.
   - `test_a_drained_engine_discards_at_info`: `engine._discard_reason = "drain"` (what `take_over()` sets in Task 6.6), then `engine.trading_until = None`; a signal gives no position and one `strategy.signal_discarded` with `reason == "drain"` and `log_level == "info"`. <!-- Red team 2026-10-28: #4 -->
   - `test_the_order_deadline_is_trading_until`: a broker that records the `deadline` keyword of `submit_order`; `engine.trading_until = T + 25 s`; one fresh signal records `deadline == T + 25 s`. <!-- Red team 2026-10-28: #5 -->
   - `test_an_expired_lease_skips_the_entry`: `engine.trading_until` = now; one `reason == "lease"`, no position.
   - `test_one_latency_line_per_live_signal`: one fresh live bar gives exactly one `live.signal_latency` record whose keys include `t0_bar_end`, `t1_closing_tick`, `t2_closed`, `t3_published`, `t4_signal`, `t5_submit`, `t6_returned`, `t0_t5_ms`, `t0_t6_ms`, `closed_by`; a backtest event gives none.
2. Run `uv run python -m pytest tests/engine_test/test_strategy_entry_guards.py -q 2>&1 | tail -1`; it must show `failed` (expected red).
3. Constant `_STALE_AFTER_S = {"1m": 10, "5m": 30, "15m": 60, "1h": 120, "4h": 300, "1d": 600, "1w": 600}`.
4. `_on_bar_completed` adds one to `self._running_bar_handlers` on entry and subtracts it in a `finally` around the whole body (inline paper fills run inside it; the counter is what Phase 07 adds to `inflight_count()`). <!-- Red team 2026-10-28: #4 --> Per matched strategy: `last = self._last_bar_start.get(strategy.id)`; if `last is not None and event.bar_start <= last`, skip this strategy (already seen). Compute `successor`: `True` unless `event.bar_end is not None`, `last is not None` and `calendar.trading_minutes(last + timedelta(seconds=INTERVAL_SECONDS[event.interval]), event.bar_start)` is non-empty (`INTERVAL_SECONDS` from `pocketquant.core.common.constants`, string keys). Set `self._last_bar_start[strategy.id] = event.bar_start`. Always call `strategy.on_bar_completed(bar)` (state stays warm). With a signal, `signal_at = get_current_time()`, then the skip reason: when `event.bar_end` is set, `stale` if `(signal_at - event.bar_end).total_seconds() > _STALE_AFTER_S[event.interval]`, else `gap` if `event.gap or not successor`. On a reason: `logger.warning("strategy.entry_skipped", reason=..., subscription_id=strategy.id, symbol=event.symbol, interval=event.interval, bar_start=event.bar_start.isoformat(), age_s=<rounded age in s, or None without bar_end>)`, `await self._notify_rejected(strategy, reason)`, next strategy. Otherwise `await self._process_signal(strategy, signal, event, signal_at)` (Task 6.3 adds the task branch). Keep the existing `strategy_on_bar_error` handling for `on_bar_completed`.
5. `_process_signal(strategy, signal, event, signal_at)`: `current_price = event.close`. At the top: `trading_until is None` -> `reason = self._discard_reason`; log `strategy.signal_discarded` with `reason` and `subscription_id=strategy.id`, at DEBUG for `standby` (every bar of a warm standby trader) and at INFO for `drain` and `lease` (bounded: only around a handover); `on_order_rejected(reason)`, return; `get_current_time() >= trading_until` -> WARNING `strategy.entry_skipped reason=lease`, `on_order_rejected("lease")`, return. Keep `deadline = self.trading_until` from this check and pass it on: `self._order_app_service.submit(order, broker, deadline=deadline)` (Phase 04 keyword; the Exness adapter re-checks it after its open lock and after the pacer wait). Right before that call `self._sending.add(strategy.id)`; a `finally` discards it. <!-- Red team 2026-10-28: #4 #5 --> Wrap the whole body in `try/except Exception` that logs `strategy_on_bar_error` and calls `_notify_rejected` (it moves here from the caller, so a task logs its own errors). Record `t5 = get_current_time()` right before `self._order_app_service.submit` and `t6` right after. When `event.bar_end is not None`, log one INFO `live.signal_latency` with `subscription_id`, `symbol`, `interval`, `bar_start`, `closed_by`, ISO strings `t0_bar_end`, `t1_closing_tick` (None for a timer close), `t2_closed`, `t3_published` (`event.occurred_at`), `t4_signal`, `t5_submit`, `t6_returned`, and integers `t0_t5_ms`, `t0_t6_ms`. One line per signal is bounded, so INFO follows the log rule.
6. Update every test that calls `_process_signal` to pass a `BarCompletedEvent` whose `close` is the price the test passes today, and a `signal_at`: `tests/engine_test/test_contract_spec_wiring.py:120` (4500.0) and `:304` (7800.0), `tests/engine_test/test_strategy_reject_delivery.py:137,154,166` (100.0), and the opposite-signal test Phase 04 added in `tests/engine_test/test_paper_position_lifecycle.py` (100.0). Re-list with `git grep -n "_process_signal" -- tests`. <!-- Red team 2026-10-28: #10 -->
7. Commit: `feat(strategy): skip stale, gapped and unleased entries and log signal latency`.

**Success criteria:** every test in the new file passes; exits (paper SL/TP) never depend on these guards.

**Verify:** `uv run python -m pytest tests/engine_test tests/backtest_test -q > /dev/null 2>&1; echo "exit=$?"` prints `exit=0`.

### Task 6.3 — Venue signals run as tasks; one per subscription (D21, H1, A6)

**Goal:** three venue (async-fill) subscriptions signalling on one bar submit concurrently and the bar handler returns at once; a second signal while a subscription's task runs is skipped with `reason=inflight`; paper stays inline.

**Target files and symbols:** `StrategyAppService._on_bar_completed`.

**Steps:**
1. Tests first, new file `tests/engine_test/test_concurrent_opens.py`, fake async broker copied from the pattern in `tests/engine_test/test_async_broker_fill_wiring.py` with `fills_async = True`, `normalize_quantity` returning its input, and `submit_order` that records `time.monotonic()` then `await asyncio.sleep(1.0)` and returns `SUBMITTED`:
   - `test_three_venue_signals_submit_concurrently`: three subscriptions on one symbol and 1m signal on one fresh bar; `await engine._on_bar_completed(event)` takes under 0.1 s; after `await asyncio.sleep(0.05)` the three recorded starts lie within 0.1 s.
   - `test_a_second_signal_while_the_task_runs_is_skipped`: the next bar for the same subscription arrives while its task sleeps; one `strategy.entry_skipped` with `reason == "inflight"`; still one submit for that subscription.
   - `test_paper_stays_inline`: with the paper factory, the position exists as soon as `_on_bar_completed` returns.
   <!-- Red team 2026-10-28: #4 #5 -->
   - `test_a_running_bar_handler_is_counted`: a strategy whose `on_bar_completed` awaits an `asyncio.Event`; publish the bar in a task; after `await asyncio.sleep(0.01)`, `engine._running_bar_handlers == 1`; set the event and await the task; `== 0`.
   - `test_cancel_pending_signals_spares_a_task_at_the_broker`: sub `a`'s `normalize_quantity` awaits an `asyncio.Event` that is never set (not yet at the broker); sub `b` is inside `submit_order` (its 1 s sleep); `engine.cancel_pending_signals()` returns `1`; `a`'s task is cancelled, `b`'s completes its submit; one `strategy.signal_discarded` with `reason == "lease"`, `subscription_id == "a"`, `log_level == "info"`.
   - `test_stop_waits_at_most_the_timeout`: one task inside a 5 s `submit_order`; `await engine.stop(timeout_s=0.2)` returns within 0.5 s, the task is cancelled and one ERROR `strategy_engine.stop_timeout` with `pending == 1` is logged. A task that finishes in 0.1 s with `timeout_s=1.0` completes before `stop` returns and no `stop_timeout` is logged.
2. Run the file; it must show `failed` (expected red).
3. In `_on_bar_completed`: add to the reason chain, after stale and gap, `inflight` when `self._signal_tasks.get(strategy.id)` exists and is not done. Without a reason: when `self._brokers[strategy.id].fills_async`, create `task = asyncio.create_task(self._process_signal(strategy, signal, event, signal_at))`, store it in `self._signal_tasks[strategy.id]` and add a done-callback that removes the entry only if it still holds that task; otherwise await `_process_signal` inline.
3a. `def cancel_pending_signals(self) -> int`: set `self._discard_reason = "lease"`; cancel every signal task that is not done and whose subscription is not in `self._sending`, log INFO `strategy.signal_discarded reason=lease subscription_id=<id>` for each, and return the count. Docstring: "A lost lease calls this: tasks that have not reached the broker stop now; a task at the broker is stopped by the order deadline check there." One method; Phase 07's on-lost path calls it right after setting `trading_until = None`. <!-- Red team 2026-10-28: #5 -->
4. Commit: `feat(strategy): run venue entries as tasks outside the bar handler`.

**Success criteria:** the six tests pass; the backtest suite is unchanged. <!-- Red team 2026-10-28: #4 #5 -->

**Verify:** `uv run python -m pytest tests/engine_test/test_concurrent_opens.py tests/engine_test/test_strategy_entry_guards.py tests/backtest_test -q > /dev/null 2>&1; echo "exit=$?"` prints `exit=0`.

### Task 6.4 — Warm-up from stored bars and direction restore (D9, A16)

**Goal:** a started strategy has its buffers filled from up to 500 stored bars and its direction set from the mirror row, so hitnrun2 can signal on the first live bar and a held LONG blocks a new entry.

**Target files and symbols:** `IStrategyService.__init__` and new `restore_direction` (`strategy_service_interface.py:35-48`); the three strategies' `__init__` direction lines; `StrategyAppService.start_strategy`; module function `_direction_of`.

**Steps:**
1. Tests first, new file `tests/engine_test/test_strategy_warm_up.py`, engine with a fake bar repository whose `find(symbol, interval, end_date=None, limit=...)` returns given `Bar` objects newest first, the 24/7 calendar stub, paper factory, `set_simulation_time` at second 25 of a minute T (no wait):
   - `test_hitnrun2_signals_on_the_first_live_bar_after_481_stored_bars`: 481 flat 1m bars (high 101, low 99) ending at T-1 min; `HitNRun2StrategyService` with default parameters; after `start_strategy`, `len(strategy._closes) == 481`; a fresh live bar for bucket T with `close=90` opens one paper position.
   - `test_a_replayed_signal_sends_nothing`: stored bars include a breakdown bar; no order during `start_strategy` and `strategy._open_direction is None` after it.
   - `test_a_long_mirror_row_restores_direction_long`: the position service holds a LONG row for the subscription; after `start_strategy`, `strategy._open_direction == Direction.LONG`.
   - `test_a_hole_after_the_stored_bars_warns_once_and_gap_skips`: stored bars end at T-5 min; exactly one `strategy.warmup_incomplete` WARNING; the first live bar at T with a signal gives one `strategy.entry_skipped reason=gap`.
2. Run the file; it must show `failed` (expected red).
3. `IStrategyService.__init__` sets `self._open_direction: Direction | None = None` (import `Direction` from `pocketquant.core.domain.strategy.enums`); add `def restore_direction(self, direction: Direction | None) -> None` with docstring "Set the open direction from the stored position after a restart." Delete the duplicate `self._open_direction: Direction | None = None` line from the three strategies' `__init__` (their `on_start` resets stay).
4. Module function `_direction_of(position) -> Direction | None`: `None` for no position, else LONG or SHORT by `position.side` (two callers: `start_strategy`, `take_over`).
5. `start_strategy`, inside the existing lock, after the broker connect (now only when `self.trading_until is not None and get_current_time() < self.trading_until`): `calendar = await self._calendar_factory.for_symbol(symbol)`; `found = await self._bar_repository.find(symbol, Interval(interval), end_date=now, limit=_WARMUP_BARS)` with `_WARMUP_BARS = 500`, keep bars with `bar.datetime + interval <= now`, oldest first. When `now.second < 20`, `found` is non-empty and its newest bar ends before `calendar.bar_start(now, interval)` (the last closed bucket is not stored yet; `sync_1m` stores T-1 at second 12), sleep `20 - now.second - now.microsecond / 1e6`, set `now = get_current_time()` and read once more. An empty store does not wait (a new symbol, and every test or sandbox engine built with `NoStoredBars`). <!-- Red team 2026-10-28: #14 --> Then, with no I/O await in between: `await strategy.on_start()`; for each bar call `on_bar_completed` with the same dict shape `_on_bar_completed` builds and call `on_order_rejected("warmup")` for any signal; set `self._last_bar_start[strategy_id]` to the last replayed bar start (or pop it when none); `strategy.restore_direction(_direction_of(self._position_app_service.get(strategy_id)))`. After that, when bars were replayed, log WARNING `strategy.warmup_incomplete` (`subscription_id`, `last_bar_start`, `current_bucket_start`) once if `calendar.trading_minutes(last + interval, calendar.bar_start(now, interval))` is non-empty. <!-- Red team 2026-10-28: #14 (no branch without a bar repository: it is required) -->
6. Commit: `feat(strategy): warm up from stored bars and restore direction on start`.

**Success criteria:** the four tests pass; `inject_prepared_strategy` (backtests) is untouched.

**Verify:** `uv run python -m pytest tests/engine_test tests/backtest_test tests/core_test/unit/domain/strategy -q > /dev/null 2>&1; echo "exit=$?"` prints `exit=0`.

### Task 6.5 — SL/TP travel on the fill event into the mirror row (A4)

**Goal:** every mirror row opened by an entry fill stores the order's SL and TP, so a restored paper position keeps its exits.

**Target files and symbols:** `OrderFilledEvent` (`events.py:21-30`); `OrderAppService.submit`, `on_order_update` (`order_app_service.py:87-96,160-169`); `PositionAppService._on_order_filled` (`position_app_service.py:61-92`).

**Steps:**
1. Test first in `tests/engine_test/test_order_filled_event_routing.py`: `test_the_mirror_row_keeps_the_order_sl_and_tp`: submit a paper order with `sl_price=95.0`, `tp_price=110.0`; the saved mirror row has the same `sl_price` and `tp_price`. Run it; it must fail.
2. `OrderFilledEvent` gains `sl_price: float | None = None` and `tp_price: float | None = None`. Both producers in `order_app_service.py` pass `sl_price=order.sl_price, tp_price=order.tp_price`. `_on_order_filled` passes them into `PositionAggregate.open`. Exit fills (paper synthetic exits, Exness close fills) keep the defaults.
3. Commit: `feat(execution): carry SL and TP from the order into the position mirror`.

**Success criteria:** the new test passes; no other producer changes.

**Verify:** `uv run python -m pytest tests/engine_test/test_order_filled_event_routing.py tests/engine_test/test_paper_position_lifecycle.py -q > /dev/null 2>&1; echo "exit=$?"` prints `exit=0`.

### Task 6.6 — Paper restore, boot-delete removal and `take_over()` (D13)

**Goal:** a restart keeps paper rows; one `take_over()` reloads orders and positions, rebuilds each paper broker's cash and SL/TP positions, restores directions and connects brokers; a pre-fix paper row with no exits is dropped with one WARNING.

**Target files and symbols:** `PositionAppService.start`, `load_open_positions` (`position_app_service.py:31-53`); `get_position_tracker` (`app/di/services.py:122-133`); new `PaperBrokerAdapter.restore`; new `TradeRepository.realized_net`; new `StrategyAppService.take_over`; `lifespan` (`app/main.py:63`).

**Steps:**
1. Tests first. `tests/engine_test/test_paper_restore.py` (in-memory repos; a fake trade repo with `save_many` appending `Trade`s and `realized_net(ids)` summing `pnl - commission` of the stored trades of those ids; wire `LiveTradeCollector(bus, fake_trade_repo, engine)` and `await collector.start()` so closed trades are stored as in prod; paper `commission_bps=10` through `default_broker_config`; open positions through `OrderAppService.submit` with SL/TP as the `_open` helper of `test_paper_position_lifecycle.py` does):
   - `test_a_rebuilt_paper_broker_shows_the_pre_restart_balance`: engine A opens a paper LONG with SL, a bar crosses the SL (round trip closed, trade stored), then opens a second LONG that stays open; record broker A's `get_balance().available_balance`. Engine B on the same repos: `load_strategy`, `start_strategy`, `take_over()`; broker B's `available_balance` equals A's (`pytest.approx`) and B holds one position with the same SL; engine B's `_discard_reason == "drain"` (it was `"standby"` before `take_over()`). <!-- Red team 2026-10-28: #4 -->
   - `test_a_restored_position_exits_on_the_next_crossing_bar`: after the restore, a bar whose low crosses the SL emits one exit fill and leaves no position.
   - `test_a_paper_row_without_exits_is_dropped`: a mirror row with no SL and no TP; `take_over()` logs one `paper_position_dropped_no_exits` and the row is gone from the repo.
   - In `tests/engine_test/test_paper_position_lifecycle.py`, replace `test_boot_deletes_paper_rows_and_keeps_the_rest` with `test_boot_keeps_paper_and_venue_rows` (both rows stay in the repo and in the mirror after `start()`).
   - In `tests/core_test/infra/persistence/test_trade_repository.py`: `test_realized_net_sums_pnl_minus_commission`: trades with `(run_id, pnl, commission)` = `("a", 50, 2)`, `("a", -20, 2)`, `("b", 7, 1)`; `realized_net(["a"]) == 26.0`, `realized_net(["a", "b"]) == 32.0`, `realized_net(["zzz"]) == 0.0`.
2. Run `uv run python -m pytest tests/engine_test/test_paper_restore.py -q 2>&1 | tail -1`; it must show `failed` (expected red).
3. `PositionAppService.start(self)` drops its argument and calls `load_open_positions()`. `load_open_positions(self)` loads every open row and replaces `self._positions` under the lock (`{p.subscription_id: p for p in rows}`); log `loaded_open_positions count=N`; docstring: "Every open row is kept: a venue still holds its position, and the trading process restores paper brokers from theirs."
4. `get_position_tracker`: `await tracker.start()`; drop the `subscription_repository` parameter.
5. `TradeRepository.realized_net(self, run_ids: list[str]) -> float`: one aggregate `[{"$match": {"run_id": {"$in": run_ids}}}, {"$group": {"_id": None, "total": {"$sum": {"$subtract": ["$pnl", "$commission"]}}}}]`; returns `0.0` when nothing matches. Docstring: "Net realized PnL (gross pnl minus commission) of these subscriptions' closed trades."
6. `PaperBrokerAdapter.restore(self, positions, realized_net)`: clear `self._positions`; for each row store a deep copy (`pos.model_copy(deep=True)`) under `f"{sub}:{symbol}"` with `entry_commission = self._commission(entry_price, quantity)` (the mirror does not store it); `self._balance = self._initial_balance + realized_net - sum(entry commissions)`. Docstring: "Rebuild cash and open positions after a restart. Copies, because the mirror reduces its own row on an exit fill."
7. `StrategyAppService.take_over()`: `await self._order_app_service.load_pending_orders()`; `await self._position_app_service.load_open_positions()`; for each distinct paper broker in `self._brokers.values()`: its subscription ids, their mirror rows (a row with `sl_price is None and tp_price is None` -> WARNING `paper_position_dropped_no_exits` with `subscription_id`, `symbol`, then `await self._position_app_service.drop(sid)`), `realized = await self._trade_repository.realized_net(ids)`, `broker.restore(rows, realized)`; <!-- Red team 2026-10-28: #14 --> then for each running strategy `restore_direction(_direction_of(...))` and connect its broker if not connected; log INFO `strategy_engine.took_over` with counts; set `self._discard_reason = "drain"` (from now on a None switch means a drain, unless `cancel_pending_signals()` marks a lost lease). <!-- Red team 2026-10-28: #4 --> Docstring: "Load what a trading process owns and connect its brokers. Runs once per process, before bars flow."
8. `app/main.py`: after `await bootstrap_live_instances(container)` add `await (await container.get(StrategyAppService)).take_over()` (import `StrategyAppService`).
9. Commit: `feat(paper): restore paper brokers and positions at takeover instead of deleting them`.

**Success criteria:** the five tests pass; `git grep -n "delete_open_by_subscription" -- src/pocketquant/engine/execution/position_app_service.py` shows only the line inside `drop()`.

**Verify:** `uv run python -m pytest tests/engine_test tests/core_test/infra/persistence/test_trade_repository.py -q > /dev/null 2>&1; echo "exit=$?"; git grep -n "delete_open_by_subscription" -- src/pocketquant/engine/execution/position_app_service.py | wc -l | tr -d ' '` prints `exit=0` then `1`. <!-- Red team 2026-10-28: #10 -->

### Task 6.7 — Gates, push `develop`, CI green

**Goal:** Phases 04-06 sit on `develop` with every gate green.

**Target files and symbols:** none new; `pyproject.toml` `[tool.code-metrics]` only if the ratchet trips.

**Steps:**
1. `uv run ruff check src tests` prints `All checks passed!`; `uv run ruff format --check src tests` exits 0; `uv run pyright` prints `0 errors`; `uv run lint-imports | tail -1` prints `Contracts: 6 kept, 0 broken.`
2. `uv run python scripts/code_metrics.py --ratchet; echo "exit=$?"` prints `exit=0`; if a ceiling trips, raise it in its own commit `chore(metrics): raise the code-metrics ceiling for the strategy runtime` and record old and new values in the report.
3. Full suite: `uv run python -m pytest tests/ -q > .cache/pytest-full.log 2>&1; tail -1 .cache/pytest-full.log; grep -E "^(FAILED|ERROR) " .cache/pytest-full.log | grep -vcE "test_utc_runtime_guard|test_cron_trigger_timezone"` prints a line with `4 failed` and `4 errors`, then `0`.
4. Push: `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin && test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `pushed`.

**Success criteria:** local red is the known Windows red; CI green on the pushed HEAD.

**Verify:** `sleep 15; export GH_TOKEN=$(gh auth token --user camping89); RUN_ID=$(gh run list --workflow cicd.yml --branch develop --limit 5 --json databaseId,headSha -q ".[] | select(.headSha==\"$(git rev-parse HEAD)\") | .databaseId" | head -1); gh run watch "$RUN_ID" --exit-status > /dev/null 2>&1; gh run view "$RUN_ID" --json conclusion -q .conclusion` prints `success`.

### Task 6.8 — Deploy D-3 [ASK]

**Goal:** Phases 04-06 run in prod in the single `app` container with live trading off.

**Target files and symbols:** none in the repo; prod `pocketquant-app`; report `reports/strategy-runtime-deploy.md`.

**Steps:**
1. Deploy window (the **Deploy window** rule in plan.md Conventions: Mon-Fri 06:00-11:20 or 12:50-19:30 UTC, outside every blackout; same command as Phase 02 Context): `d=$(date -u +%u); t=$((10#$(date -u +%H)*60 + 10#$(date -u +%M))); if [ "$d" -le 5 ] && { { [ $t -ge 360 ] && [ $t -lt 680 ]; } || { [ $t -ge 770 ] && [ $t -lt 1170 ]; }; }; then echo WINDOW_OK; else echo "NOT_IN_WINDOW d=$d t=$t"; fi`. On `NOT_IN_WINDOW`: `rm -f .cache/ssh/vps_key` and end with the `NOT_YET` block (`--from 06 after <next window start>`).
2. Record before: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'free -m; docker inspect -f "{{.Config.Image}}" pocketquant-app'`; write both outputs into the report under "Before" (the image line is the rollback tag).
3. [ASK] the owner, verbatim:
   "Recommended: yes — triển khai D-3 ngay. Lý do: CI xanh, live vẫn tắt (EXNESS_LIVE_TRADING=false), chỉ paper bị ảnh hưởng.
   Sự kiện: lệnh đẩy develop:master sẽ build và khởi động lại pocketquant-app (khoảng 1-2 phút không có bar). Thay đổi gồm: pause đọc từ Mongo mỗi lệnh, chặn lệnh ngược chiều cả trên paper, bar <= 1h đóng theo timer, bỏ qua entry khi bar trễ/có gap, warm-up 500 bar, khôi phục paper sau restart; vị thế paper cũ không có SL/TP sẽ bị xoá (giống hành vi hiện tại). Rollback: IMAGE_TAG=<tag cũ> bash deploy/vps/10-deploy.sh.
   Đồng ý triển khai lên prod bây giờ? (yes / no / wait)"
   Only an explicit yes continues; otherwise `rm -f .cache/ssh/vps_key` and end with the `NOT_YET` block.
4. Release: `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop:master && git fetch origin && test "$(git rev-parse HEAD)" = "$(git rev-parse origin/master)" && echo released` prints `released`.
5. Wait for the pipeline: `sleep 15; export GH_TOKEN=$(gh auth token --user camping89); RUN_ID=$(gh run list --workflow cicd.yml --branch master --limit 5 --json databaseId,headSha -q ".[] | select(.headSha==\"$(git rev-parse HEAD)\") | .databaseId" | head -1); gh run watch "$RUN_ID" --exit-status > /dev/null 2>&1; gh run view "$RUN_ID" --json conclusion -q .conclusion; gh run view "$RUN_ID" --log | grep "=== Verdict:" | grep -c ", 0 failures)"` prints `success` then a number of at least `1`.
6. (Removed: prod logs are console lines, not JSON; every grep below strips ANSI colours first.) <!-- Red team 2026-10-28: #9 -->
7. Record after (`free -m`) and the boot counts into the report under "After": `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'free -m; L=$(docker logs pocketquant-app --since 15m 2>&1 | sed "s/\x1b\[[0-9;]*m//g"); for e in loaded_open_positions strategy_engine.took_over paper_position_dropped_no_exits strategy.warmup_incomplete bar_app_service.seeded_from_redis strategy.entry_skipped; do printf "%s=%s\n" "$e" "$(printf "%s" "$L" | grep -c "$e")"; done'`.

**Success criteria:** CI deployed the pushed HEAD and its verify verdict has 0 failures; the report has `free -m` before and after.

**Verify:** `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'docker exec pocketquant-app python -c "from pocketquant.engine.strategy.strategy_app_service import StrategyAppService as S; from pocketquant.engine.market_data.app_services.bar_app_service import BarAppService as B; print(hasattr(S, \"take_over\") and hasattr(B, \"close_due_bars\"))"; docker exec pocketquant-app curl -s -o /dev/null -w "%{http_code}\n" http://localhost:41921/health; docker logs pocketquant-app --since 15m 2>&1 | sed "s/\x1b\[[0-9;]*m//g" | grep -cE "application_start_failed|bar.close_timer_failed|strategy_on_bar_error|Traceback"'` prints `True`, `200`, `0`. <!-- Red team 2026-10-28: #9 -->

### Task 6.9 — Pause round trip and the 2-hour watch

**Goal:** the stored pause works through the prod route, and two hours of prod logs show no new errors and (when signals exist) a timer close within 1 s.

**Target files and symbols:** prod routes `/api/v1/admin/safeguards*`; report `reports/strategy-runtime-deploy.md`.

**Steps:**
1. Read the stored pause and record the output. If it shows `"entries_paused":true`, the owner paused on purpose: skip step 2 and record "pause left as set by the owner".
   ```bash
   HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r')
   ssh -i .cache/ssh/vps_key "$HOST" 'docker exec -i pocketquant-app sh -s' <<'EOF'
   curl -s http://localhost:41921/api/v1/admin/safeguards; echo
   EOF
   ```
2. Round trip (live is off, no order is affected; the token is read inside the container, never printed and never put on a command line: `printf` is a shell builtin and `curl -H @-` reads the header from stdin). <!-- Red team 2026-10-28: #13 --> Expected: the second output line contains `"entries_paused":true` and the third `"entries_paused":false`. Record all three lines.
   ```bash
   HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r')
   ssh -i .cache/ssh/vps_key "$HOST" 'docker exec -i pocketquant-app sh -s' <<'EOF'
   printf 'X-Admin-Token: %s\n' "$ADMIN_TOKEN" | curl -s -X POST -H @- http://localhost:41921/api/v1/admin/safeguards/pause; echo
   curl -s http://localhost:41921/api/v1/admin/safeguards; echo
   printf 'X-Admin-Token: %s\n' "$ADMIN_TOKEN" | curl -s -X POST -H @- http://localhost:41921/api/v1/admin/safeguards/resume; echo
   EOF
   ```
3. Wait until 2 h after the container start: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'docker inspect -f "{{.State.StartedAt}}" pocketquant-app'`. If this session cannot wait that long, `rm -f .cache/ssh/vps_key` and end with the `NOT_YET` block (`--from 06 after <StartedAt + 2 h>`); the resumed run skips finished tasks by their Verify.
4. Pull the latency lines with the colours stripped: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'docker logs pocketquant-app --since 2h 2>&1 | sed "s/\x1b\[[0-9;]*m//g" | grep live.signal_latency' > .cache/latency.log; wc -l < .cache/latency.log`. With 5 or more lines, parse the `key=value` pairs: `uv run python -c "import re,datetime as d; f=d.datetime.fromisoformat; J=[{k: v.strip(chr(39)+chr(34)) for k, v in re.findall(r'(\w+)=(\S+)', l)} for l in open('.cache/latency.log')]; v=sorted((f(j['t2_closed'])-f(j['t0_bar_end'])).total_seconds()*1000 for j in J); w=sorted(int(j['t0_t5_ms']) for j in J); print(round(v[int(0.95*(len(v)-1))]), w[int(0.95*(len(w)-1))])"` <!-- Red team 2026-10-28: #9 --> prints the p95 of T2-T0 and of `t0_t5_ms` in ms. Write exactly one report line `p95(T2-T0) ms: <first number>` and one line `p95 t0_t5_ms: <second number>`. With fewer than 5 lines write `p95(T2-T0) ms: n/a` and `p95 t0_t5_ms: n/a` (no paper signal yet; Phase 10 measures latency).
5. Record the 2 h counts: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'L=$(docker logs pocketquant-app --since 2h 2>&1 | sed "s/\x1b\[[0-9;]*m//g"); for e in strategy.entry_skipped strategy.warmup_incomplete exness.rate_limited event_loop.lag; do printf "%s=%s\n" "$e" "$(printf "%s" "$L" | grep -c "$e")"; done'` into the report.
6. `rm -f .cache/ssh/vps_key`.
7. Commit the report: `git add plans/261028-0652-exness-only-parallel-runtime/reports/strategy-runtime-deploy.md && git commit -m "docs(plans): record the strategy runtime deploy" && git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin` (a `**/*.md` change does not trigger CI).

**Success criteria:** the pause round trip matches (or was skipped because the owner paused); the 2 h error count is 0; latency is either `n/a` or `p95(T2-T0) <= 1000` ms.

**Verify:** `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key; ssh -i .cache/ssh/vps_key "$HOST" 'docker logs pocketquant-app --since 2h 2>&1 | sed "s/\x1b\[[0-9;]*m//g" | grep -cE "application_start_failed|bar.close_timer_failed|strategy_on_bar_error|Traceback"'; rm -f .cache/ssh/vps_key; grep -cE "^p95\(T2-T0\) ms: (n/a|([0-9]|[1-9][0-9]{1,2}|1000))$" plans/261028-0652-exness-only-parallel-runtime/reports/strategy-runtime-deploy.md` prints `0` then `1` (write the latency result in the report as exactly one line `p95(T2-T0) ms: <value or n/a>`).

## Rollback

- Before the release: `git revert --no-edit <first Phase 04 sha>^..HEAD` on `develop` and push; nothing ran in prod.
- After D-3: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" "cd /opt/pocketquant && IMAGE_TAG=<tag part after ':' of the image recorded in Task 6.8 step 2> bash deploy/vps/10-deploy.sh && bash deploy/vps/11-verify.sh"` (documented emergency pin, `docs/deployment.md:168-171`; after an [ASK] and inside the **Deploy window** of plan.md Conventions; recreate the key first as in the entry gate and delete it after), then revert the commits on `develop`. Data stays valid both ways: mirror rows gain optional `sl_price`/`tp_price` values the old code ignores, and the old code deletes paper rows at its next boot (today's behaviour). The stored pause document keeps its shape. `sync_1m` returns to second 2 with the old image.

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
