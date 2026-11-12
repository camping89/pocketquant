---
phase: 5
title: "Ship"
status: pending
priority: P3
effort: "1h"
dependencies: [4]
---

# Phase 5: Ship

## Goal
Push the engine and strategy commits on `develop`. Release to `master` only on the owner's explicit yes. Open a paper subscription for C only if C survived phase 4 and the owner says yes.

## Facts
- Push to `camping89/pocketquant` with the `camping89` gh account: `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" <ref>`. Never print the token.
- A `develop` push runs tests only. A `master` push deploys through CI. A docs-only push gets no CI run.
- The health route is `/health` (`src/pocketquant/app/main_extensions.py:301`). Port 41921 listens inside the api container only. `deploy/vps/11-verify.sh` finds that container by role and runs `docker exec "$API" curl -sf http://localhost:41921/health` (`11-verify.sh:17,101`). The api service has no fixed `container_name` (`deploy/compose.prod.yml:72-76`). The response includes `event_loop_lag_max_s` and `lease_renewed_age_s`.
- Subscriptions can use `broker: "paper"` or `broker: "exness"` (`app/routes/strategy.py:20`).
- Questions to the owner are in Vietnamese, with a leading `Recommended:` line.

## Tasks

### Task 5.1 — Push develop
- **Goal:** develop CI is green on the phase 2 and phase 3 commits.
- **Steps:**
  1. `git status --short` must show no modified source file.
  2. Push `develop` with the command above.
  3. Watch the run: `gh run list --branch develop --limit 1`, then `gh run watch <id>`.
- **Success criteria:** the develop CI run concludes `success`.
- **Verify:** `gh run view <id> --json conclusion` prints `"conclusion":"success"`.

### Task 5.2 — Count stored parameters again
- **Goal:** no stored subscription carries `stop_lookback` at release time.
- **Steps:**
  1. On prod, read-only: `db.subscriptions.countDocuments({"parameters.stop_lookback": {$exists: true}})`.
  2. List the Triple Screen subscriptions with their id, `broker`, `desired_state` and `actual_state`, and no other field: `db.subscriptions.find({strategy_code:"triple_screen"}, {broker:1, desired_state:1, actual_state:1})`.
- **Success criteria:** the count is 0.
- **Verify:** the count is `0`. If it is not 0, stop and ask the owner which integer `stoploss_lookback` each listed subscription should get. Do not write or run a migration.

### Task 5.3 — Ask the owner about the release
- **Goal:** the owner decides with the full live effect in view.
- **Steps:** ask in Vietnamese, with a leading `Recommended:` line. State:
  - **Fills:** live paper is unchanged, because it already acts on 1m bars (phase 2 task 2.1).
  - **Triple Screen subscriptions:** every one in the task 5.2 list, paper and Exness broker alike, moves to `stoploss_lookback=2`, which is 8 entry bars of lookback instead of 5. Name how many are paper and how many are Exness.
  - **Backtests:** every backtest of any symbol whose window starts after that symbol's first 1m bar now fills on 1m bars. It replays about 16 times the events. Give phase 4's events per second and projected time. Stored runs before this change used entry-interval fills; the run snapshot's `fill_interval` tells them apart.
  - **Phase 4 verdict:** one line.
- **Success criteria:** the owner answers yes or no.
- **Verify:** no verification needed; the answer decides task 5.4.

### Task 5.4 — Release, on yes only
- **Goal:** master runs the new code, and the trader is healthy.
- **Steps:**
  1. Fast-forward `master` to `develop` and push it with the command above.
  2. Watch the master CI and deploy run to its end.
  3. On the VPS, run `deploy/vps/11-verify.sh`. For the raw JSON, find the api container with `docker ps --filter label=com.docker.compose.service=api --format '{{.Names}}'` and run `docker exec <name> curl -sf http://localhost:41921/health`. <!-- Updated: Validation Session 1 - health check runs inside the api container -->
  4. Read the Triple Screen subscriptions again, with the same projection as task 5.2.
  5. Right after the release (owner choice, Validation Session 1), run one 1-year backtest of A's config with 1m fills on prod through the API, window 2025-11-09T00:00Z..2026-11-08T23:59Z. Read `/health` inside the api container every minute while it runs, and record `event_loop_lag_max_s` and `lease_renewed_age_s`. If `lease_renewed_age_s` reaches 30 s (`LEASE_TTL_S`, `src/pocketquant/app/roles.py:39`), stop the check and report; do not retry.
- **Success criteria:** CI is green; the health check returns 200 with a lease; every subscription keeps its state; the backtest does not starve the trader.
- **Verify:**
  - `gh run view <id> --json conclusion` prints `"conclusion":"success"`.
  - `11-verify.sh` reports `App /health` as pass, and `lease_renewed_age_s` stays below 30 s (`LEASE_TTL_S`, `src/pocketquant/app/roles.py:39`) in every reading during the backtest.
  - Each subscription's `desired_state` and `actual_state` equal their task 5.2 values.

### Task 5.5 — Paper subscription for C, only if C survived phase 4
- **Goal:** the owner decides on a 3 to 6 month paper incubation of C (rubric G6).
- **Steps:**
  1. If phase 4 dropped C, skip this task.
  2. Ask the owner in Vietnamese, with a leading `Recommended:` line, whether to open one paper subscription with C's exact parameters (`stoploss_buffer_atr=0.0`). It would measure fills, spread, slippage and swap.
  3. On yes, create it through the API with `broker: "paper"`.
- **Success criteria:** the owner's answer is carried out.
- **Verify:** on yes, `GET` the new subscription shows C's exact parameters and `broker` `paper`.

### Task 5.6 — Docs
- **Goal:** a reader knows how backtests fill.
- **Target files:** `docs/system-architecture.md`.
- **Steps:**
  1. Add one or two lines:
     - a backtest fills on 1m bars when the symbol has a 1m bar at or before the start, as live does;
     - a bucket with no 1m bar is filled by the coarse rule;
     - without 1m coverage, the backtest fills on the entry interval;
     - the run snapshot's `fill_interval` records which.
  2. Commit `docs(architecture): state how backtests fill on 1m bars` and push `develop`. A docs-only push gets no CI run.
- **Success criteria:** the lines exist, and the file stays under 800 lines.
- **Verify:** `grep -n "fill_interval" docs/system-architecture.md` finds the line, and `wc -l docs/system-architecture.md` prints at most 800.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same
failure evidence to the user. Never continue by self-reasoning.
