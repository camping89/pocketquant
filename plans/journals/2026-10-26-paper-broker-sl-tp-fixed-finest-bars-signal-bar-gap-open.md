---
title: "Paper broker SL/TP fixed: finest bars, signal bar, gap open"
date: 2026-10-26
summary: Paper SL/TP now uses only post-entry finest bars and fills gaps at the open; also fixed a pyright regression in sync_jobs
---

# Paper broker SL/TP fixed: finest bars, signal bar, gap open

## What happened
- Live paper closed positions on prices from before entry: the pooled PaperBrokerAdapter checked SL/TP and pending LIMITs against all 7 intervals, so a 4h bar range that predates the entry triggered exits (ES G2 trades 1 and 4).
- Gapped exits filled at the SL/TP level, not the bar open (ES SHORT stopped at the 2026-10-25 reopen: filled 7681.31, real open 7690).
- ak:fix --ultra: five independent fix plans, kongming as verifier picked the finest-interval gate plus occurred_at same-bar rule plus open-first gap rule (picked 3/5, margin low).

## Decision
- User approved the signal-bar rule in backtests too: a bar acts only on positions and orders that existed when it was published. Replay stamps occurred_at with sim time.
- Commits a4993155 (paper broker) and 851e8de1 (sync_jobs pyright repair) on develop; CI green in 3 timezones. Not deployed.

## Lessons
- The earlier verify-race commit 2be18e00 shipped two pyright errors because pyright was not run. Run the full gate, including pyright, before every commit.
- The Bash tool rejects heredocs whose body contains quotes in some cases; use the editor for code edits.

## Next steps
- Release to master when the user approves; then watch the first gap exit (fill equals the 1m open times slippage) and that a 1m strategy entry survives its own signal bar.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
