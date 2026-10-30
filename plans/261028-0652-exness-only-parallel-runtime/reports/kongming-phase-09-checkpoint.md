# Kongming checkpoint after Phase 09 (go/no-go for Phase 10)

Date: 2026-10-30 (Asia/Bangkok). Advisory only. HEAD `2efc7719` = `origin/develop`; `origin/master` = `ee298e78`.

## TL;DR

GO for Phase 10. Nothing in Phase 09 must be fixed first. Following `docs/governance/documentation-rules.md` over the plan's value-copying doc steps was correct, and the recorded correction is adequate. Phase 10 needs three small text changes before its first judged row: `leases.sh < /dev/null` inside the two `bash -s` heredocs, an explicit "rows 1..N count, row 0 does not" rule, and `plan.md`'s phase table row for Phase 09 set to Done. Everything else the caller raised (row 1 timing, D36, heavy-job resume) is already handled by the plan text or is record-only.

## Verified facts (checked against the repo, not from the caller's summary)

- Task 9.1 Verify re-run locally: `deploy/vps/10-deploy.sh:0`, `deploy/vps/11-verify.sh:0`, `0`, `syntax-ok`, `3`.
- Binance fix `ab2bb9eb`: `run_forever` polls `_subscriptions` every 0.1 s while `_running` and breaks without connecting when stopped; the placeholder URL branch is gone (`git grep -F 'f"{_WS_BASE}/ws/"' -- src` prints 0). Shape matches the plan's step 2-3; the new constant `_SUBSCRIPTION_POLL_S` is a module constant, not a new flag or config key.
- Docs commit `7695ccee` touched 7 files, +32/-26. `docs/system-architecture.md` is 47 lines, `docs/deployment.md` 229. The repo-wide stale-topology gate and the TV gate both print nothing. `docs/deployment.md` quotes commands whole and points at `10-deploy.sh`, `app/roles.py::drain_trader`, `sync_jobs.py::_tracked`, `enqueue_missed_catchups`; it copies no grace period, TTL, fraction or container count.
- Plan correction `ee298e78` adds the 2-line "Correction 2026-10-30" block to `phase-09-cleanup-and-docs.md` only.
- `plan.md:92` still lists Phase 09 as `Pending` while `phase-09-cleanup-and-docs.md` frontmatter says `status: done`.
- Phase 10 Task 10.1 step 1 block run locally on `develop`: `12`, `4`, all eleven field tokens >= 1, `LOG_FORMAT=console` count `1`. The name check will pass.
- D36 session check, run locally with the code's calendar (`EXNESS_CALENDARS`, id `EXNESS_XAUUSD`, `is_open`): `2026-10-30T06:44:27Z` -> `in-session`, so row 1 counts under D36 if it passes. Also: `2026-10-30T20:50:00Z` and `21:50:00Z` -> `off-session` (Friday close), `2026-10-31T06:00Z` -> `off-session`, `2026-11-02T00:00Z` -> `in-session`.
- `deploy/vps/leases.sh` runs `docker exec -i "$t" python -c '...'` inside `read -r w tr n < <(...)`. `docker exec -i` attaches the script's stdin. When the script arrives through `ssh ... 'bash -s' <<'EOF'`, bash reads the pipe unbuffered so a child can consume the rest of the script; the lines after the `leases.sh` call are swallowed. This is the gotcha the caller hit in Task 9.9 and it is present in Phase 10 Task 10.3 step 2 and Task 10.4 step 2.
- `10-deploy.sh` roll order: `roll api 120`, `roll worker 120`, `wait_lease worker 60`, `roll trader 240`, `wait_lease trader 60`; `save_logs` writes `<svc>-<id12>-<ts>.log.gz` after `docker stop` (lines 93-131). `sync_repair` cron is `0 */12 * * *`; the file comment names `sync_backfill` as the heavy daily 03:00 UTC run; `stop_worker` waits `WORKER_STOP_S = 90.0` (`app/roles.py:46`).

## Q1. GO / NO-GO for Phase 10

GO. The Phase 10 entry gate passes on current state: the tree is clean, `origin/master:deploy/vps/10-deploy.sh` has no `pocketquant-app` (a704b745 is on master), `handover-log.md` has one `| 1 |` row, `paper-daily.md` does not exist yet (gate 4 prints nothing, which is allowed), the baseline line exists, and the five helpers were counted by the Phase 09 gate.

No Phase 09 gap is blocking. Two non-blocking loose ends:

1. `plan.md:92` Phase 09 row says `Pending`. Fix it to `Done` in the next `docs(plans)` commit (Phase 10 Task 10.7 step 5 is the natural place, or a one-line commit now). It is a record inconsistency, not a gate.
2. The new `docs/deployment.md` Restart-while-live steps rest on `StrategyAppService.take_over` restoring direction from open positions (`engine/strategy/strategy_app_service.py:144`). That is CI-tested per the plan's Direction criterion; it has not been exercised in prod with an open Exness position because live is off. The doc states the current code behaviour, which is what governance asks for. Phase 11's D12 canary is where it gets exercised. No change needed now.

## Q2. Governance over the plan's doc steps

Sound, and the right call. Reasons, in order of weight:

- `CLAUDE.md` says read and follow every file in `docs/governance/` before any work. `documentation-rules.md` line 1 of the Line Test ("Owned: delete") forbids copying names, numbers, defaults, log events and schedules into a doc. Plan Task 9.2 steps 3-4 and Task 9.3 steps 2-3 asked for exactly that (TTL 30 s, renew 10 s, poll 0.5 s, rate fractions, grace periods, "8 containers", event names). Governance also says `plans/` are records, not authority. The plan predates the rule (plan 2026-10-28, rule applied 2026-10-29 per the docs purge). A newer owner-approved rule wins over an older plan step.
- The result passes the plan's intent: the stale-topology gates are empty, the three services and the rolling handover are stated as a cross-file decision, the no-deploy-window decision is recorded with its rejected alternative, and the runbook commands were tested on prod (`/health` 200 through `compose exec -T api sh -s` + `curl -H @-`).
- The recorded Verify adjustment is adequate: it lists each replacement grep and its threshold, says which counts were dropped and why, and sits in the phase file next to the tasks it amends. One nit: it says "as run" but records no outputs. The caller's summary has them; appending the five printed values in one line would make the record self-contained. Optional.

One judgment call worth naming, not reversing: governance rule 4 keeps negative knowledge and cross-process rules. The plan wanted "standby never connects a broker" and "only the trader lease holder writes `bar:current`". The shipped architecture bullet covers the first at decision level ("Each acts only while it holds its lease"); the `bar:current` rule is not in the doc. If a test already enforces it, rule 2 says leave it out; if not, it is a one-sentence candidate for the roles bullet. Not a Phase 10 blocker.

## Q3. Phase 10 changes given these results

Ordered by importance.

1. **`leases.sh` stdin (must fix before Task 10.3 runs).** In Task 10.3 step 2 the `leases.sh` call is followed by `cat "$V/snap-$T.txt"`, the `oom_at_capture` line and the whole `peak` awk block. With the current text those lines never run, so the D25 row has no snapshots and no peaks and the `oom_at_capture` cell is missing. In Task 10.4 step 2 only `rm -f /tmp/pq-day-*.log` is lost (harmless; the next run overwrites with `>`). Fix in plan text only, no VPS change: write `bash /opt/pocketquant/bin/leases.sh < /dev/null` at both call sites. Moving the call to the last line of each heredoc also works but `< /dev/null` is the one that still protects a future edit. Do not change `deploy/vps/leases.sh` for this: `11-verify.sh` calls it without a heredoc and CI already passes with it; Conventions say Phases 08-11 install nothing on the VPS. Task 9.9 step 10 and Task 10.2 step 4 use `exec -T ... <<'PY'`/`sh -s` on purpose and are fine.

2. **Row counting.** Row 0 (cutover) has verdict `PASS` and the same table shape, so a naive grep in Task 10.6 step 1 ("10 PASS rows without `(off-session)`") counts it. Task 10.7 step 2 says "after the last fix", and the last fix (6142249f, shipped by D-6) came after row 0, so row 0 does not count; the phase Goal also says D-6 is row 1. State it once in Task 10.6 step 1 and Task 10.7 step 2: count rows numbered >= 1. Row 0 stays as the cutover record.

3. **Row 1 timing is already correct in the plan text.** Task 10.3 step 1 leaves a row pending when its start is under 65 min old and skips Task 10.6 in that run. Row 1 is judgable from `07:49:27Z`; the next deploy is allowed from `07:54:27Z` (70 min rule) and only once row 1 is judged. A Phase 10 run started now (about 07:00Z) legitimately does 10.1, 10.2 [ASK], 10.4's day snapshot, then exits `NOT_YET` from 10.7. That is not a failure. The Re-run rule allows a second run the same day.

4. **D36 for `XAUUSD:EXNESS`.** The check is the code's calendar, which is the right owner. Practical consequence from the local run: today (Friday) rows started after about `20:44Z` are off-session, Saturday is off-session, and the code reports Monday `2026-11-02T00:00Z` as in-session. Row 1 at `06:44:27Z` is in-session. Nothing to change; the runner should expect `off-session` skips on the weekend and plan the ten counted rows across weekdays. The 14 paper days are the long pole anyway.

5. **Heavy-job resume not yet exercised in prod.** Not an acceptance criterion and not a gate; the code is CI-tested and reviewed (`reports/code-reviewer-resumable-heavy-jobs.md`, nothing critical, M1-M3 fixed). With no deploy window, a random overlap over 10+ deploys is plausible but not guaranteed. Cheap, record-only option: start one of the five re-rolls at about `02:58:30Z` on a weekday (in-session), so the worker stop lands near `03:00-03:01Z` while `sync_backfill` runs (116 s on 2026-10-30). Estimate from the roll script: api roll about 45-80 s, worker becomes healthy about 30-40 s later, then `docker stop old`; label this an estimate. For that row, run the Task 9.9 step 10 notes block (it has no `leases.sh` call, so the stdin gotcha does not apply) and paste it as `## Row <n> notes` above the table. If it never overlaps, say so in the machine-limits summary; do not force it.

   Inference, not verified: if a heavy job still blocks the event loop for longer than the worker's 120 s grace, SIGTERM handling is delayed, docker SIGKILLs the worker, the lease is not released, and the new worker takes over after the 30 s TTL and marks the row `interrupted` through the orphan path (review finding L3, accepted). Both paths lead to the same catch-up resume. The CME calendar that caused the long stalls was deleted in Phase 03, so the weekly `sync_repair` p50 in Task 10.5 will show whether this still matters.

6. **Row 1 verdict inputs to double-check when judging.** `release_lines` must be read from the saved `trader-<id12>-*.log.gz` of the D-6 old trader (`old-trader-20261030T064424Z.txt`). The old trader at D-6 was the container that took over at the cutover, so its log holds exactly one `trader.lease_released`. The new trader's `trader.takeover` and `trader.takeover_complete` were each counted once by Task 9.9. Nothing suggests row 1 will fail.

## What to avoid

- Do not patch `leases.sh` on the VPS by hand or add `-n`/`-T` flags there; keep the helper set as Phase 08 installed it and fix the callers in the plan text.
- Do not count row 0 toward the ten, and do not re-judge it.
- Do not add a prod heavy-job-resume gate to Phase 10 or Phase 11; D31/D34 keep Phase 10 record-only outside the OOM rule and the handover/paper criteria.
- Do not copy the newly dropped values (TTLs, fractions, grace periods) back into the docs to "complete" Task 9.2; governance owns that decision now.

## Work checklist (for the runner, before or during the first Phase 10 run)

1. Edit `phase-10-prod-verification.md`: `bash /opt/pocketquant/bin/leases.sh < /dev/null` in Task 10.3 step 2 and Task 10.4 step 2.
2. Edit Task 10.6 step 1 and Task 10.7 step 2: "rows numbered >= 1".
3. Edit `plan.md:92`: Phase 09 `Done`.
4. Optional: append the five Verify outputs to the Phase 09 correction block.
5. Run Phase 10 from the entry gate; expect `NOT_YET` from 10.7 on the first run today; re-run after `07:54:27Z` for row 1 and the first re-roll.
6. Optional: aim one weekday re-roll at about `02:58:30Z` and attach the Task 9.9 step 10 notes to that row.

## Assumptions

- The CI deploy that moved `master` to `ee298e78` ran the full pipeline (caller: run 41015889660, verdict count 1). Not re-fetched here. Confidence high.
- `/opt/pocketquant/bin/leases.sh` on the VPS is the same file as `deploy/vps/leases.sh` on `develop` (Phase 08 installed it from the repo). Confidence high; if it differs, the `< /dev/null` fix still holds for any `docker exec -i`.
- The roll timing estimate (api roll 45-80 s, worker stop near T+80-130 s) comes from `start_period`/`interval` values in `deploy/compose.prod.yml` and the `sleep 6`; it was not measured. Confidence medium; use the row 0/1 `deploy-<T>.txt` timings to refine.
- `sync_backfill` runs at 03:00Z daily; taken from the comment in `sync_jobs.py` and the row 0 notes, not from the cron line itself. Confidence medium-high.
- Phase 10 is run by the same host that can run `uv run python` against the calendar module locally; if not, the plan's `exec -T trader python -c` form is the one to use. Confidence high either way.
