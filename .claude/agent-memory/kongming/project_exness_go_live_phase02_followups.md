---
name: exness-go-live-phase02-followups
description: Phase 02 of plans/261019-1957-exness-go-live closed 2026-10-21 (commit 94b5a98); two accepted gaps left as follow-ups, not code changes
metadata:
  type: project
---

Phase 02 (broker per subscription, one pooled Exness adapter) closed as DONE on 2026-10-21, commit 94b5a98 on develop. Two gaps were seen and deliberately left:

1. `StrategyAppService.stop()` disconnects only brokers in `self._brokers`; a pooled venue adapter whose last holder was unloaded stays connected until process exit (harm: shutdown-only noise, L/L).
2. A stored `broker` outside paper/exness makes `Subscription.from_mongo` raise, so it fails app startup (`bootstrap` -> `list_all`) and `GET /api/v1/subscriptions/`, not only reconcile as the phase text says. Fix path is a direct Mongo edit. Accepted as fail-closed.

**Why:** both are low-harm, the phase was pushed, and the plan's cook runner is strictly phase-ordered; the user prefers extending the existing plan over ad-hoc scope.
**How to apply:** when consulted on Phase 05/11, do not re-flag these as blockers; if the planner edits phase 05 anyway, the one-line `stop()` fix (iterate the pool, dedupe by identity) and a test in `tests/engine_test/test_subscription_broker_selection.py` is the cheapest place. Phase 05 must pass `Safeguards` by reference into the once-per-process adapter (its text already does). SPA `broker` type is owned by Phase 06 Task 6.2.
