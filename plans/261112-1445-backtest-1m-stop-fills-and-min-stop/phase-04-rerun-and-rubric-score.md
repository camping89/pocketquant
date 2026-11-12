---
phase: 4
title: "Re-run and rubric score"
status: done
priority: P2
effort: "5h"
dependencies: [1, 2, 3]
---

# Phase 4: Re-run and rubric score

## Goal
Measure the 1m fill, the minimum stop and candidate C with the engine, on the local Mongo from phase 1. Score them with `docs/governance/strategy-assessment-rubric.md` at 2% risk.

## Runs (pre-registered; nothing else runs)
- **Shared settings:** Triple Screen `15m,1h,4h`, `entry_type=stop`, spread 0.08, commission 3 bp, slippage 0.1 bp, 10 000 USD. Every parameter not named below keeps its default.
- **Window W:** 2024-05-01T00:00Z to 2026-11-10T23:59Z, with 1m fills. This start is fixed. If the first local 1m bar is later, stop and ask the owner (phase 1 task 1.7).

| Id | Window | Config | Role |
|---|---|---|---|
| R0 | 2023-01-01T00:00Z..2026-11-10T23:59Z, coarse (the gate keeps it coarse) | C | replica check, and the pre-2024-05 part of C's G2 sample |
| A | W | `exit_mode=strategy`, `stoploss_lookback=20` | frozen config |
| B | W | A plus `min_stop_atr=0.5` | minimum stop |
| C | W | `stoploss_lookback=10`, `takeprofit_lookback=10`, `entry_buffer_atr=0.1`, `stoploss_buffer_atr=0.0`, `min_stop_atr=0.5`, `exit_mode=sl_tp`, `risk_reward=1.0` | walk-forward candidate (kongming report 1527, section 5.3) |
| C1 | W | C with `stoploss_buffer_atr=0.1` | informational trial 222 |
| C2 | W | C with `stoploss_buffer_atr=0.2` | informational trial 223 |
| C3 | W | C with `stoploss_buffer_atr=0.3` | informational trial 224 |

- **Trial count:** 221 before this phase. A, B and C were already counted. C1, C2 and C3 add 3, for a total of 224.
- **C1 to C3 are informational.** They run on data already used to select C. They never change C's verdict, which is scored with `stoploss_buffer_atr=0.0`, and none of them can be promoted or sent to paper.

## Segment labels (by entry fill time, `opened_at`)
- **P:** 2024-05-01T00:00Z up to, not including, 2025-11-09T00:00Z.
- **Y:** 2025-11-09T00:00Z up to, not including, 2026-11-09T00:00Z.
- Trades on 2026-11-09 and 2026-11-10 count only in the window totals.

| Config | P | Y |
|---|---|---|
| A | out of sample for A's parameters; second read (the first was `01a1c980`) | in sample (the year that chose A) |
| B | as A; also used to choose `min_stop_atr` by a rule that did not read profit | as A |
| C, C1-C3 | selection data (walk-forward test folds) | selection data |

- C has no out-of-sample segment. G3 for C is "open", never "pass". The best verdict C can get in this phase is "candidate for incubation".

## G2 sample (owner decision 9)
- **A and B:** t of R over segment Y of their 1m runs.
- **C:** t of R over R0's trades with `entry_time < 2024-05-01T00:00Z`, joined with all of C's 1m-run trades. The join is not seamless: the 1m run starts flat with an empty swing window. The report says so. Report C's t over W next to it.
- G2 passes at t >= 3.0. The Deflated Sharpe Ratio is reported and does not gate.

## Facts
- Runs go through `BacktestCommandService.run` and `BacktestExecutionService.execute_and_persist`, as in `.cache/ts_direct.py` and `.cache/golden/b0.py` from phase 1.
- `.cache/km3/candidate_trades.csv` has columns `side,entry_time,exit_time,entry,exit,sl,R,reason`: 745 trades, sum R +121.3, t 3.32. Six rows have `entry_time < 2023-01-09`. From 2024-05-01 there are 552 trades with t 2.58.
- `.cache/oos/an.py` rescales a trade list to 2% compounding over each trade's stop.
- A strategy exception is logged as `skipped:strategy_error`, and a fill error as `paper.stop_fill_failed`.
- The equity curve persisted with a run is downsampled, and in a merged run its points no longer line up with exit times. Rubric numbers come from the trade list only.

## Files to Create / Modify
- Scratch, under `.cache/p4/`: `run.py`, one log per run `.cache/p4/<id>.log`, trade exports `.cache/p4/<id>.csv`, `replica.py`, `score.py`, `score.txt`.
- Create: `plans/reports/backtest-<yymmdd-hhmm>-triple-screen-1m-fills-stop-target-rubric.md`.

## Tasks

### Task 4.1 — Target guard and run script
- **Goal:** one script that runs any row of the Runs table against the local Mongo and captures its log and trades.
- **Target files:** `.cache/p4/run.py` (new; start from `.cache/golden/b0.py`, which follows `.cache/ts_direct.py`).
- **Steps:**
  1. Repeat phase 1 task 1.1 (target guard).
  2. Write `run.py <id>`. It takes the config of that row and runs it. It writes:
     - the full log to `.cache/p4/<id>.log`;
     - the trades to `.cache/p4/<id>.csv` with columns `side,entry_time,exit_time,entry_price,exit_price,sl,quantity,pnl,exit_reason,commission` (`commission` added 2026-11-12 for the net R of task 4.2);
     - a last line `run_id=<uuid> fill_interval=<value> trades=<n>`.
- **Success criteria:** the script runs a row end to end.
- **Verify:** no verification needed; task 4.2 runs it.

### Task 4.2 — Replica check, before any profit is read
- **Goal:** the engine reproduces the replica for C on the coarse window.
- **Target files:** `.cache/p4/replica.py` (new).
- **Steps:**
  1. Run `uv run python .cache/p4/run.py R0`.
  2. Write `replica.py`. It drops from both lists the trades with `entry_time < 2023-01-09T00:00Z`, then matches on `(side, entry_time)` exactly. A matched pair must agree on `exit_time` and exit reason, on entry and exit price within 0.001, and on R within 0.01. R for the engine is `(exit - entry) / (entry - sl)` for longs, mirrored for shorts. It prints `unmatched=<n> disagreeing=<n>` and lists each such trade.
  3. Run it. Do not open any profit column before this step passes.
- **Success criteria:** R0's `fill_interval` is `15m`, and at most 3 trades are unmatched or disagreeing, counted over both lists.
- **Verify:** the last line of R0's output has `fill_interval=15m`, and `unmatched + disagreeing <= 3`. If it fails, stop and ask kongming to redo its report 1527, section 5, with the engine's exit path.
- **Amendment 2026-11-12, made before R0 was run (no engine number seen; kongming counsel).** In step 2, R for the engine is net of the engine's own commission per unit: `(sign * (exit - entry) - commission / quantity) / abs(entry - sl)`, with sign +1 for longs and -1 for shorts. `commission` is the trade's entry plus exit commission. Reason: the replica's `R` column is net of 0.07 per oz (`.cache/km3/sim_mtf.py:67-71`), so the gross formula compared two different quantities. Self-test on the replica list alone, converted to the engine CSV format with quantity 1.0 and commission 0.07: the gross formula marks 114 of 739 pairs as disagreeing; the net formula marks 0 (`.cache/p4/selftest/replica-selftest.txt`). The cut date, match key, the other agreement checks, all tolerances and the pass limit of 3 are unchanged. `replica.py` also prints the gross count, the range of `commission / quantity` and any duplicate keys, as diagnostics only. Note: XAUUSD:EXNESS charges 0.035 per oz per side (`commission_per_contract`), which overrides the 3 bp in Shared settings.

### Task 4.3 — Void-run check (applies to every run)
- **Goal:** no run has silently dropped trades.
- **Steps:**
  1. For each run's log: `grep -c "skipped:strategy_error" .cache/p4/<id>.log` and `grep -c "paper.stop_fill_failed" .cache/p4/<id>.log`.
- **Success criteria:** both counts are 0 for every run.
- **Verify:** every count is `0`. A run with a non-zero count is void: stop and report.

### Task 4.4 — Timing
- **Goal:** a full 1m run fits the time budget, and its cost on prod can be stated.
- **Steps:**
  1. Run A on 2024-05-01T00:00Z..2024-05-31T23:59Z with `run.py`, under `time`. This is a timing run only; read no number from it, and delete its CSV.
  2. Compute events per second (published bars divided by wall time) and the projected wall time for W.
- **Success criteria:** the projected time for W is at most 2 hours.
- **Verify:** the projected time is at most 7 200 s, and the run's `fill_interval` is `1m`. If the projection is over 2 hours, stop and report. Record events per second and the projection for phase 5.
- **Result 2026-11-12 (local machine, solo run):** T_A published 33 402 events (1m and 15m) in 4.21 s of replay (7 s wall), about 7 934 events per second, with `fill_interval=1m`. W holds 895 411 1m and 59 862 15m bars, 955 273 events, so the projection is about 120 s of replay. Six parallel runs on one Mongo will be slower than this solo figure. The T_A CSV was deleted unread.
- **Deviation 2026-11-12 (kongming counsel):** a smoke run T_C (config C on the same month) was added, because A never exercises the take-profit path. Checks only, no profit number read: `fill_interval=1m`, void 0, 22 trades, 12 `auto_tp` and 10 `auto_sl` exits, peak working set about 101 MB. Its CSV was deleted.

### Task 4.5 — Main runs
- **Goal:** A, B, C, C1, C2 and C3 complete with 1m fills.
- **Steps:**
  1. Repeat phase 1 task 1.1.
  2. Start the six runs in parallel as separate background processes: `uv run python .cache/p4/run.py <id>`.
  3. When all have exited, run task 4.3 for each.
- **Success criteria:** six completed runs, each with `fill_interval=1m`.
- **Verify:** each output's last line has `fill_interval=1m` and `trades=` above 0, and task 4.3 passes for each.

### Task 4.6 — Compare A with stored run `01a1c980`
- **Goal:** show what the 1m fill changed.
- **Steps:**
  1. Restrict the stored `01a1c980` trades (`.cache/golden/b0.csv`) to entries in W.
  2. Key both lists on `(side, floor(entry_time, 15m))`.
  3. Count four classes:
     - same entry and same exit;
     - same entry and a different exit, where an old same-bar SL exit counts as "fill-bar stop removed";
     - only in the old run;
     - only in the new run.
  4. Report total R for each list.
- **Success criteria:** each trade falls in exactly one class.
- **Verify:** the four class counts add up to the size of the union of the two keyed lists.

### Task 4.7 — Rescale and statistics
- **Goal:** the rubric inputs, computed from trade lists.
- **Target files:** `.cache/p4/score.py` (new; reuse the logic of `.cache/oos/an.py`), `.cache/p4/score.txt`.
- **Steps:** for each of A, B, C and C1-C3, over W and over P and Y separately, compute:
  - final equity and max drawdown at 2% compounding over each trade's stop;
  - worst day and worst losing streak;
  - P(drawdown >= 50%) by bootstrap, 10 000 resamples, fixed seed 7;
  - the Kelly fraction;
  - the largest position as a multiple of equity;
  - the worst gap loss;
  - mean R, t, and the G2 t defined above.
  Count the trades whose entry bucket is in phase 1's E0 or E1 set.
- **Success criteria:** `score.txt` holds every number for every run and segment.
- **Verify:** `score.txt` has a line for each pair of the six runs and the three segments (W, P, Y): 18 lines, plus C's G2 line.
- **Deviation 2026-11-12, made after the runs (kongming counsel):** `score.py` also prints the DSR, which this phase and the rubric say to report, plus C's exit anatomy, side split and power. DSR assumptions: N = 224 independent no-skill trials (also shown at N = 50), trial Sharpe variance 1/(n-1), per-trade Sharpe, skew and kurtosis from the R list. Nothing gates on these lines. The first 22 lines of `score.txt` were identical before and after the change.

### Task 4.8 — Rubric score and decision rule
- **Goal:** a verdict for A, B and C under the fixed rules.
- **Steps:**
  1. Score A, B and C on gates G1 to G5 and S1 to S10, using the segment labels and the G2 sample above. If more than 2% of a run's trades are in E0 or E1 buckets, G1 counts them as ambiguous.
  2. **Decision rule for C, fixed now:** drop C if its 1m-run mean R over W is at or below 0, or its t over W is below 1.5. This rule tests that the result survives the engine with 1m fills. Passing it is not evidence of an edge.
  3. **Diagnostic, not a selection rule:** if C's 1m-run sum R over W is outside 67.7..91.7 R, investigate the engine against the replica and report before writing a verdict.
  4. Report C1 to C3 next to C, labelled informational.
- **Success criteria:** each gate has a pass, fail or open mark with the number behind it.
- **Verify:** no verification needed; task 4.9's report is checked by its reproducibility rule.

### Task 4.9 — Report
- **Goal:** one report with the verdict and the next step.
- **Target files:** `plans/reports/backtest-<yymmdd-hhmm>-triple-screen-1m-fills-stop-target-rubric.md`.
- **Steps:** write the report, in short plain English. It contains:
  - the phase 1 coverage values from `.cache/p1/audit.txt`;
  - the run ids and `fill_interval` of every run;
  - the replica result;
  - the A against `01a1c980` classes;
  - the rubric table with segment labels;
  - C's G2 t (joined sample) and its t over W;
  - the decision-rule outcome;
  - C1 to C3 as informational;
  - the trial count of 224;
  - events per second and the projected time;
  - unmodelled costs: swap (C holds for about 38 hours on average);
  - the note that phase-4 1m bars are all REST data while prod mixes REST and live sync;
  - the next step.
- **Success criteria:** every number can be reproduced from a script under `.cache/p4/` and the run ids.
- **Verify:** for each number in the report, `grep` finds it in `.cache/p4/score.txt`, or in the output of `replica.py` or of task 4.6. Spot-check at least 10 numbers. All must be found.

## Risk
- **Small sample:** about 18 months in P. The test can reject C but may be too small to confirm it (the rubric's power check). About 320 new trades are needed to confirm +0.15 R.
- **Not modelled:** swap. The report must state it as an unmodelled cost.
- **Silent coarse fallback:** a run whose `fill_interval` is not `1m` gives coarse numbers. Tasks 4.5 and 4.2 check it.

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
