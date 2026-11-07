---
name: exness-recorded-session-facts
description: Facts from the 2026-10-13 Exness spike fixtures that shape calendar/integrity advice (D1 Sunday candle at 00:00Z, tickless EURUSD minutes, W1 never recorded)
metadata:
  type: project
---

Exness fixtures (tests/core_test/infra/exness/fixtures, recorded 2026-10-13) show: D1 candles sit on UTC midnight for Sun-Fri (Sunday bar exists at 00:00Z although trading starts Sun 22:01:30Z for XAUUSD / 21:05Z for EURUSD), no Saturday bar; the in-progress D1 is returned. XAUUSD M1 across the Mon 20:58-22:00:29 break matched the "minute overlaps a segment" rule exactly (0 missing / 0 extra over 1000 bars); EURUSD M1 had 2 tickless minutes (Mon 21:00, 21:03) with no candle. No W1 candle was ever recorded; Exness W1 week-start convention is unknown.

**Why:** Integrity's D1 grid is `session_open(d)` for `sessions(start,end)` (integrity_jobs.py), so a session_open that is not the D1 bar time, or a sessions() that includes a Sunday before its first trade, produces a permanent weekly false "missing". Tickless minutes mean small 1m missing counts on thin pairs are expected, not a calendar bug.

**How to apply:** When advising on Exness calendar/integrity work, anchor on these recorded facts; treat W1 alignment as unverified until a prod read-only candles call shows the W1 `time` weekday.
