---
phase: 10
title: "Exness close, pending stop and cancel; only exposure ops behind the live flag"
status: pending
priority: P2
effort: 1d
dependencies: [9]
---

# Phase 10: Exness close, pending stop and cancel; only exposure ops behind the live flag

## Open issue

1. Still open (plan.md "Unresolved" 1): the venue field names this phase needs come from `reports/spike-go-no-go.md` "## Exness spec" (Phase 02), not from this file. There are four: the request fields for a pending stop, the id of a placed pending order, the field that links a pending-order fill deal to its order, and whether a close takes a body. Each is [UNVERIFIED] until Task 10.1 records it. If the spec has no link field (`absent` or `not in spec`), a fill is matched only when the event echoes the order's `client_request_id` [UNVERIFIED that the venue echoes it]; any other open deal on that instrument blocks the instrument, and the gap is recorded as negative knowledge.

## Goal

The Exness broker closes a position by id, places and cancels one pending stop per subscription, and links its fill back to the order. `openPosition` and `placePendingOrder` are fenced by the live flag; `closePosition` and `cancelPendingOrder` are not, because they only reduce exposure (D7). Live trading stays disarmed (C13). <!-- Red team 2026-11-01: #7 -->

## Context

- Verdicts (plan.md): EXIT on Exness calls `closePosition` (DELETE by position id), and the fill arrives through the existing close path. The pending stop rests in the broker. A resting stop never outlives its strategy: Phase 09 makes `stop_strategy`, `unload_strategy` and engine `stop()` call `cancel_order`, and the takeover calls `cancel_order` for every stored pending stop, then marks it CANCELLED whatever the broker answers. R4: the fill link is unverified against the venue. R5: a venue pending stop is not re-adopted after a crash. <!-- Red team 2026-11-01: #1 -->
- D7 (plan.md, Exness spec checked 2026-11-01): close and cancel are unavailable only when the instrument `trade_mode` is `trading_disabled`; a close may still fail asynchronously with `MARKET_SESSION_CLOSED` or `MARKET_NO_QUOTES`. <!-- Red team 2026-11-01: #7 -->
- Client (`src/pocketquant/core/infra/exness/exness_client.py`): `_ENDPOINTS` `:28-45`, `_ORDER_OPS = frozenset({"openPosition"})` `:46`, `_PRIORITY_OPS = _ORDER_OPS | {"getOperationStatus"}` `:47`. `_ORDER_OPS` has three uses: the live fence (`:231-232`), no retry on a 429 (`:276`), and, through `_PRIORITY_OPS`, the order pacer (`_pacer_for`, `:330`). `order_request_interval` reads the venue ids `("openPosition", "getOperationStatus")` (`:115`). The limits fixture (`tests/core_test/infra/exness/fixtures/limits.json`) lists `closePosition`, `placePendingOrder` and `cancelPendingOrder` at 4 per 1 s, like `openPosition`, so adding them to that tuple keeps `order_request_interval(LIMITS, 0.6) == 0.3`. <!-- Red team 2026-11-01: #7 -->
- With the flag off, `BrokerFactory.create("exness", ...)` raises (`src/pocketquant/core/infra/brokers/broker_factory.py:60-63`), so no Exness broker exists to send a close or cancel. Removing the client fence for close and cancel changes nothing on prod while live is off.
- Adapter (`src/pocketquant/core/infra/brokers/exness/exness_broker_adapter.py`):
  - The header claims "market orders only" and "close only by venue SL/TP" (`:1-6`).
  - `submit_order` rejects non-market orders (`:209-214`). `_submit_open` (`:216-286`) runs the pause (`:219-237`) and loss-cap (`:249-251`) checks under `_open_lock` only at placement, then registers `_inflight`. <!-- Red team 2026-11-01: #6 -->
  - `_send_tracked` hardcodes `"openPosition"` (`:385-428`) and returns `broker_order_id = operation_id` (`:421-428`), not a venue order id.
  - `_watch_operation` (`:430-452`) calls `_recover_fill` (`:454-466`), which expects an open deal.
  - `_on_snapshot` (`:486-527`). The fixture `snapshot.json` has an `orders` key (an empty list); its per-order fields are [UNVERIFIED].
  - `_on_transaction` (`:547-572`): an inflight success with no open deal does nothing, and an open deal without a known request id is ignored. Close deals go to `_on_broker_close` (`:574-591`), which logs `exness.position_closed_by_broker` (`:591`) for every close, including one the engine sent; the engine's INFO `strategy.position_close_sent` (Phase 09) carries the reason. Live trades carry no reason field.
  - `_close_reason` reads `payload.orders[].order_type` (`:802-805`), and `cancel_order` returns False (`:750-752`).
  - Phase 09 left a temporary `close_position` that logs WARNING `exness.close_unsupported`.
- Tests: `_FakeClient.call` raises `AssertionError` for unknown ops (`tests/core_test/infra/brokers/exness/test_exness_broker_adapter.py:85-105`). `_order` has no `stop_price` (`:184-200`), and the LIMIT case expects "market orders only" (`:227`). `test_exness_open_path.py:15-20` imports `_Harness`, `_deal`, `_holding_p1` and `_order` from there. The client fence test is `tests/core_test/infra/exness/test_exness_client.py:273`; its `_Exness` fake answers `200 {}` to any call (`:71-90`). `tests/app_test/integration/test_exness_live_trading_off.py:1-2` says the client "refuses every order call".
- Docs: `docs/system-architecture.md` "Real money is opt-in" says `ExnessClient` "refuses every order call"; `## Limitations` is near its end. `docs/deployment.md:79` is the go-live line; `:108-120` is the break-glass pause runbook, which says nothing about pending orders. <!-- Red team 2026-11-01: #6 #11 -->
- Live trading stays off on prod; nothing in this phase deploys or arms it.

## Entry gate

Run from `D:/w/_me/algotrading/pocketquant`:
1. `git status --porcelain -- src web deploy tests scripts docs .github | wc -l` prints `0`.
2. `git fetch -q origin && test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo synced` prints `synced`.
3. `tail -1 plans/261101-0843-stf-to-mtf-foundation/reports/phase-09-capabilities-in-paper.md` prints `Result: PASS`.
4. `git grep -n "def close_position" -- src | wc -l` prints `3`.
5. `grep -c "^## Exness spec" plans/261101-0843-stf-to-mtf-foundation/reports/spike-go-no-go.md` prints `1`.

A resumed phase may show its own task files as uncommitted (line 1), and line 2 may fail only when `git rev-list --count HEAD..origin/develop` prints `0` (local is ahead by this phase's own unpushed commits). <!-- Consistency sweep 2026-11-01 --> On a miss, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261101-0843-stf-to-mtf-foundation --from 10 after <UTC time>
```

## Files

- Modify: `src/pocketquant/core/infra/exness/exness_client.py`, `src/pocketquant/core/infra/brokers/exness/exness_broker_adapter.py`, `tests/core_test/infra/exness/test_exness_client.py`, `tests/core_test/infra/brokers/exness/test_exness_broker_adapter.py` (`_FakeClient.call`, `_order`, the `:227` case), `tests/app_test/integration/test_exness_live_trading_off.py` (header only), `docs/system-architecture.md` ("Real money is opt-in", Limitations), `docs/deployment.md` (go-live line, pause runbook). <!-- Red team 2026-11-01: #6 #7 #11 -->
- Create: `tests/core_test/infra/brokers/exness/test_exness_pending_and_close.py`.
- Plans only: `plans/261101-0843-stf-to-mtf-foundation/reports/phase-10-exness-close-pending-cancel.md`.

## Tasks

### Task 10.1 — Read the venue facts from the spike report

**Goal:** the field names the code uses are copied from the recorded spec, never guessed.

**Target files and symbols:** `reports/spike-go-no-go.md` "## Exness spec"; `.cache/exness_api.yaml` (data only, grep it, never execute it); the phase report.

**Steps:**
1. `sed -n '/^## Exness spec/,/^## [^E]/p' plans/261101-0843-stf-to-mtf-foundation/reports/spike-go-no-go.md`.
2. If `.cache/exness_api.yaml` is missing, run `curl -sSfL -m 60 https://www.exness-api.com/exness_api.yaml -o .cache/exness_api.yaml`. Then read the request and response schemas: `grep -n -A40 "operationId: placePendingOrder" .cache/exness_api.yaml` and `grep -n -A25 "operationId: closePosition" .cache/exness_api.yaml`.
3. <!-- Red team 2026-11-01: #11 --> Write these seven lines at the top of the phase report, one key per line:
   - `close_endpoint=<METHOD path>`
   - `close_body=<fields|none>`
   - `pending_endpoint=<METHOD path>`
   - `pending_body=<field names for side, volume, type=stop, trigger price, SL, TP>`
   - `cancel_endpoint=<METHOD path>`
   - `pending_order_id_field=<name>` (where the placement ack or the transaction `payload.orders[]` carries the venue order id)
   - `link_field=<deal field naming the order>`, or `absent` when the report says `absent` or `not in spec`
4. [ASK] if any of the three ops or `pending_order_id_field` is missing from the spec. Intent: "The Exness spec does not name <item>. Should the matching piece be built on guessed names, or recorded as missing?" Recommended: record it as missing. Skip only the dependent task: a missing close skips 10.3, a missing pending op or id field skips 10.4. Keep Exness rejecting that capability, and add the gap as one more Limitations bullet in 10.5. Live stays disarmed, so nothing trades on a guess.

**Success criteria:** the report holds the seven lines, and later tasks use exactly these names.

**Verify:** `grep -c -E "^(close_endpoint|close_body|pending_endpoint|pending_body|cancel_endpoint|pending_order_id_field|link_field)=" plans/261101-0843-stf-to-mtf-foundation/reports/phase-10-exness-close-pending-cancel.md` prints `7`.

### Task 10.2 — Client ops: placement fenced, close and cancel unfenced, all on the order lane

**Goal:** the three venue calls exist and share the order pacer; they are never retried on a rate limit; the live flag refuses `openPosition` and `placePendingOrder` and lets `closePosition` and `cancelPendingOrder` through (D7, A8). <!-- Red team 2026-11-01: #7 -->

**Target files and symbols:** `_ENDPOINTS`, `_ORDER_OPS`, new `_EXPOSURE_OPS`, the fence in `call` (`:231-232`), `order_request_interval` (`exness_client.py:28-47,115,231`); `test_order_calls_are_refused_while_live_trading_is_off` (`test_exness_client.py:273`).

**Steps:**
1. Tests first.
   - Parametrize the fence test as `test_exposure_calls_are_refused_while_live_trading_is_off` over `("openPosition", {})` and `("placePendingOrder", {})`: each raises `LIVE_TRADING_DISABLED` and `exness.requests == []`.
   - `test_close_and_cancel_are_sent_while_live_trading_is_off`, parametrized over `("closePosition", {"position_id": "p1"})` and `("cancelPendingOrder", {"order_id": "o1"})` passed as `path_params`, with `exness_live_trading=False`: the call returns `{}`, and `exness.other()` holds exactly one request whose path ends with `/p1` or `/o1`.
   - `test_close_and_pending_calls_use_the_order_lane`: `_pacer_for` of each new op `is` the `openPosition` pacer.
   - `test_a_rate_limited_close_is_not_retried`: one `429` answer raises `REQUEST_RATE_LIMIT` after one request.
2. Run `uv run python -m pytest tests/core_test/infra/exness/test_exness_client.py -q 2>&1 | tail -1`. Expected red: `failed` (`KeyError` for the new ops).
3. Add the three ops to `_ENDPOINTS` with the methods and paths from `close_endpoint`, `pending_endpoint` and `cancel_endpoint`, and to the `:115` tuple (venue `operationId`s). Set `_ORDER_OPS = frozenset({"openPosition", "placePendingOrder", "closePosition", "cancelPendingOrder"})`: it keeps the order pacer (through `_PRIORITY_OPS`) and the no-retry rule at `:276` for all four. Add `_EXPOSURE_OPS = frozenset({"openPosition", "placePendingOrder"})` and fence with it at `:231`, with the comment "Close and cancel only reduce exposure, so the live flag never blocks them; they still use the order lane and are never retried on a rate limit."
4. Rewrite the header of `tests/app_test/integration/test_exness_live_trading_off.py:1-2` as "# Two independent locks: BrokerFactory refuses the exness broker, and the client refuses / # every call that opens exposure before any network use. The trader flag in the store never opens them."

**Success criteria:** the two fenced cases, the two unfenced cases, the lane test and the rate-limit test pass; `test_order_request_interval_uses_the_order_limits` still passes unchanged.

**Verify:** `uv run python -m pytest tests/core_test/infra/exness tests/app_test/integration/test_exness_live_trading_off.py -q 2>&1 | tail -1` contains `passed` and no `failed`.

### Task 10.3 — Exness `close_position`

**Goal:** EXIT and a manual close send one DELETE for the subscription's held position; the fill comes back through `_on_broker_close`.

**Target files and symbols:** `ExnessBrokerAdapter.close_position` (replaces the temporary body); `_FakeClient.call`.

**Steps:**
1. Tests first in `test_exness_pending_and_close.py`, importing the helpers as `test_exness_open_path.py:15-20` does. Extend `_FakeClient.call`: `closePosition` and `cancelPendingOrder` raise `self.order_error` when set, else return `{}`.
   - `test_close_sends_one_delete_for_the_held_position`: `_holding_p1()`, then `close_position("sub1", SYMBOL, reason="strategy_exit")` is True, and `ops("closePosition")[0]["path_params"] == {"position_id": "p1"}`. The close transaction event from `:497-526` then gives one fill and one trade, and `p1` is gone.
   - `test_close_without_a_position_sends_nothing` returns False and makes no call.
   - `test_a_failed_close_keeps_the_position`: with `order_error = ExnessApiError(429, "REQUEST_RATE_LIMIT", "limited")`, the result is False, `p1` is held and one WARNING `exness.close_failed` is logged. <!-- Red team 2026-11-01: #7 -->
   - `test_a_close_is_sent_while_entries_are_paused` sets `h.pause.paused = True`.
   - `test_a_close_past_its_deadline_is_not_sent`.
2. Run `uv run python -m pytest tests/core_test/infra/brokers/exness/test_exness_pending_and_close.py -q 2>&1 | tail -1`. Expected red: `failed`.
3. Implement:
   - `held = self._held_for(subscription_id)`. Return False when it is None, or when the deadline has passed (WARNING `exness.close_rejected` with `reason="deadline"`).
   - Call `await self._client.call("closePosition", path_params={"position_id": pid}, json_body=<close_body or None>, idempotency_key=generate_id_str(), deadline=deadline)`.
   - `ExnessApiError` logs WARNING `exness.close_failed` (subscription_id, code) and returns False.
   - Success logs INFO `exness.close_sent` (subscription_id, position_id, reason) and returns True. The position is removed only when the close deal arrives.
   - WHY comment: "No pause or loss-cap check: a close only reduces risk. True means the venue took the request; the close can still fail later (D7 codes), and then the position stays held."

**Success criteria:** the five tests pass; `git grep -n "close_unsupported" -- src | wc -l` prints `0`.

**Verify:** `uv run python -m pytest tests/core_test/infra/brokers/exness -q 2>&1 | tail -1` contains `passed` and no `failed`.

### Task 10.4 — Exness pending stop: place, park, fill, cancel, snapshot

**Goal:** a STOP_MARKET is sent as one pending order and parked until its fill deal arrives. It can be cancelled while this process tracks it. A venue order we do not track blocks its instrument.

**Target files and symbols:** `submit_order`, `_submit_open`, `_send_tracked` (new `op` parameter), `_recover_fill`, `_watch_operation`, `_on_transaction`, `_on_snapshot`, `cancel_order`, new `self._parked: dict[str, tuple[OrderAggregate, str]]` (request id to order and venue order id); `_order` (new `stop_price` argument) and the `:227` case.

**Steps:**
1. Tests first (same new file). `_FakeClient.call` treats `placePendingOrder` like `openPosition`.
   - `test_a_stop_order_is_sent_as_one_pending_order`: the body holds the `pending_body` fields with type stop and the trigger price; the result is SUBMITTED; there is no `openPosition` call.
   - `test_a_placed_stop_rests_without_a_fill`: a success event whose `payload.orders` carries `{<pending_order_id_field>: "v1"}` and no deals gives no result, `inflight_count == 0`, and `"v1"` is parked.
   - `test_a_resting_stop_fill_is_delivered_once`: an open deal linked by `link_field == "v1"` (or, when `absent`, by the same `client_request_id`) gives one FILLED result and holds `p1`; replaying the event adds nothing.
   - `test_cancel_sends_one_cancel_for_the_resting_stop`: `cancel_order("op1")` is True and the call carries `path_params == {"order_id": "v1"}`; a second call is False.
   - <!-- Red team 2026-11-01: #1 --> `test_cancel_after_a_restart_sends_nothing`: a fresh adapter with nothing parked returns False from `cancel_order("op1")` and makes no `cancelPendingOrder` call (the Phase 09 takeover then marks the stored order CANCELLED).
   - `test_a_second_stop_is_rejected_while_one_rests`.
   - `test_an_unlinked_open_deal_on_a_resting_instrument_blocks_it` (ERROR `exness.pending_fill_unmapped`).
   - `test_a_venue_order_we_do_not_track_blocks_the_instrument` (snapshot `orders` holds an unknown id; ERROR `exness.pending_order_unmapped`).
   - Change the `:227` expectation to `market and stop orders only`.
2. Run `uv run python -m pytest tests/core_test/infra/brokers/exness -q 2>&1 | tail -1`. Expected red: `failed`.
3. Implement:
   - `submit_order` allows MARKET and STOP_MARKET (message `exness adapter supports market and stop orders only`).
   - In `_submit_open`, any parked order for the subscription rejects with `pending order already resting for subscription`. A stop builds its body from `pending_body`, formatting the trigger price like the SL. `_send_tracked(order, body, deadline, op)` gets `op = "placePendingOrder"` or `"openPosition"`.
   - In `_on_transaction`, inflight branch: a success for a STOP_MARKET with no open deal parks it: `_parked[rid] = (order, <id from payload.orders>)`, then pop `_inflight` and `_acked_at`, and log DEBUG `exness.pending_placed` (a stop that moves each bar would otherwise log at INFO per bar) <!-- Red team 2026-11-01: #14 -->.
   - A fill is an open deal whose `link_field` names a parked venue id (or whose `client_request_id` is a parked rid when `link_field=absent`). It pops the parked entry, re-registers `_Inflight(order, name, now)` and calls `_apply_success`. This check runs before the unknown-request branch.
   - Any other open deal on an instrument with a parked order adds that instrument to `_held_unmapped` and logs ERROR `exness.pending_fill_unmapped`.
   - `_watch_operation` returns when the rid is parked. `_recover_fill` for a STOP_MARKET logs ERROR `exness.pending_ack_missing` and calls `_reconcile_later(rid)` instead of reading deals.
   - `cancel_order(broker_order_id)` finds the parked entry whose `order.broker_order_id` matches. It calls `cancelPendingOrder` with `path_params={"order_id": venue_id}` and `idempotency_key=generate_id_str()`. On success it pops the entry, logs DEBUG `exness.pending_cancelled` and returns True. An `ExnessApiError` logs WARNING `exness.cancel_failed` and returns False; a miss returns False with no call.
   - `_on_snapshot`: each `snapshot.get("orders", [])` entry whose id is not a parked venue id adds its instrument to `unmapped` and logs ERROR `exness.pending_order_unmapped`.
   - Rewrite the header `:1-6`: market and stop orders, a stop loss on every open, the lot and loss caps, the snapshot gate, all checked at placement only. A position closes by venue SL/TP, a stop-out or `close_position`. A pending stop is tracked from the stream only; a venue order it does not track blocks its instrument. A pause or the loss cap does not cancel a resting venue stop. <!-- Red team 2026-11-01: #6 -->

**Success criteria:** the eight new tests and every existing Exness test pass.

**Verify:** `uv run python -m pytest tests/core_test/infra/brokers/exness tests/engine_test -q 2>&1 | tail -1` contains `passed` and no `failed`.

### Task 10.5 — Negative knowledge, the live-flag sentence and the runbook

<!-- Red team 2026-11-01: #6 #7 #11 -->
**Goal:** the limits of the Exness pending stop are written where the next reader looks before arming live: the architecture doc and the go-live and pause steps in the deployment doc. The live-flag sentence matches D7.

**Target files and symbols:** `docs/system-architecture.md` ("Real money is opt-in" bullet, `## Limitations`); `docs/deployment.md` (the go-live line `:79`, the "Stop real-money entries when the site is down" section).

**Steps:**
1. In "Real money is opt-in", replace "and `ExnessClient` refuses every order call" with "and `ExnessClient` refuses every call that opens exposure (`openPosition`, `placePendingOrder`). A close and a pending cancel are never fenced: they only reduce exposure."
2. Add to `## Limitations`, as written:
   - "- An Exness pending stop is tracked only from the events stream. A trader that stops or hands over cancels its pending stops; after a crash the next trader does not re-adopt one, and the snapshot marks its instrument unmapped, which blocks new orders there until the owner cancels the order in the Exness app. Re-adoption must exist before live trading is armed."
   - "- A pause or the daily loss cap does not cancel an Exness pending stop: the venue fills it without asking the trader. Cancel venue pending stops before a pause."
   - "- An accepted Exness close means the venue took the request. It can still fail later with `MARKET_SESSION_CLOSED` or `MARKET_NO_QUOTES`; the position then stays open and the owner retries."
   - When `link_field` is a name: "- An Exness pending-stop fill is linked to its order by the deal field `<link_field>` (from the venue spec)." When `link_field=absent`: "- The Exness spec names no field that links a pending-stop fill to its order. A fill is matched only by its request id; any other open deal on that instrument blocks it."
   - Any [ASK] gap from 10.1 as one more bullet.
3. In `docs/deployment.md`, after "Only an approved go-live sets `EXNESS_LIVE_TRADING=true`." add the bullet "- Before arming, read the Exness pending-stop limits in `docs/system-architecture.md`: after a crash the trader does not re-adopt a venue pending stop, and a pause does not cancel one."
4. In the same file, after "Then close any open position in the Exness app." add "A pause does not cancel Exness pending stops. Cancel them in the Exness app first."

**Success criteria:** both docs stay under 800 lines; the bullets name only symbols that exist; no Verify text is pasted into a doc.

**Verify:** `echo "arch=$(grep -c -F -e 'tracked only from the events stream' -e 'does not cancel an Exness pending stop' -e 'means the venue took the request' -e 'linked to its order by the deal field' -e 'names no field that links' -e 'refuses every call that opens exposure' docs/system-architecture.md) deploy=$(grep -c -F -e 'Before arming, read the Exness pending-stop limits' -e 'A pause does not cancel Exness pending stops' docs/deployment.md) pasted=$(grep -c -F 'Verify:' docs/system-architecture.md docs/deployment.md | awk -F: '{s+=$2} END {print s}')"` prints `arch=5 deploy=2 pasted=0`.

### Task 10.6 — CLOSE

**Goal:** the phase lands on `develop` with every gate green; live trading stays disarmed.

**Target files and symbols:** none new; `pyproject.toml` `[tool.code-metrics]` only if the ratchet alone fails.

**Steps:**
1. GATES: `uv run lint-imports | tail -1` prints `Contracts: 6 kept, 0 broken.`; `uv run python scripts/code_metrics.py --ratchet; echo "exit=$?"` prints `exit=0`; `uv run ruff check src tests scripts; echo "exit=$?"` prints `exit=0`. If only the ratchet fails, raise the ceiling in its own commit `chore(metrics): raise the code metric ceiling` and record the old and new values in the report.
2. FULLSUITE: `uv run python -m pytest tests/ -q > .cache/pytest.txt 2>&1; tail -1 .cache/pytest.txt; grep -E "^(FAILED|ERROR) " .cache/pytest.txt | grep -v -E "test_utc_runtime_guard|test_cron_trigger_timezone" | wc -l`. The tail contains `4 failed` and `4 errors`; the count prints `0`.
3. Commit: `feat(exness): close positions, rest and cancel pending stops`.
4. Push: `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin && test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `pushed`.
5. `sleep 15`, then repeat the Verify command until it prints `completed`.

**Success criteria:** CI on the pushed HEAD concludes `success`.

**Verify:** `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 1 --json headSha,status,conclusion -q '.[0] | "\(.headSha) \(.status) \(.conclusion)"'` prints `<git rev-parse HEAD> completed success`.

## Rollback

Nothing deploys. Live trading is off on prod, so `BrokerFactory` builds no Exness broker and no venue call can have been made, fenced or not. Run `git revert --no-edit <phase-commit>` (plus the metric commit, if any) and push. The revert restores the temporary `close_position` from Phase 09, the single-op fence and both docs.

## Report

`reports/phase-10-exness-close-pending-cancel.md` holds:
- the seven fact lines from 10.1, at the top;
- any [ASK] text and the owner's answer;
- every new test with its pass counts;
- the two fenced cases and the two unfenced cases passing (A8);
- the Task 10.5 Verify line;
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
