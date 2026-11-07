---
name: exness-1d-rest-equals-1m-aggregate
description: Prod check 2026-11-01 - Exness REST 1d/1w bars equal the UTC-day / Sunday-week aggregate of stored 1m bars; 1d lands via sync_repair 00:00:18-00:39Z; conditions payload has no order_types; prod had 4 subs not 1
metadata:
  type: project
---

Exness stored REST 1d bars equal the aggregate of that UTC day's stored 1m bars exactly on
OHLC (8 session days x 3 symbols, Sunday bars included; one BTCUSD volume diff of 0.009%),
and 1w bars equal the Sunday-to-Sunday 1m aggregate. Exness D1 opens 00:00Z, W1 Sunday
00:00Z. The "vendor session candle need not match a UTC bucket" reason behind
`cascade_tfs` omitting DAY_1 for session calendars is therefore false for Exness; the
advice report `plans/reports/advise-261101-0847-stf-to-mtf-migration.md` item 6 plans the
1d cascade (plan only as of 2026-11-01).

Measured path today: yesterday's 1d bar is inserted by `sync_repair` at 00:00 UTC
(`created_at` 00:00:18Z-00:39:51Z, `source=rest_repair`); `sync_backfill` 03:00Z is the
fallback and is the only writer of 1w (closed week lands Sunday 03:01-03:03Z). `sync_repair`
records no per-interval details, so job_history cannot show 1d inserts; read the bars.
The REST adapter never stores the open 1d/1w candle (cutoff at `exness_bar_start(now)`).

Exness `GET .../instruments/XAUUSD/conditions` on this account returns no `order_types`
field (keys: calc_mode, exec_mode, trade_mode, trade_sessions, volume_*, swap_*, ...), so
pending-stop support stays unverifiable read-only.

Prod state 2026-11-01 08:00Z: 4 paper subscriptions (hitnrun2 + engulfing on
BTCUSDT:BINANCE 1m running, hitnrun2 XAUUSD:EXNESS 1m running, engulfing EURUSD:EXNESS 1h
stopped), 0 exness-broker subs, entries_paused=true, live_trading=false, 2 open paper
positions on BTCUSDT:BINANCE. The 2026-10-31 handoff listed only one subscription.

**Why:** The STF-to-MTF advice first claimed an "up to an hour" lag and an hourly
freshness job; the owner asked for a verified correction and a 1d cascade plan.

**How to apply:** Do not propose a REST freshness job for Exness HTF bars; the 1d cascade
is the fix and 1w needs nothing while gold/FX are closed on Sunday morning. Re-query
subscriptions and open positions before any prod delete; handoffs go stale within a day.
Related: [[exness-venue-no-tick-gaps]] (the one risk for a cascade open differing).
