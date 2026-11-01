---
phase: 2
title: "Spike B: paper EXIT, resting stop, manual action, snapshot to UI, Exness spec; go/no-go table"
status: pending
priority: P1
effort: 1d
dependencies: [1]
---

# Phase 02: Spike B: paper EXIT, resting stop, manual action, snapshot to UI, Exness spec; go/no-go table

## Goal

Prove in the spike worktree that paper EXIT (live and backtest), the engine-ordered resting stop, the manual action channel and the snapshot path to the UI work, record the Exness API facts, complete the go/no-go table, then delete the worktree and commit only the reports.

## Context

- Same spike rules as Phase 01 (Context there): rough code in `../pocketquant-spike` only; nothing is committed, cherry-picked or copied; a test that stays red after `kongming` names a design limit is a `no-go` row, not a phase failure.
- Verdicts this phase proves (plan.md Design verdicts): EXIT means go flat: cancel the pending stop, then `IBrokerPort.close_position(subscription_id, symbol, *, reason, deadline)` if a position is open; paper closes under its own `_lock` through `_fire_synthetic_exit` (`src/pocketquant/core/infra/brokers/paper/paper_broker_adapter.py:528-586`) with reason `strategy_exit` or `manual_close`; no `reduce_only`. `on_order_update` is subscribed for every broker (today only when `fills_async`, `engine/strategy/strategy_app_service.py:676-677`) and returns early for `OrderStatus.PENDING`, because `_notify_callbacks` fires inside `submit_order` (`paper_broker_adapter.py:136`) before `OrderAppService.submit` finishes the immediate fill (`engine/execution/order_app_service.py:57-66`). Every new signal cancels the subscription's resting stop, then places. The backtest sandbox starts the position tracker (Q3).
- <!-- Red team 2026-11-01: #1, #10 --> Resting stop (plan.md verdict "Resting stop trigger order"): the stop rests in the paper broker, but the engine fills it. The engine subscribes to `BarCompletedEvent` in `start()` (`engine/strategy/strategy_app_service.py:108-117`) and the paper broker subscribes last, at `connect()` (`paper_broker_adapter.py:106-111`), so strategies decide before the broker's own bar handler (`:472-503`) runs. A broker-side trigger therefore never fills a stop that the strategy cancels and re-places every bar. `StrategyAppService._on_bar_completed` calls `PaperBrokerAdapter.fill_resting_stops(event)` before any strategy decides on that bar, only while `trading_until` is set (`strategy_app_service.py:92,504`) and only for running instances. A resting stop never survives a stop, unload or handover: `stop_strategy` (`:290-299`), `unload_strategy` (`:305-328`) and engine `stop()` (`:121-140`) cancel it, and `take_over` (`:143-180`) restores none and cancels any stored order that is still pending. The strategy re-places on its next bar.
- Manual action: `manual_action: "close" | "cancel" | None` on the subscription document, applied by the reconcile tick (`engine/live/strategy_reconcile_app_service.py:77-111`) and cleared with a filter on the same value (D1, D6).
- Snapshot: the strategy sets `snapshot = {"readings": [...], "decision": {...}}`; the engine keeps a ring of 20 and writes it as one JSON value to Redis key `strategy:snapshot:{subscription_id}` (TTL 7 days) through `Cache.set` (`core/infra/persistence/redis.py:66-85`). No per-subscription Redis key exists today.
- Traps: the risk check rejects every non-LONG/SHORT direction (`engine/execution/risk_check.py:25-26`); a SELL with no live paper position opens a SHORT (`paper_broker_adapter.py:329-362`); a paper takeover drops rows with no SL and no TP (`strategy_app_service.py:157-165`); `TradeClosedEvent` has no reason field (`core/domain/position/events.py:42-58`), the reason travels on the broker order event (`paper_broker_adapter.py:564-569`).
- Exness: the client fences only ops in `_ORDER_OPS` (`core/infra/exness/exness_client.py:46`, check at `:231-232`); today the only order op is `openPosition` (`:44`). <!-- Red team 2026-11-01: #7 (D7) --> D7: `placePendingOrder` joins the fence; `closePosition` and `cancelPendingOrder` stay outside it, because they only reduce exposure. The planner read `https://www.exness-api.com/exness_api.yaml` on 2026-11-01: operationIds `placePendingOrder` (POST `/v1/trading/accounts/{account_id}/orders`, types `limit` and `stop`), `cancelPendingOrder` (DELETE `.../orders/{order_id}`), `closePosition` (DELETE `.../positions/{position_id}`), and the sentence "deal-to-order relation is exposed through `deal.order_id`, when applicable". Task 02.5 re-reads it; the executor's reading is the record.
- Web: `npx tsc -b` has exactly 2 known errors on this HEAD, both in `web/src/components/monitor/job-status-palette.ts:3,13` (Phase 04 fixes them). The spike tree branches before that fix.
- Stop rule (C11, synthesis Task 2.5): a `no-go` on S2 or S3 (Mongo context path) or S5 or S6 (paper EXIT) is an [ASK]. The advice also says stop and ask when the Exness pending-order path fails (`plans/reports/advise-261101-0847-stf-to-mtf-migration.md:154`), so S10 is `no-go` when any of the three operations is absent from the spec; a missing fill-link sentence alone stays `go` and becomes negative knowledge for Phase 10 (plan.md Unresolved 1).

## Entry gate

Run from `D:/w/_me/algotrading/pocketquant`:

1. `git fetch -q origin && echo "dirty=$(git status --porcelain -- src web deploy tests scripts docs .github | wc -l | tr -d ' ') synced=$(test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo yes || echo no)"` prints `dirty=0 synced=yes`.
2. `tail -1 plans/261101-0843-stf-to-mtf-foundation/reports/phase-01-spike-a-data-path.md` prints `Result: PASS`.
3. `git -C ../pocketquant-spike rev-parse --abbrev-ref HEAD` prints `spike/mtf`, and `grep -c -E "^\| S[1-4] " plans/261101-0843-stf-to-mtf-foundation/reports/spike-go-no-go.md` prints `4`.
4. `docker ps > /dev/null 2>&1 && echo docker-ok` prints `docker-ok`.

On a resume of this phase after Task 02.7, line 3 may fail because the worktree is gone; then run only Task 02.7's Verify. On any other miss, end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261101-0843-stf-to-mtf-foundation --from 02 after <UTC time>
```

## Files

- Modify (develop tree, plans only): `plans/261101-0843-stf-to-mtf-foundation/reports/spike-go-no-go.md`; create `plans/261101-0843-stf-to-mtf-foundation/reports/phase-02-spike-b-money-path-and-ui.md`.
- Modify (spike tree only, never committed): any file under `../pocketquant-spike/src` and `../pocketquant-spike/web/src`; new tests under `../pocketquant-spike/tests/spike_test/`.
- Create (scratch, ignored): `.cache/exness_api.yaml`.
- Delete: the worktree `../pocketquant-spike` and the local branch `spike/mtf`.

## Tasks

### Task 02.1 — S5 and S6 paper EXIT, live and backtest

**Goal:** an EXIT signal closes the open paper position in the live engine and in a backtest sandbox.

**Target files and symbols (spike tree):** `Direction.EXIT` (`core/domain/strategy/enums.py:4-8`), `RiskCheckHandler.validate`, `IBrokerPort.close_position` (`core/domain/brokers/broker_port.py`), `PaperBrokerAdapter.close_position`, `StrategyAppService._process_signal`, `build_backtest_sandbox`; new `tests/spike_test/test_spike_exit.py`.

**Steps:**
1. Tests first. A probe returns LONG with SL and TP on bar 1, nothing on bar 2, `Direction.EXIT` on bar 3.
   - `test_an_exit_signal_closes_the_paper_position`: live engine with started `PositionAppService`; after bar 3 the tracker holds no open position, exactly one `TradeClosedEvent` was published, and the broker's exit order event carries reason `strategy_exit`.
   - `test_an_exit_signal_closes_the_position_in_a_backtest`: `BacktestExecutionService.run` over the same bars; the run finishes with `total_trades == 1`.
   Run them; expected red (`Unsupported signal direction: exit`).
2. Rough change: risk check passes EXIT only with an open position; `close_position` on the port; paper implementation calls `_fire_synthetic_exit(pos, current_price, opposite_side, "strategy_exit")` under `_lock`; `_process_signal` routes EXIT to cancel-pending-then-close; the sandbox calls `await position_app_service.start()`.

**Success criteria:** both tests pass.

**Verify:** `cd ../pocketquant-spike && uv run python -m pytest tests/spike_test/test_spike_exit.py -q 2>&1 | tail -1` contains `2 passed` (or rows S5 and S6 read `no-go` per Context).

### Task 02.2 — S7 resting stop, filled by the engine before strategies
<!-- Red team 2026-11-01: #1, #10 -->

**Goal:** a stop entry rests in the paper broker; the engine fills it on a later bar's touch before any strategy decides, so a stop re-placed every bar still fills; a new signal cancels the old stop; no resting stop survives a stop, an unload, an engine stop or a takeover.

**Target files and symbols (spike tree):** `Signal` (`core/domain/strategy/value_objects.py:9-23`, add `entry_type`), `StrategyAppService._on_bar_completed`, `_create_order` (`:633-651`), `_get_or_create_broker` (`:676-677`), `stop_strategy`, `unload_strategy`, `stop`, `take_over`, `OrderAppService.on_order_update` (`:129-165`), `PaperBrokerAdapter.submit_order`, new `fill_resting_stops`, `cancel_order`, `restore`; new `tests/spike_test/test_spike_stop.py`.

**Steps:**
1. Tests first, spread 0:
   - `test_a_stop_entry_rests_then_fills_on_the_next_touch`: a LONG `entry_type="stop"` at 101 on a bar with high 100.5; the order is `submitted`; the placing bar never fills it; the next bar (open 100.8, high 101.2) fills it at `max(open, stop) = 101`; exactly one `OrderFilledEvent`.
   - `test_a_gap_fills_the_stop_at_the_open`: next bar opens 102; fill at 102.
   - `test_a_new_signal_cancels_the_resting_stop`: a second stop signal at 101.5 leaves the first order `cancelled` and one resting order.
   - `test_a_stop_replaced_every_bar_still_fills_on_the_bar_that_touches_it`: the probe sends a LONG stop on every bar, at 101.0, then 101.1, then 101.2. Bar 2 has high 100.9. Bar 3 opens 100.95 with high 101.15, so it touches the bar-2 stop at 101.1, which fills at 101.1 before the probe decides on bar 3. Exactly one `OrderFilledEvent`; the bar-3 signal is rejected because a position is open; no resting order remains.
   - `test_stopping_unloading_or_stopping_the_engine_cancels_the_resting_stop`, parametrized over `stop_strategy`, `unload_strategy` and engine `stop(5)`: the stored order is `cancelled`, the broker holds no resting order, and a later touching bar fills nothing.
   - `test_a_takeover_restores_no_resting_stop`: store a `submitted` stop order for a running subscription in the order repository, as a previous trader would leave it; after `take_over()` that order is `cancelled` and the paper broker holds no resting order; a later bar that touches the price fills nothing; the probe's next signal places a new stop.
   - `test_no_stop_fills_without_the_lease`: with `trading_until = None`, a touching bar fills nothing and the order stays resting.
   - `test_an_immediate_market_fill_publishes_one_fill`: a market LONG with `on_order_update` subscribed publishes exactly one `OrderFilledEvent`.
   Run them; expected red.
2. Rough change: `STOP_MARKET` order with `stop_price`. The paper broker keeps resting orders and exposes `fill_resting_stops(event)` (skip an order with `placed_at >= event.occurred_at`): fill BUY when `high + spread >= stop` at `max(open + spread, stop)`, SELL when `low <= stop` at `min(open, stop)`; fills go out through `_notify_callbacks`. `StrategyAppService._on_bar_completed` first calls `fill_resting_stops(event)` on each distinct connected paper broker, only when `trading_until` is set and in the future, and only for orders of running instances. `stop_strategy` (outside its `is_running` check), `unload_strategy` and engine `stop()` cancel the subscription's resting stop. `take_over` cancels every stored pending order and restores none into the broker. `on_order_update` is subscribed for every broker and returns early on `OrderStatus.PENDING`. `_process_signal` cancels the subscription's resting stop before placing.

**Success criteria:** eight test functions pass (ten cases: the stop, unload and engine-stop test has three).

**Verify:** `cd ../pocketquant-spike && uv run python -m pytest tests/spike_test/test_spike_stop.py -q 2>&1 | tail -1` contains `10 passed` (or row S7 reads `no-go` per Context).

### Task 02.3 — S8 manual action channel

**Goal:** a `manual_action` written by the api runs on the next reconcile tick and is cleared.

**Target files and symbols (spike tree):** `Subscription`, `SubscriptionRepository` (set and clear), `StrategyReconcileAppService._reconcile`, `StrategyAppService` (a `manual_action(sid, action)` entry); new `tests/spike_test/test_spike_manual_action.py`.

**Steps:**
1. Tests first on the test Mongo: a running paper subscription with an open LONG; write `manual_action="close"` on its document; one `_reconcile()` closes the position (reason `manual_close`) and the stored `manual_action` is `None`. A second test with `"cancel"` cancels a resting stop. Run; expected red.
2. Rough change: a reconcile step that reads `manual_action`, calls the engine, then clears with `{"_id": sid, "manual_action": action}`.

**Success criteria:** both tests pass.

**Verify:** `cd ../pocketquant-spike && uv run python -m pytest tests/spike_test/test_spike_manual_action.py -q 2>&1 | tail -1` contains `2 passed` (or row S8 reads `no-go` per Context).

### Task 02.4 — S9 snapshot to the UI

**Goal:** the strategy's snapshot reaches Redis, the api serves it, and the web shows it raw.

**Target files and symbols (spike tree):** `IStrategyService` (`core/domain/strategy/strategy_service_interface.py:16`), `StrategyAppService._on_bar_completed`, `app/routes/strategy.py` (new `GET /subscriptions/{sub_id}/snapshot`), `web/src/components/strategies/strategy-config-card.tsx`; new `tests/spike_test/test_spike_snapshot.py`.

**Steps:**
1. Test first: `test_the_snapshot_ring_is_served_after_two_live_bars`: an engine with a real `Cache` (redis container) runs two live bars of a probe that sets `snapshot`; `GET /api/v1/subscriptions/{id}/snapshot` through `app_client` returns 2 entries with different `bar_start`, each with `readings` and `decision`. Run; expected red (`404`).
2. Rough change: ring of 20 per subscription, `Cache.set("strategy:snapshot:{sid}", ring, ttl=7*86400)` for live bars only; the route injects `Cache` and returns the value; the web card polls it every 5 s and renders `<pre>{JSON.stringify(snapshot, null, 2)}</pre>`.
3. `cd ../pocketquant-spike/web && npm ci`.

**Success criteria:** the test passes; the web type check shows only the 2 known errors and the bundle builds.

**Verify:** `cd ../pocketquant-spike && uv run python -m pytest tests/spike_test/test_spike_snapshot.py -q 2>&1 | tail -1 && cd web && npx tsc -b 2>&1 | grep "error TS" | sed 's/(.*//' | sort | uniq -c && npx vite build > /dev/null 2>&1; echo build=$?` prints a line containing `1 passed`, then `2 src/components/monitor/job-status-palette.ts`, then `build=0`.

### Task 02.5 — S10 Exness spec and fence

**Goal:** record the venue paths and prove that the live flag fences pending placement but not close or cancel (D7). <!-- Red team 2026-11-01: #7 (D7) -->

**Target files and symbols:** `.cache/exness_api.yaml`; spike tree `_ENDPOINTS`, `_ORDER_OPS` (`core/infra/exness/exness_client.py:28-46`), the fence check in `ExnessClient.call` (`:231-232`); new `tests/spike_test/test_spike_exness_fence.py`.

**Steps:**
1. `curl -sSfL -m 60 https://www.exness-api.com/exness_api.yaml -o .cache/exness_api.yaml` (data only; grep it, never execute it).
2. `grep -n -E "operationId: (closePosition|placePendingOrder|cancelPendingOrder)|deal-to-order|trading_disabled|close_only|MARKET_SESSION_CLOSED|MARKET_NO_QUOTES|^  /v1/trading/accounts/\{account_id\}/(orders|positions)" .cache/exness_api.yaml`; record each hit with its line, the HTTP method above it, whether `stop` is listed as an order type, the `trade_mode` that makes close and cancel unavailable, and the fill-link sentence (or `absent`) under `## Exness spec` in `spike-go-no-go.md`.
3. Tests first, using the `_Exness` fake and `_client` helper pattern of `tests/core_test/infra/exness/test_exness_client.py:71-124,273-285`, each with `exness_live_trading=False`:
   - `test_placing_a_pending_order_needs_the_live_flag`: `ExnessApiError` code `LIVE_TRADING_DISABLED`, and `exness.requests == []`.
   - `test_closing_a_position_is_sent_while_the_live_flag_is_off`: `exness.other()` holds one `DELETE` to `/v1/trading/accounts/<account_id>/positions/<position_id>`.
   - `test_cancelling_a_pending_order_is_sent_while_the_live_flag_is_off`: `exness.other()` holds one `DELETE` to `/v1/trading/accounts/<account_id>/orders/<order_id>`.
   Run; expected red (`KeyError`, the ops are not in `_ENDPOINTS`).
4. Rough change: add the three ops to `_ENDPOINTS`; add only `placePendingOrder` to `_ORDER_OPS`.

**Success criteria:** the spec section names all three ops or marks one `absent`; three tests pass.

**Verify:** `echo "spec=$(grep -c -E "closePosition|placePendingOrder|cancelPendingOrder" plans/261101-0843-stf-to-mtf-foundation/reports/spike-go-no-go.md) tests=$(cd ../pocketquant-spike && uv run python -m pytest tests/spike_test/test_spike_exness_fence.py -q 2>&1 | tail -1)"` prints `spec=<n>` with `n >= 3` and `tests=` followed by a line containing `3 passed`.

### Task 02.6 — Complete the table and decide

**Goal:** every piece has a recorded decision, and a no-go on a stop-rule piece reaches the owner.

**Target files and symbols:** `reports/spike-go-no-go.md`.

**Steps:**
1. Add rows `| S5 paper EXIT live |`, `| S6 paper EXIT backtest |`, `| S7 resting stop |`, `| S8 manual action |`, `| S9 snapshot to UI |`, `| S10 Exness spec and fence |` with evidence (test names, asserted values, Verify outputs). No freshness line: D9 drops the column. <!-- Red team 2026-11-01: #15 --> Extend `## Traps found` and `## Kept vs rewritten`.
2. If S2, S3, S5, S6 or S10 is `no-go`: [ASK] in Vietnamese. Intent: "The spike shows no-go on <rows>: <one-line evidence each>. Recommended: stop and rethink these pieces before any build phase, because C11 says the full build only hardens what the spike proved." On an explicit owner yes to proceed with a named change, change the row to `owner-go` and quote the answer under `## Owner answers`; on anything else end with the `NOT_YET` block (`NOT_YET: spike no-go <rows>`), keeping the worktree.
3. Any other `no-go` row names in `carried to phase` the phase that owns the fix.

**Success criteria:** ten rows; S2, S3, S5, S6, S10 each read `go` or `owner-go`.

**Verify:** `f=plans/261101-0843-stf-to-mtf-foundation/reports/spike-go-no-go.md; echo "rows=$(grep -c -E "^\| S([1-9]|10) " $f) stop_rule_go=$(grep -c -E "^\| S(2|3|5|6|10) [^|]*\| (go|owner-go) \|" $f)"` prints `rows=10 stop_rule_go=5`.

### Task 02.7 — Remove the spike and commit the reports

**Goal:** no spike code survives; the evidence is on origin.

**Target files and symbols:** the worktree, branch `spike/mtf`, `plans/261101-0843-stf-to-mtf-foundation/reports/`.

**Steps:**
1. `git worktree remove --force ../pocketquant-spike && git branch -D spike/mtf`.
2. Write the phase report (see Report).
3. `git add plans/261101-0843-stf-to-mtf-foundation/reports && git commit -m "docs(plans): record the money-path spike and the go/no-go table"`; push with the Ops recipe.

**Success criteria:** worktree and branch are gone; the tree outside `plans/` is clean; origin has the commit.

**Verify:** `echo "wt=$(git worktree list | grep -c pocketquant-spike) br=$(git branch --list spike/mtf | wc -l | tr -d ' ') dirty=$(git status --porcelain -- src web tests | wc -l | tr -d ' ') synced=$(test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo yes || echo no)"` prints `wt=0 br=0 dirty=0 synced=yes`.

## Rollback

Develop holds only report commits; `git revert <sha>` and push. The spike tree is already deleted; nothing reached prod. Exness was never called (the spec is a public file).

## Report

`reports/phase-02-spike-b-money-path-and-ui.md`: Verify outputs of Tasks 02.1-02.5 verbatim; the final go/no-go table copied from `spike-go-no-go.md`; any [ASK] text and the owner's answer; traps; the commit sha. Last line `Result: PASS`.

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
