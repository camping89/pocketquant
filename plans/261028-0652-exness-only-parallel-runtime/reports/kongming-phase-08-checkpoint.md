# Phase 08 checkpoint: go/no-go for Phase 09

Date: 2026-10-30 (Asia/Bangkok). Advisory only. Verified on `develop` @ 2ff298b1, `origin/master` @ 659120ef. No SSH, no push, no code edits in this run.

## TL;DR

**GO for Phase 09**, with one precondition: a docs-only plan commit before the executor starts, so Phase 09 writes the post-Task-8.6 behaviour into the docs and does not inherit stale text (worker stop wording, `docs/deployment.md:212`, the missing Binance WS task, the leftover window clauses in Phases 09-11). Do not deploy the index-race fix on its own; it ships with D-6, and D-6's Verify should prove it (`RestartCount` 0 on all three role containers). Define "market hours" for Phase 10 as a counting rule, not a deploy permission: a row counts when the XAUUSD:EXNESS calendar is open from the deploy start until 15 min later (D36 proposal below).

## Q1. GO or NO-GO

GO. Evidence, all from the records and the repo:

- Phase 09 entry gate lines hold today: line 1 (`git status --porcelain -- src web deploy tests scripts docs` printed nothing in this run); line 2 (`origin/master` is 659120ef, which contains 17026288, the commit that removed `container_name: pocketquant-app`); line 3 (`reports/handover-log.md` exists with row 0); line 4 (`machine-baseline.md` has the baseline line, per Phase 08 gate 4 having passed); line 5 (helpers installed by Task 8.8 step 3 and checked by the Task 8.8 Verify; not re-checked over SSH here).
- Row 0 meets every Phase 10 judging value (`inflight=0`, `offset_s=0.61`, `drain_timeout=0`, `handover_gap_ms=421 <= 2000`, `takeover_ms=45 <= 5000`, `gap_skips=0`, leases `2/2 owners_match=yes`, `OOM_OK`). The only FAIL row is Boot integrity, explained and fixed on `develop` (6142249f, CI success).
- Machine (record only, D31): the four-runtime overlap left `min_available_mb=1363` and `max_swap_used_mb=119`; MongoDB peaked at 1589 MiB RSS and is the dominant consumer. A rolling deploy overlaps two copies of one role, not four runtimes, so D-6 is a lighter overlap than D-5.

Precondition (soft, no prod step): apply the plan edits in Q3 as one `docs(plans)` commit before `/eve:cook-plan --from 09`. `**/*.md` does not trigger CI, so this costs nothing.

Named risk, not a blocker: D-6 is the first run of the `roll` path in prod (rehearsed on Docker Desktop only, `reports/cutover-rehearsal.md`). It is also, if it lands during a heavy job, the first prod exercise of the Task 8.6 resume path, which so far has CI coverage only. Record that in the row notes either way (see Q3 item 7).

## Q2. Anything to act on before Phase 09

**Deploy the fix sooner: no.** The race needs two or more role containers running `ensure_indexes` at the same moment. That happens on the one-time cutover (done), on a host reboot (`restart: unless-stopped` starts all three together), or on a compose recreate of all three. A rolling deploy starts one new container at a time and waits for health before the next (`10-deploy.sh` `roll api 120`, `roll worker 120`, `roll trader 240`), so D-6 cannot hit the race even with the old code, and the D-6 image carries the fix. When the race does hit, the effect is one failed startup and a Docker restart (prod: `RestartCount=1`, the worker took its lease at 03:07:06 after a 03:02 push). A fix-only deploy would spend a handover row for no evidence.

**Is the fix right?** Facts: 6142249f drops `idx_skip_idempotency` only when the existing index lacks `unique` or its `partialFilterExpression` differs from `{"scheduled_run_time": {"$type": "date"}}` (`job_history_repository.py:322-334`). The test `test_ensure_indexes_never_drops_a_matching_index` spies on `AsyncCollection.drop_index` against a real Mongo and CI passed on 6142249f. Assumption (high): prod's Mongo returns the same `partialFilterExpression` shape as CI's; if it did not, the index would be dropped on every start, which is the old behaviour, not a new failure. Cheap proof after D-6: no `job_history.idempotency_drop_failed` line in the three new containers' logs and `RestartCount` 0 on each. Add both to the Task 9.8 Verify (Q3 item 7).

**Other repositories:** verified with `git grep -n drop_index -- src`: the only two hits are `job_history_repository.py:332` and `:352`. Every other `ensure_indexes` (`bar`, `backtest*`, `order`, `position`, `subscription`, `symbol`, `sync_status`, `trade`, `tracked_symbol`, `lease`) calls `create_index` only. Identical concurrent `create_index` calls on one spec are safe (one builds, the others find it or join). Nothing to change.

**`_ensure_ttl_index`:** already conditional (`job_history_repository.py:350`: drop only when `expireAfterSeconds != _TTL_SECONDS`). The same race shape exists only on the first start after `_TTL_SECONDS` changes, and only when two containers start together (a reboot on that exact day). The outcome would be the same self-healing restart. Accept; do not touch it.

**Row 0 probe `2/546` non-200:** inside the `web` recreate, recorded only (D27). Not traced; nothing to act on. The same-tag re-rolls in Phase 10 must show 0, and the rehearsal roll did.

## Q3. What Phase 09 should adjust

Edit the phase files (docs-only commit) before running, then run as written.

1. **Task 9.1** also deletes `oom_ok` (its only caller is the cutover branch, `10-deploy.sh` step 2 of Task 8.3). Say so in the phase report: after Phase 09 the deploy script itself runs no OOM check; the check lives in the Phase 10 capture-stop step (Task 10.6 step 8) and the day snapshot. That matches D31 and D34; do not add an `oom_ok` call to the rolling path (new behaviour, no request).
2. **Task 9.2 step 3, "Worker stop" bullet** is stale after Task 8.6. Code now (`roles.py:46,145-155`): pause the scheduler, wait for running jobs until stop start + 90 s (`WORKER_STOP_S`), cancel what is left (`stop_running_jobs`), log WARNING `worker.jobs_interrupted count=`, release the lease, log `worker.lease_released running=`. Add the resume facts to the same section: a cancelled heavy job (`sync_backfill`, `sync_integrity`, `sync_repair`) ends its history row `interrupted`; every run write carries a `run_id`; the next worker marks stuck `running` rows `interrupted` at takeover (`main_extensions.py:123-127`, `orphan_jobs_interrupted`); the catch-up resumes the newest interrupted row under a new `run_id` and skips `done_symbols`; a fresh cron run closes the job's interrupted rows as `failed` / `superseded`; a second run of a running job logs `job.already_running`. Extend the Task 9.2 Verify grep with `interrupted`.
3. **Task 9.3**: `docs/deployment.md:212` ("when a deploy overlaps that job's window") must be rewritten: a deploy may cut a heavy job; the row ends `interrupted` and the next worker's catch-up resumes it per symbol; there is no deploy window. The deploy-flow text in step 2 should state the worker's 90 s job wait inside its 120 s grace.
4. **Rollback line 221**: drop "and window" from "(same [ASK] and window)".
5. **Binance WS HTTP 400**: Phase 09 has no task for it, although `phase-08:74` and `reports/kongming-phase-07-checkpoint.md` both say "scheduled for Phase 09". Add a small task (default) with the fix shape from that checkpoint: `run_forever` waits until `_subscriptions` is non-empty before the first `connect()`, delete the placeholder-URL branch (`binance_websocket_adapter.py:174-175` on that date; locate by text), one test, its own `fix(...)` commit, CI green before Task 9.5 step 6. Cost: a Python change rides on D-6. Benefit: without it every one of the ten Phase 10 handovers writes one ERROR line at trader start (a WARN in `11-verify.sh`, never a FAIL; Phase 10 counts only `Error notifying listener`). If the owner wants D-6 to carry nothing but the index fix and the cleanup, defer it to a Phase 10 fix push (Task 10.6 step 9 already handles `image` rows); then write that choice into `phase-08:74`.
6. **Leftover window clauses outside Phase 09** that `plan.md:60` overrides in prose but an executor can still trip on: `phase-10:291` ("inside the **Deploy window**"), `phase-10:280` ("when the window is open"), `phase-11:29`, `:138`, `:209`, and above all `phase-11:177`, which contains an executable `date -u +%u` / `%H%M` check whose empty output skips the D33 re-roll task. Remove the command and the clauses in the same docs commit. This is the one item I would not leave for later: it silently blocks Phase 11 re-rolls outside Mon-Fri 06:00-11:20 / 12:50-19:30 UTC.
7. **Task 9.8** additions, all read-only: (a) the [ASK] text names what D-6 ships (cutover-branch removal, docs, the index fix, the Binance fix if included); (b) Verify adds `for c in $(dc ps -q api worker trader); do docker inspect -f '{{.Name}} {{.RestartCount}}' $c; done` -> three lines ending `0`, and `role_logs`-style grep for `idempotency_drop_failed` -> `0`; (c) row-1 notes record `job_history` rows with `status=interrupted` at D-6, plus any `worker.jobs_interrupted`, `orphan_jobs_interrupted` and catch-up resume lines, so the first prod exercise of Task 8.6, if it happens, is documented. Also note the `interrupted` count is expected to be 0 when no heavy job was running.
8. **plan.md**: the Phase 08 row in the phase table still reads `Pending`; set it to Done with Phase 09's close commit. Add D36 (Q4) and rewrite `plan.md:113` from "in market hours" to the D36 rule.

Nothing in Phase 09's entry gate, Task 9.1 Verify counts (`roll` lines = 3), or Task 9.4 gate is affected by the Task 8.6 renumbering; the cross-references to "Task 10.6 step 8" still point at the capture-stop step.

## Q4. Defining "market hours" for the Phase 10 counted handovers

What the words protect (verified): the judged values that need a live market are `gap_skips` (0 `reason=gap` within one interval of the boundary), `offset_s` after a 1m boundary, and the paper latency samples; the Phase 10 paper symbol is `XAUUSD:EXNESS` 1m (`phase-10:79-81`). The sessions in code (`src/pocketquant/core/infra/calendars/exness_session_calendar_adapter.py:44-76`): XAUUSD is open Sun 22:01:30Z to Fri 20:58:00Z with a daily break 20:58:00-22:00:29Z Mon-Thu; EURUSD is open Sun 21:05Z to Fri 20:59Z without a break. Memory from Phase 02: EURUSD loses random 0-17 min of ticks around 21:00Z, so the session edges are a known confound.

Options for the owner (all keep `plan.md:60`: a deploy may run at any time; the rule decides which rows count toward the ten):

- **A (recommended, D36):** a handover row counts when the paper symbol's calendar is open at the deploy start and stays open for 15 min after it. Derived clock table for XAUUSD: Mon-Fri 00:00-20:40Z and Sun-Thu 22:15-24:00Z. A row outside this is recorded with `kind` suffixed `(off-session)` and does not count. Task 10.6 step 1 adds "or the session rule fails" to its skip list so no re-roll is spent on a non-counting row. Benefit: one rule, verifiable from the code and the row's start time, no blackouts, works for a Bangkok daytime owner (02:00-10:00Z is in session). Cost: Asian-session rows are thinner than London/NY rows; the numbers are still real handovers of a live 1m feed.
- **B:** A plus a liquidity floor: at least 3 of the 10 rows (at least 2 of them re-rolls) start inside 12:00-16:00Z Mon-Fri (London/NY overlap, 19:00-23:00 Bangkok). Benefit: `takeover_ms` and `handover_gap_ms` measured under the highest tick rate before live is re-armed. Cost: three evening sessions for the owner.
- **C:** restore the old clock, Mon-Fri 06:00-19:30Z, without blackouts. Cost: it is the rule the owner just removed, it excludes the Bangkok morning (02:00-06:00Z), and it slows Phase 10 for no judged value.

Default: A. Evidence that would flip to B: the first three A rows show `takeover_ms` or `handover_gap_ms` rising with tick rate, or `gap_skips` appearing only in busy hours. Write the chosen rule as D36 in `plan.md`, rewrite `plan.md:113`, and add the session condition to Task 10.6 step 1 and Phase 11's D33 re-roll preconditions (replacing the removed window command at `phase-11:177`).

## What to avoid

- A fix-only deploy of 6142249f; it buys nothing a rolling deploy can show.
- Turning the market-hours rule back into a deploy permission; it is a counting rule.
- Adding an OOM check to the rolling path while deleting the cutover branch.
- Calling the Boot integrity FAIL closed before D-6 shows `RestartCount` 0.
- Fixing `phase-11:177` in prose only; the executable check has to go.

## Work checklist (caller)

1. One `docs(plans)` commit: Q3 items 2-6 and 8, plan.md D36 and the `plan.md:113` rewrite, Phase 08 row status.
2. Put Q4 options to the owner in Vietnamese with A as `Recommended`; also ask whether the Binance fix rides on D-6 (recommend yes).
3. Run `/eve:cook-plan ... --from 09`.
4. In Task 9.8, apply the Q3 item 7 additions and keep their output in the row-1 notes.

## Success metrics

- D-6 exits 0, CI verdict 0 failures, `RestartCount` 0 on api/worker/trader, no `idempotency_drop_failed` line, one `trader.takeover` and one `trader.takeover_complete`, leases `2/2 owners_match=yes`.
- Phase 10 counts rows against D36 without a second debate about hours, and Phase 11's re-roll task is never skipped by a clock check.
- No ERROR line at trader start after the Binance fix ships.

## Assumptions

- Prod Mongo returns `partialFilterExpression` as written (high; CI's real-Mongo test passed). Flipped by a `job_history.idempotency_drop_failed` or a restart on D-6.
- The helpers and topology on the VPS match the Task 8.8/8.9 Verify outputs recorded in the reports (high; not re-read over SSH in this run).
- XAUUSD:EXNESS 1m stays the Phase 10 paper symbol (high; `phase-10:79`). If the owner picks a 24/7 symbol instead, D36 degenerates to "always in session" and option B becomes the only meaningful rule.
- The two non-200 probes in row 0 belong to the `web` recreate (medium; untraced, record only).
- Owner reachability for the first hour after D-6 is the real scheduling constraint, not the clock (medium).

Status: DONE_WITH_CONCERNS
Summary: GO for Phase 09 after a docs-only plan commit; ship the index fix with D-6 and prove it there; define market hours as a counting rule (D36, option A).
Concerns/Blockers: Phase 09 has no Binance WS task although two records say it is scheduled there; `phase-11:177` still carries an executable deploy-window check; `docs/deployment.md:212` and the Task 9.2 worker-stop bullet describe pre-Task-8.6 behaviour.
