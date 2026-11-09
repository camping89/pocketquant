---
phase: 4
title: "Track B release to master and post-deploy checks"
status: pending
priority: P2
effort: "0.5h + CI time"
dependencies: [3]
---

# Phase 04: Track B release to master and post-deploy checks

## Goal

With the owner's explicit yes, `master` equals `develop`, the master pipeline deploys, prod lists `hitnrun2`, live stays off, the trader reconciles without failures, and the three existing subscriptions run unchanged.

## Context

- `develop:master` is an explicit owner ask every time (`CLAUDE.md` memory rule, `docs/deployment.md` Branches). A `master` push runs tests, builds and deploys; a green run needs no extra check (`docs/deployment.md` Deploy, Verify). Images are tagged `sha-<7 chars>`; a manual re-roll is `IMAGE_TAG=sha-<short> bash deploy/vps/10-deploy.sh` (`docs/deployment.md` Restart while live).
- No `exness` subscription exists (Phase 01 baseline: three paper subscriptions), so the "Restart while live" steps do not apply. The deploy rolls the trader; the three paper subscriptions warm up again in the new trader, which is a restart, not a config change (A6).
- Reconcile log events: `reconcile.failed`, `reconcile.load_failed`, `reconcile.unknown_template` (`src/pocketquant/engine/live/strategy_reconcile_app_service.py`).
- Ops names: plan.md Ops recipe.

## Entry gate

1. Conventions EG (1)-(3); the previous report is `reports/phase-03-hitnrun2-strategy.md`.
2. `git fetch -q origin && git diff --stat origin/master origin/develop -- src tests | tail -1` contains `changed`.
3. KEY, then LIVECHK prints exactly `trader_live=False`.

On a miss, run `rm -f .cache/ssh/vps_key`, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 04 after <UTC time>
```

## Files

- Create: the phase report. Repo code: none.
- Prod writes: the release push (deploy).

## Tasks

### Task 04.1 — Pre-release record

**Goal:** the rollback tag and memory baseline are recorded.

**Target files and symbols:** `origin/master`; VPS memory.

**Steps:**
1. Record `prev_master=$(git rev-parse --short=7 origin/master)` as `prev_master=<sha7>`.
2. FREE; record `free_before=<Mem: line>`.
3. Record `commits_to_release=` with the output of `git log --oneline origin/master..origin/develop | wc -l`.

**Success criteria:** the three lines exist.

**Verify:** `grep -c -E "^(prev_master=[0-9a-f]{7}|free_before=Mem:|commits_to_release=[1-9][0-9]*)" plans/261109-1349-1m-strategy-evidence/reports/phase-04-release-hitnrun2.md` prints `3`.

### Task 04.2 — [ASK] release

**Goal:** the owner approves the release.

**Target files and symbols:** none.

**Steps:**
1. Ask in Vietnamese (intent): "Release hitnrun2 to prod? It ships one new strategy file and its registry entry (`hitnrun2`, one 1m interval, cost filter `min_cost_multiple` reading the symbol spec) plus tests; <commits_to_release> commits; no schema, route or config change; no subscription is created; live stays off (`trader_live=False`). The deploy restarts the trader, so the three paper subscriptions warm up again. Rollback: re-roll `sha-<prev_master>`." Lead with `Recommended: yes`, reason: CI is green on develop and nothing on prod uses the new strategy until Phase 06.
2. Record `release_ask=<reply>`. Only an explicit yes continues.

**Success criteria:** the report holds the owner's yes.

**Verify:** no verification needed (Task 04.3 runs only after the recorded yes).

### Task 04.3 — Release push and master run

**Goal:** `master` equals `develop` and the master pipeline succeeds.

**Target files and symbols:** `origin/master`.

**Steps:**
1. Record `pushed_at=<output of date -u +%Y-%m-%dT%H:%M:%SZ>`.
2. `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop:master && git fetch origin`; then `test "$(git rev-parse origin/master)" = "$(git rev-parse origin/develop)" && echo released` prints `released`.
3. `sleep 15`, then poll `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch master --limit 1 --json headSha,status,conclusion` every 60 s until `status` is `completed`. Record the run id.

**Success criteria:** the master run concludes `success` on the released sha.

**Verify:** `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch master --limit 1 --json headSha,status,conclusion -q '.[0] | "\(.status) \(.conclusion) \(.headSha)"'` prints `completed success <sha>` with `<sha>` equal to `git rev-parse origin/develop`.

### Task 04.4 — Post-deploy checks

**Goal:** prod serves `hitnrun2`, live is off in the new trader, reconcile is clean, and A6 holds.

**Target files and symbols:** `GET /api/v1/backtest/strategies`; trader container and log; prod `subscriptions`.

**Steps:**
1. PRODPY with HEADER plus:
```python
import json
import urllib.request
codes = json.load(urllib.request.urlopen("http://localhost:41921/api/v1/backtest/strategies"))
print("prod_has_hitnrun2=" + ("yes" if "hitnrun2" in codes else "no") + " codes=" + ",".join(sorted(codes)))
```
2. LIVECHK.
3. SSH `cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env logs --since <pushed_at> trader 2>&1` piped locally to `sed 's/\x1b\[[0-9;]*m//g' > .cache/trader.log`; then `grep -c -E "reconcile\.(failed|load_failed|unknown_template)" .cache/trader.log`.
4. SUBSCHECK to `.cache/subs.txt`; SUBSDIFF.
5. FREE; record `free_after=<Mem: line>`. `rm -f .cache/ssh/vps_key`.

**Success criteria:** `hitnrun2` listed; live off; no reconcile failure; the three subscriptions unchanged.

**Verify:** step 1 prints `prod_has_hitnrun2=yes codes=hitnrun2,triple_screen`; LIVECHK prints `trader_live=False`; the `grep -c` prints `0`; SUBSDIFF prints `subs_unchanged`.

## Rollback

Each step is an [ASK]. SSH `cd /opt/pocketquant && IMAGE_TAG=sha-<prev_master> bash deploy/vps/10-deploy.sh`, then `git revert <feature commit>` on `develop`, push `develop`, and a later release [ASK] brings `master` back in line. No prod data depends on `hitnrun2` before Phase 06. Record `free -m` after a rollback.

## Report

`reports/phase-04-release-hitnrun2.md`: entry-gate outputs; `prev_master=`, `free_before=`, `commits_to_release=`; `release_ask=`; `pushed_at=`, the master run id and sha; the post-check lines, `free_after=`; then `Result: PASS`.

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

