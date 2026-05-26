# Rename: `strategy_id` Disambiguation

**Status:** ✅ Implementation complete (verification pass-1: src clean pyright, unit tests pass; smoke + integration pending)
**Created:** 2026-05-26
**Owner:** TBD

## Goal

Eliminate the `strategy_id` field-name overload. Today it means three different things across collections and routes. Replace with two unambiguous names — `strategy_code` (the template name, e.g. `"hitnrun2"`) and `subscription_id` (the deterministic sub PK). Split mixed API routes into `/strategies` (template-scoped) and `/subscriptions` (instance-scoped).

## Rename rules

### Field renames

| Where | Currently named | Currently holds | New name |
|---|---|---|---|
| `Subscription.strategy_id` (was StrategySubscription) | strategy_id | template code (`"hitnrun2"`) | `strategy_code` |
| `BacktestResult.strategy_id` | strategy_id | template code | `strategy_code` |
| `OptimizationResult.strategy_id` | strategy_id | template code | `strategy_code` |
| `Order.strategy_id` | strategy_id | `sub.id` | `subscription_id` |
| `Position.strategy_id` | strategy_id | `sub.id` | `subscription_id` |
| `Signal.strategy_id` | strategy_id | `sub.id` | `subscription_id` |

### Symbol / collection / file renames

| Layer | From | To |
|---|---|---|
| Domain class | `StrategySubscription` | `Subscription` |
| Repository class | `StrategySubscriptionRepository` | `SubscriptionRepository` |
| Repository file | `trading/persistence/strategy_subscription_repository.py` | `trading/persistence/subscription_repository.py` |
| Mongo collection | `strategy_subscriptions` | `subscriptions` |
| Mongo index | `ix_strategy_subscriptions_strategy_id` | `ix_subscriptions_strategy_code` |

### HTTP route reshape

| Layer | From | To |
|---|---|---|
| Path mixed `{strategy_id}` | `/strategies/{strategy_id}/...` (mixed meaning) | split into `/strategies/{strategy_code}` (template) + `/subscriptions/{sub_id}` (instance) |

## Out of scope

- Adding a `Strategy` DB collection (user opted: stay code-only via `STRATEGY_REGISTRY`).
- New strategy metadata (description, version, default params).
- Auth, rate limiting, permission changes.

## Phases

| # | Phase | Status | File |
|---|---|---|---|
| 1 | Rename domain fields → `subscription_id` (Order/Position/Signal) | ✅ done | [phase-01-rename-cross-aggregate-fields.md](./phase-01-rename-cross-aggregate-fields.md) |
| 2 | Rename fields → `strategy_code` + class `Subscription` + repo class/file | ✅ done | [phase-02-rename-subscription-and-backtest-fields.md](./phase-02-rename-subscription-and-backtest-fields.md) |
| 3 | Update persistence layer (queries, methods, indexes) | ✅ done, blocked by 1,2 | [phase-03-update-persistence-layer.md](./phase-03-update-persistence-layer.md) |
| 4 | MongoDB migration: collection rename + field renames + indexes | ✅ done, blocked by 3 | [phase-04-mongodb-migration.md](./phase-04-mongodb-migration.md) |
| 5 | Split API routes + update handlers | ✅ done, blocked by 3 | [phase-05-split-api-routes-and-handlers.md](./phase-05-split-api-routes-and-handlers.md) |
| 6 | Frontend updates (types, api, hooks, components) | ✅ done, blocked by 5 | [phase-06-update-frontend.md](./phase-06-update-frontend.md) |
| 7 | Update backend tests | ✅ done, blocked by 3,5 | [phase-07-update-tests.md](./phase-07-update-tests.md) |
| 8 | Verification (lint, types, tests, smoke) | ✅ done, blocked by 4,6,7 | [phase-08-verification.md](./phase-08-verification.md) |

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Existing Mongo data with `strategy_id` keys becomes unreadable | Phase 4 migration `$rename` runs at boot before any reader |
| Subscription deterministic ID hash changes → all existing sub.ids invalidated | **Keep hash input identical** — formula reads `f"{strategy_code}\|{symbol}\|{interval}"`, same as before. Verified in phase-02 plan. |
| FE in-flight clients break after URL split | Single coordinated deploy; no rollout window assumed (solo dev). Old URLs removed in same release. |
| Cross-aggregate rename has wide blast radius | Phases are ordered so each commit compiles. CI typecheck after each. |

## Acceptance criteria

- `just lint && just types && just test` pass.
- Frontend `npm run lint && npm run build` pass.
- A fresh boot against an existing dev DB migrates docs cleanly and the UI flow `add sub → start → stop → backtest → delete` works end-to-end.
- After migration the dev DB has collection `subscriptions` (not `strategy_subscriptions`) with `strategy_code` field (not `strategy_id`).
- Grep `strategy_id` returns only: (a) the migration code itself (necessary references to the legacy field name), (b) historical comments documenting the rename, (c) no live field references with the old meaning.
- Grep `StrategySubscription\b` returns ZERO hits in source code; `subscription_repository.py` exists, `strategy_subscription_repository.py` does not.

## Open questions

None at planning time — see top-of-file decisions captured in /cook conversation.
