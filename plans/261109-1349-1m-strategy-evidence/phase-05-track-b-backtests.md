---
phase: 5
title: "Track B: two hitnrun2 backtests, table, verdict"
status: completed
priority: P2
effort: "about 1.5h wall time"
dependencies: [4]
---

# Phase 05: Track B: two hitnrun2 backtests, table, verdict

## Goal

Two finished hitnrun2 backtests on `XAUUSD:EXNESS` over the same window as Track A, one with the default `min_profit_pct` (0.02) and one with `min_profit_pct=0.005` (D7), recorded in the same table format, and one `verdict:` line for the `hitnrun2-1m` set from the same VERDICT code.

## Context

- Advice: backtest hitnrun2 with the default `min_profit_pct` and one lower value; the 2% floor means a TP at least about 80 USD/oz away at today's gold price (advice, item 4), which a 1m strategy may rarely reach. The owner fixed the lower value at 0.005 (plan.md D7), so Task 05.1 records it without asking.
- Runs (plan.md BTRUN): `r5` `{"min_profit_pct": 0.02}`, `r6` `{"min_profit_pct": <LOW>}`. Every other parameter takes `DEFAULTS` (240/480/60 bars, `max_loss_pct=0.01`, `direction=both`, `min_cost_multiple=3.0`). Costs: the seeded spec, nothing sent (A2, A4).
- Coverage: Phase 01 checked 1m over this exact window; the window ends before plan day, so it does not move.
- Cost rule and recipe: the same as Phase 02 (1800 s ask, WINDOW, one at a time).
- Ops names: plan.md Ops recipe; BTRUN and VERDICT: plan.md Shared scripts.

## Entry gate

1. Conventions EG (1)-(3); the previous report is `reports/phase-04-release-hitnrun2.md`.
2. `grep -c "^prod_has_hitnrun2=yes" plans/261109-1349-1m-strategy-evidence/reports/phase-04-release-hitnrun2.md` prints `1`.

On a miss, run `rm -f .cache/ssh/vps_key`, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 05 after <UTC time>
```

## Files

- Create: `plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests.md`; local scratch `.cache/f.py`, `.cache/verdict.py`, `.cache/subs.txt`.
- Prod writes: two `backtest_runs`.

## Tasks

### Task 05.1 — Record the lower `min_profit_pct`

**Goal:** the report holds the owner's lower `min_profit_pct` value.

**Target files:** `plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests.md`.

**Steps:**
1. Write the line `min_profit_low=0.005` and, under it, `source: owner decision D7 (validation 2026-11-09)`. Do not ask the owner.

**Success criteria:** one `min_profit_low=` line with a value below 0.02.

**Verify:** `grep -c -E "^min_profit_low=0(\.[0-9]+)?$" plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests.md` prints `1`, and `grep -c "^min_profit_low=0.005$" plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests.md` prints `1`.

### Task 05.2 — Two backtests, one at a time

**Goal:** `r5` and `r6` finish, each followed by a memory reading.

**Target files and symbols:** `POST /api/v1/backtest/run`, `GET /api/v1/backtest/{id}`.

**Steps:**
1. KEY. Write BTRUN from plan.md to `.cache/f.py` with `<LOW>` replaced by the `min_profit_low` value (a Python float literal, for example `0.005`).
2. For `r5` then `r6`, follow Phase 02 Task 02.1 step 2 exactly (skip, poll, WINDOW, submit, `busy=` retry, `still_running` re-poll, report lines, `free_after_run=<label>`, and the 1800 s [ASK] recorded as `cost_ask=<label> <reply>` before `r6`).
3. `rm -f .cache/ssh/vps_key`.

**Success criteria:** two final `run=` lines with `status=finished` and two `free_after_run=` lines. A `failed` run or a run still `started` after 3 h is a failed Verify.

**Verify:** `grep -c -E "^run=r[56] set=hitnrun2-1m id=\S+ status=finished " plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests.md; grep -c -E "^free_after_run=r[56] " plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests.md` prints `2` then `2`.

### Task 05.3 — Run table

**Goal:** the two runs read side by side, in the Phase 02 format.

**Target files and symbols:** the phase report.

**Steps:**
1. Write the table `| # | set | intervals | min_profit_pct | run id | elapsed_s | trades | total_return | profit_factor | max_drawdown | win_rate | gate |` with rows `| r5 | hitnrun2-1m | 1m | 0.02 | ...` and `| r6 | hitnrun2-1m | 1m | <min_profit_low> | ...`, values copied from the final `run=` lines.
2. Under it, `https://pocketquant.xyz/backtest/compare?runs=<r5 id>,<r6 id>`.

**Success criteria:** 2 rows and 1 URL.

**Verify:** `grep -c -E "^\| r[56] \| " plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests.md; grep -c "^https://pocketquant.xyz/backtest/compare?runs=" plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests.md` prints `2` then `1`.

### Task 05.4 — Verdict line

**Goal:** one `verdict:` line for `hitnrun2-1m`, from the same code as Track A.

**Target files and symbols:** `.cache/verdict.py`; the phase report.

**Steps:**
1. Write VERDICT from plan.md to `.cache/verdict.py` (unchanged).
2. `uv run python .cache/verdict.py plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests.md`; append its line under the table as a plain line.

**Success criteria:** one line.

**Verify:** `grep -c -E "^verdict: hitnrun2-1m (pass|fail) r5:pf=\S+,trades=\S+,gate=(pass|fail) r6:pf=\S+,trades=\S+,gate=(pass|fail)$" plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests.md` prints `1`.

### Task 05.5 — Existing subscriptions untouched

**Goal:** A6 holds after the runs.

**Target files and symbols:** prod `subscriptions`.

**Steps:**
1. KEY. SUBSCHECK to `.cache/subs.txt`. `rm -f .cache/ssh/vps_key`.
2. SUBSDIFF.

**Success criteria:** unchanged.

**Verify:** SUBSDIFF prints `subs_unchanged`.

## Rollback

None in code. The two runs stay as evidence; only the owner deletes a run (UI).

## Report

`reports/phase-05-track-b-backtests.md`: entry-gate outputs; the `min_profit_low=` and `source:` lines; every `run=`, `free_after_run=` and `cost_ask=` line; the table and URL; the `verdict:` line; the SUBSDIFF output; then `Result: PASS`.

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

