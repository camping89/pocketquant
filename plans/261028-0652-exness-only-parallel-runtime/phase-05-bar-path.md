---
phase: 5
title: "Bar path: publish outside the lock, timer close, gap facts, Redis seed"
status: done
priority: P1
effort: 1d
dependencies: [4]
---

# Phase 05 — Bar path (one process, no deploy)

## Goal

Completed bars carry the facts the entry guards need (`bar_end`, `gap`, close timing) and leave the bar lock before any handler runs, so one slow handler (an order) never holds the bar lock (D21). Every bar closes on a timer 0.5 s after its end instead of waiting for the next tick (D20, D35); bars up to 1h are cut at the session close. Tick silence over 60 s of trading time, a stale restart seed and an uncovered mid-bucket start set `gap` (D10, D20). The dead Mongo seed and `flush_all_bars` are deleted. `sync_1m` moves to second 12, off the entry window. For the later split, the service also exposes `last_closed_boundary` (the latest 1m boundary whose bars are all published), writes `bar:current` only while its `publishes_current` switch is on, stores `gap` and `coverage_start` in the seed, and the process-local bar write cache is deleted. <!-- Red team 2026-10-28: #4 #12 --> Nothing is deployed; the timer close ships with Phase 06 after its NTP gate.

## Context

Line numbers are from `develop` @ 453e8e90; Phase 03 may have edited comments in `bar_app_service.py` (CME wording), so locate targets by symbol first.

- `BarCompletedEvent` has no end, gap or timing fields (`src/pocketquant/core/domain/bar/events.py:7-22`); `DomainEvent.occurred_at` is set at construction (`core/domain/shared/events.py:10`).
- The builder already has `bar_end`, defaulting to `bar_start + interval` (`core/domain/bar/services/bar_builder_domain_service.py:60-81`); `add_tick` rejects ticks outside `[bar_start, bar_end)` (`:83-110`).
- `add_tick` holds `self._lock` across every interval (`engine/market_data/app_services/bar_app_service.py:81-92`); a bar closes only when a later bucket's tick arrives (`:117-132`); `_save_completed_bar` awaits `self._event_bus.publish(event)` under that lock (`:137-178`, publish at `:162`), so strategy handlers and their order calls run under the bar lock.
- The first builder per key seeds from Mongo (`:104-115`, `_seed_builder_from_mongo` `:180-208`). `bar:current` is written at most every 0.2 s with a wall-clock `last_update` (`:24-25`, `:210-236`, `last_update` at `:234`). `flush_all_bars` has no caller in `src` (`:270-289`; only `tests/app_test/market_data/test_bar_app_service_unit.py:305-330` calls it). The docstrings promise at-least-once delivery (`:54`, `:149`).
- Calendar port: `trading_minutes(start, end)` returns minute opens in `[start, end)` (`core/domain/market_data/trading_calendar_port.py:65-68`); `session_date`, `session_close` (`:36-49`). The Exness `session_close` returns the last open second (span end minus 1 s, `core/infra/calendars/exness_session_calendar_adapter.py:201-206`); `Continuous24x7Calendar.session_close` returns the next midnight (`core/domain/market_data/continuous_24x7_calendar.py:37-38`). So the bar end is `min(bar_start + interval, session_close(session_date(bar_start)) + 1 s)`; this adds 1 s to the A15 formula so the last minute of a session is not cut by one second.
- The quote feed starts in `QuoteAppService.start` (`engine/market_data/app_services/quote_app_service.py:100-108`) via `start_quote_feed`; `stop_quote_feed` cancels `app.state.ws_task` (`app/main_extensions.py:185-208`).
- `sync_1m` runs at `second=2` (`engine/market_data/app_services/sync_jobs.py:703-709`, comment `:693`).
- Clock: `get_current_time()` returns the simulated time when a test sets it, else UTC now (`core/common/time/simulation.py:15-31`).
<!-- Red team 2026-10-28: #4 #12 -->
- `EventBus.publish` awaits every handler in order and re-raises the first error after all ran (`core/common/messaging/event_bus.py:26-42`), so "the publish returned" means every subscriber (strategy engine, paper SL/TP check) finished with that bar.
- `bar:current` is written by `_cache_current_bar` (`bar_app_service.py:210-236`) and deleted on close (`:164-170`); the API's SSE reads it (`get_current_bar`, `:238-268`). `BarBuilderDomainService.to_dict` has no `gap` (`core/domain/bar/services/bar_builder_domain_service.py:115-127`). After the split a standby trader and a probe container would write and delete the same keys as the lease holder.
- `BarRepository` keeps a module-level `_BAR_VALUE_CACHE` (`core/infra/persistence/repositories/bar_repository.py:16-20`) that skips a write when the cached OHLCV matches (`:83-85`, set at `:115,126,144`); `delete_by_symbol` evicts only this process's entries (`:284-293`). After the split the `api` process deletes a symbol while the `worker` keeps its cache, so a re-added symbol skips bar writes and leaves holes. The `find_one` comparison (`:95-127`) already prevents redundant writes. Test users: `tests/core_test/infra/persistence/test_bar_repository.py:25-28,44-48,113-123,144-148,168`, `tests/app_test/integration/test_tracked_symbol_cascade_delete_api.py:21-23,202-203`. `cachetools` stays (`symbol_lookup_helper.py:13`).

**Rules this phase fixes (A14, A15, D20).**
- Trading seconds between `a < b`: the part of `[a, b)` that falls inside the minutes `trading_minutes(floor_minute(a), ceil_minute(b))` returns. Only computed when the wall gap exceeds 60 s; below that it equals the wall gap.
- Timer close (D35): every interval closes on the timer when `bar_end + 0.5 s <= now`. Bars of 1h or less end at `min(bar_start + interval, session_close + 1 s)`; 4h/1d/1w end at `bar_start + interval` (no session cut, so ticks after a daily break still land in their bucket). A 4h/1d/1w bar whose market closed before its end is therefore published at its bucket end, not on the next session's first tick. <!-- Validation 2026-10-28: D35 -->
- After any close of a key, `_last_end[(symbol, interval)]` holds that bar's end. A tick whose bucket starts before `_last_end` is late and dropped. A builder created while `_last_end` is known starts its coverage at its bucket start.
- `gap` is set when (G1) a tick follows the builder's last tick, or the close follows it at `bar_end`, by more than 60 trading seconds; or (G2) the first builder of a key in this process has no covering Redis seed and its first tick is more than 60 trading seconds after the bucket start. A covering seed has the same `bar_start` and a `last_update` at most 60 trading seconds before the first tick.
- The successor check (a skipped bucket) lives in the strategy engine in Phase 06, where it also catches the warm-up seam (A16); it is not duplicated here.

## Entry gate

Run each command from `D:/w/_me/algotrading/pocketquant`:

1. `git fetch -q origin && echo "branch=$(git rev-parse --abbrev-ref HEAD) dirty=$(git status --porcelain -- src web deploy tests scripts docs | wc -l | tr -d ' ') synced=$(test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo yes || echo no)"` prints `branch=develop dirty=0 synced=yes`.
2. `git grep -n -E "closePosition|(^|[^_])set_entries_paused" -- src | wc -l | tr -d ' '` prints `0` (Phase 04 merged). <!-- Red team 2026-10-28: #10 --> <!-- Added 2026-10-29: Verify regex excluded the route helper named in step 8 -->
3. `export GH_TOKEN=$(gh auth token --user camping89); gh run list --workflow cicd.yml --branch develop --limit 5 --json headSha,conclusion -q ".[] | select(.headSha==\"$(git log -1 --format=%H -- src tests scripts web pyproject.toml uv.lock .github)\") | .conclusion" | head -1` prints `success`. <!-- Added 2026-10-29: CI skips docs-only commits, so the gate checks the last code commit -->
4. `docker ps > /dev/null 2>&1 && echo docker-ok` prints `docker-ok` (if not, start `"/c/Program Files/Docker/Docker/Docker Desktop.exe" &`, wait 10 s, re-run once).

On a resume after this phase's own unpushed commits (plan.md Conventions, Resume), line 1 may print `synced=no`; that passes when `git rev-list --count HEAD..origin/develop` prints `0`, and line 3 is unchanged (it already checks the last code commit).

On any miss: edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <which gate line failed and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261028-0652-exness-only-parallel-runtime --from 05 after <UTC time>
```

## Files to create/modify

- Modify: `src/pocketquant/core/domain/bar/events.py`, `src/pocketquant/core/domain/bar/services/bar_builder_domain_service.py`, `src/pocketquant/engine/market_data/app_services/bar_app_service.py`, `src/pocketquant/core/infra/persistence/repositories/bar_repository.py` (#12), `src/pocketquant/engine/market_data/app_services/quote_app_service.py`, `src/pocketquant/app/main_extensions.py` (`start_quote_feed`, `stop_quote_feed` only), `src/pocketquant/engine/market_data/app_services/sync_jobs.py` (sync_1m registration only).
- Modify tests: `tests/app_test/market_data/test_bar_app_service_unit.py`, `tests/core_test/unit/domain/bar/services/test_bar_builder.py`, `tests/core_test/infra/persistence/test_bar_repository.py`, `tests/app_test/integration/test_tracked_symbol_cascade_delete_api.py` (#12).
- Create tests: `tests/app_test/market_data/test_bar_timer_close.py`, `tests/app_test/market_data/test_bar_gap_flags.py`, `tests/core_test/infra/persistence/test_bar_repository_shared_writes.py` (#12). <!-- Red team 2026-10-28: #12 -->

## Tasks

<!-- Added 2026-10-29 after the Phase 04 checkpoint -->
**Corrections (2026-10-29).**
- Entry gate line 3 looks up the CI run of the last code commit: a docs-only `HEAD` has no CI run.
- Anchors moved: `start_quote_feed` is `app/main_extensions.py:213-227`, `stop_quote_feed` `:230-235`; `QuoteAppService.start` is `quote_app_service.py:94-102`; `TestFlushAllBars` is `test_bar_app_service_unit.py:308-333`. Locate by symbol.
- `QuoteAppService.start` returns early when `self.running` is set (`:97-99`). Task 5.3 step 8 creates `close_timer_task` after that check, beside `ws_task`.
- Task 5.2 step 3 also breaks two existing tests in `tests/app_test/market_data/test_bar_app_service_unit.py`. `test_bar_completion_no_mongo_write` (`:175`) calls `_complete_bar(bar, calendar, closed_by="tick", closing_tick_at=None)` and keeps `upsert_bar.assert_not_called()`. `test_event_bus_publishes_on_bar_completion` (`:195-198`) feeds two ticks through `add_tick` (the 12:00 and then the 12:05 bucket) instead of calling the private method, and keeps its event asserts.


### Task 5.1 — Event and builder fields

**Goal:** every completed bar can say when it ended, whether it has a gap, and how and when it closed; backtest events keep the defaults.

**Target files and symbols:** `BarCompletedEvent` (`events.py:7-22`); `BarBuilderDomainService` fields and `add_tick` (`bar_builder_domain_service.py:60-110`).

**Steps:**
1. Test first in `tests/core_test/unit/domain/bar/services/test_bar_builder.py`: `test_add_tick_records_the_last_tick_time`: a builder, `add_tick(1.0, 1.0, t)` returns `True` and sets `last_tick_at == t`; a rejected tick (outside the bucket) leaves `last_tick_at` unchanged; a new builder has `gap is False` and `last_tick_at is None`.
2. Run `uv run python -m pytest tests/core_test/unit/domain/bar/services/test_bar_builder.py -q -k last_tick 2>&1 | tail -1`; it must show `1 failed` (expected red).
3. `BarCompletedEvent` gains, after `tick_count`: `bar_end: datetime | None = None`, `gap: bool = False`, `closed_at: datetime | None = None`, `closing_tick_at: datetime | None = None`, `closed_by: str = "tick"`. Docstring adds: "``bar_end`` is None for replayed (backtest) bars; ``closed_by`` is ``tick`` or ``timer``."
4. `BarBuilderDomainService` gains `last_tick_at: datetime | None = None`, `gap: bool = False` and `coverage_start: datetime | None = None` (the time from which this bucket's ticks are covered); `add_tick` sets `self.last_tick_at = timestamp` after a tick is accepted. `to_dict` adds `"gap": self.gap` and `"coverage_start": self.coverage_start.isoformat() if self.coverage_start else None`, so the `bar:current` seed carries both (the SSE payload gains two keys; the web type ignores unknown keys). Add to the step 1 test: `to_dict()` of a new builder has `gap is False` and `coverage_start is None`. <!-- Red team 2026-10-28: #12 -->
5. Commit: `feat(bars): carry bar end, gap and close timing on completed bars`.

**Success criteria:** the new test passes; `engine/backtest/backtest_app_service.py` still builds `BarCompletedEvent` without the new fields (defaults).

**Verify:** `uv run python -m pytest tests/core_test/unit/domain/bar tests/backtest_test -q > /dev/null 2>&1; echo "exit=$?"` prints `exit=0`.

### Task 5.2 — Publish completed bars after releasing the bar lock (D21)

**Goal:** a slow `BarCompletedEvent` handler on symbol A does not block ticks of symbol B.

**Target files and symbols:** `BarAppService.add_tick`, `_process_tick_for_interval`, `_save_completed_bar` (`bar_app_service.py:81-178`).

**Steps:**
1. Test first, new file `tests/app_test/market_data/test_bar_timer_close.py` (it also holds Task 5.3 tests). Build `BarAppService(cache=<AsyncMock(spec=Cache) with get returning None>, bar_repository=AsyncMock(spec=BarRepository), event_bus=EventBus(), intervals=[Interval.MINUTE_1])`. `test_a_slow_bar_handler_does_not_block_another_symbol`: subscribe a handler that `await asyncio.sleep(0.3)` only for symbol `"AAA:EXNESS"`; feed `AAA` ticks at 12:00:10 and then 12:01:01 in a task (the second closes the 12:00 bar); after `await asyncio.sleep(0.01)` time `await svc.add_tick(<BBB:EXNESS tick at 12:01:02>)`; it returns in under 0.1 s while the AAA task is still pending.
2. Run the test; it must fail (the handler runs under the lock today).
3. Rename `_save_completed_bar` to `_complete_bar(bar, calendar, *, closed_by, closing_tick_at) -> BarCompletedEvent | None`. It keeps the empty and OHLC guards, builds the event (new fields: `bar_end=bar.bar_end`, `gap=bar.gap` after the tail check of Task 5.4, `closed_at=get_current_time()`, `closing_tick_at`, `closed_by`), records `self._last_end[(bar.symbol, bar.interval)] = bar.bar_end`, deletes the `bar:current` key only when `self.publishes_current` is on (step 5) and returns the event. <!-- Red team 2026-10-28: #12 --> It does not publish. The Redis delete stays under the lock: the next builder writes the same key with `force=True` right after, so a delete after the release would erase the new bar.
4. `_process_tick_for_interval` returns the event of the bar it closed (`closed_by="tick"`, `closing_tick_at=tick.timestamp`) or `None`. `add_tick` collects the non-None events under the lock and, still under the lock when there are events, adds one to `self._publishes_running`; after the `async with` block it calls `await self._publish(events)`. `_publish(events)`: in a `try`, publish each in order with `await self._event_bus.publish(event)` and log the existing DEBUG `bar_completed_event_published`; in the `finally`, subtract one from `self._publishes_running`. Taking the count under the lock means a timer pass never sees 0 while a tick-close publish is about to start. <!-- Red team 2026-10-28: #4 -->
5. Add `self._last_end: dict[tuple[str, Interval], datetime] = {}` in `__init__` (process lifetime, one entry per tracked symbol and interval) and `self._publishes_running = 0`. <!-- Red team 2026-10-28: #4 --> Add the public switch `self.publishes_current: bool = True` (process lifetime; Phase 07 sets it from the trader role) with the comment "Only the trading process writes or deletes ``bar:current``; a standby trader only reads it as its seed. True until roles exist."; `_cache_current_bar` returns at once, without touching `_last_flush_ts`, when it is off. <!-- Red team 2026-10-28: #12 -->
6. Commit: `fix(bars): publish completed bars after releasing the bar lock`.

**Success criteria:** the test passes; `await self._event_bus.publish` appears only in `_publish`, which runs outside `async with self._lock` blocks in `bar_app_service.py`.

**Verify:** `uv run python -m pytest tests/app_test/market_data -q > /dev/null 2>&1; echo "exit=$?"` prints `exit=0`.

### Task 5.3 — Timer close for every interval (F2b, D20, A15, D35)

**Goal:** a bar is published 0.5 s after its end even when no tick follows; a late tick for a closed bucket never publishes it twice; 4h/1d/1w bars end at their bucket end. <!-- Validation 2026-10-28: D35 -->

**Target files and symbols:** `BarAppService` (new `run_close_timer`, `close_due_bars`, `_new_builder`, constants); `QuoteAppService.__init__`, `start` (`quote_app_service.py:23-38,100-108`); `start_quote_feed`, `stop_quote_feed` (`app/main_extensions.py:185-208`).

**Steps:**
1. Tests first in `test_bar_timer_close.py`, all with `set_simulation_time(...)` from `pocketquant.core.common.time.simulation` as the clock and a collecting bus subscriber:
   - `test_a_1m_bar_closes_on_the_timer_half_a_second_after_its_end`: tick at 12:00:30Z; `set_simulation_time(12:01:00.4)`, `await svc.close_due_bars()` publishes nothing; at 12:01:00.6 it publishes one event with `closed_by == "timer"`, `bar_end == 12:01:00Z`, `closing_tick_at is None`, `closed_at == 12:01:00.6`.
   - `test_a_late_tick_for_a_timer_closed_bucket_is_dropped`: after that close, a tick stamped 12:00:59.9 produces no event and no builder for 12:00; a tick at 12:01:05 creates the 12:01 builder and publishes nothing.
   - `test_a_tick_close_before_the_timer_is_not_published_twice`: tick 12:00:30, tick 12:01:00.2 publishes the 12:00 bar with `closed_by == "tick"`; `close_due_bars()` at 12:01:00.6 publishes nothing more.
   - `test_a_4h_bar_closes_on_the_timer_at_its_bucket_end`: `intervals=[Interval.HOUR_4]`, `EURUSD:EXNESS` with the `CALENDAR_EXNESS_FX` calendar, one tick at Friday 2026-10-16 20:10:00Z; `close_due_bars()` at Saturday 00:00:00.4Z publishes nothing; at 00:00:00.6Z it publishes one event with `closed_by == "timer"` and `bar_end == 2026-10-17T00:00:00Z` (bucket end, not the 20:59 session close). <!-- Validation 2026-10-28: D35 -->
   <!-- Red team 2026-10-28: #4 -->
   - `test_last_closed_boundary_moves_after_the_publish_returns`: a subscriber that awaits an `asyncio.Event` for `AAA:EXNESS`; tick at 12:00:30; `set_simulation_time(12:01:00.6)`; `task = asyncio.create_task(svc.close_due_bars())` (created after the clock is set, so the task sees it); after `await asyncio.sleep(0.01)`, `svc.last_closed_boundary is None`; set the event, `await task`; `svc.last_closed_boundary == 12:01:00Z`.
   - `test_a_running_tick_close_publish_holds_the_boundary`: the same blocking subscriber; ticks at 12:00:30 and then 12:01:00.2 in a task (it tick-closes the 12:00 bar and blocks in the subscriber); `set_simulation_time(12:01:00.6)`, `await svc.close_due_bars()` leaves `last_closed_boundary is None`; set the event, await the tick task, `await svc.close_due_bars()` again sets `12:01:00Z`.
   - `test_an_idle_service_still_advances_the_boundary`: no ticks; `set_simulation_time(12:05:00.6)`, `await svc.close_due_bars()` sets `last_closed_boundary == 12:05:00Z` (a drain never waits on a trader with no symbols).
   <!-- Red team 2026-10-28: #12 -->
   - `test_bar_current_is_written_only_while_publishing`: `svc.publishes_current = False`; ticks at 12:00:10 and 12:01:01 (a roll) leave `cache.set` and `cache.delete` never awaited; then `svc.publishes_current = True`; a tick at 12:01:02 awaits `cache.set` once, with the `CACHE_KEY_BAR_CURRENT` key of that symbol and interval and a value whose `gap` is `False` and whose `coverage_start` is the ISO string of 12:01:00Z (the builder followed a closed bar, so coverage starts at its bucket start).
   - `test_a_bar_cut_by_the_session_close_ends_at_the_close`: calendar factory stub whose `async def for_symbol(self, s)` returns the `CALENDAR_EXNESS_FX` adapter from `EXNESS_CALENDARS`; `intervals=[Interval.HOUR_1]`; tick `EURUSD:EXNESS` at Friday 2026-10-16 20:58:30Z; the builder's `bar_end == 2026-10-16T20:59:00Z`; `close_due_bars()` at 20:59:00.6 publishes it with `bar_end == 20:59:00Z`.
2. Run `uv run python -m pytest tests/app_test/market_data/test_bar_timer_close.py -q 2>&1 | tail -1`; it must show `failed` (`close_due_bars` does not exist).
2a. A public field in `__init__` (process lifetime; Phase 07's drain reads it): `self.last_closed_boundary: datetime | None = None` with the comment "The latest 1m boundary whose bars are all closed and whose publish returned; a draining trader releases only after it." <!-- Red team 2026-10-28: #4 -->
3. Constants in `bar_app_service.py`: `_TIMER_CLOSE_GRACE_S = 0.5`, `_TIMER_TICK_S = 0.25`, `_SESSION_CUT_MAX_INTERVAL_S = 3600` (only bars up to 1h are cut at the session close). <!-- Validation 2026-10-28: D35 -->
4. `_new_builder(symbol_key, interval, bar_start, calendar)`: for `INTERVAL_SECONDS[interval] <= _SESSION_CUT_MAX_INTERVAL_S`, `bar_end = min(bar_start + interval, calendar.session_close(calendar.session_date(bar_start)) + timedelta(seconds=1))`, falling back to `bar_start + interval` on `KeyError` (a date with no session); longer intervals keep the builder default. Use it at both creation sites in `_process_tick_for_interval`; the roll site (a tick that closes the previous bar) sets `coverage_start = bar_start`; its `last_tick_at` stays unset as before, so a silence across the roll is flagged on the closed bar by the tail check. <!-- Red team 2026-10-28: #12 -->
5. In `_process_tick_for_interval`, when no builder exists: if `_last_end` for the key is known and `bar_start < _last_end`, log DEBUG `bar.late_tick_dropped` (`symbol`, `interval`, `tick_ts`) and return `None`; if `_last_end` is known, create the builder with `last_tick_at = bar_start` and `coverage_start = bar_start` (coverage from the bucket start) <!-- Red team 2026-10-28: #12 -->. The seed path for an unknown `_last_end` is Task 5.4.
6. `add_tick` stores the resolved calendar in `self._calendars[symbol_key]` (new dict, process lifetime, one entry per tracked symbol) before taking the lock.
7. `close_due_bars()`: `now = get_current_time()`; under the lock, for every builder (any interval, D35) whose `bar_end + 0.5 s <= now`, call `_complete_bar(builder, self._calendars.get(symbol, self._default_calendar), closed_by="timer", closing_tick_at=None)` and delete the builder from `self._bars[symbol]`; after the lock (the lock section adds one to `_publishes_running` when there are events), `await self._publish(events)`; then, when `self._publishes_running == 0`, set `self.last_closed_boundary = (now - timedelta(seconds=_TIMER_CLOSE_GRACE_S)).replace(second=0, microsecond=0)`: every bar that ended at or before that boundary is closed (by tick or by this pass) and no publish is still running. A pass that sees a running publish leaves the field as it is; the next pass, 0.25 s later, sets it. <!-- Red team 2026-10-28: #4 --> `run_close_timer()`: forever `await asyncio.sleep(_TIMER_TICK_S)` then `await self.close_due_bars()`; an exception logs ERROR `bar.close_timer_failed` with `exc_info=True` and the loop continues.
8. `QuoteAppService`: `self.close_timer_task: asyncio.Task | None = None` in `__init__`; `start()` also sets `self.close_timer_task = asyncio.create_task(self.bar_manager.run_close_timer())`. `start_quote_feed` stores `app.state.close_timer_task = quote_svc.close_timer_task`; `stop_quote_feed` first runs `await _cancel(getattr(app.state, "close_timer_task", None))`.
9. Commit: `feat(bars): close bars on a timer at their end`.

**Success criteria:** the nine tests pass; the timer starts and stops with the quote feed. <!-- Red team 2026-10-28: #4 #12 -->

**Verify:** `uv run python -m pytest tests/app_test/market_data/test_bar_timer_close.py -q 2>&1 | tail -1` shows `10 passed` (with the Task 5.2 test) and no `failed`.

### Task 5.4 — Gap facts, the Redis seed, and the deletions (H3, D10, D20, A14)

**Goal:** a bar built across a feed silence, a stale restart seed or an uncovered mid-bucket start carries `gap=True`; a covering seed restores the bucket's true open; dead code and false docstrings are gone.

**Target files and symbols:** `BarAppService._process_tick_for_interval`, `_complete_bar`, `_seed_builder_from_mongo` (delete), `flush_all_bars` (delete), class docstring (`bar_app_service.py:48-56,94-208,270-289`).

**Steps:**
1. Tests first, new file `tests/app_test/market_data/test_bar_gap_flags.py`: calendar stub as in Task 5.3 with `CALENDAR_EXNESS_FX`, symbol `EURUSD:EXNESS`, `intervals=[Interval.MINUTE_5]` unless stated, Tuesday 2026-10-13 for in-session cases, `set_simulation_time` plus `close_due_bars()` for the timer close at `bar_end + 0.6 s`, a collecting subscriber. Times are UTC:
   - `test_a_61_second_silence_sets_gap`: ticks at 10:00:05, 10:01:06, 10:01:56, 10:02:46, 10:03:36, 10:04:26; the 10:00 bar has `gap is True`.
   - `test_a_59_second_silence_does_not`: ticks at 10:00:05, 10:01:04, 10:01:54, 10:02:44, 10:03:34, 10:04:24; `gap is False`.
   - `test_a_tail_silence_over_60_seconds_sets_gap`: ticks at 10:00:05, 10:00:55, 10:01:45, 10:02:35, 10:03:25, 10:03:58; `gap is True` (62 s to the end).
   - `test_a_mid_bucket_start_without_seed_sets_gap`: `cache.get` returns None; ticks at 10:01:10, 10:02:00, 10:02:50, 10:03:40, 10:04:30; `gap is True`.
   - `test_an_early_start_without_seed_has_no_gap`: ticks at 10:00:40, 10:01:30, 10:02:20, 10:03:10, 10:04:00, 10:04:50; `gap is False`.
   - `test_a_fresh_seed_covers_the_start`: `cache.get` returns `{"bar_start": "2026-10-13T10:05:00+00:00", "open": 1.1, "high": 1.3, "low": 1.0, "close": 1.2, "volume": 5.0, "tick_count": 7, "gap": False, "coverage_start": "2026-10-13T10:05:00+00:00", "last_update": <epoch of 10:07:00>}` (the two seed fields are new, #12); ticks at 10:07:30, 10:08:20, 10:09:10, each at price 1.25; the 10:05 bar has `open == 1.1`, `high == 1.3`, `low == 1.0`, `close == 1.25`, `tick_count == 10`, `gap is False`.
   - `test_an_old_seed_sets_gap`: the same seed with `last_update` at 10:05:50 (100 s before the first tick); `gap is True` and `open == 1.25`.
   <!-- Red team 2026-10-28: #12 -->
   - `test_a_gapped_seed_keeps_its_gap`: the fresh seed above plus `"gap": True, "coverage_start": "2026-10-13T10:06:30+00:00"`; the 10:05 bar has `gap is True` and `open == 1.1`.
   - `test_a_seed_without_coverage_start_is_not_used`: the fresh seed without `gap` and `coverage_start` (as the previous image writes it); the bar has `open == 1.25` and `gap is True` (the first tick is 150 s after the bucket start).
   - `test_a_weekend_silence_is_not_a_gap`: `intervals=[Interval.HOUR_4]`; ticks every 50 s from Friday 2026-10-16 20:00:10 to 20:58:30 (71 ticks), then Sunday 2026-10-18 21:05:10; the Friday bar (closed by the Sunday tick, because this test runs no timer pass) has `gap is False` and the Sunday builder has `gap is False`.
2. Run `uv run python -m pytest tests/app_test/market_data/test_bar_gap_flags.py -q 2>&1 | tail -1`; it must show `failed` (expected red).
3. Constant `_GAP_AFTER_S = 60.0`. Module function `_trading_seconds(calendar, a, b) -> float`: `wall = (b - a).total_seconds()`; return `wall` when `wall <= _GAP_AFTER_S`; else `start = a.replace(second=0, microsecond=0)`, `end = b.replace(second=0, microsecond=0)`, add one minute to `end` when `end < b`, and return `sum((min(m + minute, b) - max(m, a)).total_seconds() for m in calendar.trading_minutes(start, end))`. Minute-aligned bounds matter: `trading_minutes` steps from its `start` argument, so an unaligned start would count partial minutes as whole ones.
4. G1 in `_process_tick_for_interval`: before `add_tick` on an existing builder, if `builder.last_tick_at` is set and `_trading_seconds(calendar, builder.last_tick_at, tick.timestamp) > _GAP_AFTER_S`, set `builder.gap = True`. Tail in `_complete_bar`: if `bar.last_tick_at` is set and `_trading_seconds(calendar, bar.last_tick_at, bar.bar_end) > _GAP_AFTER_S`, set `bar.gap = True` before building the event. Apply G1 also to the new builder created with `last_tick_at = bar_start`.
5. G2: when no builder exists and `_last_end` for the key is unknown, read `seed = await self._cache.get(CACHE_KEY_BAR_CURRENT.format(symbol=symbol_key, interval=interval.value))`. Covering when `seed` is a dict, `seed["bar_start"] == bar_start.isoformat()`, `seed.get("coverage_start")` is set (a seed written before this change has none and is not used) and `_trading_seconds(calendar, datetime.fromtimestamp(seed["last_update"], UTC), tick.timestamp) <= _GAP_AFTER_S`: copy `open`, `high`, `low`, `close`, `volume`, `tick_count`, `gap` and `coverage_start` (parsed with `datetime.fromisoformat`), and set `last_tick_at` from `last_update`; log INFO `bar_app_service.seeded_from_redis` (one per key per process start). Otherwise set `coverage_start = tick.timestamp`. Then for every new builder (seeded, unseeded, or created after a known `_last_end` with `coverage_start = bar_start`): if `_trading_seconds(calendar, bar_start, coverage_start) > _GAP_AFTER_S`, set `gap = True`. One rule for all three paths; a seeded builder inherits the late start of the process that wrote the seed. <!-- Red team 2026-10-28: #12 --> A cache read exception logs ERROR `bar_app_service.seed_failed` and is treated as no seed.
6. Delete `_seed_builder_from_mongo` and `flush_all_bars`; delete `TestFlushAllBars` (`test_bar_app_service_unit.py:305-330`). Keep `_bar_repo` for `get_current_bar`.
7. Docstrings: class line 54 becomes "On bar close: publish ``BarCompletedEvent`` after the bar lock is released, at most once. A restart or a feed gap loses a bar or sets ``gap``; consumers skip entries on gapped bars." Replace the at-least-once comment (`:149`) with "At most once: a bar is never re-published."
8. Commit: `feat(bars): flag tick silence and seed from the live redis bar`.

**Success criteria:** the ten tests pass; `git grep -n -E "flush_all_bars|_seed_builder_from_mongo|at-least-once" -- src tests` prints nothing. <!-- Red team 2026-10-28: #10 #12 -->

**Verify:** `uv run python -m pytest tests/app_test/market_data -q > /dev/null 2>&1; echo "exit=$?"; git grep -n -E "flush_all_bars|_seed_builder_from_mongo|at-least-once" -- src tests | wc -l | tr -d ' '` prints `exit=0` then `0`.

### Task 5.5 — `sync_1m` off the entry window

**Goal:** the minute sync's REST calls never compete with a 1m entry (timer close at +0.5 s, orders out by about +2 s); the stored T-1 bar is in Mongo by second 20 for the Phase 06 warm-up.

**Target files and symbols:** `register_sync_jobs`, the `sync_1m` `add_cron_job` call and its comment (`sync_jobs.py:690-709`).

**Steps:**
1. Change `second=2` to `second=12` for `job_id="sync_1m"`.
2. Replace the comment line "sync_1m runs at +2s from bar close. Gives the data provider time to settle the just-closed bar." with "sync_1m runs at +12 s from bar close: the provider has settled the bar, and the live 1m entries (timer close at +0.5 s, orders by about +2 s) are done."
3. Commit: `perf(sync): run sync_1m at second 12, after the entry window`.

**Success criteria:** exactly one `second=12` in the file; the comment states the reason.

**Verify:** `grep -c "second=12" src/pocketquant/engine/market_data/app_services/sync_jobs.py; grep -c "second=2," src/pocketquant/engine/market_data/app_services/sync_jobs.py` prints `1` then `0`.

<!-- Red team 2026-10-28: #12 -->
### Task 5.6 — Delete the process-local bar write cache

**Goal:** a bar write never depends on what one process remembers: after the split the `api` deletes a symbol and the `worker` writes its bars again, so every write decides from Mongo alone (the `find_one` comparison).

**Target files and symbols:** `_BAR_VALUE_CACHE`, `_cache_key`, `_cache_value`, `BarRepository.upsert_bar`, `BarRepository.delete_by_symbol` (`bar_repository.py:16-35,71-144,284-293`).

**Steps:**
1. Test first, new file `tests/core_test/infra/persistence/test_bar_repository_shared_writes.py` (`pytestmark = pytest.mark.integration`; fixture as in `tests/core_test/infra/persistence/test_stale_recovery.py:20-28`, dropping the bars collection first): `test_a_bar_deleted_by_another_process_is_written_again`: repo A on its own `Database` writes `bar` with `upsert_bar(bar, source="test")`; a second `Database` connection deletes it with a raw `delete_many({"symbol": bar.symbol.upper()})` (another process's delete never reaches this process's memory); repo A writes the same `bar` again; `count_documents({"symbol": bar.symbol.upper()}) == 1`.
2. Run `uv run python -m pytest tests/core_test/infra/persistence/test_bar_repository_shared_writes.py -q 2>&1 | tail -1`; it must show `1 failed` (today the cached value skips the second write).
3. `bar_repository.py`: delete the `_BAR_VALUE_CACHE` comment and constant, `_cache_key`, `_cache_value`, the `TTLCache` import, the cache check at the top of `upsert_bar` and the three cache stores; delete the `delete_by_symbol` override (the base `SymbolScopedRepository.delete_by_symbol` stays). `upsert_bar` docstring: "Diff-aware upsert from one ``find_one``: a new bar is inserted, an equal one is left alone, a changed one gets ``$set`` with a new ``updated_at``."
4. Tests: in `tests/core_test/infra/persistence/test_bar_repository.py` delete the `_BAR_VALUE_CACHE`, `_cache_key`, `_cache_value` imports, the `_reset_cache` fixture, `TestCacheHit`, `test_populates_cache_after_insert` and the cache asserts of `test_no_write_when_db_already_has_same_value` (keep its `find_one`/`update_one` asserts). In `tests/app_test/integration/test_tracked_symbol_cascade_delete_api.py` delete the `_BAR_VALUE_CACHE` import and the two cache asserts after the cascade (`:202-203`). Re-locate each with `git grep -n -w "_BAR_VALUE_CACHE\|_cache_key\|_cache_value" -- tests` first. <!-- Added 2026-10-29: -w; unbounded pattern matched build_bar_cache_key, _build_cache_key, _cache_keys -->
5. Commit: `fix(bars): decide bar writes from mongo only, not a per-process cache`.

**Success criteria:** the new test passes; no reference to the cache remains.

**Verify:** `docker ps > /dev/null && uv run python -m pytest tests/core_test/infra/persistence tests/app_test/integration/test_tracked_symbol_cascade_delete_api.py -q > /dev/null 2>&1; echo "exit=$?"; git grep -n -w -E "_BAR_VALUE_CACHE|_cache_key|_cache_value" -- src tests | wc -l | tr -d ' '` prints `exit=0` then `0`. <!-- Added 2026-10-29: -w; unbounded pattern matched build_bar_cache_key, _build_cache_key, _cache_keys -->

### Task 5.7 — Gates, push `develop`, CI green

**Goal:** the phase lands on `develop` with every gate green; no deploy.

**Target files and symbols:** none new; `pyproject.toml` `[tool.code-metrics]` only if the ratchet trips.

**Steps:**
1. `uv run ruff check src tests` prints `All checks passed!`; `uv run ruff format --check src tests` exits 0; `uv run pyright` prints `0 errors`.
2. `uv run lint-imports | tail -1` prints `Contracts: 6 kept, 0 broken.`
3. `uv run python scripts/code_metrics.py --ratchet; echo "exit=$?"` prints `exit=0`; if a ceiling trips, raise it in its own commit `chore(metrics): raise the code-metrics ceiling for the bar path` and record old and new values in the phase summary.
4. Full suite (Verify below).
5. Push: `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin && test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `pushed`.
6. CI: `sleep 15; export GH_TOKEN=$(gh auth token --user camping89); RUN_ID=$(gh run list --workflow cicd.yml --branch develop --limit 5 --json databaseId,headSha -q ".[] | select(.headSha==\"$(git rev-parse HEAD)\") | .databaseId" | head -1); gh run watch "$RUN_ID" --exit-status > /dev/null 2>&1; gh run view "$RUN_ID" --json conclusion -q .conclusion` prints `success`.

**Success criteria:** local red is exactly the known Windows red; CI on the pushed HEAD concludes `success`.

**Verify:** `uv run python -m pytest tests/ -q > .cache/pytest-full.log 2>&1; tail -1 .cache/pytest-full.log; grep -E "^(FAILED|ERROR) " .cache/pytest-full.log | grep -vcE "test_utc_runtime_guard|test_cron_trigger_timezone"` prints a summary line containing `4 failed` and `4 errors`, then `0`.

## Rollback

Nothing is deployed. `git revert --no-edit <first-sha>^..HEAD` on `develop` and push. No stored data changes: `bar:current` gains two keys (`gap`, `coverage_start`) that the old code ignores, and `sync_1m`'s schedule is re-registered from code at the next start. A seed written by the old code has no `coverage_start`, so the new code does not use it (the bar is gap-flagged instead). <!-- Red team 2026-10-28: #12 -->

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
