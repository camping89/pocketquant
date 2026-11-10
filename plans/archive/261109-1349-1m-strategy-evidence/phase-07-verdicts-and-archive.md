---
phase: 7
title: "Written verdict per set, status completed, archive"
status: pending
priority: P2
effort: "0.5h"
dependencies: [6]
---

# Phase 07: Written verdict per set, status completed, archive

## Goal

One written `final:` line per set (two) with the backtest verdict and the paper record, a one-paragraph conclusion, the plan at `status: completed`, and the plan directory moved to `plans/archive/`.

## Context

- D5: the plan ends at the paper reconciliation and a written pass/fail verdict per set. D4: the backtest decides; paper only reconciles. So a set's final verdict is its `verdict:` line; the paper record is attached, not judged.
- If no set passed, the conclusion states that 1m does not clear the gate on gold at these costs, with the numbers (advice, "My take").
- Plan status changes go through `ak plan update <id> --status completed`, which rewrites the `plan.md` front matter (`ak plan update --help`). The plan id is `pocketquant/261109-1349` once indexed (`ak plan list --json`). Earlier plans were archived with a `git mv` into `plans/archive/` and a docs-only commit (commit `00272823`).
- Commits touching only `plans/**` trigger no CI (`.github/workflows/cicd.yml:3-10`).

## Entry gate

1. Conventions EG (1)-(3); the previous report is `reports/phase-06-paper-reconcile.md`.

On a miss, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 07 after <UTC time>
```

## Files

- Create: `plans/261109-1349-1m-strategy-evidence/reports/phase-07-verdicts-and-archive.md`.
- Modify: `plan.md` front matter (through `ak plan update` only).
- Move: `plans/261109-1349-1m-strategy-evidence/` to `plans/archive/261109-1349-1m-strategy-evidence/`.

## Tasks

### Task 07.1 — Final verdict per set

**Goal:** two `final:` lines and a summary table that a reader can act on.

**Target files and symbols:** reports of Phases 02, 05, 06.

**Steps:**
1. For each set `ts-1m-5m-15m`, `ts-1m-15m-1h`, write `final: <set> <pass|fail> backtest=<the verdict line's run values> paper=<recorded|not_run> on_bar_error=<n|n/a> stale=<n|n/a>`, where `<pass|fail>` is copied from that set's `verdict:` line and the paper values from its `recon:` error line (`not_run` and `n/a` for a set that failed the gate).
2. A table `| set | runs (pf, trades, gate) | verdict | paper trades/day (bt vs paper) | avg commission (bt vs paper) | exit mix (bt vs paper) | errors/stale |` with one row per set, values copied from the reports.
3. A conclusion of at most five sentences: which sets pass, the main number behind each fail, and, if none passed, the sentence "1m does not clear the gate (net profit_factor >= 1.2 and total_trades >= 100 over 12 months) on XAUUSD:EXNESS at the seeded costs." Facts only; label any inference as such.

**Success criteria:** two `final:` lines whose pass/fail match the verdict lines.

**Verify:** `uv run python -c "import re; r='plans/261109-1349-1m-strategy-evidence/reports/'; t=open(r+'phase-02-track-a-backtests.md',encoding='utf-8').read(); f=open(r+'phase-07-verdicts-and-archive.md',encoding='utf-8').read(); v=dict(re.findall(r'^verdict: (\S+) (pass|fail) ', t, re.M)); g=dict(re.findall(r'^final: (\S+) (pass|fail) ', f, re.M)); print('final_ok=' + str(len(v) == 2 and v == g))"` prints `final_ok=True`.

### Task 07.2 — Status completed

**Goal:** `plan.md` front matter reads `status: completed`.

**Target files and symbols:** `plans/261109-1349-1m-strategy-evidence/plan.md`.

**Steps:**
1. `ak plan list --json | grep -c '"id": "pocketquant/261109-1349"'`; if it prints `0`, run `ak plan reindex` and check again.
2. `ak plan update pocketquant/261109-1349 --status completed`.

**Success criteria:** the front matter changed through the CLI.

**Verify:** `grep -c "^status: completed$" plans/261109-1349-1m-strategy-evidence/plan.md` prints `1`.

### Task 07.3 — Archive, commit, push

**Goal:** the plan lives in `plans/archive/` on `origin/develop`.

**Target files and symbols:** the plan directory.

**Steps:**
1. Append to the report everything above plus `Result: PASS` as the last line (the report moves with the directory).
2. `git mv plans/261109-1349-1m-strategy-evidence plans/archive/261109-1349-1m-strategy-evidence`; then `ak plan reindex`.
3. `git add -A plans/archive/261109-1349-1m-strategy-evidence`; commit `docs(plans): record the 1m strategy verdicts and archive the plan`; push `develop` (no CI runs for `plans/**`).

**Success criteria:** the directory is archived, completed and pushed.

**Verify:** `test -d plans/archive/261109-1349-1m-strategy-evidence && test ! -e plans/261109-1349-1m-strategy-evidence && grep -c "^status: completed$" plans/archive/261109-1349-1m-strategy-evidence/plan.md && git fetch -q origin && test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo archived` prints `1` then `archived`.

## Rollback

`git revert <archive commit>` and push restores the directory; `ak plan update pocketquant/261109-1349 --status in-progress` reopens it.

## Report

`reports/phase-07-verdicts-and-archive.md`: entry-gate outputs; the two `final:` lines, the table and the conclusion; the `ak` outputs; then `Result: PASS` (written before the move, as Task 07.3 says).

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
