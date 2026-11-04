---
title: Symbol lookup race, cascade read limit and positions route fixed
date: 2026-11-04
summary: "One cache read in SymbolLookupHelper, no calendar-sized limit on the cascade's 1m read, and the unused positions route removed; three commits green in CI"
---

# Symbol lookup race, cascade read limit and positions route fixed

## What happened
This is Phase 02 of `plans/261103-1741-1d-cascade-fold-and-small-fixes`. It has three commits on `develop`, and CI run 41765510772 passed on `4933e028`.

- `SymbolLookupHelper.get` reads the TTLCache once. The installed cachetools 7.1.4 `TTLCache.get` freezes its timer for the membership test and the read together, so they cannot disagree. A plain `in` followed by `[]` reads the clock twice and raised the `KeyError` that reconnected the prod Binance stream.
- `cascade_for_symbol` no longer passes `limit=expected_count + 5`. The read returns newest first, so a day with more stored minutes than the calendar counts lost its opening bars. In the new test the 1d open came out as 157 instead of 100.
- The `/subscriptions/{id}/positions` route and `get_positions` are gone.

## Lessons
- A Python script that edits a file with `read_text`/`write_text` on Windows writes CRLF. The repo's `.gitattributes` requires LF. Read and write bytes, then check with `git ls-files --eol`.
- Integration tests error instead of failing when Docker Desktop is down. Start Docker before reading a red pytest run.

## Next steps
Phase 03 re-cascades 7 days on every repair and backfill. kongming's top risk: the longer `sync_repair` stall may pass `sync_1m`'s 100-minute lookback. Time the re-cascade across all tracked symbols.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
