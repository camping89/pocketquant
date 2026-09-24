---
title: A weekend test found a calendar bug that had corrupted prod bars
date: 2026-09-24
summary: Data-lag flag shipped; cascade.partial_aggregate retired; CME evening minutes fixed and 24 bars repaired
---

# A weekend test found a calendar bug that had corrupted prod bars

## What happened
The user asked for a data-lag flag (the free TradingView feed runs ~10-15 min behind
CME) and for `cascade.partial_aggregate` to stop, since it fired ~17 times a minute on
futures and duplicated the daily integrity check. Both shipped in `bc7a0e8..cfbc1f4`.

The advisor's first catch was that a flag already half-existed: `is_stuck` read true
for ES/NQ/YM all session. Lag is now counted in trading minutes from the newest 1m bar
(no provider branching), classified ok/delayed/stuck/closed/unknown, stored in Redis
by a `data_lag_check` job each minute, and shown as a ticker badge.

The test "five minutes after the Sunday open, Friday's last bar is five minutes
behind" returned 0. `CmeGlobexCalendarAdapter.trading_minutes` loaded sessions only up
to the window's end date, and a CME session opens the evening before its date. Every
window ending 22:00-24:00 UTC counted no minutes. The cascade sizes its 1m query from
that count, so each evening 15m/1h bucket was built from its last five 1m bars. In
prod: 24 bad bars from the evening of 2026-09-23 (ES 1h 22:00 stored volume 87, true
5091). `sync_backfill` never overwrites existing bars, so they would have stayed wrong.

## Decision
- Backed up futures 15m/1h with a filtered `mongodump`, rewrote only the 24 mismatched
  bars from their 1m bars, re-checked to zero.
- Code review found two classification bugs before ship: a shut market read as
  "delayed" all weekend (the sync stops before the delayed tail arrives), and a sync
  that stopped running never became stuck (the empty-sync streak only grows when the
  sync runs). Closed now wins outright; stuck also fires past 30 min of lag or 5 min
  without a 1m sync.

## Next steps
- The 04:00 UTC integrity run still sees the delayed tail as missing; ending its grid
  at `now - lag` would fix that.
- Two deploys today reset the container log that the dated measurements rely on.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
