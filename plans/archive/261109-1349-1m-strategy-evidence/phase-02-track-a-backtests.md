---
phase: 2
title: "Track A: four Triple Screen 1m backtests, table, verdicts"
status: completed
priority: P2
effort: "about 2.5h wall time (4 runs at an estimated 20-25 min each)"
dependencies: [1]
---

# Phase 02: Track A: four Triple Screen 1m backtests, table, verdicts

## Goal

Four finished Triple Screen backtests on `XAUUSD:EXNESS` over the plan window (A1), run one at a time with the seeded costs (A2), recorded in the Phase 16 table format plus a `gate` column, and one `verdict:` line for each of the two sets.

## Context

- Runs (plan.md BTRUN): `r1` `1m,5m,15m` market/sl_tp, `r2` `1m,5m,15m` stop/strategy, `r3` `1m,15m,1h` market/sl_tp, `r4` `1m,15m,1h` stop/strategy. The body sends no `spread`, `commission_bps` or commission, so the symbol spec applies (`backtest_execution_service.py:42-43`; per-contract fee wins, `commission_model.py:25-28`). No code change: the route accepts a 1m entry today (plan.md Facts).
- Cost: a run is an asyncio task in the api process with no cap, sharing the live Mongo pool (`src/pocketquant/app/routes/backtest.py:46-60`). The 12-month 5m set took 234-273 s (Phase 16 report, run lines 1-2); 1m has five times the entry bars, so 20-25 min is an estimate, not a measurement. A2: owner ask when a run exceeds 1800 s. No cancel route exists, so the ask comes after the run and before the next one.
- Run status values `started`, `finished`, `failed` (`src/pocketquant/core/domain/backtest/entities.py:23`); BTRUN prints `still_running` while it polls.
- Do not change Triple Screen (non-goal).
- Ops names: plan.md Ops recipe; BTRUN and VERDICT: plan.md Shared scripts.

## Entry gate

1. Conventions EG (1)-(3); the previous report is `reports/phase-01-coverage-and-baseline.md`.
2. `grep -c "^existing_sub " plans/261109-1349-1m-strategy-evidence/reports/phase-01-coverage-and-baseline.md` prints `3`.

On a miss, run `rm -f .cache/ssh/vps_key`, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 02 after <UTC time>
```

## Files

- Create: `plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md`; local scratch `.cache/f.py`, `.cache/verdict.py`, `.cache/subs.txt` (not committed).
- Prod writes: four `backtest_runs` (and their `backtest_orders`, `backtest_trades`).

## Tasks

### Task 02.1 — Four backtests, one at a time

**Goal:** `r1`-`r4` finish, each followed by a memory reading; a run above 1800 s gets the owner's answer before the next run starts.

**Target files and symbols:** `POST /api/v1/backtest/run`, `GET /api/v1/backtest/{id}`.

**Steps:**
1. KEY. Write BTRUN from plan.md to `.cache/f.py`.
2. For each label in `r1`, `r2`, `r3`, `r4`, in order:
   - If the report already has `run=<label> set=... status=finished`, skip the label.
   - If it has only `run=<label> set=<set> id=<id>`, poll: PRODPY-ARG `<label> <id>`.
   - Else run WINDOW; on `window_ok=no` run `rm -f .cache/ssh/vps_key` and exit `NOT_YET` (plan.md WINDOW). On `yes`, submit: PRODPY-ARG `<label>`. A `busy=` line means another run is `started`: wait 5 min and submit again, at most 6 times, then treat it as a failed Verify.
   - While the output's last line starts with `still_running`, run PRODPY-ARG `<label> <id>` again. Each call returns within about 8 min.
   - Append the `run=<label> set=<set> id=<id>` line and the final `run=` line to the report as plain lines.
   - FREE; append `free_after_run=<label> <Mem: line>`.
   - If the final line's `elapsed_s` is above `1800` and a later label remains, [ASK] (intent) "run <label> took <minutes> min; free -m after it: <line>; start the next 1m run?" `Recommended: yes`, reason: runs go one at a time, the paper subscriptions keep trading, and the memory line shows headroom. Record `cost_ask=<label> <reply>`. A non-yes ends the phase with `NOT_YET`.
3. `rm -f .cache/ssh/vps_key`.

**Success criteria:** four final `run=` lines with `status=finished`, four `free_after_run=` lines, and a `cost_ask=` line for every run above 1800 s that had a run after it. A `status=failed` line, or a run still `started` after 3 h of polling, is a failed Verify.

**Verify:** `grep -c -E "^run=r[1-4] set=\S+ id=\S+ status=finished " plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md; grep -c -E "^free_after_run=r[1-4] " plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md` prints `4` then `4`.

### Task 02.2 — Run table

**Goal:** the four runs read side by side in the Phase 16 format plus the gate.

**Target files and symbols:** the phase report.

**Steps:**
1. Write a table `| # | set | intervals | entry_type | exit_mode | run id | elapsed_s | trades | total_return | profit_factor | max_drawdown | win_rate | gate |` with one row per run (`| r1 | ts-1m-5m-15m | 1m 5m 15m | market | sl_tp | ...`), values copied from the final `run=` lines (4 decimals for ratios).
2. Under it, two compare URLs: `https://pocketquant.xyz/backtest/compare?runs=<r1 id>,<r2 id>` and `https://pocketquant.xyz/backtest/compare?runs=<r3 id>,<r4 id>`.

**Success criteria:** 4 rows and 2 URLs.

**Verify:** `grep -c -E "^\| r[1-4] \| " plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md; grep -c "^https://pocketquant.xyz/backtest/compare?runs=" plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md` prints `4` then `2`.

### Task 02.3 — Verdict lines

**Goal:** one `verdict:` line per Track A set, produced by the shared VERDICT code.

**Target files and symbols:** `.cache/verdict.py`; the phase report.

**Steps:**
1. Write VERDICT from plan.md to `.cache/verdict.py`.
2. `uv run python .cache/verdict.py plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md`; append its two lines to the report right under the table, as plain lines.

**Success criteria:** two lines, one per set, each `pass` or `fail` with both runs' values.

**Verify:** `grep -c -E "^verdict: (ts-1m-5m-15m|ts-1m-15m-1h) (pass|fail) r[1-4]:pf=\S+,trades=\S+,gate=(pass|fail) r[1-4]:pf=\S+,trades=\S+,gate=(pass|fail)$" plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md` prints `2`.

### Task 02.4 — Existing subscriptions untouched

**Goal:** the runs did not disturb the three paper subscriptions (A6).

**Target files and symbols:** prod `subscriptions`.

**Steps:**
1. KEY. SUBSCHECK with output to `.cache/subs.txt`. `rm -f .cache/ssh/vps_key`.
2. SUBSDIFF; record its output.

**Success criteria:** the three lines equal Phase 01's.

**Verify:** SUBSDIFF prints `subs_unchanged`.

## Rollback

Nothing to roll back in code. The four runs stay as evidence; only the owner deletes a run (UI). A failed run leaves a `failed` document, which is recorded, not deleted.

## Report

`reports/phase-02-track-a-backtests.md`: entry-gate outputs; every `run=` line, `free_after_run=` line and `cost_ask=` answer; the table and two URLs; the two `verdict:` lines; the SUBSDIFF output; then `Result: PASS`.

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

