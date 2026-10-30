# Deploy window, first principles: is the rule needed for D-5?

Date: 2026-10-30 (Asia/Bangkok). Written at 2026-10-29 ~23:50 UTC. Advisory only; no code, push or SSH.
Model note: this run used the configured strongest model; no runtime override was needed.

## TL;DR

The three blackouts (23:50-00:50, 02:50-04:50, 11:50-12:50 UTC) protect something real and code-grounded: a worker handover at a heavy job's fire time loses that run, and a heavy job running while four runtimes overlap on a 3 GB host raises the OOM-stop and drain-timeout odds. Keep them. The Mon-Fri 06:00-19:30 part is an evidence-quality rule for the ten counted handovers, not a safety control, and D-5 is row 0, which is not one of the ten. Deploying "right now" (23:45 UTC) is the one case the blackout exists for: do not. The cheapest safe move is to wait for Fri 2026-10-30 06:00 UTC (13:00 Bangkok), about six hours away. If the owner prefers the Bangkok morning, 01:00-01:20 UTC today (08:00-08:20 Bangkok) is acceptable with a one-line plan amendment and the owner reachable for an hour after the push.

## Reframed problem

The owner is deciding when D-5 (the one-time `app` -> `api`/`worker`/`trader` cutover) may run, and whether the plan.md Conventions rule should be kept, relaxed or dropped. Requirements: no lost or doubled scheduled jobs, no OOM on the 2 vCPU / 3 GB host during the four-runtime overlap, a clean trader drain at a 1m boundary, a rollback path that does not wait on the clock, and usable row-0 measurements. Non-goals: live-trading safety (live is off for the whole plan) and the Phase 10 counted handovers (rows 1-10), which keep their own rule.

## Where the rule came from (verified in the records)

- Blackouts: present in `reports/planner-debate-candidate-1.md:56` and the synthesis `reports/kongming-261028-1445-debate-synthesis.md:11`, carried into `plan.md:54`. No written rationale, but the three bands are exactly 10 min before to 50 min after `sync_repair` (00:00, 12:00), `sync_backfill` (03:00) and `sync_integrity` (04:00) (`sync_jobs.py:672-691`).
- Weekday hours: `reports/planner-debate-candidate-3.md:454,467` proposed "Mon-Fri 06:00-11:00Z or 14:00-20:00Z" for the cutover and "Market hours = Mon-Fri 06:00-20:00Z outside the cron hours" for the counted handovers; the synthesis Phase 08 line kept it; the red-team consistency sweep (`plan.md:155,171-176`) unified every copy into one rule at `plan.md:60`. The acceptance criterion `plan.md:113` reads "Over 10 deploys in market hours". The Phase 01 spike window note (`phase-01:24`) gives the same reasoning in words: "liquid FX and metals, no cron hour, outside every deploy blackout".
- Inference (medium): 11:20 = 11:50 minus 30 min (an 8 min deploy plus verification); 19:30 leaves 1.5 h before the Exness daily break at ~21:00 UTC; 06:00 sits after the 04:50 blackout end plus margin and at the European open. Nobody wrote these numbers down with a reason.

## Q1. What each part prevents

### Blackouts (verified mechanism, inferred magnitude)

Shutdown path, verified in code: SIGTERM -> `main.py:97-101` runs `stop_worker` and `hand_over` together. `stop_worker` (`roles.py:134-155`) pauses the scheduler, waits for running job tasks until shutdown start + 90 s (`WORKER_STOP_S`), cancels renewal, shuts the scheduler down without waiting, releases the `worker` lease, logs `worker.lease_released running=<n>`. The container is SIGKILLed at the compose grace (`app` 180 s on master, verified with `git show origin/master:deploy/compose.prod.yml`; `worker` 120 s from Phase 08).

So a deploy that lands while a heavy job runs on the old worker has one of two outcomes:

1. The job finishes within 90 s: clean.
2. It does not: the lease is released with `worker.jobs_still_running`, the job keeps running in the dying process and is killed at SIGKILL. The run is lost. The new worker does not re-run it (see Q2) and the catch-up (`sync_jobs.py:74-78`) only fires when the last success is older than 12 h + 30 min / 24 h + 1 h, so one lost run is simply deferred to the next cron.

Measured history (memory, prod read 2026-10-28, before the TradingView removal): `sync_repair` median 1,527 s and max 2,947 s, `sync_integrity` ~7 min. That makes outcome 2 near-certain for any deploy inside the 50 min after 00:00/12:00 and likely after 03:00/04:00, which is where the "50 min after" tail comes from (inference, high). The "10 min before" head keeps an 8 min deploy from straddling the fire time (inference, high).

Two further effects that are specific to D-5 (inference, medium-high, based on measured stalls and the deploy script):

- Resource overlap. `10-deploy.sh` runs the cutover with the old `app` plus new `api`, `worker`, `trader` all alive ("four runtimes overlap now", script comment) before `oom_ok`. A heavy job's working set on top of that is the most likely way to trip the OOM stop (R2, D31), which aborts the cutover and leaves the owner with a failed D-5 to re-plan.
- Drain quality. The old `app`'s event loop ran the job; a stalled loop delays `drain_trader`'s 0.2 s polls and the timer close that advances `last_closed_boundary` (`roles.py:226-251`), pushing the drain to `drain_retry` or `drain_timeout`. Row 0's drain evidence would then be about the job, not the handover.
- Noise. WS reconnect lines cluster in 00-04Z and 12Z (~120/day measured 2026-10-27/28, memory). A row-0 taken there confounds R1 attribution.

Caveat (verified absent): after the TradingView and CME-calendar removal the plan targets p50 `sync_repair` < 120 s and `sync_integrity` < 10 s (`plan.md:99`), but no report in this plan records a post-removal measurement. The 50 min tail may now be oversized; nobody has shown it. Until measured, keep it.

### Weekday limit (evidence-quality, not safety)

Verified: the only place the weekday matters in the plan's logic is the acceptance line "Over 10 deploys in market hours" (`plan.md:113`) and the Phase 10 re-roll gate (`phase-10:248`). D-5 is row 0; D-6 is "handover 1/10" (`plan.md:91`). Nothing in `roles.py`, `10-deploy.sh` or the scheduler reads the weekday or the clock. The drain does not need ticks: it waits for `last_closed_boundary >= boundary`, and the plan's consistency sweep states the timer advances that boundary idle or not (`plan.md:165`; I did not re-read the Phase 05 code in this run). The Exness weekly close and daily break are venue-empty periods handled by the trading calendar (D10 text; not re-verified in code).

What a weekend or off-hours cutover loses: FX/metals tick flow during the handover, so the row-0 numbers (`handover_gap_ms`, `takeover_ms`, `gap_skips`) are taken under thinner conditions. For row 0 that is record-only anyway (D27 for the probe; the handover numbers are recorded but not counted among the ten). It loses nothing in correctness that I could find.

### 06:00-19:30 hours (margins, inferred)

See "Where the rule came from". The one concrete margin worth keeping in any rewrite is "do not start a deploy less than ~60 min before a blackout", because Task 8.7 runs a 1 h sampler and probe and a rollback decision wants that hour.

## Q2. A worker-lease handover on a job's fire time

APScheduler 3.11.2 (`uv.lock`), `MongoDBJobStore`, `coalesce=True`, `max_instances=1` (`scheduler.py:44-57`). Upstream 3.x source fetched for `_real_add_job`, `start()`, `_process_jobs`, `pause()` and the executor's misfire check.

Verified sequence on the new worker (`roles.py:110-116`): acquire lease (0.5 s poll after a clean release, up to 30 s TTL after a missed one) -> `recover_orphan_jobs` (marks `running` history rows older than 600 s as failed, `job_history_repository.py:128-134`) -> `scheduler.initialize()` -> `scheduler.start()` -> `register_sync_jobs()`. `start()` calls `wakeup()`, which runs `_process_jobs()` synchronously against the Mongo store, which still holds the old scheduler's job docs and their `next_run_time`. Due jobs are submitted; the executor checks each run time: `now - run_time > misfire_grace_time` -> `EVENT_JOB_MISSED` and skip, else run. Only then does `register_sync_jobs` re-add every job with `replace_existing=True`, which overwrites the stored doc with a fresh `next_run_time` computed from now.

Cases for a fire time F (take 00:00 `sync_repair`, grace 1800 s):

- Old scheduler paused before F (SIGTERM shortly before 00:00): stored `next_run_time` = F. New worker starts at F + gap. Gap is normally a few seconds to ~2 min (release <= 90 s, poll, orphan sweep). Gap <= grace -> the job runs once on the new worker, late by the gap. Not missed, not doubled. For `sync_1m` (grace 120 s) a gap over 120 s yields one `missed` row (the Phase 02 listener fix is in `scheduler.py:84-91`) and the cascade lookback heals it. With `coalesce=True` several overdue minutes collapse to one run with no event.
- Old scheduler already running the job at SIGTERM: the old `_process_jobs` already advanced the stored `next_run_time` to the next fire (12:00). The old process waits <= 90 s, releases, and the job dies at SIGKILL if still running. The new worker sees nothing due and does not re-run it. The history row stays `running` until a later worker boot finds it older than 600 s. Harm: that repair/backfill/integrity pass is deferred 12-24 h. I expect no data corruption because the sync paths upsert bars (inference, medium; not re-verified in this run).
- Doubling: not possible while the lease holds. The old scheduler is paused before the lease is released and the new one starts only after acquiring it; the jobstore comment at `scheduler.py:30-32` is about two live schedulers, which the lease rules out. The only overlap is case 2's dying job versus a new run of the same job, and that needs a second fire inside 90-180 s, which no heavy job has.

Conclusion for Q2: a handover exactly on a fire time is benign (delayed by seconds to minutes). A handover during a long run loses that run. The blackout prevents the second, not the first.

## Q3. Paper-only risk of deploying at 00:50-02:50 UTC, right now, or on a weekend

- Right now (23:45-23:50 UTC): no. The push would start inside the 23:50 head, the ~8 min deploy would straddle 00:00, and the old `app` could be mid-`sync_repair` at SIGTERM. This is the exact failure the blackout encodes, plus the 00Z WS-reconnect cluster in row 0.
- 00:50-02:50 UTC today (07:50-09:50 Bangkok): no blackout mechanism applies. Verified facts that still hold at that hour: live is off (`EXNESS_LIVE_TRADING=false`), the drain is timer-driven, the rehearsal passed (`reports/cutover-rehearsal.md`, abort/cutover/roll, gap 30 ms), D-4 ran clean on Thursday. Costs: Asian-session FX is thinner (row-0 numbers less representative; record-only); the 1 h sampler/probe must end before 02:50, so start by about 01:20 UTC; under the current rule a rollback push would have to wait until 06:00 UTC (see Q4; this is the rule's weakest clause); the owner must stay reachable until about 02:40 UTC. Nothing else found.
- Weekend: FX/metals closed, BTC data 24/7, the trader drains on the timer. No code-level hazard found. Evidence value of row 0 lowest; owner availability for rollback is a scheduling matter, not a technical one. The ten counted handovers must not be taken on a weekend because the acceptance line says market hours.

What a night/weekend deploy actually loses, in order: owner availability for the first hour (the real risk, independent of the clock); representativeness of row-0 numbers (recorded, not judged); FX activity to exercise `strategy.entry_skipped reason=gap` checks around the boundary (the XAUUSD 1m paper subscription has been stopped since 2026-10-28 per `phase-10:36`, so an Exness 1m subscription is not exercising the path today anyway; Phase 10 starts it).

## Q4. Options

The window was accepted by the owner in the plan; changing it is the owner's call. Options, cheapest first:

A. Keep the rule, deploy Fri 2026-10-30 06:00-11:20 UTC (13:00-18:20 Bangkok). Default recommendation. Cost: about six hours of waiting. Benefit: no amendment, European session, 5 h of in-window time for a same-day rollback, no blackout within reach.

B. Relax for non-counted deploys. Proposed text: "Blackouts (UTC): 23:50-00:50, 02:50-04:50, 11:50-12:50; no deploy starts inside one or within 60 min before one. Counted handovers (Phase 10 rows 1-10) also run Mon-Fri 06:00-11:20 or 12:50-19:30 UTC. Every other deploy (the D-5 cutover, rollbacks, emergency pins, fix pushes) may run any day at any other time, after the [ASK], with the owner reachable for 60 min after the push." For today that means pushing D-5 at 01:00-01:20 UTC (08:00-08:20 Bangkok). Cost: one plan.md edit (a D36 line and the Conventions bullet), a note in handover-log row 0, and a thinner-market row 0. Benefit: deploy in the owner's morning; rollbacks no longer wait on the clock.

C. Drop the rule for paper-only deploys. Not recommended. The blackouts protect job integrity and the 3 GB host, which do not care whether trading is paper or live; and the ten counted handovers must be taken under the conditions future deploys will face, or Phase 11's go-live inference weakens.

Regardless of A or B, the rollback clause (`phase-08:596,598`, and the same wording in Phases 02-11) should be changed so a rollback is gated only by the blackouts and the [ASK], not by the weekday window. Waiting until 06:00 Monday to undo a broken Friday-evening cutover is the opposite of what a window should buy. This is the one change I would make even if the owner keeps A.

## What to avoid

- Pushing between 23:50 and 00:50 UTC, or at any time that puts the 00:00/12:00/03:00/04:00 fire inside the push-to-`wait_lease` span.
- Starting a deploy less than an hour before a blackout (the sampler/probe and a rollback decision need that hour).
- Treating D-5 as handover 1 of 10; it is row 0 and the rule's market-hours clause does not serve it.
- Dropping the blackouts on the strength of the TradingView removal before a 7-day `job_history` p50 for `sync_repair`/`sync_integrity` is recorded.
- Letting the window gate a rollback.

## Work checklist (for the caller)

1. Put options A and B to the owner in Vietnamese with A as `Recommended`, and ask separately whether to amend the rollback clause (recommend yes).
2. If A: run Task 8.7 from 06:00 UTC today; nothing else changes.
3. If B: before the push, add the D36 line and the Conventions text above to `plan.md`, replace the window check in Task 8.7 step 1 with a blackout check (the Phase 02 command prints `NOT_IN_WINDOW` for the weekday clause, so it cannot be reused as-is), commit as docs, then push D-5 at 01:00-01:20 UTC with the owner reachable until ~02:40 UTC.
4. In either case, record in handover-log row 0 notes the UTC start, which rule applied, and the `worker.lease_released running=` value from the old `app` log.
5. In Phase 10, record 7-day p50/max `duration_ms` for `sync_repair`, `sync_backfill`, `sync_integrity` and shrink or keep the 50 min tails with numbers.

## Success metrics

- Row 0 PASS: `trader.lease_released inflight=0`, 0 `drain_timeout`, `OOM_OK` before and after, `owners_match=yes`.
- Old `app` log shows `worker.lease_released running=0`.
- No `missed` or `failed` `job_history` rows for the four heavy jobs within 2 h of the deploy; `sync_1m` at most one `missed` row.
- If B was chosen: the rollback never had to wait for a window, and the row-0 numbers were not challenged in Phase 10 for being off-hours.

## Assumptions

- The post-removal durations of `sync_repair`/`sync_integrity` are still unmeasured in prod (high; verified absent from the plan's reports; a measured p50 under 2 min would justify shrinking the 50 min tails to ~15 min).
- Bar sync paths upsert, so a killed job leaves no partial-state corruption (medium; not re-read in this run).
- `last_closed_boundary` advances on the timer when no tick arrives, so the drain completes in a closed market (medium-high; stated in `plan.md:165` and tested per the sweep; code not re-read here).
- Prod currently runs the paper strategies loaded at D-4 (`strategies=4`, `paper_brokers=3`), with the XAUUSD 1m subscription stopped (medium; from `strategy-runtime-deploy.md:48` and `phase-10:36`, not read live).
- The owner can be present 13:00-18:20 Bangkok today (unknown; if not, B at 08:00-08:20 Bangkok is the fallback).
- Exness has no scheduled maintenance tonight (low confidence either way; a venue notice would move the deploy to A).
