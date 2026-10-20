# Red team: scope and complexity critic, with contract verification

Date: 2026-10-20. Reviewer stance: hostile. Every claim below was checked with grep or a file read in `D:/w/_me/algotrading/pocketquant` at `a4ae323`. [V] = verified in source. [I] = inference.

Checked and consistent, so not raised as findings: 17 mutation routes (`app/routes/*.py`, and tracked_symbols is mounted only once now, `main_extensions.py:452-459`); 8 import-linter contracts (`pyproject.toml:89-160`); every log event name the plan greps exists (`exness.broker_connected` `exness_broker_adapter.py:146`, `exness.snapshot_reconciled` `:459`, `exness.order_rejected_async` `:491`, `exness.daily_loss_cap_reached` `:262`, `exness_ws.circuit_breaker_open` `exness_stream.py:115`, `exness_ws.reconnecting` `:119`, `data_lag.state_changed` `sync_jobs.py:745`); Mongo collections and fields `orders.status/created_at/subscription_id`, `positions.is_closed/opened_at/closed_at/sl_price`, and `trades.run_id` = subscription id (`live_trade_collector.py:58-63`); `workflow_dispatch` exists (`cicd.yml:11`); `provider_bars.py` flags (`:57-61`) and the `fetched=` line (`:100`); the dead SPA files have no importer outside the deleted set.

## Finding 1: Report files use two different paths, so the state files can split
- **Severity:** High
- **Location:** Phase 08, Tasks 8.7, 8.8 and 8.10. Phase 09, Tasks 9.9, 9.10 and 9.12. Phase 10, Tasks 10.3, 10.7 and 10.8. Phase 11, Tasks 11.1, 11.3 and 11.12 ("Target files"). Phase 12, entry gate and Tasks 12.1, 12.3, 12.4 and 12.5.
- **Flaw:** The plan sets the working directory to the repo root (`plan.md:30`). The write instructions then say "append to `reports/ship-log.md`", "`reports/round-trip.md` (create … if absent)" and "`reports/live-observation.md` (create … if absent)". But every Verify step greps `plans/261019-1957-exness-go-live/reports/...`. From the repo root, `reports/` resolves to `pq-develop/reports/`, which does not exist [V `ls reports` → no such directory]. A literal executor would create it there. Bare paths: Phase 08 = 6, Phase 09 = 6, Phase 10 = 4, Phase 11 = 3, Phase 12 = 7. Full paths are used 2-5 times per file.
- **Failure scenario:** In Task 8.7 the worker appends `SSE deferred` to `pq-develop/reports/ship-log.md`. The Verify then greps the plan-dir file, prints 0, and the Failure Protocol spawns `kongming` during a prod deploy phase. Worse case, Phase 12: Task 12.1 creates `reports/live-observation.md` at the repo root while the entry gate reads the other file. The "one row per day" and "five clean rows" counts then read an empty file every day, so go-live is never reached, or rows get duplicated. Phase 11 has a full path in its state-record definition (`phase-11:23`) but a bare path in its targets (`phase-11:57,119,271`). An executor that follows the target path would read "no current run" and start a fresh run at 11.2 [I].
- **Evidence:** `plan.md:30`; `phase-08:100,114,115,121,155,159` (bare) vs `phase-08:117,144,161` (full); `phase-11:23` vs `:57,119,271`; `phase-12:14` vs `:32,39,111,122,129`.
- **Suggested fix:** One mechanical edit: replace every bare `reports/` with `plans/261019-1957-exness-go-live/reports/` in phases 08-12. No new text.

## Finding 2: The Phase 11 state machine has paths that loop back, re-create a subscription, or can never finish
- **Severity:** High
- **Location:** Phase 11, "State record" (`phase-11:23-35`), Tasks 11.8, 11.9, 11.10 and 11.11.
- **Flaw:** The file is 299 lines. The next task is chosen by a prose parser ("last present key line … decides the next task", `phase-11:35`) and there are 78 lines of embedded Python in 5 heredocs. Three transitions are wrong:
  1. Task 11.11 step 2 offers "Re-baseline and wait for the next trade (NOT_YET)" (`:262`). The only baseline format is `- baseline:` (Task 11.4). If it is appended again, the last key becomes `baseline`, which maps to 11.5 (`:35`). The next run then re-asks to delete the paper subscription. `DELETE /subscriptions/{id}` returns 204 even when nothing is deleted [V `routes/strategy.py:141-146`, `remove_symbol` returns a count that the route ignores], so the Verify passes. Task 11.6 then tries to create a second `exness` subscription on a triple that is already taken, and the unique index rejects it (`subscription_repository.py:102-106`).
  2. Task 11.9 counts every trade with `run_id == <id>` and no time window (`:211`). After a re-baseline, the old trade satisfies "next trade" at once.
  3. Task 11.10's Verify requires "exactly 1 position … exactly 1 trade" (`:223`), but Task 11.9 resumes "after now + 24 h" (`:212`). hitnrun2 on 1m can close more than one trade in 24 h [I, from the 1m re-signal behaviour at `hitnrun2_strategy_service.py:130-132`]. Two trades make the Verify fail on every later run, so the run can never reach `round_trip: DONE`.
  - Also: Task 11.8 says to "re-run 11.2 if older than 24 h" (`:200`). But 11.2 skips `broker != "paper"` and `key in live` (`:97`), and by then the chosen strategy is `exness`. The re-run prints no margin line for the strategy being resumed.
- **Failure scenario:** A real-money run gets stuck in Failure Protocol, or creates a duplicate-triple subscription, after a deposit or a busy trading day.
- **Evidence:** `phase-11:35,97,200,211,212,223,262`; `src/pocketquant/app/routes/strategy.py:141-146`; `src/pocketquant/engine/strategy/strategy_command_service.py:99-107`.
- **Suggested fix:** Use the first closed trade, not an exact count. In 11.9 and 11.10, select `trades` with `run_id` and `entry_time ≥ resumed_at`, sorted by `exit_time`, limit 1, and run the checks on that one trade. Replace "Re-baseline" with "accept without AC6, or stop" (no new state key). In 11.8, read free margin from the Task 11.4 baseline snippet instead of re-running 11.2. Each fix removes text.

## Finding 3: The "one adapter per venue" promise in Phase 02 breaks after the last `exness` subscription is deleted
- **Severity:** High
- **Location:** Phase 02, Task 2.4. AC3. Phase 11, Task 11.6 Verify and "Rollback".
- **Flaw:** Task 2.4 changes only the pool key. It claims "a venue broker is one account, so one instance and one event stream". But the pool reuses a broker only while a loaded strategy still holds it [V `strategy_app_service.py:467-469`]. `unload_strategy` pops `_brokers` and never disconnects the broker [V `:169-177`]. Delete the last `exness` subscription (Phase 11 "Rollback": "stop and delete its `exness` subscription") and orphan-unload runs (`strategy_reconcile_app_service.py:183-197`). The next `exness` load then builds a second `ExnessBrokerAdapter` while the first stays connected with its trade and order-update callbacks wired (`strategy_app_service.py:470-478`).
- **Failure scenario:** The user returns strategy A to paper and later re-runs Phase 11 for strategy B. Task 11.6's Verify `grep -c exness.broker_connected` prints 2, not 1, and Failure Protocol starts. If it is passed anyway, two adapters consume one account's events [I]: duplicated forwards, or `exness.position_unmapped` from the stale adapter, which is a stop event in Phases 11 and 12. This is exactly the B9 defect the phase says it closes.
- **Evidence:** `src/pocketquant/engine/strategy/strategy_app_service.py:465-478,169-177`; `phase-02` Task 2.4; `phase-11` Rollback; plan.md AC3.
- **Suggested fix:** Inside Task 2.4's existing edit, reuse a pooled non-paper broker without the "still held" check (one condition: `if broker is not None and (broker_type != "paper" or any(...))`). Add one case to Task 2.6 step 5: unload the only `exness` strategy, load another, and assert `create` is called once. No new symbol.

## Finding 4: Hand-written Exness scripts copy adapter logic and drop two of its guards
- **Severity:** High
- **Location:** Phase 11, Tasks 11.2, 11.4 and 11.11. Phase 12, Task 12.2 step 2.
- **Flaw:** About 120 lines of embedded Python build a second `ExnessClient(get_settings())` in a separate `docker exec` process. They re-implement `_deals` paging and `_realized_today` (`PNL = {...}`, `realized -= abs(commission)`). That is a parallel copy of `exness_broker_adapter.py:266-294`, and it leaves out two things the original has:
  - The history-window clamp. `_deals` clamps `since` to `now − deals_window_days()` because "the API rejects a window of exactly history_age_days" [V `exness_broker_adapter.py:280-282`, `exness_client.py:370-372`]. In Task 11.11 `BASE_AT` is the baseline, which can be weeks old ("days of calendar").
  - The rate share. The second process runs at `exness_rate_fraction=1.0`, but the config says the backfill "lowers it so it can run beside the app" [V `config.py:122-124`; backfill default `--rate-fraction 0.5`, `provider_bars.py:60`]. The pacer is per process (`exness_client.py:346`) while limits are cluster-wide. A 429 on an order op is never retried (`exness_client.py:296-298`). "A 429 on an order returns rejected and marks the snapshot stale" (`docs/system-architecture.md:190`).
- **Failure scenario:** Task 12.2 pages deals every day while a live position is open. If its burst pushes the account over the limit just as the strategy sends `closePosition`, the exit is rejected and the position stays on its venue SL [I]. Separately, an old `BASE_AT` gets a rejected `getDealsHistory`, so the AC6 step fails into Failure Protocol.
- **Evidence:** `phase-11:90,142,237-242`; `phase-12:79-94`; the source lines above.
- **Suggested fix:** Run every script as `docker exec -e EXNESS_RATE_FRACTION=0.5 …`, which is the existing knob with no new code. Clamp `from` to `now − (history_age_days − 1)` with `await c.deals_window_days()`, which already exists. The plan text shrinks: Task 12.2 can drop its own `realized_today` loop and keep only `close_deals`. The cap's arithmetic is already pinned by AC6.

## Finding 5: The plan says the shell keeps no variables, then its own Verify steps depend on them
- **Severity:** Medium
- **Location:** Phase 08, Task 8.4 Verify. Phase 09, Task 9.8 Verify. Phase 10, Task 10.1 Verify and Tasks 10.3 step 2, 10.4 Verify and 10.6.
- **Flaw:** `plan.md:30` and the preamble of every ops phase say "The shell keeps no variables between commands". Yet:
  - The Verify lines use `gh run view "$RUN_ID"`, with `RUN_ID` set in a different step's command.
  - Phase 10 runs `ssh -i … "$HOST"` with no `HOST=` in the same command (`phase-10:42,73,108`).
  - The Phase 10 watch/view commands omit the `GH_TOKEN=` prefix that the list command carries (`phase-10:85-87`).
- **Failure scenario:** Right after deploy A, B or C, `gh run view ""` errors, the verdict grep prints 0, and Failure Protocol spawns `kongming` on a deploy that actually succeeded. In Phase 10, the arming phase, `ssh ""` fails Task 10.1 before any fact is gathered.
- **Evidence:** `phase-08:68,70`; `phase-09:113,115`; `phase-10:42,73,85,87,108`; `plan.md:30`.
- **Suggested fix:** Make each Verify one self-contained command: `RUN_ID=$(…); gh run watch "$RUN_ID" --exit-status && gh run view "$RUN_ID" --log | grep …`. Prefix the Phase 10 lines with `HOST=$(head -1 … | tr -d '\r');`.

## Finding 6: Phase 04 says Phase 12 "records" unexpected bars; Phase 12 fails on them
- **Severity:** Medium
- **Location:** Phase 04, Context and Risk. Phase 12, Task 12.3 Verify and Task 12.2 step 3.
- **Flaw:** Phase 04 says "Phases 08 and 12 read them" from the `integrity.issues_found` WARNING (`phase-04:13`). Neither phase reads the WARNING; both call `POST /market-data/integrity/check` (`phase-08` Task 8.5, `phase-12:77`). The route does return the raw dict [V `routes/market_data.py:111-118`], so it works, but the stated contract is false. Phase 04 also rates "a venue bar in a minute the session model marks closed" as likelihood M and says "Phase 12 records it" (`phase-04:76`). Phase 12 instead makes "both `unexpected` `0`" a hard Verify, and any miss goes to Failure Protocol (`phase-12:118`). Phase 12 also adds a DST-reopen check with hard-coded 2026-11-01 windows as a gate (`phase-12:104,118`). The user decided the 11-02 DST check is optional and gates nothing.
- **Failure scenario:** One stray venue bar, which Phase 04 rates as likely, makes every daily row fail and spawn `kongming`. AC11's five clean rows are then never reached, even though Phase 04 classifies the event as information, not a fault.
- **Evidence:** `phase-04:13,76`; `phase-12:77,104,118`; `src/pocketquant/app/routes/market_data.py:111-118`.
- **Suggested fix:** Decide the contract once. Either Phase 12 records `unexpected` in the row and only `close_deals ≠ new_trades` or a stop event fails it, or Phase 04's Risk text says it is a gate. Question for the user, not a cut: should the Phase 12 DST-reopen cell gate go-live, given the 11-02 E2 check was made optional? Fix Phase 04 Context to say "the integrity check route", not "the WARNING".

## Finding 7: Read-only checks the user did not ask for, duplicated across deploy phases
- **Severity:** Medium
- **Location:** Phase 08, Tasks 8.7 and 8.8. Phase 09, Task 9.9 step 3. Phase 10, Task 10.7. Phase 12 row column "E2 latest".
- **Flaw:** The user asked to deploy as soon as possible. The plan adds:
  - Task 8.8, a stop-distance preflight with hard-coded paper subscription ids and fixed limits (`phase-08:129`). Its own text says "it is decided in Phase 11". Phase 11's Task 11.2 recomputes the same thing per candidate with limits derived from live free margin. Nothing reads 8.8's output, and it writes a `## Preflight` section into `round-trip.md`, the file Phase 11's state parser scans.
  - An SSE stream check written three times with deferral bookkeeping (8.7, then 9.9 step 3, then 10.7 "gates nothing").
  - An "E2 latest" column in every daily row, although E2 is optional.
  Each copy is another place for the path bug in Finding 1 to fire.
- **Failure scenario:** A weaker executor spends deploy-day attention on checks that change no decision. The extra `## Preflight` heading in `round-trip.md` is one more thing the Phase 11 "last section" parser must skip [I].
- **Evidence:** `phase-08:98-117,119-144`; `phase-09:117-125`; `phase-10:112-117`; `phase-12:44`; `phase-11:73-115` (Task 11.2 supersedes 8.8).
- **Suggested fix:** Question for the user before cooking: keep 8.8 and 10.7? If not, delete them. Keep one SSE check in 9.9 and record "deferred" there only. These are plan additions, not user-requested scope.

## Finding 8: A line-numbered delete in Phase 02 leaves an empty test function, which breaks the module Phase 05 edits next
- **Severity:** Medium
- **Location:** Phase 02, Task 2.5.
- **Flaw:** The target is "`tests/core_test/infra/brokers/exness/test_exness_broker_factory.py:41`" with "delete all three". Line 41 is the only body line of `def test_exness_is_not_an_available_type() -> None:` at line 40 [V]. Deleting only that line leaves a function with no body, which is a module-level IndentationError. That file's other tests stop collecting too. Phase 05 Task 5.8 item 3 edits the same file and assumes its "refusal and build cases keep their meaning".
- **Failure scenario:** Task 2.5's Verify grep passes (prints nothing), then Task 2.6 or 2.8 pytest errors on collection. Failure Protocol spawns `kongming` for a one-line plan ambiguity.
- **Evidence:** `tests/core_test/infra/brokers/exness/test_exness_broker_factory.py:40-41`; `phase-02:20,72-73`.
- **Suggested fix:** Change the target to "delete the test `test_exness_is_not_an_available_type` (`:40-41`)".

## Unresolved questions
- Finding 6: should `unexpected ≠ 0`, and the DST-reopen cell, fail a Phase 12 row, or only be recorded?
- Finding 7: does the user want Task 8.8 and Task 10.7 kept?
