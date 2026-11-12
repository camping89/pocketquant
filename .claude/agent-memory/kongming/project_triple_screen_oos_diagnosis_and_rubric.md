---
name: triple-screen-oos-diagnosis-and-rubric
description: 2026-11-12 verdict on Triple Screen 15m,1h,4h lb80 gold - no edge out of sample (2/20 on the rubric), long profit = gold drift, fill-bar rule hides up to 95 R, 1h/4h canonical lead dead; rubric lives in the report section 3
metadata:
  type: project
---

Diagnosis of frozen run `01a1c980-46bc-7400-acb1-f2f6a90c6323` (2023-01..2026-11-10, 1 991 trades) on 2026-11-12. Report with the reusable rubric (section 3): `plans/reports/kongming-261112-1356-triple-screen-diagnosis-and-assessment-rubric.md`.

- Verdict given: do not trade it with real money at any risk percent. Out of sample (1 497 trades before 2025-11-09): mean -0.007 R, t -0.16; five rubric gates fail; score 2/20. The in-sample year scores 11/20 and already failed the trials and out-of-sample gates.
- Long +73.4 R / short -84.1 R out of sample equals what gold's drift pays random trades of the same side and holding time (+71.9 / -87.6). A long-only variant is diluted buy-and-hold, not an edge.
- Engine fill-bar rule: 125 trades (6.3%) stopped on the fill bar, 93 not decidable on 15m bars. 1m replay (possible only since 2025-10-22): 18 of 32 were false. Optimistic bound out of sample +83.8 R (t 1.13) against -10.9 R; still fails every gate.
- The stop (extreme of 80 entry bars) has no minimum distance: stops from 0.5 USD, and 2% risk gives positions up to 87x equity. Trades with a stop of at least 0.25 daily ATR are flat under both fill rules.
- The canonical 1h/4h sketch (PF 1.48 in sample) makes -44 R out of sample. Daily/weekly sketch: 69 trades in 46 months, not judgeable. All six lookbacks are negative out of sample.
- Elder's 6% monthly rule on 2% risk would halt 33 of 47 months: the 2% rule assumes a few trades a month, ours makes 43.
- Trials so far: about 142 configurations on gold. The 15m window 2022-05..2022-12 is untouched (about 350 trades; can only kill, not confirm). No prod backtest was needed: an offline replica (`.cache/km2/sim.py`, gitignored scratch, may be gone) reproduced 1 990 of 1 991 engine trades.
- Prod XAUUSD:EXNESS coverage on 2026-11-12: 1m and 5m from 2025-10-21; 15m from 2022-05-01; 1h from 2020-05-14; 4h from 2020-11-09; 1d from 2019-03-25.
- The running `15m,1h,4h` paper subscription has no `stop_lookback` (default 5), so it is not the frozen config.

**Why:** the owner believes the strategy is "proven and well-known" and chose 2% risk; later requests will likely ask for more sweeps, a long-only variant, or a filter from the regime tables.

**How to apply:** score any new candidate with the rubric before sizing talk; count every new variant toward the trial total; refuse to adopt long-only, volatility, weekday or session filters found in this slicing; for any stop-entry backtest on 15m or longer bars, count fill-bar stops first. Supersedes the sizing advice in [[leveraged-triple-screen-reanalysis]] and the open lead in [[triple-screen-canonical-gap-and-old-run-costs]].
