# Red team: failure modes (Flow Tracer)

Date: 2026-10-20. Scope: `plan.md` and phases 01-12, checked against the code on `develop`.
Binding user decisions (pause resets on restart, the pause is global, the token is needed for pause and resume, and so on) are treated as constraints. A finding below names the plan step that turns a binding decision into an uncovered failure path. It does not reverse the decision.
[V] = verified in source or plan text. [I] = inference.

## Finding 1: A restart turns "paused, waiting for approval" into real-money trading, and nothing re-pauses until a person re-runs the worker
- **Severity:** Critical
- **Location:** Phase 11, sections "Task 11.6", "Task 11.7" and "Task 11.8"; Phase 12, "Task 12.3"; `plan.md`, "Conventions / No restart while live state matters"
- **Flaw:** From Task 11.6 until Resume, the only barrier against real orders is the in-memory `entries_paused`. That window covers the zero-money proof wait and the Resume [ASK], which can be deferred for any length of time. The plan bans only planned restarts. Unplanned restarts (a crash with `restart: unless-stopped`, a Docker daemon restart, a VPS reboot) are detected only when the user re-runs Phase 11 (Task 11.1 step 3) or Phase 12 (Task 12.3 step 2). The NOT_YET resume interval is the same length as the warmup buffer, so it offers no margin.
- **Failure scenario:** The `exness` subscription is running and paused, and the zero-money proof is pending. The app crashes at T. Docker restarts the same container. Reconcile bootstraps every subscription and converges `desired_state=running`. `Safeguards` starts with `entries_paused=False`. hitnrun2 warms up in about 8 open-market hours. The NOT_YET says "resume after now + 8 h", and the user re-runs at T+9 h or later. By then a real 0.01-lot order has been sent with no Resume approval. Task 11.7 reports it only after the fact (`other > 0 → stop and report`). If the tunnel is down at the same time (a VPS reboot restarts `cloudflared` too), Phase 11's entry gate fails on the public `curl https://pocketquant.xyz/...`. The worker exits NOT_YET before Task 11.1 can re-pause, even though the SSH path works. If a position was open, the strategy restarts with `_open_direction=None`. An opposite-side entry of the same size is then sent as `closePosition` (the adapter treats it as an exit).
- **Evidence:**
  - [V] `deploy/compose.prod.yml:35` sets `restart: unless-stopped` on `app`.
  - [V] Phase 05 Task 5.2 (`phase-05...md:50`) says "`entries_paused` is never stored, so a restart clears it".
  - [V] `strategy_reconcile_app_service.py:71-85` (bootstrap loads every subscription) and `:117` (`_converge_one` starts subscriptions whose desired state is running).
  - [V] `hitnrun2_strategy_service.py:68-73` (`on_start` clears the buffers and `_open_direction`) and `:93` (warmup guard).
  - [V] `phase-11...md:192` resumes after "now + 8 h (hitnrun2)"; `:201` defers Resume with "default now + 4 h"; the entry gate at `:50` curls the public tunnel.
  - [V] `exness_broker_adapter.py:197-212`: when a position is held, an opposite-side order of equal quantity becomes `closePosition`.
- **Suggested fix:** Keep the binding "resets on restart" and add an external re-pause that does not depend on the agent. For example, a VPS cron job every minute compares `docker inspect StartedAt` with a stored value. While a marker file `intended_paused` exists, it runs the existing SSH pause command. Phases 10, 11 and 12 create and remove the marker. Move Phase 11's entry gate and Task 11.1 onto SSH (`docker exec ... curl localhost`), not the public URL. Present the alternative, a boot-time "start paused" setting, to the user as a change to a binding decision.

## Finding 2: The zero-money proof cannot show that the pause gate caused the rejection
- **Severity:** High
- **Location:** Phase 11, "Context / Zero-money proof" and "Task 11.7"; AC7
- **Flaw:** Task 11.7 counts `orders` with `status: "rejected"` and treats one of them as proof that both the sizing and the pause gate work. The rejection reason is never saved to Mongo. Any rejection after `normalize_quantity` counts the same way. That includes "awaiting trading snapshot reconciliation" (normal right after a restart), "daily loss check failed: …", "unmapped exness position on …" and "quantity not normalized". The below-minimum check (step 2) reads `docker logs` across the whole wait. The app's logs rotate at 30 MB.
- **Failure scenario:** A restart clears the pause (Finding 1). The first signal after warmup lands while the snapshot is still being rebuilt. It is rejected for "awaiting trading snapshot reconciliation", and Task 11.7 records `zero_money_proof` as if the pause gate had been shown to work. Separately, during a wait of several days, an `order_quantity_below_broker_minimum` line from day 1 (a wide stop) rotates out of the logs. Step 2 then prints 0 and the proof says "below_minimum 0" even though the strategy produced sub-minimum signals.
- **Evidence:**
  - [V] `core/domain/order/entities.py:191-199`: `reject(reason)` puts the reason only on the event.
  - [V] `entities.py:225-236`: `to_mongo` has no reason field.
  - [V] `exness_broker_adapter.py:243-253` lists the other `_presubmit_reason` rejections; `:326` covers TRANSPORT and rate-limit rejections.
  - [V] `deploy/compose.prod.yml:63` caps the app's logs at `max-size: "10m"` with `max-file: "3"`.
  - [V] `phase-11...md:192` gives the decision rule.
- **Suggested fix:** For the proof, require at least one `exness.order_rejected_presubmit reason=entries_paused subscription_id=<id>` log line (Phase 05 Task 5.4 already emits it). Also require StartedAt to be unchanged since `exness_sub_id` was recorded. Record each check's count in `round-trip.md` at every NOT_YET exit, so rotation cannot erase the evidence.

## Finding 3: A second Phase 11 run and the daily Phase 12 runs fight over the one global pause, and go-live can release a strategy that has no zero-money proof
- **Severity:** High
- **Location:** Phase 12, "Task 12.1 step 3", "Task 12.3" and "Task 12.6"; Phase 11, "Context" (the pause is global); `plan.md`, "Unresolved questions" (how the runner handles BLOCKED)
- **Flaw:** Phase 12 works out "intended paused" only from `after round trip:`, `go-live` and `weekend hold` lines. It ignores an open `## Live run` section that has no `resumed_at`. Task 12.6 resumes entries globally, and its question does not mention a pending run. The runner dispatches the next phase on `worker_done --outcome succeeded`. Its skill text has no rule for a worker that ends with `Status: BLOCKED`. So a Phase 11 NOT_YET may be followed straight away by Phase 12 [I].
- **Failure scenario:** Strategy A is live (run 1 is DONE, `after round trip: keep on`, 3 clean rows so far). The user runs `--from 11` for strategy B. Task 11.4 pauses globally, the `exness` subscription for B is created, and Task 11.7 ends NOT_YET. (a) If the runner or the user then runs Phase 12, intended = "keep on" and actual = paused. The Verify fails and kongming is spawned on a correct state. (b) On a later day with 5 rows counted from A's `resumed_at` (B has not resumed yet), Task 12.6 asks "Declare go-live? (This resumes entries if they are paused.)". A yes resumes B's real-money entries with no zero-money proof and no Task 11.8 [ASK].
- **Evidence:**
  - [V] `phase-12...md:43` (rule for intended paused); `:130` (count from the latest `resumed_at`); `:138` (go-live resumes entries).
  - [V] `phase-11...md:19`: "The pause is global".
  - [V] `~/.claude/skills/eve-cook-plan/SKILL.md:130`: `worker_done --outcome succeeded` leads to dispatching the next phase. The file has no NOT_YET or BLOCKED handling.
  - [V] `plan.md:155`: the runner behaviour is "inferred".
- **Suggested fix:** Phase 12 entry gate: if any `## Live run` section lacks `round_trip: DONE`, end NOT_YET ("Phase 11 run in progress; resume with --from 11"). Task 12.6 must list the pending runs and refuse to resume while one exists. Have Phase 11 NOT_YET exits end the session with a non-success exit the runner treats as a stop. Do not rely only on printed text.

## Finding 4: Deleting the last `exness` subscription leaves its adapter connected, and the next `exness` subscription builds a second adapter (the B9 duplicate comes back)
- **Severity:** High
- **Location:** Phase 02, "Task 2.4"; Phase 11, "Rollback" ("To return a strategy to paper: stop and delete its `exness` subscription"); `plan.md`, "Rollback"
- **Flaw:** Task 2.4 changes only the pool key. It keeps the rule that reuses a pooled broker only while a loaded strategy holds it, and `unload_strategy` never disconnects the broker. After every `exness` subscription has been deleted, the old adapter's event stream keeps running. Its trade and order callbacks stay wired. The next `exness` load builds and connects a new adapter. `remove_symbol` deletes a subscription even with an open position, and the DELETE route returns 204 whatever happens.
- **Failure scenario:** The user takes strategy A back to paper (deletes its `exness` subscription; with Phase 06, Delete is allowed once the subscription is stopped, even with a position open). Later they run Phase 11 for strategy B. Adapter B connects; adapter A is still connected. On A's next WS reconnect, `_on_snapshot` maps B's venue position by `(symbol, side)` from the open rows in the repository. When the venue SL closes it, both adapters emit `TradeClosedEvent`. Result: duplicate `trades` rows and close fills, so AC6 and Phase 12's `close_deals == new_trades` fail. Any orphaned position of A stays mapped in A only. Task 11.6's Verify (`broker_connected` == 1) prints 2, which leads to kongming. The only cleanup is a restart, which the plan forbids while paused.
- **Evidence:**
  - [V] `engine/strategy/strategy_app_service.py:169-178`: `unload_strategy` pops the maps and does not disconnect.
  - [V] `strategy_app_service.py:467-469`: "Reuse only while a loaded strategy still holds the broker".
  - [V] `exness_broker_adapter.py:136-146`: `connect` starts the stream task.
  - [V] `exness_broker_adapter.py:441-448`: snapshot mapping by candidate.
  - [V] `strategy_command_service.py:99-107`: `remove_symbol` deletes without checking positions.
  - [V] `app/routes/strategy.py:141-147`: the DELETE route always returns 204.
- **Suggested fix:** In Task 2.4, make a venue broker (non-paper) a process singleton. A pool hit returns it whether or not a strategy holds it (it is one account and one stream). Add a unit test: delete the last `exness` subscription, load a new one, and assert `create` was called once. In the rollback text, require a flat account (positions endpoint empty) before deleting an `exness` subscription.

## Finding 5: The post-Resume monitoring leaves out the plan's own stop conditions, so a live strategy can fail to trade for days while the rows read "clean"
- **Severity:** Medium
- **Location:** Phase 12, "Task 12.2 step 1" and "Task 12.3 Verify"; Phase 11, "Task 11.9 step 1"; `plan.md`, "Stop and report"
- **Flaw:** `plan.md` lists "A `below_min_lot` or `order_quantity_below_broker_minimum` line for a live subscription" as a stop. Phase 12 counts nine events and Phase 11.9 counts five; neither includes it. Neither counts synchronous rejections either (`exness.order_rejected` code=TRANSPORT/REQUEST_RATE_LIMIT, "daily loss check failed"). All counts use `docker logs --since`, which only reaches back 30 MB [V cap; I that a day can exceed it]. `paused_rejections` counts every rejected order, whatever its reason, and is not judged.
- **Failure scenario:** hitnrun2's stop exceeds 25 USD/oz on most signals. That is allowed up to 41.8 (`phase-05` Risk). Every entry ends as `order_quantity_below_broker_minimum`, and no order is created. Phase 12 rows show 0 for every counted event and `close_deals == new_trades == 0`. They pass as clean for five days. Go-live is then declared on a strategy that never traded live after its first round trip.
- **Evidence:**
  - [V] `plan.md:120` (the stop condition).
  - [V] `phase-12...md:55` (the event list, which has no below-minimum entry).
  - [V] `phase-11...md:210` (5 events only).
  - [V] `engine/strategy/strategy_app_service.py:406-409` logs `order_quantity_below_broker_minimum` with `strategy_id`.
  - [V] `exness_broker_adapter.py:326-330` logs `exness.order_rejected`.
  - [V] `deploy/compose.prod.yml:63` (log cap).
- **Suggested fix:** Add `order_quantity_below_broker_minimum.*<live id>`, `exness.order_rejected ` and `zero_position_size.*<live id>` to the Phase 12 and Task 11.9 greps, and make any non-zero count fail the row. Add a row column "entry signals vs orders sent" (orders with any status for the live IDs), so a strategy that never trades shows up.

## Finding 6: Every recovery and rollback path is a restart, and the plan has no procedure for a planned restart while live
- **Severity:** Medium
- **Location:** `plan.md`, "Conventions / No restart while live state matters" and "Rollback"; Phase 09, "Rollback"; Phase 11, "Task 11.12" (D4 `pause`)
- **Flaw:** The ban on restarts has no end date. When the user picks D4 `pause` or weekend-hold option 2, entries are "paused on purpose" with no end, which freezes deploys with no end. The code rollback for 01, 03, 04, 06, 07 and 09 is "revert, fast-forward `master`", which is a full recreate of `app`. Only the rollback of 02 and 05 says to flatten first, and none says to re-pause afterwards. Rollback step 4 (flag off) is itself a redeploy.
- **Failure scenario:** After Phase 10, the tunnel misbehaves and the user approves the Phase 09 rollback (revert, re-add `WEB_PORT`, push `master`). CI recreates `app` with an `exness` subscription running and paused, or with a position open. The pause clears, strategy state is lost, and Finding 1 follows. No plan step says to re-pause after the deploy's health check. An Exness API change that needs a hotfix leaves only one choice: break the plan rule, or keep running broken code.
- **Evidence:**
  - [V] `plan.md:27` (the ban), `:138` (code rollback), `:144` (step 4 redeploys).
  - [V] `phase-09...md:165` (master push in the rollback).
  - [V] `deploy/vps/10-deploy.sh:50` (`docker compose up -d --remove-orphans` recreates `app` when the image or env changes).
  - [V] `.github/workflows/cicd.yml:190-240` (deploy runs on every `master` push or dispatch).
- **Suggested fix:** Add a short "planned restart while live" runbook that every rollback step references: pause; stop the live subscriptions; confirm the account is flat or accept that the venue SL protects the position; deploy; within 1 minute of the health check, run the SSH pause; verify `entries_paused:true`; start the subscriptions. Resuming then needs a new [ASK]. State that D4 `pause` does not freeze deploys once this runbook is followed.

## Finding 7: Several Verify steps read `docker logs` across the container's whole life, so they fail falsely after a crash restart or log rotation and send kongming to a healthy state
- **Severity:** Medium
- **Location:** Phase 11, "Task 11.6 Verify" (`grep -c exness.broker_connected` prints `1`); "Task 11.7 step 2"; "Task 11.9 step 1"
- **Flaw:** `restart: unless-stopped` restarts the same container, so `docker logs` keeps the lines from before the crash, and json-file rotation drops lines older than about 30 MB. On a second strategy's run the adapter already exists. It logs no new `exness.broker_connected`, and the line from the first run has probably rotated out [I].
- **Failure scenario:** Second run of Phase 11, several days after run 1. Task 11.6 prints `broker_connected` = 0 (rotated) or 2 (an earlier crash restart), so the Verify fails and kongming is spawned with an `exness` subscription running. Conversely, Task 11.9's whole-log grep for stop events can report an `exness.position_unmapped` from an earlier run of the same container and stop a healthy run.
- **Evidence:**
  - [V] `deploy/compose.prod.yml:35` (restart policy keeps the container) and `:63` (rotation cap).
  - [V] `phase-11...md:173` (the Verify step) and `:210` (whole-log grep).
  - [V] `exness_broker_adapter.py:146` logs `broker_connected` only in `connect`.
- **Suggested fix:** Scope every log check with `--since <created ISO or StartedAt>`. For one adapter, assert "`broker_connected` since this run's create ≤ 1, and `exness.broker_connected` count since StartedAt == 1". Run 2 accepts 0 new lines when run 1's adapter is still held.

## Finding 8: Phase 11's state record is written after each side effect, so a crashed or interrupted worker re-runs a non-idempotent step
- **Severity:** Medium
- **Location:** Phase 11, "State record", "Task 11.5" and "Task 11.6"
- **Flaw:** Task 11.6 creates and starts the `exness` subscription, waits 30 s, and only then appends `exness_sub_id`. Re-runs choose the next task from the last key line present. An interruption between the create and the append (a context limit, a dropped SSH session, the user aborting) leaves the record at `paper_deleted`.
- **Failure scenario:** The re-run goes back to Task 11.6 and asks again. The POST hits the unique index on the triple and fails. The agent was told to "note the returned id", so it then POSTs `/start` with a missing or garbage id and the Verify fails. Meanwhile the real `exness` subscription is running but not in the record. Phase 12's `IDS` (every `exness_sub_id` in `round-trip.md`) leaves it out, so its orders, positions and rejections are never counted. Task 11.1's restart re-pause still works only because a current run exists.
- **Evidence:**
  - [V] `core/infra/persistence/repositories/subscription_repository.py:102-106` (unique index on the triple).
  - [V] `strategy_command_service.py:60-97` (`add_symbol` stores the subscription as stopped and raises on a duplicate through the repository).
  - [V] `phase-11...md:171` (append after "Wait 30 s").
  - [V] `phase-12...md` Task 12.1 step 2: "Live ids = every `exness_sub_id`".
- **Suggested fix:** Write an intent line (`exness_create_requested: <UTC>`) before the POST. On a re-run, look up `GET /api/v1/subscriptions/` for the triple with `broker == "exness"` and adopt its id before deciding to create. Take Phase 12's live IDs from that GET (`broker == "exness"`), not only from the markdown.

## Unresolved questions
- How Orca classifies a worker that prints `Status: BLOCKED` and exits normally (as succeeded or as failed). It is not stated in `eve-cook-plan/SKILL.md`, and Finding 3(a) depends on it.
- How much the prod app logs per day (not measured here; reading it needs prod SSH). If a day is well under 30 MB, Findings 2, 5 and 7 lose their log-rotation part. The parts about crash restarts and missing reasons remain.
