---
phase: 2
title: "Symbol lookup race, cascade read limit, unused positions route"
status: pending
priority: P1
effort: 3h
dependencies: []
---

# Phase 02: Symbol lookup race, cascade read limit, unused positions route

## Goal

Three independent fixes, one commit each: the TTLCache race that reconnected the Binance stream in prod, the cascade read limit that can drop a bucket's earliest 1m bars, and the dead positions route.

## Context

- Design and line references: `plans/reports/kongming-261103-1741-1d-cascade-and-small-fixes.md` items 3, 4, 5.
- Prod evidence: trader log 2026-11-03T07:22:33Z `binance_ws.callback_failed ... error="'ETHUSDT:BINANCE'"`, then `binance_ws.error` with the same text, then `binance_ws.reconnecting`.

## Task 02.1: Symbol lookup reads the cache once

**Target files:** `src/pocketquant/core/infra/persistence/symbol_lookup_helper.py`, `src/pocketquant/core/infra/binance/binance_websocket_adapter.py`, a new test `tests/core_test/infra/persistence/test_symbol_lookup_helper.py`.

**Steps:**
1. Write the test first. Monkeypatch `symbol_lookup_helper._CACHE` with `TTLCache(maxsize=500, ttl=60, timer=fake)` where `fake` returns 0 for the insert, then 59, then 60 on later calls. Use a fake repository whose `find_by_symbol` returns a `Symbol` or `None`. Call `get("ETHUSDT:BINANCE")` twice. Name it `test_an_entry_expiring_between_reads_never_raises`. Run it and confirm it fails with `KeyError`.
2. Fix `get`: read once, `hit = _CACHE.get(key, _MISS)` with a module sentinel `_MISS = object()`; return `hit` unless it is `_MISS`. Misses stay cached as `None`. Add one `#` line above the read: the TTLCache checks expiry on every access, so a membership test followed by a read can raise when the entry expires in between.
3. Keep the re-raise in `BinanceWebSocketAdapter._invoke_callback` (E4, recommended keep). Add `exc_info=True` to `logger.error("binance_ws.error", ...)` in `run_forever`; it fires at most once per reconnect.

**Verify:** `uv run python -m pytest tests/core_test/infra/persistence/test_symbol_lookup_helper.py -q` passes; reverting only step 2 (`git stash` of the source file) makes it fail with `KeyError`; restore it.

**Commit:** `fix(market-data): read the symbol lookup cache once`.

## Task 02.2: Cascade reads the whole bucket

**Target files:** `src/pocketquant/engine/market_data/app_services/cascade_aggregator.py`, `tests/app_test/market_data/test_cascade_aggregator.py`.

**Steps:**
1. Write the test first with the `mock_bar_repo` fixture (it sorts descending and applies `limit`): store all 1440 minutes of one weekday as 1m bars for `XAUUSD:EXNESS` (its calendar expects 1383 for that day, see the assert near line 551), cascade that one 1d boundary, assert the upserted 1d open equals the first minute's open and its volume equals the sum of all 1440. Name it `test_a_day_with_more_minutes_than_the_calendar_keeps_its_first_bar`. Confirm it fails on the current code.
2. In `cascade_for_symbol` delete `expected_count`, its `calendar.trading_minutes` call, its comment and the `limit=expected_count + 5` argument. The bucket range bounds the read (at most 1440 docs for 1d, below the 5000 default).
3. Delete the tests that pin the old limit: `test_a_halted_hour_bounds_the_query_by_the_calendar`, `test_the_same_hour_on_a_24x7_calendar_fetches_sixty`, `test_a_short_session_day_bounds_the_daily_read`, and the `limit` assert in the test near line 551 (keep the rest of that test).

**Verify:** `uv run python -m pytest tests/app_test/market_data/ -q` passes; `git grep -n "expected_count" -- src/pocketquant/engine/market_data/app_services/cascade_aggregator.py | wc -l` prints `0`.

**Commit:** `fix(market-data): read every 1m bar of a cascaded bucket`.

## Task 02.3: Delete the positions route

**Target files:** `src/pocketquant/app/routes/strategy.py`, `src/pocketquant/engine/strategy/strategy_query_service.py`, `tests/app_test/integration/test_admin_token_guard.py`, `tests/engine_test/test_strategy_service.py`.

**Steps:**
1. Delete `get_subscription_positions` (the `/{sub_id}/positions` route) and `StrategyQueryService.get_positions`.
2. Delete the `/positions` entry in the guarded-route list of `test_admin_token_guard.py` (near line 101).
3. Delete `test_get_positions_maps_open_positions` and `test_get_positions_returns_empty_when_none_open` in `test_strategy_service.py`, update the section comment above them to name only `get_trades`, and delete any helper in that file left without a caller.
4. Keep `PositionRepository.find_open_by_subscription` (used by `strategy_command_service.py`). Leave `test_exness_live_trading_off.py` alone; its `/positions` match is an Exness client path.

**Verify:** `git grep -n -E "get_positions\(sub|def get_positions\(self, subscription_id|/\{sub_id\}/positions" -- src tests | wc -l` prints `0`; `git grep -n "/positions" -- web/src | wc -l` prints `0`; `uv run python -m pytest tests/engine_test/test_strategy_service.py tests/app_test/integration/test_admin_token_guard.py -q` passes.

**Commit:** `refactor(api): remove the unused subscription positions route`.

## Close

CLOSE (plan.md Conventions). Report `plans/261103-1741-1d-cascade-fold-and-small-fixes/reports/phase-02-small-fixes.md` with each Verify output, the three commit ids and the CI run id.

## Risk and rollback

- 02.2 changes what every cascade run reads; values change only for buckets that had more 1m bars than the calendar expected, which is the bug.
- Rollback: `git revert` the single commit of the task.

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
