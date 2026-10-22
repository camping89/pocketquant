---
title: Exness live trading armed with entries paused
date: 2026-10-21
summary: Deploy C armed EXNESS_LIVE_TRADING with the stored pause surviving the restart; all subscriptions paper
---

# Exness live trading armed with entries paused

## What happened
- Phase 10 of plans/261019-1957-exness-go-live ran on 2026-10-21 UTC.
- M1 edge probe found XAUUSD 1m candles 360 days back. XAUUSD:EXNESS 1m backfill (246 days): fetched=354240, total_bars=354268, exit 0.
- Entries were paused on deploy B, then `EXNESS_LIVE_TRADING=true` was pushed to pocketquant-config and deploy C dispatched (run 39655247217, HEALTHY 21/21).
- After the restart (StartedAt 2026-10-21T18:46:57Z): live_trading true, entries_paused true, 4 of 4 subscriptions paper, no exness.broker_connected. First prod proof that the stored pause survives a restart.

## Decision
- User decision 2026-10-22: skip the EURUSD and BTCUSD 1m backfills. Deep backfill is now blocked while armed (needs flag off plus two dispatches).
- Upserts overwrite `source`, so re-fetched 1m bars are now labelled rest_backfill regardless of which job first wrote them.

## Next steps
- Phase 11: take one strategy live. kongming flags XAUUSD stop distance vs. the ~25 USD risk leg at 0.01 lot as the first risk; treat `above > 0` as disqualifying.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
