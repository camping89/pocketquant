---
phase: 10
title: "Close Open Metrics and Archive"
status: completed
priority: P3
effort: "0.5d"
dependencies: [9]
---

## Context

The 2026-09-24 run-through (`completion-report.md`) left five rows open: 4, 5, 10, 11 and 13. Counsel: `plans/reports/kongming-261022-1145-asset-class-open-items.md` (its "Verified facts" section holds the file:line evidence). What changed since:

- Row 4: `cascade.partial_aggregate` was removed on 2026-09-24 by user decision (`a9233245`, plan.md Session 11). The cascade no longer reports short buckets. The other row-4 events are structural on the delayed free feed and covered by the data-lag flag.
- Row 5: prod data for the old `:CME_MINI`/`:CBOT_MINI` names was deleted on 2026-10-12. The symbols were re-seeded as `ES1!`/`NQ1!`/`YM1!:TRADINGVIEW` on 2026-10-13, after `f101f4ee` stamped `session_date` on every write path. Expected unstamped count: 0.
- Row 10: `job_history` keeps per-symbol `skipped/closed` details for 30 days and survives deploys, so the weekend of 2026-10-17/18 is measurable.
- Row 11: `sync_verify_cascade` results live only in the app log. The container last started 2026-10-22T02:01:48Z, so 24 runs exist after 2026-10-23T03:05Z (10:05 Bangkok). No deploy before then.
- Row 13: G2 needs a sizing decision. Recommended default: defer, since no strategy is profitable and no futures strategy is pursued (`plans/261019-1957-exness-go-live/plan.md`, decision 2026-10-22 08:55).

This phase changes no code. Its one possible prod write is the Task 3 repair, behind an [ASK].

**Measured 2026-10-22 ~10:40-10:50 UTC (Tasks 1-5, read-only).** Counsel on the misses:
`plans/reports/kongming-261022-1745-phase8-row10-row11-failures.md`.

- Task 1: 9 tracked, including the three `:TRADINGVIEW` futures. Pass.
- Task 2 (row 10): 2,874 `sync_1m` runs in the window; every futures detail `skipped/closed`
  (2,874 per symbol), zero `completed`. `sync_backfill` 2026-10-17T03:00Z inserted one `1w` bar
  per symbol: the week opened 2026-10-11T22:00Z (`session_date` 2026-10-12) that closed Friday
  21:00Z, created 03:00:27Z. The 10-18 run inserted 0. Friday's ES 1d bar was written
  2026-10-17T00:06Z by `rest_repair`, after the close. Pass in substance; the "no backfill
  insert" clause was mis-specified (a closed week's bar must land once).
- Task 3 (row 5): 0 unstamped 1d/1w bars (ES 4993/1500, NQ 4993/1406, YM 4993/1264). Closed.
- Task 4 (row 11): `StartedAt` 2026-10-22T02:01:48Z, 8 runs. ES 1 ok, 5 alerts (each 1 of 11),
  2 vendor `symbol_failed`. Cause is the verify/sync race; fix moved to Phase 8, re-measure in
  Phase 9.
- Task 5 (row 4): `misaligned_bars_dropped` 7 lines, all from the 03:01Z backfill dropping
  2000-2012 holiday 1d/1w bars (per symbol from `job_history`: ES 32, NQ 32, YM 35 bars);
  `integrity.issues_found` 3 per symbol, all 04:00-04:06Z; `no_progress` ES 14, NQ 8, YM 59
  (ES 7 and NQ 6 at minutes :00/:01, during the verify burst); `stuck_threshold_crossed` 0.
- Row 13: user chose leverage routing with a futures-only paper balance (Phase 8) and a paper
  `engulfing` 15m ES session (Phase 9).

Remaining here after Phase 9: Task 6 records and Task 7 archive.

## Constraints

- Work context: `D:/w/_me/algotrading/pocketquant`, branch `develop`, English only. Read `CLAUDE.md`.
- Creds live in `../pocketquant-config`. Never print a token, password or connection string. Print counts only.
- Prod reads are read-only, except the Task 3 repair after an explicit yes.
- Every `gh` call uses `GH_TOKEN=$(gh auth token --user camping89)`. A `develop` push runs tests only and does not deploy.
- Ops recipe:
  - Key: `mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key`.
  - Each command: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" '<cmd>'`. The shell keeps no variables between commands.
  - Mongo probes: `docker exec -i pocketquant-app python - <<'EOF' ... EOF`, reading `mongodb_url` and `mongodb_database` from `pocketquant.core.config.Settings`. Collections: `bars`, `job_history`, `tracked_symbols`, `subscriptions`.
  - Delete `.cache/ssh/vps_key` at the end and before any early exit.

## Tasks

### Task 1 — Tracked set (read-only)

- Count `tracked_symbols` and list their `symbol` fields. List `subscriptions` with symbol, broker and status.
- Pass: `ES1!:TRADINGVIEW`, `NQ1!:TRADINGVIEW` and `YM1!:TRADINGVIEW` are tracked.
- If fewer than three futures are tracked: stop measuring, record "futures no longer tracked", mark rows 4, 5, 10 and 11 "moot", and go to Task 6.

### Task 2 — Row 10, weekend quiet (read-only)

- Query `job_history` for `job_id="sync_1m"` with `started_at` in [2026-10-16T21:01:00Z, 2026-10-18T22:00:00Z]. Unwind `details`. For symbols matching `:TRADINGVIEW`, group by (status, error) and count.
- Query `job_id="sync_backfill"` runs started 2026-10-17 and 2026-10-18 at 03:00Z.
- Pass: every futures group is `status="skipped"`, `error="closed"`; zero futures details with `status="completed"`; no futures `sync_backfill` detail with `bars_inserted > 0`.
- Record the counts and the exact window.

### Task 3 — Row 5, `session_date` (read-only first) [ASK on repair]

- For each of the three futures and each interval in {`1d`, `1w`}: count `bars` documents, and count those with `session_date` missing or null.
- All unstamped counts 0: row 5 is closed; no repair.
- Any count above 0:
  1. Confirm in `src/pocketquant/core/infra/persistence/repositories/bar_repository.py` that a direct backfill overwrites a stored row's `session_date`. If it is insert-only, stop and report.
  2. [ASK] "Recommended: yes, repair N unstamped rows. Facts: <counts>. Plan: `mongodump --archive` of `bars` for the three symbols and intervals 1d/1w to `/opt/pocketquant/backups/pre-session-date-repair-<UTC stamp>.archive`; then per symbol, inside the container, `POST /api/v1/market-data/tracked-symbols/<symbol, ':' as %3A>/backfill?interval=1d&mode=direct&n=5000` with header `X-Admin-Token: $ADMIN_TOKEN` on `localhost:41921`, the same with `interval=1w`, 20 s apart (the scraper drops bursts); then recount."
  3. Only an explicit yes runs it. Record the backup path and the before and after counts.
- Rollback: `mongorestore --archive=<backup> --nsInclude=<db>.bars` after deleting the repaired rows of those symbols and intervals.

### Task 4 — Row 11, 24 runs with `divergence_count=0` (read-only)

- `docker inspect -f '{{.State.StartedAt}}' pocketquant-app`. If later than 2026-10-22T02:01:48Z, a deploy happened: use the new StartedAt and restart the 24 h count.
- `docker logs pocketquant-app --since <StartedAt> 2>&1 | grep sync_verify_cascade.ok | grep 'ES1!:TRADINGVIEW'`: count lines and their `divergence_count` values. Also grep `cascade.divergence_alert` for ES.
- Pass: at least 24 consecutive lines with `divergence_count=0`, and no ES alert line.
- Fewer than 24 lines because 24 h have not passed: record "pending; measure after <StartedAt + 25 h>; do not deploy before then", stop before Task 6, and tell the user to re-run this phase then.

### Task 5 — Row 4, re-scope with a one-day count (read-only)

- Over the Task 4 log window, count for each of ES, NQ and YM: `market_data.sync.misaligned_bars_dropped`, `integrity.issues_found`, `market_data.sync.no_progress`, `market_data.sync.stuck_threshold_crossed`.
- Record per event: count, first and last timestamp, and whether it clusters at 22:00Z (session open) or 04:00Z (integrity run).
- Decision to record: the `partial_aggregate` clause was retired on 2026-09-24; the remaining events are structural on the delayed free feed and covered by the data-lag flag; the 2026-11-30 full-week watch is dropped.
- No code change. If the user wants the daily `integrity.issues_found` line gone, the follow-up is Prompt 2 of the kongming report.

### Task 6 — Row 13 and records [ASK]

- [ASK] "Recommended: defer G2. Alternatives: fund paper futures accounts to at least 400,000 USD (`PAPER_INITIAL_BALANCE`, global), or route `RiskConfig.leverage` into futures paper sizing (small code, one new caller; today only Exness subscriptions use it, `src/pocketquant/engine/live/strategy_reconcile_app_service.py:179-184`)."
- In `completion-report.md`, add a dated addendum. Do not rewrite the 2026-09-24 text. Update rows 4, 5, 10, 11 and 13 with the measured numbers and decisions.
- In `plan.md`: set front-matter `status: completed`, set this phase's status to completed, and add "Session 12" with the decisions and numbers.

### Task 7 — Archive

- `git mv plans/260921-1436-asset-class-index-futures plans/archive/260921-1436-asset-class-index-futures`.
- `grep -rn "260921-1436-asset-class-index-futures" plans docs README.md CLAUDE.md --include=*.md` and fix links that break. Keep report filenames unchanged.
- `uv run ruff check src tests scripts` stays green (no code changed).
- Commit `docs(plans): close and archive the asset-class index-futures plan`, including `plans/reports/kongming-261022-1145-asset-class-open-items.md`.
- Push: `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin`.

## Success criteria

- Every row of the completion-report summary is Pass, Closed, Dropped, Deferred or Moot, with a date and a number or decision.
- `git diff --stat` on `src web tests scripts` is empty.
- The plan dir is under `plans/archive/`, `develop` is pushed, and `.cache/ssh/vps_key` is deleted.

## Risks and rollback

- Risk: one prod data repair (Task 3), only if unstamped rows exist and the user says yes. Rollback: restore the `bars` dump.
- Risk: a prod deploy before the Task 4 window completes restarts the 24-run count. Do not deploy during this phase.
- Everything else is read-only or plan text; rollback is `git revert`.
