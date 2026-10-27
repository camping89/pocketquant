---
title: Asset-class index-futures plan closed
date: 2026-10-24
summary: "Row 11 and G2 measured, plan archived; paper SL/TP interval defect and 04:00 stall deferred"
---

# Asset-class index-futures plan closed

## What happened
- Verify-cascade race fixed (`_verify_one_symbol` drops the newest bucket). Row 11 re-measured: Pass, ES 23 compared runs at div=0, 1 vendor fail, 0 alerts.
- Futures paper sizing: `PAPER_FUTURES_INITIAL_BALANCE=200000`, `PAPER_FUTURES_LEVERAGE=25`, released to prod.
- G2 ES 15m engulfing paper session: 4 trades, pnl arithmetic exact. 2 of 4 exits were triggered by 4h bars, not by prices after entry. Cause: `PaperBrokerAdapter._on_bar_completed` has no interval filter (`plans/reports/archive/debug-261024-0423-paper-sl-tp-fires-on-higher-interval-bars.md`).
- Plan archived to `plans/archive/260921-1436-asset-class-index-futures/`, commit `1c6aa54d` on develop. No deploy.

## Process mistakes
- A blanket sed of the old plan path over 22 md files also rewrote historical command text in reports. Fixed by restoring and rewriting only the `Plan:`/`plan:` header pointers.
- The restore loop ran `git checkout HEAD --` on every modified file, which reverted two uncommitted files of the Exness session (`plans/261009-0858-.../plan.md`, `phase-08-...md`). That session was messaged with the lost edits' tool ids; it began rewriting them. Full recovery not verified here.
- Lesson: restore only files you changed yourself; check `git status` against your own edit list first.

## Decision
- Paper SL/TP interval defect, daily 04:00 `sync_integrity` event-loop stall, and ES `commission_per_contract: null` go to a separate follow-up plan.
- ES subscription `01a16440-...de0d` stopped; delete after its open SHORT closes.

## Next steps
- One-shot check 2026-10-26 08:23 Bangkok: confirm the open position closed, delete the subscription, record it in phase 9.
- Write the follow-up plan; the interval defect first (live paper results are untrustworthy until fixed).

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
