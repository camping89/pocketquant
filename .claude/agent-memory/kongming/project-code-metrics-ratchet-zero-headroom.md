---
name: code-metrics-ratchet-zero-headroom
description: The code-metrics ratchet (tiny_share 0.48 / delegations 77) was frozen at develop's exact numbers with no slack; Phase 06 Exness could not pass it by honest restructuring and was escalated 2026-10-16
metadata:
  type: project
---

Commit 12f73cc froze `[tool.code-metrics]` at develop's exact values (tiny_share 372/775 = 0.4800, delegations 77). Any new module with more than 48% tiny functions, or a single new one-line `return self._x.y()` method, fails CI.

**Why:** On 2026-10-16 Phase 06 (Exness market data) added 74 measured functions of which 32 tiny ones are plan-mandated API/port members; even inlining every non-mandated helper left tiny_share at 0.4827 and delegations at 85. Kongming advised the honest 3-step package (inline `_utc`, move the pacer lookup into `_send_paced`, direct lookup in `_on_tick`) and escalation as the plan's "ratchet would need a higher ceiling" stop-and-ask.

**How to apply:** Before advising on any ratchet failure, check `pyproject.toml` `[tool.code-metrics]` to see whether the user raised the ceiling, changed the metric, or paid down debt elsewhere. Adapter-heavy phases (07 broker adapter, 08) will hit the same wall unless the decision was made once. Excluding `@override` port members from the metric is NOT sufficient on its own (estimated 0.489 for Phase 06).
