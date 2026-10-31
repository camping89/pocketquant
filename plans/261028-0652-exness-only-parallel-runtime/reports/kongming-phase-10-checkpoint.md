# Kongming checkpoint: Phase 10 early close (D37) to Phase 11 re-arm

Advisory only. Written 2026-10-31T02:50Z (Saturday, markets closed). Evidence is marked [V] when read from the repo or reports in this session, [I] when inferred.

## TL;DR

GO for Phase 11, with the sequence below: arm on the weekend with zero `exness` subscriptions and entries paused, let the armed split runtime sit through the Sunday 2026-11-01 reopen (the first US-DST-shifted session) under pause, and give the first real-money Resume no earlier than Monday 2026-11-02 after one snapshot and one session check. Do not add a WiredTiger cap or `mem_limit` before arming. The waived criteria do not change the order-safety case; they move three time-dependent observations (weekend/DST reopen, multi-day memory, 7-day job stats) from paper into a bounded live run.

## Reframed problem

The decision is not "was Phase 10 good enough" (the owner already decided that, D37) but "does the early close leave an unobserved failure mode that real money would meet first, and can Phase 11's own sequence cover it cheaply". Requirements: no unbounded money exposure, no untested prod change right before arming, every real-money step behind its own [ASK]. Non-goal: re-litigating D37.

## What the evidence covers and what it does not

Covered well [V]: the handover itself. 8 rows (cutover plus rows 1-7) with `inflight=0`, `handover_gap_ms` max 499 against a 2000 cap, `takeover_ms` max 58 against 5000, 0 `drain_timeout`, 0 gap skips, 0 lease loss, warm-up 11-32 s (`handover-log.md:74-81`, `machine-limits.md:6-12`). Paper 1m latency p95 699 ms against 1000 (`paper-daily.md:13`).

Not covered [V, from D37 and the reports]:

1. A weekend close and reopen on the split runtime, and the first session after US DST ends on 2026-11-01 (XAUUSD reopen moves from 22:01:30Z to 23:01:30Z; the calendar is held in `America/New_York`, `exness_session_calendar_adapter.py:26`, "proven in code, not yet in prod" per go-live `phase-12:19`).
2. Memory over several days. Snapshots: 2114 MB used on 10-28 (single app), 1911 MB on 10-30 07:10Z, 2049 MB on 10-31 02:33Z (`machine-baseline.md`, `machine-limits.md:5,21`). Across three days this is flat, not rising [I: three point samples, not a trend]. MongoDB RSS 1.48-1.59 GB sits at the WiredTiger default of about 50% of (RAM minus 1 GB), about 1.45 GB on this host [I], so its growth is bounded by design. Lowest `mem_available` ever seen is 1363 MB at the cutover with four copies running (`handover-log.md:42`); a same-tag re-roll moves `used` by under 40 MB (h2-h7).
3. The 7-day job metrics and the rolling 7-day rate budget (2 retries in 19 h against 72 per 7 days).
4. The heavy-job resume after a worker handover (`sync_jobs.py:141-168`, `job_history_repository.py:74-83`; CI-tested in `tests/app_test/unit/market_data/test_sync_jobs_tracked.py`, never cut in prod).

How each fails with live armed [I, reasoned from the code paths named above]: a wrong DST calendar either skips entries (`reason=gap|stale`) or the venue rejects an order (`order_rejected`, which stops the go-live row); an OOM-killed trader restarts under `restart: unless-stopped`, the old lease expires, the new trader takes over and the open position keeps its venue SL/TP, and go-live 11.1 step 5 stops the run on the unplanned restart; a cut heavy job affects stored-bar completeness, not the trader's tick-built 1m bars, so the worst case is a skipped entry. None of these sends an extra order.

## Question 1: GO or NO-GO

GO, with four conditions. None requires a code or compose change.

1. **Arm with zero exposure.** Run Phase 11 Task 11.3 (arm) while `exness` subscriptions are 0 and entries are paused. With no `exness` subscription no broker connects, so the flag changes nothing at runtime until go-live 11.6 creates one.
2. **One Monday-open observation before the first Resume.** The first real-money Resume (go-live 11.8) is given on or after Monday 2026-11-02, after (a) the Sunday reopen has produced bars and the session check (Phase 10 Context, D36) prints `in-session` at 23:10Z on 2026-11-01 and `off-session` at 22:30Z, (b) one `snapshot.sh` line is recorded that day, (c) the zero-money proof (go-live 11.7) has passed under pause. This is the cheapest cover for the biggest waived unknown and costs hours, not days.
3. **Memory: record, and add one soft rule for the live period.** Keep D31 (OOM is the only hard stop). Add to every Phase 11 run day the `snapshot.sh day` line in `re-arm-log.md` (the phase already snapshots before and after the arm deploy). Soft rule for the caller to apply: if `mem_available_mb` is below 1000 before a D33 re-roll, do not re-roll; pause entries and consult. Basis: the worst observed overlap cost is about 420 MB at the cutover, so 1000 MB is more than twice that. This is my threshold, not the owner's; record it as such if adopted.
4. **No WiredTiger cap and no `mem_limit` now.** Both are untested prod changes to the data layer or the trader's cgroup made days before live. A `mem_limit` on the trader with no multi-day RSS measurement can produce the OOM-kill it is meant to prevent. Keep them as owner levers for after go-live, as `machine-limits.md:34` already states.

## Question 2: what can run before Monday

Can run now, Saturday or Sunday before 22:00Z (each [ASK] still asked):

- Phase 11 Task 11.1 preflight (read-only). The entry gate passes on the records: `Verification verdict: PASS` count 1 (`paper-daily.md:24`), no go-live journal.
- Task 11.2 [ASK] close go-live run 1 (doc-only; `round-trip.md` has `baseline` and `called off`, no `round_trip: DONE`).
- Task 11.3 [ASK] arm with entries paused. A weekend arm is preferable: it is an image deploy (web recreated, D27) and a trader handover, and it lands when nothing trades. Its handover row is off-session, which does not matter because nothing is being counted.
- Go-live 11.2 preflight (read-only Exness snapshot, conditions, last stored bar).
- Go-live 11.3 [ASK] choose the strategy, 11.4 pause and baseline, 11.5 [ASK] delete the paper subscription, 11.6 [ASK] create and start the `exness` subscription. Recommended timing: Sunday before 22:00Z, so the reopen and the DST shift are observed with the `exness` subscription running and paused. Note for the caller: warm-up now reads 500 stored bars at start (`strategy_app_service.py:45,288`), so the go-live text "about 8 open-market hours" and its `now + 8 h` resume times are stale [V]; the first paused rejection can arrive within minutes of the reopen and the proof may be ready Sunday night. Still hold Resume to Monday per condition 2.

Must wait for an open market and an explicit owner yes:

- Go-live 11.8 Resume (first real money), Monday 2026-11-02 or later, after condition 2.
- The three D33 live re-rolls (Task 11.7): need a running `exness` subscription, `in-session`, the trader 70 min old, the deploy lock free. Suggested order: run re-roll 1/3 while the subscription is in its paused-after-first-entry state with an open position (the task keeps the current pause state, so this is within D33); it exercises the drain and `take_over` with a live position but no order in flight. Run 2/3 and 3/3 with entries on. Choose minutes away from the heavy jobs so the never-exercised resume path is not triggered during a live re-roll: avoid 03:00-03:10Z (`sync_backfill`, `sync_jobs.py:759`), 04:00-04:10Z (`sync_integrity`, `:766`) and the `sync_repair` windows at 00:00Z and 12:00Z (prior observation: the repair can hold the worker 25-49 min).
- The D12 canary needs 20 live entries; it accrues across go-live Phase 12 days after `keep on`.

## Question 3: the one thing the owner should know before saying yes

The waived criteria were the only test of the split runtime across time: a weekend close and reopen, the DST shift on 2026-11-01, and memory beyond one day. Saying yes means those are first observed with real money attached instead of paper. The exposure is bounded by the go-live design (0.01 lot, venue SL/TP, 25 USD daily realized cap, single-order run with pause stored across restarts, about 50-100 USD worst day per go-live `phase-11:315`), and every failure path I traced ends in a skipped entry, a venue rejection that stops the run, or a restart that the venue SL/TP protects, never in an extra order. The owner is trading free paper days for a bounded live cost, not skipping a safety check.

## What to avoid

- Changing mongod flags, adding `mem_limit`, or any `src`/compose change between now and the canary. A code deploy mid-canary also adds image-deploy handovers that D33 does not count.
- Resuming entries on Sunday night: the reopen bar is gap-flagged by design (D10) and the DST shift is unproven in prod; wait for Monday.
- Reading the 138 MB rise over 19 h as a leak; the 10-28 single-app baseline was higher than both later snapshots.
- Treating go-live Phase 11's `now + 8 h` waits as current; they predate the stored-bar warm-up.

## Work checklist for the caller

1. Phase 11 Task 11.1, 11.2 [ASK], 11.3 [ASK] on the weekend; record both snapshots and `OOM_OK` in `re-arm-log.md`.
2. Go-live 11.2-11.6 (three [ASK]s) Sunday before 22:00Z.
3. Sunday 22:30Z and 23:10Z: session check; Monday after the first bars: `snapshot.sh day` into `re-arm-log.md`; go-live 11.7 proof.
4. Go-live 11.8 [ASK] Resume on Monday; the 4 h watch; then the daily loop (go-live 12.x plus Tasks 11.6-11.7).
5. D33 re-rolls at the times above, 1/3 while paused-after-first-entry if the timing allows; apply the 1000 MB soft rule before each.

## Success metrics

Zero-money proof with `submitted 0, other 0`; DST cell `ok` on the first row dated 2026-11-02 or later; three `Live re-roll` PASS lines with `inflight=0`; canary p95 `t0_t6_ms` <= 2000 over 20 entries; every snapshot `OOM_OK` with `mem_available_mb` >= 1000; no unplanned trader `StartedAt`.

## Assumptions

- The owner will accept a self-imposed "Resume not before Monday" ordering as sequencing, not as a new gate (high; it adds no approval and costs under two days).
- Exness read-only calls (snapshot, conditions) work on a closed market (medium; the go-live 11.2 preflight ran on 2026-10-22 at 01:54Z, a Thursday, so a weekend run is untested here).
- `sync_repair` runs at 00:00Z and 12:00Z (medium; from prior observation, `sync_jobs.py:772` was not read to the schedule line).
- MongoDB's WiredTiger cache default applies unchanged (high; `deploy/compose.prod.yml:127-150` sets no `command:` and no memory limit).

Status: DONE_WITH_CONCERNS
Summary: GO for Phase 11 with a weekend arm at zero exposure and the first real-money Resume held to Monday 2026-11-02 after the DST-shifted reopen is observed under pause; no memory cap or limit before arming.
Concerns/Blockers: the first weekend reopen, the DST shift and multi-day memory are observed with live armed; exposure is bounded by the go-live design, and the suggested 1000 MB soft rule and re-roll timing are my recommendations, not owner decisions.
