---
title: Integrity counts unexpected 1m bars
date: 2026-10-21
summary: check_integrity reports stored 1m bars at closed minutes, and the daily integrity warning logs them
---

# Integrity counts unexpected 1m bars

## What happened
`check_integrity` reported only bars the calendar expects but the store lacks. A stored bar at a minute the calendar marks closed was invisible, so a wrong session model (for example after a DST change) could not show up.

## Change
- On 1m, `check_integrity` returns `unexpected_count` and `unexpected_ranges`: aligned stored bars before the bar in progress that are not on the expected grid. Other intervals return 0 and an empty list; the weekly report has neither key.
- The daily `integrity.issues_found` WARNING also fires on unexpected bars and carries `unexpected` and at most five `unexpected_ranges`.
- Two tests on the Exness XAUUSD calendar: a bar at a closed minute counts 1, a bar at an open minute counts 0.
- `docs/system-architecture.md` describes the new fields in the `sync_integrity` row.
- Commit `072c24f` on `develop`, pushed.

## Risk left
The XAUUSD calendar follows `America/New_York` DST (switch 2026-11-01). If the venue follows European DST (switch 2026-10-25), `unexpected` may fire around 21:00 UTC for one week. That is the signal working; read the first warning after 2026-10-26 before calling it a venue fault (counsel's inference, not verified).

## Next steps
Phase 05 (safeguards, stored entry pause, leverage-aware sizing).

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
