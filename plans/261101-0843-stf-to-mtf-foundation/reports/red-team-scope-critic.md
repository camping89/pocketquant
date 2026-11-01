# Red team: scope critic and contract verifier

Plan: `plans/261101-0843-stf-to-mtf-foundation` (plan.md + 17 phases). Repo `develop` @ `e4a998b8`. All `path:line` citations below were read on this HEAD on 2026-11-01. "Fact" = grep- or read-verified; "Inference" = my judgement.

## Finding 1: Phase 11 and Phase 13 disagree on the response shapes, and Phase 11 departs from owner contract C7
- **Severity:** High
- **Location:** Phase 11 Task 11.1 step 6 and Task 11.3 step 4; Phase 13 Task 13.1 step 2, Task 13.2 step 1, Task 13.4 step 2
- **Flaw:** C7 fixes the snapshot field as `pending{side, price} | null`. Phase 11 writes `pending = {side, stop_price, sl_price, tp_price}` (phase-11:77) and tests `pending.stop_price` (phase-11:68). Phase 13 types `pending: { side: string; price: number }` (phase-13:63), and its unit test feeds `pendingText({ side: 'buy', price: 71250 })` (phase-13:80). Phase 11's `/orders` rows are `id, side, order_type, status, quantity, stop_price, sl_price, tp_price, filled_price, created_at` (phase-11:127). Phase 13 needs `price` and `updated_at` (phase-13:63), and `timeline` sorts orders by `updated_at` (phase-13:84). Phase 13 Task 13.1 says "the code wins", but the Task 13.2 tests are still written against the fabricated keys. Those tests pass on fake data, and the real UI then renders `BUY STOP @ undefined`. Two more duplicate sources: the row reads pending from `sub.snapshot.pending` while the drawer reads it from the orders list (phase-13:118), and the drawer calls `useOpenPosition(sub.id)` even though Phase 11 already adds `position` (with `unrealized_pnl`) to every list row.
- **Failure scenario:** After Phase 13, vitest and `tsc -b` are green. On prod (Phase 16/17) the row shows no stop price and the timeline order is random, because the sort key is undefined. A manual cancel clears the drawer (orders, polled every 5 s) while the row still shows the pending stop until the next entry bar rewrites the snapshot. On a 4h entry interval that can be hours.
- **Evidence:** fact: `OrderAggregate.to_mongo` already stores `price` and `updated_at` (`src/pocketquant/core/domain/order/entities.py:180-188`), so the gap is only in Phase 11's row mapping. Fact: `GET /subscriptions/{sub_id}/positions` already exists (`src/pocketquant/app/routes/strategy.py:88`) and the web already uses `useOpenPosition` (`web/src/components/strategies/strategies-page-layout.tsx:62`).
- **Suggested fix:** Use C7's key: `pending = {side, price}` (plus `sl_price` only if a reader needs it), and change Phase 11's test to `pending.price`. Add `price` and `updated_at` to the Phase 11 `/orders` row. Take the drawer's pending and position from one source each: either the row (`snapshot.pending`, `position`) or the dedicated endpoints, not both.

## Finding 2: Callers missing from file lists turn three Verify steps red
- **Severity:** High
- **Location:** Phase 06 Task 06.1 and 06.3; Phase 08 Files and Task 08.1; Phase 09 Task 09.4 step 7
- **Flaw:** Each of these phases changes a contract but does not list every consumer. The executor then hits a red Verify, and the Failure Protocol sends it to `kongming`.
  - Phase 06 Task 06.1: `from_mongo` reads `doc["intervals"]` with no fallback. The test `test_from_mongo_legacy_doc_without_keys_defaults_stopped` builds a raw doc with only `"interval"` (`tests/core_test/unit/domain/subscription/test_subscription_desired_actual_state.py:42-52`), so it raises KeyError. Task 06.1's Verify runs `tests/core_test/unit/domain` before Task 06.3 step 6, which is the step that greps raw docs. Task 06.1 step 1 never names this test.
  - Phase 06 Task 06.3: a second hand-built `StrategyCommandService(...)` (`tests/engine_test/test_strategy_service.py:158-162`) does not go through `_cmd_svc`. It needs the new `position_repository` and `order_repository` arguments. Its `add_symbol("hitnrun2", "XAUUSD:EXNESS", "5m", broker=...)` calls (`:166,170`) also miss the new positional `parameters`.
  - Phase 08: 5 `BacktestConfig(interval=...)` keyword sites in 4 files are not in the Files list. The Files greps (`"interval": ?"` and `NoStoredBars|Continuous24x7CalendarFactory`) do not match them: `tests/backtest_test/engine/test_backtest_app_service_persistence.py:117,213`, `test_paper_broker_signal_bar.py:91`, `test_report_annualization_source.py:25`, `test_result_collector_mark_to_market.py:51`. Also, the phase claims 19 stub importers on HEAD; `git grep -l` prints 18.
  - Phase 09 step 7 drops the `fills_async` gate. That breaks `test_paper_broker_is_not_subscribed_to_order_updates` (`tests/engine_test/test_async_broker_fill_wiring.py:167-179`, which asserts `len(broker._order_callbacks) == 0`) and makes the file header (`:1-2`) false. Phase 09 lists this file only to add a `close_position` stub to the fake (phase-09:30,54).
- **Failure scenario:** The Verify steps of Tasks 06.1, 06.3, 08.1 and 09.4 fail on tests the phase never mentioned. A Sonnet-class worker stops, spawns `kongming`, and may "fix" the test by deleting it.
- **Evidence:** the line references above. `git grep -n -E "BacktestConfig\(" -- tests` lists those 5 sites plus 3 in STF files that Phase 05 deletes.
- **Suggested fix:** In Task 06.1 step 1, say to delete or rewrite the legacy-doc test (no fallback is the design). Add `test_strategy_service.py:158-170` to Task 06.3 step 1. Add the 4 Phase 08 files to its Files list and widen its grep to `interval=`. In Phase 09 step 7, invert `test_paper_broker_is_not_subscribed_to_order_updates` into "paper is subscribed exactly once" and rewrite the `:1-2` header.

## Finding 3: Spike B proves the stop placement the plan rejected
- **Severity:** High
- **Location:** Phase 02 Context (phase-02:19) and Task 02.2 step 2; plan.md Design verdict "Resting stop trigger order"; Phase 09 Open issue 1
- **Flaw:** plan.md says the engine must call `PaperBrokerAdapter.fill_resting_stops(event)` before the strategies run, "otherwise a stop re-placed every bar would be cancelled before it could fill". Phase 02 Task 02.2 builds and proves the opposite: "the paper broker keeps resting orders and checks them in `_on_bar_completed`". None of its four tests re-places the stop on the next bar, which is the exact failure mode. Phase 02 Context also still quotes `close_position(subscription_id, symbol, *, deadline)` without `reason`, while plan.md has `reason`.
- **Failure scenario:** Row S7 records `go` for a design that Phase 09 replaces. Acceptance A1 ("go/no-go per piece before the full build") is then met on paper only. Whether a re-placed stop ever fills (the Triple Screen `stop` setting, D4) is first tested in Phase 09, after the D-1 deploy and four build phases.
- **Evidence:** fact: strategies subscribe to `BarCompletedEvent` before the paper broker (cited at phase-09:14). Fact: the engine already imports `PaperBrokerAdapter` and filters with `isinstance` (`src/pocketquant/engine/strategy/strategy_app_service.py:28,149,315`), so the plan.md design is cheap to spike.
- **Suggested fix:** Change Task 02.2 step 2 to the plan.md mechanism (the engine calls `fill_resting_stops` at the top of `_on_bar_completed`). Add Phase 09's `test_a_stop_replaced_every_bar_still_fills_on_the_bar_that_touches_it` as the fifth spike test. Add `reason` to the Phase 02 Context signature.

## Finding 4: The web gets a second interval table and a copy of the backend validation rule
- **Severity:** Medium
- **Location:** Phase 12 Task 12.1 (`web/src/lib/intervals.ts`: `INTERVAL_SECONDS`, `intervalsError`)
- **Flaw:** `web/src/lib/datetime.ts:65-70` already exports `INTERVAL_MS` for the same 7 intervals. Phase 12 adds `INTERVAL_SECONDS` beside it. Its success criterion, "no other module defines an interval seconds map in `web/src/lib`" (phase-12:67), is worded so that the existing milliseconds map does not count. `intervalsError` also copies the backend `check_strategy_inputs` rule: empty, unknown, ascending, multiple. The backend already answers with a 422 and a message, and Phase 13 shows every server error as `CODE: message`. That makes three interval tables (`src/pocketquant/core/common/constants.py:42-50`, `datetime.ts`, `intervals.ts`) and two copies of the rule, which must change together. This is the "interval rules mirrored in web and Python" pattern.
- **Failure scenario:** Someone adds or changes an interval, or the multiple rule, in Python. The form keeps blocking or allowing it under the old rule, and no test notices the drift.
- **Evidence:** the files above. `ACTIVE_INTERVALS` (`web/src/constants/active-intervals.ts:3`) already carries a "Keep in sync with backend" comment, so a manual sync exists today.
- **Suggested fix:** Derive the order from `INTERVAL_MS` (`sortIntervals` needs only that). Keep at most a sort-and-dedupe in the chip control, and show the backend 422 message for the rest. If the owner wants the pre-submit message, reuse `INTERVAL_MS` and drop the new map.

## Finding 5: Phase 15 migrates 21 legacy backtest runs that nothing reads and Phase 17 deletes
- **Severity:** Medium
- **Location:** Phase 15 Task 15.4 (phase-15:137); plan.md Design verdict "Prod migration"
- **Flaw:** The subscription migration is needed, because Phase 06 `from_mongo` has no fallback. The backtest-run half is not:
  - Phase 08 step 7 reads `data.get("intervals", [])`.
  - Phase 12 `configLabel(intervals, fallback, parameters)` falls back to `interval`.
  - `_config_from_dict` reads only fresh request payloads (`src/pocketquant/engine/backtest/backtest_execution_service.py:96-101`, `src/pocketquant/app/routes/backtest.py:57`).
  - Legacy runs keep the top-level `interval`, which the index and the rubric use (`scripts/rubric/data_access.py:100`).
  - Every one of the 21 runs is STF. Phase 17 deletes them by `{"strategy_code": {"$in": STF}}` (phase-17:158).
- **Failure scenario:** An irreversible prod write (C12: no backup) runs inside the release window for zero behaviour change. It adds one more count to assert (`runs=`) and one more thing that can fail the D-2 gate.
- **Evidence:** above. Fact: `BacktestResult.from_mongo` already tolerates legacy shapes ("Ignores legacy keys from pre-migration docs", `src/pocketquant/core/domain/backtest/entities.py:78-96`).
- **Suggested fix:** Drop the `backtest_runs.update_many` line and the `runs=` assertion from Task 15.4 and Task 15.2. Keep the subscriptions update and the index drop.

## Finding 6: Five strategy test doubles and duplicated rubric tests
- **Severity:** Medium
- **Location:** Phase 05 Task 05.1 (`ProbeStrategy`), Phase 07 Task 07.1 (`_Recorder`), Phase 08 Task 08.2 (`_LongThenShort`, phase-08:81), Phase 09 Open issue 4 (`ScriptedStrategy`); Phase 06 Task 06.4 and Phase 14 Task 14.3 (two DoF tests); Phase 14 Task 14.1 (`test_the_registry_holds_only_triple_screen`, phase-14:78)
- **Flaw:**
  - `_LongThenShort` returns a fixed script (LONG, SHORT, then None). That is a `ScriptedStrategy` with `script=[...]`. It exists only because `ScriptedStrategy` arrives one phase later.
  - `ProbeStrategy` and `ScriptedStrategy` overlap. A scripted double with `DEFAULTS = {"min_bars": 0}` covers both, which is the "two test doubles" pattern.
  - Phase 06 adds `test_degrees_of_freedom_count_the_declared_defaults` (probe). Phase 14 adds `test_degrees_of_freedom_match_the_declared_defaults` (triple_screen). Both assert the same `static_audit` line.
  - `test_the_registry_holds_only_triple_screen` pins the registry contents. It breaks on the second strategy and repeats what A2 already checks.
  - Each new engine test file (Phase 07, 09 `test_paper_capabilities.py`, 11 `test_strategy_snapshot.py`, `test_manual_action.py`) copies the `_Factory`/`_Repo` harness. Six copies already exist (`tests/engine_test/test_strategy_warm_up.py:53,61`, `test_paper_position_lifecycle.py:27,38`, `test_strategy_entry_guards.py:46,58`, `test_concurrent_opens.py:102,113`, `test_trader_fence.py:38,49`). Meanwhile the plan creates `tests/strategy_doubles.py` precisely to share doubles.
- **Failure scenario:** The suite grows four more harness copies and two more strategy doubles. Changing the engine constructor (Phase 11 adds `cache`) means editing every copy.
- **Evidence:** the line references above.
- **Suggested fix:** Introduce one `ScriptedStrategy` (with `DEFAULTS` and the `min_bars` rule as its default script) in Phase 05, and drop `ProbeStrategy` and `_LongThenShort`. Put one paper-engine builder in `tests/strategy_doubles.py` and have Phases 07, 09 and 11 import it. Delete Phase 14's duplicate DoF test and the registry-pin test.

## Finding 7: Phase 13's freshness check cannot find what Phases 01 and 02 write
- **Severity:** Medium
- **Location:** Phase 13 Task 13.5 step 1 (phase-13:135); Phase 01 Task 01.3; Phase 02 Task 02.6 (phase-02:140)
- **Flaw:** Phase 01 writes `freshness_moves_5m=yes|no` and Phase 02 writes `freshness_column=build|drop`. Phase 13 greps `last_bar_at` and wants "a verdict cell equal to `go`". No phase writes such a row. The Phase 01 lines copied to `## Measurements` hold `fresh` and `freshness_moves_5m=`, not `last_bar_at` (inference from Task 01.3 steps 3-4).
- **Failure scenario:** Freshness is always `dropped`, even when the spike measured `yes`. Plan.md Unresolved 2 then resolves by accident, not by evidence.
- **Evidence:** plan text above. The mockup marks the column `[assumption]` (`plans/reports/advise-261101-0847-stf-to-mtf-migration-ui-mockup.html:79`). D1-D6 hold no owner decision on it.
- **Suggested fix:** Change Task 13.5 step 1 to `grep -c "^freshness_column=build$" .../spike-go-no-go.md`. Separately, ask the owner whether the column is wanted at all (Question 1).

## Finding 8: Phase "Open issue" blocks contradict the reconciled plan.md and re-decide verdicts with no [ASK]
- **Severity:** Medium
- **Location:** Phase 07 Open issue (phase-07:14-15); Phase 09 Open issues 1-2 (phase-09:14-15); Phase 11 Open issue 2 and Task 11.5 step 2; the Open issues of Phases 12, 13, 14, 16 and 17
- **Flaw:** plan.md already contains the trigger-order verdict, `close_position(..., *, reason, deadline)` and the AGNOSTIC grep (`triple[ _-]?screen|force[ _-]?index|elder`, with the MACD exception). The phase files still say plan.md lacks them:
  - Phase 09: "real gap in the synthesis" and "plan.md gives `close_position(subscription_id, symbol, *, deadline)`".
  - Phases 11-17: "plan.md Conventions require `triple|macd|force_index|elder`".
  - Phase 11: "the plan owner decides on the web pattern before Phase 13".

  Phase 07 also changes two plan.md verdicts: the cache becomes a 3-tuple `(window_start, bars, complete)`, and the warm-up wait gains `and bars`. It ends with "Owner or plan author: confirm or replace", but there is no [ASK] gate and plan.md was not updated.
- **Failure scenario:** A fresh worker reads plan.md ("do not re-decide in a phase") and then a phase that re-decides. It cannot tell which source is authoritative and either stops or picks one at random. Phase 07's change ships without the owner seeing it.
- **Evidence:** plan.md "Design verdicts" (Resting stop trigger order; EXIT) and "Conventions" (Strategy-agnostic UI), against the phase lines above. Fact: the broad grep prints 41 on HEAD and AGNOSTIC prints 0. Only one backend hit exists (`src/pocketquant/engine/strategy/strategy_command_service.py:70`).
- **Suggested fix:** Fold Phase 07's two changes into plan.md "Design verdicts" (or [ASK] them), then delete every Open issue that plan.md already resolves. Phase 11 Task 11.5 step 2 should run AGNOSTIC like the other phases.

## Finding 9: Phase 10 builds venue pending-order tracking beyond C6 on unverified fields, plus a garbled doc step
- **Severity:** Medium
- **Location:** Phase 10 Task 10.4 steps 1 and 3; Task 10.5 step 2 (phase-10:163)
- **Flaw:**
  - C6 asks only that "Exness `DELETE positions/{id}` and `POST orders` type `stop` exist behind the live flag", and C13 keeps live disarmed. Task 10.4 adds a `_parked` map, fill linking by an [UNVERIFIED] field (or by a request-id echo that is also [UNVERIFIED]), blocking on unlinked deals, snapshot unmapped-order blocking, and new `_recover_fill`/`_watch_operation` branches. Two tests cover the blocking alone.
  - R5 and Task 10.5 already state that re-adoption "must exist before live trading is armed", so this tracking will be reworked before it ever runs.
  - Task 10.5 step 2 has a Verify command pasted into the middle of the bullet text: "- An **Verify:** `grep -c ...` prints ... fill is linked to its order by the deal field...". A literal executor will paste that into `docs/system-architecture.md`.
- **Failure scenario:** An 809-line adapter (`src/pocketquant/core/infra/brokers/exness/exness_broker_adapter.py`) grows its most complex branch. That branch is tested only against fakes built from guessed field names, and no venue call ever exercises it during this plan.
- **Evidence:** C6/C13 text in `reports/debate-evidence-packet.md`. `wc -l` on the adapter prints 809. Phase 02 Context (phase-02:24) already records the spec sentence `deal.order_id`.
- **Suggested fix:** Ask Question 2. If the answer is "exist only", keep `closePosition`, `placePendingOrder`, `cancelPendingOrder`, the fence tests and a stop placed through the order lane. Leave fill linking and unmapped detection to the re-adoption work, as negative knowledge. Fix the Task 10.5 step 2 text either way.

## Finding 10: Phases 09, 11 and 13 are each about 22 files and 3-4 capabilities; the manual-close flow spans 5 non-leaf files
- **Severity:** Medium
- **Location:** Phase 09 Files (9 src, 7 test edits, 3 test creates, 2 docs); Phase 11 Files (12 src, 6 test edits, 3 creates, 1 doc); Phase 13 Files (7 creates, 12 edits, 3 deletes)
- **Flaw:**
  - Phase 11 bundles three independent contracts in one commit: snapshot ring, manual action through reconcile, and read endpoints. Phase 09 bundles Signal and risk, the order store, the paper broker, engine wiring and two docs.
  - The CLAUDE.md flow limit ("a flow reads in one file, three at most") is exceeded by the manual close. It goes through `app/routes/strategy.py` → `StrategyCommandService.request_action` → (Mongo) → `StrategyReconcileAppService._reconcile` → `StrategyAppService.manual_action` → `_cancel_stop` → `OrderAppService.cancel` plus `broker.cancel_order`/`close_position`. That is 5 non-leaf files.
  - Inference: the reconcile channel itself is D1, an owner decision, and stands. The split of one cancel across `_cancel_stop` (engine) and `OrderAppService.cancel` plus `broker.cancel_order` adds a hop D1 did not require.
- **Failure scenario:** One fresh worker must hold 20+ files and 8+ new tests in context. A late red test in Task 11.3 forces a re-run of the whole phase, because the CLOSE commit bundles all of it.
- **Evidence:** the plan Files sections. `src/pocketquant/engine/strategy/strategy_app_service.py` is 684 lines today, and Phases 07, 09 and 11 add about 9 methods to it (`closed_before`, `_bar_dict`, `_refresh_context`, `_context_at`, `_decide`, `_cancel_stop`, `_handle_bar`, `_record_snapshot`, `manual_action`). `_context_at` has one caller (`_decide`).
- **Suggested fix:** Split Phase 11 into "snapshot ring" and "manual action + reads". Move Phase 09's docs and order-store tasks into their own commit-sized phase. Have `OrderAppService.cancel` own both the broker cancel and the store update, so `_cancel_stop` disappears. Inline `_context_at` into `_decide`.

## Questions (requested scope; doubts only)

1. Freshness column: the mockup marks it `[assumption]` and no D-decision covers it. Does the owner want it at all, independent of the spike measurement?
2. C6 "Exness pending stop exists behind the live flag": does that include fill linking and unmapped-order blocking, or only the three venue calls behind the fence (re-adoption and linking deferred to the pre-arming work in R5)?
3. Should Phase 12's pre-submit interval message stay, given that the backend 422 message already reaches the user as `INVALID_INTERVALS: <message>`?
