---
title: Exness plan validation session 3
date: 2026-10-11
summary: "Lean access point, plan dir committed per ship, editorial fixes; plan validates OK"
---

# Exness plan validation session 3

## What happened
An advisory pass on `plans/261009-0858-exness-venue-lean-sync-refactor` re-checked about 49 load-bearing claims against the repo at `29f2f67` and Exness OpenAPI 1.0.2. All held except the Session 2 access-point subsystem: `GET /v1/trading/access-point` is absent from the spec and only trading calls (never made in this plan) need it.

## Decision
- Access point is resolved once per process, in memory. The Redis cache, TTL, 421 re-resolve, hourly refresh job, preload and their tests were removed from P06/P09; persistence and refresh move to the go-live plan.
- The plan directory is committed whole in every ship step (CI ignores `plans/**`).
- Editorial fixes: T1.1 drops the stale IP-allowlist wording and skips when preconditions are already recorded; T5.2 names source headings; T8.4 derives BTCUSD minimums from the session calendar; T8.6 states the paper week runs without spread; T4.3 drops a stale router comment; P03 line citations corrected.

## Next steps
`ak plan validate` prints `[OK]`. Cook from Phase 01 T1.2 (T1.1 is already satisfied).

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
