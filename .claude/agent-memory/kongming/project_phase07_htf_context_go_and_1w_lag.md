---
name: phase07-htf-context-go-and-1w-lag
description: 2026-11-01 GO for Phase 08 after Phase 07 (145590f0); reviewer's "partial 1w row stored by REST" Medium is false (both REST adapters cut at bar_start(now)); real 1w limit is a 3 h stale window on Binance Monday 00-03Z
metadata:
  type: project
---

Phase 07 (closed HTF context, commit 145590f0) got GO for Phase 08 on 2026-11-01 with no
code change. The code-reviewer's Medium ("sync_backfill may store the in-progress 1w bar")
was rejected on evidence: `exness_adapter.py:39,58` and `binance_adapter.py:66,91` both
drop bars with `datetime >= bar_start(now)`, so no open candle is ever stored by REST.

The real 1w limit is lag, not partiality: the closed 1w bar lands only when
`sync_backfill` runs at 03:00Z. Binance weeks open Monday 00:00Z, so a `1w` context
interval on a Binance symbol serves the week-before-last for Monday 00:00-03:00Z and
re-reads Mongo on every entry bar in that window (one WARNING). Exness gold/FX are closed
Sunday 00:00-22:00Z so the lag never meets an entry bar there; Exness BTCUSD trades
weekends (unverified whether its week also opens Sunday 00:00Z).

Carried, not fixed: 1w note goes into Phase 09's architecture-doc rewrite (A13); shared
mutable cached Bar objects, shorter warm-up contexts for early replayed bars, and the
harmless double read from two concurrent bar handlers were accepted.

**Why:** Phase 07's doc bullet text was mandated verbatim and names only the sync_1m
limit; Triple Screen (Phase 14) uses 15m/1h/4h, so 1w has no consumer in this plan.

**How to apply:** Do not reopen the "partial 1w" claim; if a strategy later declares `1w`
on a Binance symbol, the fix is a cascade or an earlier backfill, not a context change.
Related: [[exness-1d-rest-equals-1m-aggregate]].
