# Red team: Assumption Destroyer / Scope Auditor

Date: 2026-10-20. Scope: `plan.md` and `phase-01` to `phase-12`. Binding user decisions (pause resets on restart, 0.10 risk, 25 USD cap, one strategy per Phase 11 run, deploy ASAP) are treated as constraints, not findings. Evidence was checked with grep/read in `D:/w/_me/algotrading/pq-develop` and `gh api`. No secret values were read or printed.

## Finding 1: Every `git push origin develop` hits the account that cannot push
- **Severity:** High
- **Location:** Phases 01-07, final "Gates and push" task (01 Task 1.9, 02 Task 2.8, 03 Task 3.4, 04 Task 4.5, 05 Task 5.10, 06 Task 6.12, 07 Task 7.6). Also 08 Task 8.11, 09 Tasks 9.7/9.12, 10 Task 10.8, 11 Task 11.12, 12 Tasks 12.5/12.6. Ops recipe in `plan.md`.
- **Flaw:** The plan uses the `camping89` token URL only for `master` and `pocketquant-config`. It says the 403 is about `master` ("Push `master` (active gh account `vunguyen-ai` gets 403)", `plan.md:39`). Every develop push is a bare `git push origin develop`. Git's github.com credential helper is `gh auth git-credential`, which uses the active gh account (`vunguyen-ai`). That account has no push right on the repo.
- **Failure scenario:** Phase 01 Task 1.9 runs `git push origin develop` and gets 403. The Verify (`git status -sb` shows no `ahead`) fails, so the worker goes to Failure Protocol and spawns `kongming` in the first phase. The same happens in Phase 09 Task 9.7 step 1. That push comes after the user has already moved DNS (Task 9.2), so the cutover stops halfway, with no develop CI run to wait for. The Phase 08 entry gate ("no `ahead`") then fails for good.
- **Evidence:** `gh api repos/camping89/pocketquant --jq .permissions` under the active account returns `"push":false`. `~/.gitconfig` sets `credential.https://github.com.helper = !gh.exe auth git-credential`. `gh auth status` lists `vunguyen-ai` as the active account and `camping89` as inactive. The user memory `pocketquant-vps-access-quirks.md` says "Push to `camping89/pocketquant` needs the `camping89` gh account". That is the whole repo, not only master. Phase files: `phase-01-admin-token-auth.md:115`, `phase-07-cloudflare-tunnel-service.md:105`, `phase-09-tunnel-cutover.md:102`.
- **Suggested fix:** Put one develop-push line in the ops recipe and use it in every phase: `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop`. Check that `git status -sb` shows no `ahead`. Also run `gh run watch` with `GH_TOKEN=$(gh auth token --user camping89)` where a run id is needed.

## Finding 2: Phase 09 tells the executor to delete the `source .env` that the Redis check needs
- **Severity:** High
- **Location:** Phase 09, Task 9.5 step 1; verified after the fact by Task 9.8.
- **Flaw:** Step 1 says: delete the `WEB_PORT_VAL` line "and its `source .env` line if nothing else in 3b uses it". Nothing else in 3b uses it, so a literal executor deletes it. But `11-verify.sh:118` is the only `source .env` before section 5. Section 5 runs `redis-cli -a "${REDIS_PASSWORD:-}"` (`:140`), and prod Redis runs with `--requirepass ${REDIS_PASSWORD}` (`compose.prod.yml:97`). The other `source .env` (`:176`) sits in section 8, which this task deletes.
- **Failure scenario:** Deploy B (Task 9.8) runs. The Redis ping is sent with an empty password, gets NOAUTH and reports "no PONG", so the verdict shows `1 failures`. Task 9.8 Verify (`grep -c ", 0 failures)"` ≥ 1) fails after prod has already dropped the host port and DNS has been cut over. The executor goes to `kongming` on a live cutover, and the verify script is now permanently red for every later deploy, including deploy C.
- **Evidence:** `deploy/vps/11-verify.sh:118` (`source .env`), `:140` (`REDIS_PASSWORD`), `:176` (the only other `source`, inside section 8); `deploy/compose.prod.yml:97,101`; `phase-09-tunnel-cutover.md:70`.
- **Suggested fix:** Replace step 1 with: "Keep `source .env 2>/dev/null || true` at :118; delete only `WEB_PORT_VAL=...` (:119)." Add a pre-push check that runs `bash deploy/vps/11-verify.sh` logic for the Redis ping, or `grep -n "source .env" deploy/vps/11-verify.sh` prints a line number below 140.

## Finding 3: The "zero-money proof" counts any `rejected` order, so it does not prove the pause gate
- **Severity:** High
- **Location:** Phase 11, Task 11.7 (steps 1 and 3), Context "Zero-money proof"; AC7.
- **Flaw:** The proof is `rejected ≥ 1` and `other = 0` on the `orders` collection. But the order document stores no rejection reason: `to_mongo` has no reason field (`order/entities.py:219-236`). Many paths besides the pause also persist `status: "rejected"`:
  - a synchronous Exness API error on `openPosition`, including `TRANSPORT` and `REQUEST_RATE_LIMIT`, where "the request may have reached the venue" (`exness_broker_adapter.py:324-331` returns `_rejected`, `:711-717`; `OrderAppService` saves it, `order_app_service.py:103-112`);
  - "awaiting trading snapshot reconciliation";
  - "daily loss check failed".

  Phase 05 Task 5.4 adds the discriminating log `exness.order_rejected_presubmit reason=entries_paused subscription_id=…`, but Task 11.7 never reads it, and never checks that `exness.order_submitted` is 0.
- **Failure scenario:** During the 8 h `NOT_YET` wait in Task 11.7, the container restarts (host reboot, OOM, `restart: unless-stopped`). The pause clears and reconcile reloads the `exness` subscription as running. After warmup, a signal sends a real `openPosition`. The venue rejects it synchronously (closed session, margin) or the call times out (`TRANSPORT`, possibly opened at the venue), and the order is saved as `rejected`. On the next run, Task 11.1 re-pauses and Task 11.7 counts it as the zero-money proof. Task 11.8 then asks for Resume on a false fact: "the pause gate is proven".
- **Evidence:** `src/pocketquant/core/domain/order/entities.py:219-236`; `src/pocketquant/core/infra/brokers/exness/exness_broker_adapter.py:243-253,318-331,711-717`; `src/pocketquant/engine/execution/order_app_service.py:103-112`; `phase-11-go-live-one-strategy.md:15,187-194`.
- **Suggested fix:** Make the proof from the log. For `<id>` since `created`: `grep "<id>" | grep -c 'exness.order_rejected_presubmit.*entries_paused'` ≥ 1, and `docker logs … | grep -c 'exness.order_submitted'` since `created` = 0 (or its `order_id`s do not map to `<id>`). Also check that StartedAt equals the value recorded in `exness_sub_id`; if it differs, void the proof and restart the wait.

## Finding 4: Phase 12 ignores an in-progress second Phase 11 run and can resume it
- **Severity:** High
- **Location:** Phase 12, Task 12.1 step 3 ("Intended paused"), Task 12.3 Verify, Task 12.6 step 1/3; entry gate. Plan Conventions (runner behaviour).
- **Flaw:** In Task 12.1 step 3, intended-paused comes only from the last `after round trip:` line, `go-live` or `weekend hold`. It skips a current `## Live run` section that has no `resumed_at`, which is the state where Phase 11 paused on purpose (Task 11.4). The Phase 12 entry gate passes as soon as any earlier run is DONE. The plan also infers, without verifying, that a `Status: BLOCKED` worker stops the runner. `SKILL.md:130-136` only defines `succeeded` (dispatch the next phase) and `failed` (stop); how a text `BLOCKED` maps to an outcome is not shown (`plan.md:155` admits this).
- **Failure scenario:** Strategy A is live with `keep on`. The user starts Phase 11 run 2 for strategy B, which pauses entries globally and waits at 11.7. The daily `--from 12` (or the runner, if the 11.7 `NOT_YET` exit counts as succeeded) runs Phase 12. Intended = not paused, actual = paused, so the Task 12.3 Verify fails and goes to `kongming`. If the clean-row count is already at 5, Task 12.6 asks "Declare go-live? (This resumes entries if they are paused.)". A yes resumes strategy B before its zero-money proof and without the Task 11.8 Resume gate.
- **Evidence:** `phase-12-observation-and-go-live.md:43,138-139`; `phase-11-go-live-one-strategy.md:35,128-133`; `~/.claude/skills/eve-cook-plan/SKILL.md:130-136`; `plan.md:155`.
- **Suggested fix:** In Task 12.1, if `round-trip.md` has a current run without `resumed_at`, intended = paused and Task 12.6 must end `NOT_YET: a Phase 11 run is in progress`. Add to the Phase 12 entry gate: "no `## Live run` section lacks `round_trip: DONE`". Tell the user to run Phase 11 with `--to 11`.

## Finding 5: Ad-hoc `ExnessClient`s in Phases 11/12 compete with the live app for the account rate limit
- **Severity:** Medium
- **Location:** Phase 11 Tasks 11.2, 11.4, 11.11; Phase 12 Task 12.2 step 2.
- **Flaw:** Each script runs `ExnessClient(get_settings())` in a second Python process inside the app container. Its pacer is independent and runs at `exness_rate_fraction = 1.0` (prod sets no override). The published limits are account-wide, and order ops get no 429 retry. The codebase already handles this for the backfill (it lowers `exness_rate_fraction` "so it can run beside the app"); the plan scripts do not.
- **Failure scenario:** A Phase 12 daily run pages `getDealsHistory` twice while a live strategy signals and `sync_1m` pulls candles. A live `openPosition` gets 429, becomes `REQUEST_RATE_LIMIT`, and is saved as `rejected`, with `_reconcile_later`. A real entry is lost. If a strategy-initiated close collides instead, the position stays open. With Finding 3, this rejection also counts as a fake pause proof.
- **Evidence:** `src/pocketquant/core/infra/exness/exness_client.py:290-299` (order ops raise on 429, "limits are cluster-wide"), `:339-347` (pacer = interval / `exness_rate_fraction`); `src/pocketquant/core/config.py:122-124`; precedent `scripts/backfill/provider_bars.py:79-81` (`model_copy(update={"exness_rate_fraction": ...})`); `phase-11-go-live-one-strategy.md:90,142,239`; `phase-12-observation-and-go-live.md:79`.
- **Suggested fix:** In every script, build the client with `ExnessClient(get_settings().model_copy(update={"exness_rate_fraction": 0.2}))`. Better: read balance from `GET /api/v1/trading/...` or the adapter state where it exists, so the app's pacer is the only caller.

## Finding 6: Phase 11 state machine breaks on more than one trade and on re-baseline
- **Severity:** Medium
- **Location:** Phase 11, "State record", Task 11.9 step 3, Task 11.10 Verify, Task 11.11 step 2.
- **Flaw:**
  - Task 11.9 waits "now + 24 h, check daily" for a 1m strategy that re-arms after every close. Task 11.10 then demands "exactly 1 position … exactly 1 trade". A late re-run with two or more round trips fails the Verify.
  - Task 11.11 step 2 offers "Re-baseline and wait for the next trade", but the state machine maps the last key line `baseline` to Task 11.5. That task deletes a paper subscription that is already gone (the route returns 204 unconditionally) and then re-creates the `exness` subscription on an occupied triple (unique index, so 409).
- **Failure scenario:** hitnrun2 trades twice in 24 h, so 11.10 Verify fails and goes to `kongming` on a real-money run. Or a deposit lands in the window, the user picks re-baseline, and the next run walks 11.5 then 11.6, which hits a duplicate-key error. The run never reaches `round_trip: DONE`.
- **Evidence:** `phase-11-go-live-one-strategy.md:35,212,223,262`; `src/pocketquant/app/routes/strategy.py:141-147` (DELETE always 204); `src/pocketquant/engine/strategy/strategy_command_service.py:99-107`; `src/pocketquant/core/infra/persistence/repositories/subscription_repository.py:102-106` (unique triple per plan context); `core/domain/strategy/services/hitnrun2_strategy_service.py:96-97,119-128` (re-arms after the opposite fill).
- **Suggested fix:** In 11.10, check the first trade by `entry_time` after `resumed_at` (≥ 1 allowed; assert per-trade single records). Define a new key, `- rebaseline: balance <x> at <ISO>`, that maps to Task 11.9, and state that `baseline` maps to 11.5 only when no `paper_deleted` line exists.

## Finding 7: Entry gates grep the working tree, not what was pushed or released
- **Severity:** Medium
- **Location:** Phase 05 entry gate, Phase 06 entry gate, Phase 08 entry gate and Task 8.2.
- **Flaw:** The gates say "`git log origin/develop` shows the commits of Phases 01 and 02", but the only measurable check is a `grep -c` on local files. Phase 08 checks `git status -sb | head -1` for ahead/behind, which ignores a dirty tree. A `NOT_YET` exit (for example a "no" to the Phase 05 ratchet [ASK]) or a Failure Protocol stop leaves uncommitted edits in place, and those edits satisfy the next gate.
- **Failure scenario:** Phase 05 stops at the ratchet [ASK] with `exness_safeguards.py` written but not committed. Phase 06 passes its gate (`grep "admin/safeguards" …/safeguards.py`) and builds the SPA against an uncommitted API. Phase 08 Task 8.2 tests that dirty tree green, and deploy A ships `origin/develop` without the safeguards code. In prod, Task 8.5 fails only after the master push.
- **Evidence:** `phase-05-safeguards-pause-and-sizing.md:33`; `phase-06-spa-mode-pause-and-hints.md:33`; `phase-08-ship-with-live-off.md:30-31,335-337`.
- **Suggested fix:** Each gate adds `test -z "$(git status --porcelain -- src web deploy tests)"` and runs the grep against `git show origin/develop:<path> | grep -c …` instead of the working file.

## Finding 8: Phase 12 never checks the below-minimum stop condition that `plan.md` mandates
- **Severity:** Medium
- **Location:** Phase 12, Task 12.2 step 1 (event list), Task 12.3 Verify; `plan.md` "Stop and report".
- **Flaw:** `plan.md:120` lists "A `below_min_lot` or `order_quantity_below_broker_minimum` line for a live subscription" as stop-and-report. Phase 11 checks this only up to the proof. Phase 12's daily event loop (9 events plus `stuck`) does not include it, and no column records it. hitnrun2 stops can reach 1% of price (about 41.8 USD/oz), which is above the 25 USD/oz the sizer can fit at 250 USD (`phase-05` Risk). So skipped entries are expected during observation.
- **Failure scenario:** On observation days 2-5, wide-stop signals are silently dropped below the minimum lot (logged at `info`, no order). The five rows still read "clean", so go-live is declared on a strategy that skips some of its own signals. That contradicts AC8 and the plan's stop rule.
- **Evidence:** `plan.md:120`; `phase-12-observation-and-go-live.md:54-55` (event list), `:417` (Verify list); `src/pocketquant/engine/strategy/strategy_app_service.py:405-409`; `core/domain/strategy/services/hitnrun2_strategy_service.py:103-104` (`max(min(prev_lows_sl), close*(1-max_loss_pct))`); `src/pocketquant/core/infra/brokers/exness/exness_broker_adapter.py:175-177`.
- **Suggested fix:** Add `order_quantity_below_broker_minimum` and `below_min_lot`, filtered by live ids, to Task 12.2 step 1 and a `below_min` column. A non-zero value means stop and report.

## Finding 9: The "one adapter per process" claim fails after the last `exness` subscription is removed
- **Severity:** Medium
- **Location:** Phase 02 Task 2.4; AC3; Phase 11 Rollback ("return a strategy to paper") together with a Phase 11 re-run.
- **Flaw:** The pool reuses a broker only while some loaded strategy still holds it (`strategy_app_service.py:466-468`). `unload_strategy` and `stop_strategy` never call `disconnect()` (`:156-174`); only engine `stop()` does (`:96-98`). Phase 02 changes only the pool key.
- **Failure scenario:** Strategy A is returned to paper per the Phase 11 rollback, so its `exness` subscription is deleted and the instance unloaded. Its adapter and WS stay connected. Phase 11 run 2 creates strategy B's `exness` subscription, and a second adapter subscribes to the same account `transactions` stream. Task 11.6 Verify (`grep -c exness.broker_connected` = 1) prints 2 and goes to Failure Protocol. If it is missed, the orphan adapter receives B's fills: `exness.unknown_request_fill` / `position_unmapped` stop events, and possibly duplicate `trades` rows. That is B9 again.
- **Evidence:** `src/pocketquant/engine/strategy/strategy_app_service.py:96-98,156-174,462-480`; `src/pocketquant/core/infra/brokers/exness/exness_broker_adapter.py:133-143` (connect opens the account WS); `phase-02-subscription-broker-selection.md` Task 2.4; `phase-11-go-live-one-strategy.md:173,287`.
- **Suggested fix:** In Task 2.4, reuse a pooled non-paper broker regardless of holders (key `(broker_type, None)`, no `any(...)` check for venue brokers). Or disconnect and evict the pool entry when the last holder unloads. Add a unit case: load, unload, then load `exness` calls `create` once.

## Unresolved questions
- The Orca `worker_done` outcome for a worker that ends with `Status: BLOCKED` is not documented in `SKILL.md`. Findings 4 and 7 assume it may be `succeeded` [inference].
- Phases 08, 09 and 10 select `RUN_ID` immediately after the push or dispatch (only Phase 10 sleeps 15 s). An empty `RUN_ID` for `gh run watch` was not tested.
