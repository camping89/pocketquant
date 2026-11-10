---
name: project-exness-go-live-split
description: Exness plan (261009-0858) builds the broker but keeps live trading off; go-live, auth, broker selection and :OKX data identity decisions
metadata:
  type: project
---

User decisions from validation session 1 on 2026-10-10 for `plans/261009-0858-exness-venue-lean-sync-refactor/`:
- The Exness broker is built and tested with recorded fixtures, but it stays behind `EXNESS_LIVE_TRADING` (default false). There is no per-subscription broker field and no public API change. Auth on mutation routes, broker selection, the U3 risk cap and live round trips belong to a separate, later go-live plan.
- The code metric gate is a ratchet: freeze the post-refactor values in `[tool.code-metrics]`. The ceiling only moves down. The ≤30% tiny share and ≤20 delegations are aspirations, not gates.
- Market data routes strictly by exchange suffix through `SyncPolicies.policy_for`. Each policy carries its own providers. There is no router module and no cross-exchange fallback.
- `:OKX` market-data symbols are migrated to `:BINANCE` (OKX is broker-only). The migration requires a backup and user approval.
- Follow-up answers:
  - Async fill wiring is Exness-only, through `IBroker.fills_async`, and OKX stays byte-identical.
  - Exness 429s are never retried automatically, following the spec literally. Transport-error retries with the same idempotency key are allowed.
  - The daily loss cap counts close, swap_fee, admin_fee and dividend deals plus commission, and excludes balance deals.

**Why:** Live money should not move before auth and broker selection exist. The user prefers measurable ratchets over aspirational thresholds.

**How to apply:** In follow-up Exness plans, treat going live as its own plan with these preconditions. Never propose setting `EXNESS_LIVE_TRADING=true` or adding a broker field inside refactor or data work. Related: [[feedback-dishka-di]]
