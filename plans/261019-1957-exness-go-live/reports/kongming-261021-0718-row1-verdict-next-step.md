# Kongming: E2 row 1 verdict and next step (2026-10-21 07:18 Bangkok)

## TL;DR

Row 1 is a PASS with a note, which is what `712eca1` already records. The first C3 `FAIL` was a measurement artefact: C3 as written checks the just-closed minute while `sync_1m` is still writing it. Add a two-line timing note to T8.7 (no pass-rule change, no user approval needed). Phase 05 is not blocked: the raised ceiling is committed, pushed and CI-green, so the next step is Phase 06.

## Verified facts (file:line)

- C3 window includes the just-closed minute. `check_integrity` sets `end = get_bar_start(now, interval)` and expects every calendar instant `< calendar.bar_start(now, interval)` (`src/pocketquant/engine/market_data/app_services/integrity_jobs.py:71-73,103-104`). At 22:34:02Z the 22:33 bar is expected.
- The 1m bar can only arrive through `sync_1m`. "Cron sync_1m + cascade is the sole MongoDB writer" (`src/pocketquant/engine/market_data/app_services/bar_app_service.py:53`); the WS feed writes no 1m bars. `sync_1m` is a cron at `second=2` of every minute (`src/pocketquant/engine/market_data/app_services/sync_jobs.py:843-847`), fetching 100 bars per tracked symbol (`:457-478`). Row 1 measured its p95 at 12573 ms.
- So C3 at 22:34:02Z started at the same second as `sync_1m` and read the DB before the write. The read-only re-run 42 s later found the bar. The row-1 `VENUE_HAS 22:33:00` line is the race, not lost data.
- Repair is bounded. `repair_integrity` deletes only `misaligned_ids` (`integrity_jobs.py:143-144`), then resyncs 5000 bars with `skip_filter=True` (`:161-170`) through `SyncService.sync_one` → `insert_many` (`src/pocketquant/engine/market_data/sync_service.py:171`) → per-bar upsert that `$set`s OHLCV, `updated_at` and `source` only when the stored OHLCV differs (`src/pocketquant/core/infra/persistence/repositories/bar_repository.py:71-78`). It cannot delete aligned bars; it can overwrite a bar whose values changed at the venue and re-tag it `rest_repair`. With `misaligned 0`, repair would have deleted nothing.
- Pass rule step 3 (`phase-08-validation-spread-backtests-paper-week.md:253`): on a C3 `FAIL`, repair once, re-run C3, still `FAIL` → the row fails. The intent stated at `:308`: "a gap the venue can fill fails the row".
- Phase 05 state: `96c4675` ("Code-metric ceilings rise to 0.4862 and 93") changed `pyproject.toml` from 0.4861/92 to 0.4862/93; `HEAD` = `origin/develop` = `f79b54b`; CI run 39520339312 for `f79b54b` concluded `success`; `phase-05-safeguards-pause-and-sizing.md` front matter is `status: completed`; `uv run python scripts/code_metrics.py --ratchet` exits 0 locally.
- E2 gates nothing (`plans/261019-1957-exness-go-live/plan.md:78`). Phase 08 of the go-live plan already lists the next rows (row 2 Sat 2026-10-24 03:00Z) and the subscription ids (`phase-08-ship-with-live-off.md:16`).
- Phase 12 calls the same `/integrity/check` for `unexpected_count` only, record-only (`phase-12-observation-and-go-live.md:97`; `plan.md:121`).
- `plan.md:147` lists "The ratchet needs a higher ceiling" under "Stop and report (no improvised fix)", while Phase 05's gate says `Recommended: raise the ceiling` (`phase-05:25`). The worker followed the more specific gate.

## Q1. Row 1 verdict

PASS with a note (the note already sits in the Integrity column of row 1). Reasoning:

- The rule's intent is "stored bars match what the venue can give". At the re-check, they did: XAU 1m 0/0, EUR 1m 5/0 with the only gap venue-empty.
- The rule's step 3 (repair then re-check) exists to give a fillable gap one chance to fill. Here the regular `sync_1m` filled it 42 s later with no repair. The step's purpose was met by a weaker action.
- Inference (not verifiable from the text): the read-only re-run is a valid substitute only for this class of failure, a gap whose end is within one or two minutes of the check time. For an older fillable gap (outside `sync_1m`'s 100-bar lookback) a re-run proves nothing and the repair step stays mandatory. Rows 2-4 must keep step 3 as written for such gaps.
- Procedure deviation to record (already recorded): repair was not run. No further edit to the row is needed. The Failure Protocol and the "failing row stops the schedule" rule did not trigger because the row never failed under step 3's definition.
- The two `exness.rate_limited_retry` lines C3 produced are record-only (`RL`, pass rule item 5) and do not affect row 2.

## Q2. C3 is racy by design, and the minimal fix

Yes. The check is built for the daily `sync_integrity` job, where a one-minute edge does not matter; run 2 s after a minute boundary it will report the last minute missing whenever `sync_1m` has not finished (p95 ~12.5 s, misfire grace 120 s).

Minimal fix, procedure text only, in T8.7 (two sentences; no change to the C3 script and no change to what passes or fails):

1. Under **Commands → C3**: "Start C3 when the UTC clock reads second 20 or later (`sync_1m` fires at second 2 and takes up to ~15 s), so the last closed minute is already stored."
2. Under **Pass → 3**: prepend "If the only `VENUE_HAS` range ends within 2 minutes of the check time, re-run C3 once after 60 s before repairing." Then the existing text follows unchanged.

Approval: not required. The pass criterion (misaligned 0, every gap venue-empty, repair-then-recheck on a fillable gap) is the user's decision of 2026-10-20 and stays intact; the edit fixes when the measurement is taken. Record it with an `<!-- Updated: 2026-10-21 ... -->` comment per the file's convention and mention it in the next message to the user. Dropping or replacing the repair step would be a pass-rule change and would need an [ASK]; do not do that.

Rejected alternative: ending the window at `now − 2 min` inside `check_integrity`. It is a `src/` change to a function the daily job and Phase 12 also use, Phase 08 forbids code fixes inside the schedule (`:281`), and the plan's "no change for a measurement quirk" stance applies.

## Q3. Effect on the go-live plan

None on sequencing: E2 gates nothing (`plan.md:78`). Row 1 PASS is the fact Phases 10, 11 and 12.6 state. Two carry-overs:

- Deploy A (Phase 08) will restart the container before row 2; row 2's C1 `S` changes, which the phase already calls not a failure.
- Phase 12's integrity call (`unexpected_count`, 1m, 1 day) has the same timing exposure. It is record-only, so no edit is needed; if an observation row runs within 15 s of a minute boundary, the count may read one high. Mention it when writing that row, nothing more.

## Q4. Next steps in order

1. Phase 05 ratchet [ASK]: the answer is "raise the ceiling" (Phase 05 gate text, user memory: KISS over padding). In fact it is already applied and shipped (`96c4675`, pushed, CI green). If the worker is still waiting on a stale prompt, reply `raise` and have it confirm `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)"` and the green run; do not re-run the phase.
2. Optional one-line cleanup for consistency: in `plan.md:147` change "The ratchet needs a higher ceiling" to "The ratchet needs a higher ceiling outside the Phase 05 [ASK]" (or delete the item). Not blocking; avoids the next worker reading a contradiction.
3. Apply the two T8.7 sentences from Q2 (agent edit, `<!-- Updated -->` comment, commit as `docs(plans): ...`), and tell the user in the same message as the row-1 verdict.
4. Dispatch Phase 06 (SPA; needs 01, 02, 05, all completed), then 07, then Phase 08 deploy A at its [ASK].
5. E2 row 2 on Sat 2026-10-24 03:00Z (10:00 Bangkok): market closed, so the race cannot bite; row 3 (Mon 03:00Z) and row 4 are the ones the timing note protects.

## Assumptions

- The caller's "Phase 05 worker is blocked at [ASK]" is stale: the commit and push are 2 minutes old relative to the stated "now". Confidence high (git and CI verified). If a worker process is still waiting, the reply is `raise` and nothing else changes.
- The 22:33 bar landed through `sync_1m` at 22:34:02Z+, not through any other writer. Confidence high (sole-writer statement at `bar_app_service.py:53`, cascade writes higher intervals only).
- `sync_1m` p95 of 12.5 s is representative; the "second 20" rule is a heuristic, not a bound. If a future C3 at second ≥ 20 still shows a fresh-minute `VENUE_HAS`, the 60 s re-check in step 3 covers it. Confidence medium.
