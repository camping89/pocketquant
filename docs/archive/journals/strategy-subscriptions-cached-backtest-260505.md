# Strategy Subscriptions + Cached Backtest Framework Shipped

**Date**: 2026-05-05 10:24  
**Severity**: Low (feature ship)  
**Component**: Strategy Subscriptions, Backtest Cache, Job Scheduling  
**Status**: Resolved  
**Commit**: 98574c496cc76ff881b74be977928b09682efeae (develop)

## What Happened

Completed 4-phase implementation of strategy subscriptions (1:N cardinality with symbols/exchanges/intervals) and cached backtest jobs via APScheduler. Feature deployed to production VPS with all integration tests green.

## Technical Details

### Core Changes
- **Mongo schema**: New `strategy_subscriptions` collection with sparse unique index `(strategy_id, symbol, exchange, interval)`.
- **Backtest cache**: `backtest_runs` doc keyed by `subscription_id`, keyed retrieval via subscription lookup.
- **Job scheduler**: APScheduler one-off tasks via `add_one_off_job()` + DateTrigger; auto-removal post-fire.
- **Cascade deletion**: strategy → subscriptions → backtest_runs + scheduled job cleanup.
- **Stale recovery**: Startup hook marks `running` backtest docs >10 min old as `failed`.

### Bug Fixes (Review → Shipped)

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| **C1** Backtests misreported as 'done' | `save_for_subscription` hard-coded status instead of using `BacktestResult.status` | Now honors actual result status |
| **C2** Concurrent jobs clobbered in-memory strategy state | No job ID isolation; multiple jobs wrote same doc | Synthetic ID: `{strategy_id}::bt::{sub_id}` per job |
| **M1** TOCTOU: running jobs could resurrect deleted backtest docs | No subscription existence check during write | Re-check subscription before each backtest save |
| **M2** N+1 Mongo queries in `ListSymbolsHandler` | Sequential subscription status fetches | Batch via `get_subscription_statuses` |
| **M3** FE status flip gap | `running` → `completed` transition missed cache invalidation | Track prev-status via `useRef` in hook |
| **M7** Status vocabulary mismatch | Mixed `'done'` vs `'completed'` strings | Unified to `'completed'` throughout |

### Deployment
- **CI**: Docker images pushed to Docker Hub, all tests green.
- **VPS**: deploy.sh successful, containers healthy.
- **Smoke tests**: 6 new endpoints respond correctly; edge cases (404s) validated.

## What We Tried

- **E2E path on VPS**: Could not exercise full happy path (load strategy YAML → add subs → run-all → cached read) due to missing sample YAML. Covered instead via unit + integration tests against testcontainer Mongo.

## Root Cause Analysis

All critical issues stemmed from missing isolation/validation patterns:
- **Job isolation**: No synthetic ID scheme → concurrent writes collided.
- **Cascade safety**: No subscription existence re-check → orphaned backtest docs possible.
- **Status contract**: No single-source-of-truth for status enum → mixed 'done'/'completed' strings leaked.

## Lessons Learned

1. **Synthetic IDs for concurrent resources**: When APScheduler/Celery jobs mutate shared Mongo docs, prefix job ID into doc ID to prevent clobbering.
2. **TOCTOU on cascade**: Re-check parent existence before each child mutation, even if parent was validated moments before.
3. **Enum contracts in distributed systems**: Define status enums in domain layer, not controllers; use them consistently across backend/frontend.
4. **Cache invalidation timing**: FE state flip requires prev-value tracking (`useRef`) to catch intermediate states before polling catches up.

## Next Steps

- **Code size**: `BacktestRepository` now 243 LOC, exceeds 200-LOC guideline. Scheduled for follow-up modularization.
- **Status code mismatch**: Duplicate subscriptions return 400 (DomainError) vs plan's stated 409. Update API spec or handler.
- **Config**: Stale-recovery threshold hardcoded to 10 min. Make Settings-configurable per plan intent.
- **Test coverage**: Concurrent run-all test (N9) is weak — jobs auto-remove post-fire, so assertion passes regardless. Strengthen by capturing job IDs pre-fire.

## Unresolved Questions

- Should duplicate subscription attempt return 409 (Conflict) per REST convention, or remain 400 (BadRequest) for domain-layer consistency?
- Is 10-minute stale-recovery threshold correct, or should it be derived from max_job_wait or similar SLA setting?
