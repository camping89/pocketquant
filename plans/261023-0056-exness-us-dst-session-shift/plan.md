---
title: "Exness sessions after the US DST change"
description: "After US daylight saving ends on 2026-11-01, check in prod that the Exness XAUUSD and EURUSD sessions moved one hour later in UTC and that stored bars still pass integrity."
status: pending
priority: P2
effort: 1 check (Mon 2026-11-02)
branch: develop
tags: [exness, calendar, dst, validation]
blockedBy: []
blocks: []
created: 2026-10-23
---

# Exness sessions after the US DST change

## Overview
US daylight saving ends on Sun 2026-11-01. `ExnessSessionCalendarAdapter` holds the Exness sessions in `America/New_York` (`src/pocketquant/core/infra/calendars/exness_session_calendar_adapter.py`), so from that date it expects every UTC session edge one hour later: the Sunday reopen moves to EUR 22:05Z and XAU 23:01:30Z. Unit tests cover both sides of the change (plan 261009-0858, Phase 06). The Exness docs that claim the shift were never read (HTTP 403), so the live venue behaviour is unverified. This plan runs one read-only check in prod after the change.

Extracted on 2026-10-23 from plan `archive/261009-0858-exness-venue-lean-sync-refactor` (Phase 08, T8.7 row 4), which now treats the DST check as out of scope.

## Phases
| # | Phase | Effort | Status |
|---|-------|--------|--------|
| 01 | [Post-DST session and integrity check](./phase-01-post-dst-session-check.md) | 1 check | Pending (not before Mon 2026-11-02 03:00Z) |

## Success criteria
- C5 prints `3600 True`: the live `trade_sessions` equal the recorded constants shifted +1 h.
- C3 prints `PASS` with `misaligned 0` on every line for XAUUSD and EURUSD 1m (2 days) and 1h (7 days).
- `sync_1m p95_ms < 60000` and `CB=0`.

## Out of scope
Any code change. A `False` from C5 or a failing C3 line is recorded and reported to the user; a calendar fix would be a new plan.
