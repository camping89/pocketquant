---
name: triple-screen-canonical-gap-and-old-run-costs
description: 2026-11-10 Triple Screen review - old Phase 16 runs were charged ~3 USD/oz so their PF is not comparable; gold window was a round trip; canonical-rule sketch lead at 1h/4h
metadata:
  type: project
---

Findings of the 2026-11-10 Triple Screen review (report `plans/reports/kongming-261110-1218-triple-screen-canonical-gap.md`).

- The six Phase 16 backtests of 2026-11-02 stored `commission_bps: 3.0`, no per-contract fee, `spread: 0.0`, `slippage_bps: 0.5`: about 3.09 USD per oz per round trip, against about 0.24 for the runs of 2026-11-10. Re-priced at the new cost: 5m/15m/1h 0.85/0.82, 15m/1h/4h 0.97/1.17, 1h/4h/1d 0.83/0.69 (market / stop).
- XAUUSD:EXNESS over 2025-11-09..2026-11-08 is a round trip: 4006 -> 5593 (late Jan) -> 3871 (late Oct) -> 4055. Not an uptrend.
- Raw setup signal on a 1m entry: +0.08 USD after 5 min for 5m/15m, none for 15m/1h. Cost is 0.24.
- Our strategy takes the trigger and the SL from the entry bar; Elder takes both from the middle (trading) bar. A sketch sim of the canonical rules (own script, 1m fills, unreviewed, 16 variants tried) gave 1h/4h tide-exit PF 1.48 on 431 trades and 1h/1d 0.58.
- The engine's fill-bar stop rule cut the same sketch from 1.48 to 1.05 when run on 1h bars instead of 1m bars.

**Why:** the owner asked why a published strategy loses; later advice will be tempted to cite the old PF 0.78 figures or the "uptrend".

**How to apply:** do not compare PF across runs without reading `config_snapshot` costs. The 1h/4h lead is closed: on 2023-01..2025-11-08 the same sketch made -44 R (t -0.51), see [[triple-screen-oos-diagnosis-and-rubric]]. See [[project_subscription_reset_before_new_strategy]].
