---
name: exness-venue-no-tick-gaps
description: Exness emits 1m candles only for minutes with ticks; EURUSD loses 0-17 random minutes after the 21:00Z (summer) rollover every weekday, so integrity "missing 0" is the wrong pass rule for Exness
metadata:
  type: project
---

Exness candle gaps are venue no-tick minutes, not a schedule and not our code. Verified 2026-10-19 in prod `bars`: EURUSD:EXNESS 1m is missing a random 0–17 minutes starting 21:00Z (2026-10-08: 21:01–21:17; ten weekdays since June have none). XAUUSD and BTCUSD:EXNESS show isolated no-tick minutes too; TradingView futures carry dozens per week. A forward `getCandleHistory(from=gap_start, count=n)` read confirms the venue has nothing.

**Why:** Phase-08 row 0 (2026-10-19) failed on `missing 12` for EURUSD 1m and `missing 2` for XAUUSD 1h (2026-09-07, US Labor Day gold early close). Kongming advised option (d): no calendar change, no holiday table, no "confirmed empty" marker; the pass rule becomes "misaligned 0 and every gap venue-empty" (C3 snippet in the kongming report `plans/reports/kongming-261020-0035-exness-integrity-gaps.md` under `D:/w/_me/algotrading/plans/`).

**How to apply:** Do not propose modelling a 21:00–21:05 break in `_EURUSD_SESSIONS` (breaks C5, gap is random). Expect the thin window to move to 22:00Z after 2026-11-01 (unverified, no winter data stored). `sync_repair` re-fetches 5000 bars every 12 h for any gap inside the 7-day window and logs `integrity.repair.still_missing`; that is bounded noise already present for TradingView symbols.
