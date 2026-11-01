---
phase: 4
title: "Web gate: fix tsc, add the CI web job"
status: pending
priority: P2
effort: 1h
dependencies: [3]
---

# Phase 04: Web gate: fix tsc, add the CI web job

## Goal

`npx tsc -b` exits 0 in `web/`, and a CI job `web` runs lint, the type check and vitest on every push and gates `build-web` (D2).

## Context

- D2: add a CI `web` job (lint, `tsc -b`, vitest) that `build-web` depends on; fix the two existing `tsc` errors first. Reason (synthesis owner question 2): the web image builds with `npx vite build` (`web/Dockerfile`), which runs no type check, and later phases ship real-money buttons.
- Baseline measured by the planner on this HEAD: `npx tsc -b` exits 2 with exactly two `TS2741` errors, `src/components/monitor/job-status-palette.ts(3,7)` and `(13,14)`: `interrupted` is missing from `Record<JobRunStatus, string>`. `JobRunStatus` includes `'interrupted'` (`web/src/types/job-history.ts:1-9`). `npm run lint` reports `0 errors, 6 warnings` (eslint exits 0 on warnings); `npx vitest run` passes 70 tests in 9 files.
- Palette: `STATUS_COLOR` `web/src/components/monitor/job-status-palette.ts:3-11`, `STATUS_LABEL` `:13-21`. An interrupted run is a failed run cut short by a restart, so it takes the `failed` colour `#f43f5e` and the label `interrupted` (synthesis, candidate 3 Task 4.1).
- CI `.github/workflows/cicd.yml`: job `tests` `:20-56` (`runs-on: ubuntu-24.04`, `actions/checkout@v5`); `build-web` `:104-107` has `needs: [tests]` and runs only on master; `cleanup-tags` and `deploy` need `[build-app, build-web]` (`:151`, `:194`). Pushes that touch only `docs/**`, `plans/**` or `**/*.md` start no run (`:3-11`). Node is 22 in `web/Dockerfile:4`; the lock file is `web/package-lock.json`. `package.json` scripts: `lint` = `eslint .`, `test` = `vitest run`.
- From this phase on, GATES include `npx tsc -b` exits 0 whenever web files change (plan.md Conventions).

## Entry gate

Run from `D:/w/_me/algotrading/pocketquant`:

1. `git fetch -q origin && echo "dirty=$(git status --porcelain -- src web deploy tests scripts docs .github | wc -l | tr -d ' ') synced=$(test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo yes || echo no)"` prints `dirty=0 synced=yes`. On a resume, `dirty` may count only files from this phase's Files list, and `synced=no` passes only when `git rev-list --count HEAD..origin/develop` prints `0`.
2. `tail -1 plans/261101-0843-stf-to-mtf-foundation/reports/phase-03-1d-cascade-session-calendars.md` prints `Result: PASS`.
3. `grep -c "^d1_deployed_at=" plans/261101-0843-stf-to-mtf-foundation/reports/phase-03-1d-cascade-session-calendars.md` prints `1`.
4. `docker ps > /dev/null 2>&1 && echo docker-ok` prints `docker-ok`.

On a miss, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261101-0843-stf-to-mtf-foundation --from 04 after <UTC time>
```

## Files

- Modify: `web/src/components/monitor/job-status-palette.ts`, `.github/workflows/cicd.yml`.
- Create: `plans/261101-0843-stf-to-mtf-foundation/reports/phase-04-web-gate.md`.

## Tasks

### Task 04.1 — Cover the interrupted status

**Goal:** the web type check is green.

**Target files and symbols:** `STATUS_COLOR`, `STATUS_LABEL` in `web/src/components/monitor/job-status-palette.ts`.

**Steps:**
1. Red first: `cd web && npx tsc -b 2>&1 | grep -c "error TS2741"` prints `2`.
2. Add `interrupted: '#f43f5e',` to `STATUS_COLOR` after `running`, and `interrupted: 'interrupted',` to `STATUS_LABEL` after `running`.
3. `cd web && npm run lint` reports `0 errors`; `npx vitest run` passes.
4. `git add web/src/components/monitor/job-status-palette.ts && git commit -m "fix(web): cover the interrupted job status in the palette"` (not pushed yet).

**Success criteria:** `tsc -b` exits 0; lint and vitest unchanged.

**Verify:** `cd web && npx tsc -b > /dev/null 2>&1; echo tsc=$?` prints `tsc=0`.

### Task 04.2 — CI web job

**Goal:** CI runs the web gate on every push, and a master build of the web image needs it.

**Target files and symbols:** `.github/workflows/cicd.yml` (new job `web`; `build-web.needs`).

**Steps:**
1. Add after the `tests` job:
```yaml
  web:
    # vite build runs no type check, so the web gate is its own job.
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    defaults:
      run:
        working-directory: web
    steps:
      - uses: actions/checkout@v5

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: web/package-lock.json

      - name: Install web deps
        run: npm ci

      - name: Lint
        run: npm run lint

      - name: Type check
        run: npx tsc -b

      - name: Unit tests
        run: npm test
```
2. Change `build-web`'s `needs: [tests]` (`:106`) to `needs: [tests, web]`. Leave `build-app`, `cleanup-tags` and `deploy` as they are.
3. `git add .github/workflows/cicd.yml && git commit -m "ci: run the web lint, type check and tests"`.

**Success criteria:** the workflow parses; `web` appears as a job.

**Verify:** `uv run python -c "import yaml; j=yaml.safe_load(open('.github/workflows/cicd.yml'))['jobs']; print(sorted(s['run'] for s in j['web']['steps'] if 'run' in s), j['build-web']['needs'])"` prints `['npm ci', 'npm run lint', 'npm test', 'npx tsc -b'] ['tests', 'web']`.

### Task 04.3 — CLOSE

**Goal:** both commits are on `develop` and CI, including the new `web` job, is green.

**Target files and symbols:** the two commits.

**Steps:**
1. GATES (plan.md Conventions), web part in `web/`: `npx tsc -b` exits 0, `npm run lint` reports `0 errors`, `npx vitest run` exits 0; Python part: `uv run lint-imports` prints `Contracts: 6 kept, 0 broken.`, `uv run python scripts/code_metrics.py --ratchet` exits 0, `uv run ruff check src tests scripts` exits 0.
2. FULLSUITE (plan.md Conventions).
3. Push `develop` with the Ops recipe; `sleep 15`; poll `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 1 --json databaseId,headSha,status,conclusion` until `completed`.

**Success criteria:** the run on HEAD concludes `success` and its job list has `web` with conclusion `success`.

**Verify:** `id=$(GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 1 --json databaseId,headSha -q ".[] | select(.headSha==\"$(git rev-parse HEAD)\") | .databaseId"); GH_TOKEN=$(gh auth token --user camping89) gh run view "$id" --json conclusion,jobs -q '"\(.conclusion) " + ([.jobs[] | select(.name=="web") | .conclusion] | join(","))'` prints `success success`.

## Rollback

`git revert` the two commits (the CI job first, then the palette fix) and push. Nothing reached prod; `build-web` runs only on master.

## Report

`reports/phase-04-web-gate.md`: the red output of Task 04.1 step 1; both commit shas; the GATES and FULLSUITE tail lines; the CI run id with its `web` job conclusion. Last line `Result: PASS`.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same failure evidence to the user. Never continue by self-reasoning.
