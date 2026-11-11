---
name: leveraged-triple-screen-reanalysis
description: 2026-11-11 offline rescale of Triple Screen 15m,1h,4h lb80 run to 2% risk at 1:500; edge t=1.28, margin never binds, advice 0.5-1% + 5x cap
metadata:
  type: project
---

Offline rescale of prod run `01a1c41f-dee3-7070-b7ac-086fbb5dacfc` (489 trades) on 2026-11-11. Report: `plans/reports/kongming-261111-1351-leveraged-triple-screen-reanalysis.md`.

- 2% risk over strategy SL, compounding: 10 000 -> 18 808 closed; EOD max drawdown -27.8%; worst day -13.3% (7 stop-outs, 2026-08-24). 1%: 14 376 / -14.9%. 0.5%: 12 139 / -7.8%.
- Margin at 1:500 peaked at 5.7% of equity; notional peaked at 28x equity. Leverage is not the constraint.
- Under equal-risk sizing: mean +0.085 R, sd 1.46, t = 1.28, PF 1.215 (stored PF 1.456 is ounce-weighted). Top 5 trades exceed the whole profit. 12 winners came within 1 USD of the stop.
- No realised loss beyond -1.026 R; 61 weekend holds, none gapped (data has gaps up to 2%).
- Prod XAUUSD:EXNESS 15m and 1m bars start 2025-10-21; 1h 2023-10-31; 4h 2023-09-01. BTCUSDT:BINANCE 15m starts 2024-05-08.
- `PaperBrokerAdapter._can_afford` gates BUY on full notional <= balance and never gates SELL, so a leveraged engine run would refuse longs only.
- `docker compose cp` into `api` creates root-owned files; removing them needs `exec -u root`.

**Why:** owner asked for a 1:500 simulation with strategy-driven stops; advice given was 0.5% (max 1%) plus a 5x notional cap, and an out-of-sample test on imported gold history before live size.

**How to apply:** if the owner returns with a leveraged engine plan or a risk-percent decision, start from these numbers; recheck Exness account terms (stop-out, swap, min lot) since they were search-snippet only. Related: [[project_gold_window_round_trip_and_timeframe_edge]], [[project_triple_screen_canonical_gap_and_old_run_costs]].
