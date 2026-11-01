---
phase: 11
title: "Snapshot ring, manual actions, read endpoints"
status: pending
priority: P1
effort: 1d
dependencies: [10]
---

# Phase 11: Snapshot ring, manual actions, read endpoints

<!-- Red team 2026-11-01: #15 -->
No open issue: plan.md settles the `manual_action` return rule (verdict "Manual action", D7), the strategy-agnostic grep (Conventions) and the one test double.

## Goal

Every live entry bar leaves a generic `{bar_start, interval, readings, decision, outcome, pending}` record in a 20-entry ring in Redis. A human can request a close or a cancel; the lease holder's reconcile tick attempts it once it can act, clears it, and records `accepted` or `rejected:<code>` in the ring and on the subscription row. The API serves the snapshot, the orders and an enriched subscription list, and these reads plus the existing positions and trades reads require the admin token (D8).

## Context

- Verdicts (plan.md): the strategy sets `snapshot = {"readings": [...], "decision": {...}}`. The engine appends the record and writes the ring as one JSON value to `strategy:snapshot:{subscription_id}` with a 7-day TTL, only for live bars while the trader holds the lease, with no cleanup job. `pending = {side, price} | null`, where `price` is the stop price (C7). `manual_action: "close" | "cancel" | None`: the route sets it only when it is null (409 `ACTION_PENDING` otherwise). `manual_action(sid, action)` leaves the action queued only in standby or drain, or while the broker has no current price for the symbol; otherwise it attempts the action, and every attempt clears the field and records `accepted` or `rejected:<code>` (D7). No withdraw route. <!-- Red team 2026-11-01: #3 #7 #8 -->
- D1: the reconcile loop gains this step; its period, lease gating and load/unload ownership stay unchanged. D6: no expiry. D8: the snapshot, orders and list reads and the existing positions and trades reads require the admin token. <!-- Red team 2026-11-01: #7 -->
- Synthesis §3: the outcome is `no_signal | sent | skipped:<reason> | rejected:<reason>`. Writes happen only when `event.bar_end is not None` and `trading_until` is set. A write failure logs WARNING and never blocks. `unload_strategy` pops the ring. The command service takes no `Cache`.
- Phase 09 names used here: `OrderAppService.pending_stop`, `StrategyAppService._cancel_stop`, `IBrokerPort.close_position(..., *, reason, deadline)`, the DEBUG `strategy.stop_kept` and `strategy.exit_ignored` returns in `_process_signal`, and `REASON_STRATEGY_EXIT`. A failed cancel never blocks a close (#5).
- Why a close waits for a price: paper `close_position` prices the fill at `self._current_prices.get(symbol, pos.current_price)` (Phase 09). After a takeover `_current_prices` is empty until the first finest bar (`paper_broker_adapter.py:237-246` leaves it untouched; `:478` is its live writer), and a restored row's `current_price` is the entry price (`core/domain/position/entities.py:69`; the tracker saves only on fills, `engine/execution/position_app_service.py:49-74`). The first reconcile tick runs right after `take_over()` (`app/roles.py:203-206`, `engine/live/strategy_reconcile_app_service.py:65-67`). <!-- Red team 2026-11-01: #3 -->
- Reconcile starts only after `take_over()` (`app/roles.py:203-205`). `trading_until` is None in standby and drain (`strategy_app_service.py:90-92`). The per-sub loop is `_reconcile` (`strategy_reconcile_app_service.py:77-111`).
- Code: `IStrategyService.__init__` state is at `core/domain/strategy/strategy_service_interface.py:17-22`. The engine bar loop is `_on_bar_completed`; Phases 07 and 09 changed it, so locate it by name. `Cache.get/mget/set` are at `core/infra/persistence/redis.py:44-85` (JSON with `default=str`). Redis keys and TTLs are at `core/common/constants.py:20-32`. The engine factory is `app/di/services.py:122-153`; `Cache` is provided at `app/di/infrastructure.py:62`. `StrategyQueryService` (`engine/strategy/strategy_query_service.py:12-19`) is auto-provided (`services.py:214`) and built by hand in `tests/engine_test/test_strategy_service.py:40-49`. `OrderAggregate.to_mongo` stores `price` and `updated_at` (`core/domain/order/entities.py:181,188`). The order index `ix_orders_subscription_id` is at `core/infra/persistence/repositories/order_repository.py:29`. `PositionRepository.find_open(limit=200)` is at `position_repository.py:20`. <!-- Red team 2026-11-01: #8 -->
- Admin guard: `verify_admin_token` (`app/middleware/admin_auth_middleware.py:16-35`) returns early for GET, HEAD and OPTIONS (`:10,19-20`) because the SPA's EventSource streams cannot send headers. It is attached once, router-wide, to the `api` router (`app/main_extensions.py:332-336`), so a guard on reads needs a second dependency on the chosen routes. The existing reads are `GET /subscriptions/` (`app/routes/strategy.py:62-67`), `/{sub_id}/positions` (`:88-93`) and `/{sub_id}/trades` (`:96-103`). `tests/app_test/integration/test_admin_token_guard.py` counts mutation routes (`:34-46`, 17 on HEAD, 18 after Phase 06) and asserts in two tests that `GET /subscriptions/` answers 200 without a token (`:61,71`). Tests run with `ENVIRONMENT=development` and no `admin_token` (`tests/conftest.py:35`; `core/config.py:85`), so other tests' reads stay open. <!-- Red team 2026-11-01: #7 -->
- Test double: the one `ScriptedStrategy` (`tests/strategy_doubles.py`; Phase 08 script mode). This phase adds per-bar snapshots to it and no second double. <!-- Red team 2026-11-01: #15 -->

## Entry gate

Run from `D:/w/_me/algotrading/pocketquant`:
1. `git status --porcelain -- src web deploy tests scripts docs .github | wc -l` prints `0`.
2. `git fetch -q origin && test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo synced` prints `synced`.
3. `tail -1 plans/261101-0843-stf-to-mtf-foundation/reports/phase-10-exness-close-pending-cancel.md` prints `Result: PASS`.
4. `git grep -n "manual_action\|CACHE_KEY_STRATEGY_SNAPSHOT\|require_admin_token" -- src | wc -l` prints `0` (on a resume, skip each task whose Verify already passes).
5. `grep -n "assert len(routes) ==" tests/app_test/integration/test_admin_token_guard.py` prints a line ending `== 18`.
6. `git grep -n -E "def pending_stop|def _cancel_stop|SCRIPT: ClassVar" -- src tests/strategy_doubles.py | wc -l` prints `3`. <!-- Red team 2026-11-01: #15 -->
7. `docker ps > /dev/null 2>&1 && echo docker-ok` prints `docker-ok`.

A resumed phase may show its own task files as uncommitted (line 1), and line 2 may fail only when `git rev-list --count HEAD..origin/develop` prints `0` (local is ahead by this phase's own unpushed commits). <!-- Consistency sweep 2026-11-01 --> On a miss, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261101-0843-stf-to-mtf-foundation --from 11 after <UTC time>
```

## Files

- Modify (src, under `src/pocketquant/`): `core/common/constants.py`, `core/domain/strategy/strategy_service_interface.py`, `core/domain/brokers/events.py`, `core/domain/subscription/entities.py`, `core/infra/persistence/repositories/subscription_repository.py`, `core/infra/persistence/repositories/order_repository.py`, `core/infra/brokers/paper/paper_broker_adapter.py` (`has_price`), `engine/strategy/strategy_app_service.py`, `engine/strategy/strategy_command_service.py`, `engine/strategy/strategy_query_service.py`, `engine/live/strategy_reconcile_app_service.py`, `app/middleware/admin_auth_middleware.py`, `app/routes/strategy.py`, `app/di/services.py`. <!-- Red team 2026-11-01: #3 #7 -->
- Modify (tests): `tests/engine_test/test_strategy_reconcile_service.py`, `tests/engine_test/test_strategy_service.py`, `tests/core_test/infra/persistence/test_subscription_repository.py`, `tests/app_test/integration/test_strategy_subscriptions_api.py`, `tests/app_test/integration/test_admin_token_guard.py`, `tests/strategy_doubles.py` (`ScriptedStrategy.snapshots`).
- Create (tests): `tests/engine_test/test_strategy_snapshot.py`, `tests/engine_test/test_manual_action.py`, `tests/core_test/infra/persistence/test_live_order_repository.py`.
- Modify (docs): `docs/system-architecture.md`.

## Tasks

### Task 11.1 — Snapshot ring in the engine

**Goal:** each decided live bar appends one record to the subscription's ring, and the lease holder writes it to Redis.

**Target files and symbols:** `IStrategyService.__init__` (`self.snapshot: dict | None = None`); `CACHE_KEY_STRATEGY_SNAPSHOT`, `TTL_STRATEGY_SNAPSHOT`; `StrategyAppService.__init__` (`cache: Cache | None = None`, `self._snapshots: dict[str, deque[dict]]`), `_decide`, `_on_bar_completed`, new `_handle_bar`, `_process_signal` (returns `str`), new `_record_snapshot`, `start_strategy` replay, `unload_strategy`; `get_strategy_engine`; `ScriptedStrategy`.

**Steps:**
1. <!-- Red team 2026-11-01: #15 --> Extend `ScriptedStrategy`: `self.snapshots: list[dict | None] | None = None`; when it is a list, `on_bar_completed` pops its next item (None once empty) into `self.snapshot`. Tests set it on the loaded instance.
2. Tests first in `test_strategy_snapshot.py` (paper engine as in `tests/engine_test/test_paper_capabilities.py`, `ScriptedStrategy`, and a fake cache that stores `set` calls with their `ttl`):
   - `test_a_live_bar_writes_one_record_with_a_seven_day_ttl`: key `strategy:snapshot:<sid>`, ttl `604800`, last record keys `{bar_start, interval, readings, decision, outcome, pending}`, `outcome == "no_signal"`.
   - `test_the_ring_keeps_the_last_twenty`: 25 bars give 20 records, the first `bar_start` is bar 6.
   - `test_outcomes_name_what_happened`: a market signal gives `sent`, a signal while an order is in flight gives `skipped:inflight` (put an unfinished future in `engine._signal_tasks[<sid>]`: the in-flight guard reads only that map, which a paper broker never fills, `strategy_app_service.py:407-409` on `e4a998b8`) <!-- Consistency sweep 2026-11-01 -->, a zero-balance signal gives `rejected:zero position size`, a re-sent unchanged stop gives `skipped:stop_unchanged`, and an EXIT with nothing open gives `skipped:nothing_open`.
   - <!-- Red team 2026-11-01: #8 --> `test_pending_shows_the_resting_stop`: after a stop LONG 105, `pending == {"side": "buy", "price": 105.0}`.
   - `test_nothing_is_written_without_the_lease` (`trading_until = None`).
   - `test_warm_up_fills_the_ring_without_writing`.
   - `test_a_failed_write_never_blocks_the_bar` (`set` raises; the signal still reaches the broker; one WARNING `strategy.snapshot_write_failed`).
   - `test_unload_drops_the_ring`.
3. Run `uv run python -m pytest tests/engine_test/test_strategy_snapshot.py -q 2>&1 | tail -1`. Expected red: `failed`.
4. Constants, next to the other keys: `CACHE_KEY_STRATEGY_SNAPSHOT = "strategy:snapshot:{subscription_id}"` and `TTL_STRATEGY_SNAPSHOT = 7 * 86400`, with the comment "No cleanup job: subscription ids are UUIDv7 and never reused, and no reader lists these keys."
5. `_decide` sets `strategy.snapshot = None` before calling the strategy.
6. Move the per-strategy body of `_on_bar_completed` unchanged into `_handle_bar(strategy, event, published_at) -> str`. Each `continue` becomes a return of its outcome: `no_signal`, `skipped:<reason>`, `sent` for a spawned venue task, or the result of `_process_signal`. `_process_signal` returns `rejected:<reason>` beside every `on_order_rejected(reason)`, `skipped:stop_unchanged` beside `strategy.stop_kept`, `skipped:nothing_open` for an ignored EXIT, `rejected:close_failed` when an EXIT's `close_position` returns False, and `sent` after the broker call. The loop then builds `{"bar_start": iso, "interval": event.interval, "readings": (snapshot or {}).get("readings", []), "decision": (snapshot or {}).get("decision"), "outcome": outcome}` and calls `await self._record_snapshot(strategy.id, record, write=event.bar_end is not None)`.
7. `_record_snapshot(sid, record, *, write)` adds `"pending": None` or `{"side": order.side.value, "price": order.stop_price}` from `pending_stop(sid)`, appends to `self._snapshots.setdefault(sid, deque(maxlen=20))`, and writes `list(ring)` with `TTL_STRATEGY_SNAPSHOT` only when `write and self._cache is not None and self.trading_until is not None`, inside `try`; an exception logs WARNING `strategy.snapshot_write_failed` with subscription_id. <!-- Red team 2026-11-01: #8 -->
8. The warm-up replay records with `outcome="skipped:warmup" if signal else "no_signal"` and `write=False`. `unload_strategy` pops the ring. `get_strategy_engine` takes `cache: Cache` and passes `cache=cache`.

**Success criteria:** the eight tests pass, and the existing engine tests pass with `cache` omitted.

**Verify:** `uv run python -m pytest tests/engine_test tests/backtest_test -q 2>&1 | tail -1` contains `passed` and no `failed`.

### Task 11.2 — Manual close and cancel through reconcile

**Goal:** `POST /subscriptions/{id}/close|cancel` records one pending action; the lease holder attempts it through the engine paths strategies use as soon as it can act, then clears it with its outcome.

**Target files and symbols:** `Subscription.manual_action: Literal["close", "cancel"] | None = None` and `Subscription.manual_action_outcome: dict | None = None` (`to_mongo`, `from_mongo` with `.get`); `SubscriptionRepository.request_action`, `clear_action`; `StrategyCommandService.request_action`; routes `close_subscription`, `cancel_subscription`; `REASON_MANUAL_CLOSE = "manual_close"` in `events.py`; `PaperBrokerAdapter.has_price`; `StrategyAppService.manual_action`; `StrategyReconcileAppService._reconcile`. <!-- Red team 2026-11-01: #7 -->

**Steps:**
1. Tests first:
   - `test_subscription_repository.py`: `test_request_action_sets_only_when_none` (1, then 0 for a second request); `test_clear_action_clears_only_the_same_value` (`clear_action(id, "cancel", "accepted")` on `"close"` returns 0); `test_clear_action_records_the_outcome` (after `clear_action(id, "close", "rejected:close_failed")`: `manual_action is None`, `manual_action_outcome` has `action == "close"`, `outcome == "rejected:close_failed"` and an `at` datetime). <!-- Red team 2026-11-01: #7 -->
   - `test_manual_action.py` (paper engine, `ScriptedStrategy`, a fake cache):
     - `test_close_cancels_the_stop_and_closes_the_position`: returns `"accepted"`; one `TradeClosedEvent`; no pending; the last ring record has `decision == {"action": "manual_close", "reason": "owner request"}`, `interval is None` and `outcome == "accepted"`.
     - <!-- Red team 2026-11-01: #5 --> `test_close_runs_when_the_cancel_fails` (the broker's `cancel_order` patched to return False): one `TradeClosedEvent`, returns `"accepted"`, one WARNING `strategy.pending_cancel_failed`.
     - `test_cancel_leaves_the_position_open` (`"accepted"`); `test_cancel_with_nothing_pending_is_rejected` (`"rejected:nothing_pending"`); `test_close_with_nothing_open_is_rejected` (`"rejected:nothing_open"`); `test_a_failed_close_is_rejected` (`close_position` patched to return False: `"rejected:close_failed"`); `test_no_broker_is_rejected` (`"rejected:no_broker"`). <!-- Red team 2026-11-01: #7 -->
     - `test_drain_keeps_the_action_queued` (`trading_until = None`: returns None, no broker call).
     - <!-- Red team 2026-11-01: #3 --> `test_close_waits_for_a_price_after_a_takeover`: `take_over` restores a LONG entered at 1900; `manual_action(sid, "close")` before any bar returns None and fills nothing; after a 1m bar closing at 2000 it returns `"accepted"`, and the trade's exit price is 2000, not 1900.
   - `test_strategy_reconcile_service.py` (extend `_FakeStrategyService.manual_action` and `_FakeSubRepo.clear_action`): `test_an_attempted_action_is_cleared_with_its_outcome` (`"accepted"` and `"rejected:close_failed"` each clear with that outcome); `test_a_queued_action_stays_for_the_next_tick` (None: no `clear_action`); `test_an_action_without_an_instance_is_cleared_with_a_warning` (outcome `rejected:not_loaded`, WARNING `reconcile.manual_action_dropped`). <!-- Red team 2026-11-01: #7 -->
   - `test_strategy_subscriptions_api.py`: `test_close_returns_202_then_409_while_pending` (`error.code == "ACTION_PENDING"` in the response body) <!-- Consistency sweep 2026-11-01 --> and `test_cancel_on_a_missing_subscription_is_404`.
   - The mutation guard count is `20`.
2. Run `uv run python -m pytest tests/core_test/infra/persistence/test_subscription_repository.py tests/engine_test/test_manual_action.py tests/engine_test/test_strategy_reconcile_service.py tests/app_test/integration/test_strategy_subscriptions_api.py tests/app_test/integration/test_admin_token_guard.py -q 2>&1 | tail -1`. Expected red: `failed`.
3. Repo: `request_action` uses `update_one({"_id": id, "manual_action": None}, {"$set": {"manual_action": action}})` and returns `modified_count`; a missing field matches `None` in Mongo, so documents from before this change need no migration. `clear_action(id, action, outcome)` runs `update_one({"_id": id, "manual_action": action}, {"$set": {"manual_action": None, "manual_action_outcome": {"action": action, "outcome": outcome, "at": utc_now()}}})` and returns `modified_count`.
4. Command `request_action(sub_id, action)`: a missing subscription raises `NotFoundError`; 0 modified raises `DomainError("an action is already pending", error_code="ACTION_PENDING", status_code=409)`. Routes `POST /{sub_id}/close` and `POST /{sub_id}/cancel` return status 202 with `{"subscription_id", "action"}`.
5. `PaperBrokerAdapter.has_price(symbol) -> bool` returns `symbol.upper() in self._current_prices`. <!-- Red team 2026-11-01: #3 -->
6. <!-- Red team 2026-11-01: #3 #5 #7 --> Engine `manual_action(subscription_id, action) -> str | None` (None = stays queued):
   - `trading_until is None` returns None (standby or drain).
   - No bound broker: the outcome is `rejected:no_broker`.
   - A paper broker without `has_price(symbol)` returns None, with DEBUG `manual_action.waiting_for_price`. Comment: "Right after a takeover the paper broker has no price, and a close would fill at the stored entry price."
   - `cancel`: no `pending_stop` gives `rejected:nothing_pending`; a failed `_cancel_stop` gives `rejected:cancel_failed`; otherwise `accepted`.
   - `close`: a pending stop is cancelled through `_cancel_stop`, and a failure only logs (the close still goes). With an open position (`self._position_app_service.get(id)`), `broker.close_position(id, position.symbol, reason=REASON_MANUAL_CLOSE, deadline=self.trading_until)` returning False gives `rejected:close_failed`, True gives `accepted`. With no position: `accepted` when the stop was cancelled, `rejected:cancel_failed` when its cancel failed, `rejected:nothing_open` when nothing was held.
   - Every attempt records `{"bar_start": <now iso>, "interval": None, "readings": [], "decision": {"action": f"manual_{action}", "reason": "owner request"}, "outcome": outcome}` through `_record_snapshot(id, record, write=True)`, logs INFO `manual_action.done` (subscription_id, action, outcome) and returns the outcome.
7. In `_reconcile`, after `_converge_one` for each sub, inside the same per-sub `try`: when `sub.manual_action` is set, a sub with no loaded instance gets `clear_action(sub_id, action, "rejected:not_loaded")` and WARNING `reconcile.manual_action_dropped`; otherwise `outcome = await self._strategy_service.manual_action(sub_id, sub.manual_action)`, and `clear_action(sub_id, sub.manual_action, outcome)` runs when it is not None. WHY comment: "Applied by the lease holder only. Every attempt clears the action and records its outcome; the owner retries. It stays queued only while this trader cannot act yet."

**Success criteria:** the listed tests pass.

**Verify:** the step 2 command's tail contains `passed` and no `failed`.

### Task 11.3 — Read endpoints and the enriched list

**Goal:** the UI reads the snapshot, the recent orders, and per-row position, latest snapshot, pending action and last action outcome without a request per row.

**Target files and symbols:** route `get_subscription_snapshot` (injects `Cache` directly); route `get_subscription_orders`; `OrderRepository.list_by_subscription(subscription_id, limit)`; `StrategyQueryService.__init__` (adds `order_repository`, `cache`), `get_orders`, `list_symbols`; the `_query_service` test helper (`test_strategy_service.py:40-49`).

**Steps:**
1. Tests first:
   - `test_live_order_repository.py` (fixture as `test_subscription_repository.py:29-37`): `test_list_by_subscription_returns_newest_first_up_to_limit`.
   - `test_strategy_service.py`: the helper gains `order_repo` and `cache` (AsyncMock defaults). Add `test_list_symbols_adds_position_snapshot_and_action` (one `find_open` and one `mget` call for two subs; the row without data shows `position: None, snapshot: None, manual_action: None, manual_action_outcome: None`) and `test_get_orders_maps_orders` (row keys exactly `id, side, order_type, status, quantity, price, stop_price, sl_price, tp_price, filled_price, created_at, updated_at`). <!-- Red team 2026-11-01: #8 -->
   - `test_strategy_subscriptions_api.py`: `test_snapshot_is_an_empty_list_before_any_bar` and `test_orders_limit_is_bounded` (`?limit=0` is 422).
2. Run `uv run python -m pytest tests/core_test/infra/persistence/test_live_order_repository.py tests/engine_test/test_strategy_service.py tests/app_test/integration/test_strategy_subscriptions_api.py -q 2>&1 | tail -1`. Expected red: `failed`.
3. `list_by_subscription` runs `find({"subscription_id": id}).sort("created_at", -1).limit(limit)` (filter on `ix_orders_subscription_id`).
4. Routes:
   - `GET /{sub_id}/snapshot` returns `await cache.get(CACHE_KEY_STRATEGY_SNAPSHOT.format(subscription_id=sub_id)) or []` (oldest first).
   - `GET /{sub_id}/orders` takes `limit: int = Query(50, ge=1, le=200)` and calls `query_svc.get_orders`. Each row has `id, side, order_type, status, quantity, price, stop_price, sl_price, tp_price, filled_price, created_at, updated_at`. <!-- Red team 2026-11-01: #8 -->
5. `list_symbols`: one `position_repo.find_open()` mapped by `subscription_id` to `{direction, entry_price, quantity, sl_price, tp_price, unrealized_pnl}`, with `direction = p.side.value.upper()` (`"LONG"`/`"SHORT"`, as `get_positions` already does; the web type in Phase 13 expects upper case) <!-- Consistency sweep 2026-11-01 -->, one `cache.mget` over the subs' keys (last entry or None), `manual_action` and `manual_action_outcome`. It keeps every existing field.

**Success criteria:** the listed tests pass.

**Verify:** the step 2 command's tail contains `passed` and no `failed`.

### Task 11.4 — Admin token on the subscription reads (D8)

<!-- Red team 2026-11-01: #7 -->
**Goal:** `GET /subscriptions/`, `/{sub_id}/positions`, `/{sub_id}/trades`, `/{sub_id}/snapshot` and `/{sub_id}/orders` need the admin token; every other GET stays open.

**Target files and symbols:** `admin_auth_middleware.py` (new `require_admin_token`, shared token check); the five routes in `app/routes/strategy.py`; `test_admin_token_guard.py`.

**Steps:**
1. Tests first in `test_admin_token_guard.py`:
   - `test_the_subscription_reads_carry_the_read_guard`: the GET `APIRoute`s whose dependencies include `require_admin_token` have exactly the paths `{prefix}/subscriptions/`, `{prefix}/subscriptions/{sub_id}/positions`, `.../trades`, `.../snapshot` and `.../orders`.
   - `test_a_guarded_read_needs_the_token`: with the token set, `GET /subscriptions/` without a header and with a wrong header is 401, with the right header 200.
   - `test_production_without_token_fails_closed_on_guarded_reads`: `GET /subscriptions/` is 503.
   - In `test_token_set_rejects_missing_or_wrong_header_and_accepts_right_one` (`:61`) and `test_production_without_token_fails_closed_on_mutations_only` (`:71`), the open read becomes `GET {prefix}/strategies/` (new helper `_list_templates_path`), still 200.
2. Run `uv run python -m pytest tests/app_test/integration/test_admin_token_guard.py -q 2>&1 | tail -1`. Expected red: `failed`.
3. In `admin_auth_middleware.py`, move everything after the safe-method return into `_check_token(x_admin_token)`. `verify_admin_token` keeps the safe-method return, then calls it. New `async def require_admin_token(x_admin_token: str | None = Header(default=None)) -> None` always calls it. Comment above it: "Reads that expose positions, orders and strategy state need the token too; none of them is an EventSource stream."
4. Add `dependencies=[Depends(require_admin_token)]` to the five route decorators (a guard dependency, like the router-wide one in `main_extensions.py:335`; services still come through `FromDishka`).

**Success criteria:** the new and changed guard tests pass; the mutation count stays `20`; the other integration tests still read without a token (development mode).

**Verify:** `uv run python -m pytest tests/app_test -q 2>&1 | tail -1` contains `passed` and no `failed`.

### Task 11.5 — Architecture doc

**Goal:** the three contracts are written where the next reader looks.

**Target files and symbols:** `docs/system-architecture.md` decision bullets.

**Steps:**
1. Add: "- **A strategy reports a generic snapshot.** It sets `snapshot = {readings, decision}`. The engine adds `bar_start`, `interval`, the outcome and the pending stop as `{side, price}`, keeps the last 20 per subscription, and writes them as one JSON value to `strategy:snapshot:{subscription_id}` for live bars while it holds the lease. The key expires after 7 days; there is no cleanup job." <!-- Red team 2026-11-01: #8 -->
2. Add: "- **A manual close or cancel is a stored request.** The route sets `manual_action` only when it is empty (409 `ACTION_PENDING` otherwise). The lease holder's reconcile tick attempts it through the engine paths strategies use, clears it, and records `accepted` or `rejected:<code>` on the row and in the snapshot ring; the owner retries. It stays queued only in standby or drain, or until the paper broker has a price after a takeover. There is no expiry and no withdraw route. A close is sent even when the pending-stop cancel fails." <!-- Red team 2026-11-01: #3 #5 #7 -->
3. Add: "- **Subscription reads need the admin token.** The subscription list and its positions, trades, snapshot and orders reads use `require_admin_token`. Other GETs stay open because the SPA's EventSource streams cannot send headers." <!-- Red team 2026-11-01: #7 -->

**Success criteria:** the doc stays under 800 lines.

**Verify:** `grep -c -E "generic snapshot|manual close or cancel is a stored request|Subscription reads need the admin token" docs/system-architecture.md` prints `3`.

### Task 11.6 — CLOSE

**Goal:** the phase lands on `develop` with every gate green.

**Target files and symbols:** none new; `pyproject.toml` `[tool.code-metrics]` only if the ratchet alone fails.

**Steps:**
1. GATES: `uv run lint-imports | tail -1` prints `Contracts: 6 kept, 0 broken.`; `uv run python scripts/code_metrics.py --ratchet; echo "exit=$?"` prints `exit=0`; `uv run ruff check src tests scripts; echo "exit=$?"` prints `exit=0`. If only the ratchet fails, raise the ceiling in its own commit `chore(metrics): raise the code metric ceiling` and record the old and new values in the report.
2. <!-- Red team 2026-11-01: #15 --> Strategy-agnostic check (plan.md Conventions): `git grep -n -i -E "triple[ _-]?screen|force[ _-]?index|elder" -- web/src src/pocketquant/app src/pocketquant/engine | wc -l` prints `0`.
3. FULLSUITE: `uv run python -m pytest tests/ -q > .cache/pytest.txt 2>&1; tail -1 .cache/pytest.txt; grep -E "^(FAILED|ERROR) " .cache/pytest.txt | grep -v -E "test_utc_runtime_guard|test_cron_trigger_timezone" | wc -l`. The tail contains `4 failed` and `4 errors`; the count prints `0`.
4. Commit: `feat(strategy): snapshot ring, manual close and cancel, guarded subscription reads`.
5. Push: `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin && test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `pushed`.
6. `sleep 15`, then repeat the Verify command until it prints `completed`.

**Success criteria:** CI on the pushed HEAD concludes `success`.

**Verify:** `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 1 --json headSha,status,conclusion -q '.[0] | "\(.headSha) \(.status) \(.conclusion)"'` prints `<git rev-parse HEAD> completed success`.

## Rollback

Nothing deploys. Run `git revert --no-edit <phase-commit>` (plus the metric commit, if any) and push. The `manual_action` and `manual_action_outcome` fields and the snapshot keys are additive: old code ignores the fields, and the keys expire within 7 days. The revert also reopens the five reads to callers without a token.

## Report

`reports/phase-11-snapshot-manual-actions-endpoints.md` holds:
- every new test with its pass counts;
- the mutation guard count (`20`) and the five guarded read paths;
- the strategy-agnostic grep (`0`);
- the FULLSUITE tail line;
- the commit SHAs, the CI run id and its conclusion;
- any metric ceiling change.

It ends with `Result: PASS`.

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
