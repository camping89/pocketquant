---
title: Exness spike gate checks candle presence
date: 2026-10-11
summary: T1.11 condition (f) stops on empty or stale XAUUSD candles
---

# Exness spike gate checks candle presence

## What happened
The spike's feasibility gate (P01 T1.11) had no check that candles came back. If a negative `count` reads forward (the spec only says "bidirectional"), the spike could pass with empty fixtures and the failure would surface only in Phase 06.

## Decision
T1.4 step 13 records `fetched_at`; T1.11 condition (f) stops when any XAUUSD candle file is empty or the latest M1 candle is not within 24 h before `fetched_at`. A one-line command prints `True`/`False` and is part of the T1.11 Verify.

## Next steps
`ak plan validate` prints `[OK]`; cook from T1.2.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
