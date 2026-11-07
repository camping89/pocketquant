---
name: phase10-early-close-d37-phase11-rearm
description: Phase 10 of plan 261028-0652 closed early (D37) on 2026-10-31; Phase 11 re-arm advised GO with weekend arm and Monday-first Resume; go-live phase text has stale 8 h warm-up waits
metadata:
  type: project
---

Phase 10 (prod verification) closed early on 2026-10-31T02:33Z by owner decision D37: 7 counted handovers (6 re-rolls) and ~19 h paper, with the 10-handover, 14-day and weekly-row criteria waived. Kongming advised GO for Phase 11 (re-arm live) on 2026-10-31: arm on the weekend with 0 exness subscriptions and entries paused; first real-money Resume no earlier than Monday 2026-11-02 after the Sunday 2026-11-01 reopen (first US-DST-shifted session, XAUUSD reopen 23:01:30Z) is seen under pause; no WiredTiger cap or mem_limit before arming; soft rule mem_available_mb >= 1000 before a D33 re-roll (kongming's threshold, not an owner decision). Report: plans/261028-0652-exness-only-parallel-runtime/reports/kongming-phase-10-checkpoint.md.

**Why:** The waived criteria were the only coverage of weekend reopen, DST shift and multi-day memory; Phase 11 sequencing covers the first two cheaply, and every traced failure path ends in a skipped entry, a venue rejection or a venue-protected restart.

**How to apply:** When consulted during Phase 11, check whether the Monday observation and the snapshot rule were applied. Note the go-live plan text (261019-1957 phase-11) still says warm-up takes "about 8 open-market hours" and uses `now + 8 h` waits; warm-up now reads 500 stored bars at start (`strategy_app_service.py:45,288`), so the zero-money proof can land minutes after a reopen. Heavy-job resume after a worker handover has never run in prod; avoid re-rolls at 03:00Z, 04:00Z, 00:00Z and 12:00Z job windows.
