# Realtime Quote/Bar Pipeline: Architecture Decisions & Mental Model Corrections

**Date**: 2026-05-06 19:59  
**Severity**: High (foundational architecture)  
**Component**: Quote/Bar pipeline (WS + Cron + SSE streams)  
**Status**: Decision-locked, implementation planned

## What Happened

Brainstorm session to fix dead realtime bar infrastructure. Static bars (5m refresh only on window close; 1d never changes) exposed architectural rot: WS client + BarAppService.add_tick() exist but never auto-start, never subscribe, SSE ignores Redis in-progress bars (MongoDB-only reads). Realtime stack = abandoned code.

## The Brutal Truth

This hurt. Two hours debating what should've been obvious: either commit to realtime or don't. Half-implemented infrastructure masquerading as features wastes engineering time during backtesting and confuses strategy authors about data freshness. Worse: discovered during user testing, not integration testing. We shipped broken promises.

## Architectural Decisions

**Single-writer principle locked across bar lifecycle:**
- **quote:latest**: Redis only (WS writes). No MongoDB.
- **bar:current** (in-progress): Redis only (WS writes). No MongoDB.  
- **bars** (closed): MongoDB only (sync_1m cron writes). No WS.
- **event_bus**: In-process (WS publishes). No cron.

**Cron consolidation**: 8 jobs (sync_5m, sync_15m, sync_hourly, sync_swing, sync_daily, sync_backfill, sync_integrity, sync_repair) → 1 job (sync_1m every 60s, batch n=100). sync_1m is canonical closed-bar writer; REST get_hist reflects MongoDB truth.

**WS scope**: Chart drawing FE + Redis state only. Does NOT persist bars to MongoDB.

**Strategy onboarding**: Tracked_symbols = single MongoDB config collection (admin-managed). Strategy validates symbol exists at setup → 400 error if not. NO auto-subscribe.

**v1 scope**: 1m timeframe only. Multi-timeframe aggregation post-MVP.

## Mental Model Corrections (Critical Learning)

**Correction 1: Cascade aggregation myth**

*What user believed*: "1d bar requires too many ticks to aggregate realtime; must store all ticks; only cron can consume tick stream."

*Reality*: Running OHLCV state is O(1) per tick. No tick storage. Each timeframe maintains independent in-progress bar:
- open = first tick price
- high = max(high, tick)
- low = min(low, tick)  
- close = tick price
- volume += tick volume

Same tick stream feeds all timeframes in parallel. User was conflating "need many ticks" with "need to store many ticks" — confusing input volume with state cardinality.

**Correction 2: Dual-writer fallacy**

*What user proposed*: "WS persists closed bars to MongoDB as optimization; cron acts as backup/validation."

*Why it failed*: Two concurrent writers for same bar entity = race condition, divergence without resolution rule. Closed bar at cron run time could differ from WS-written bar (lag, rounding, network jitter). No way to pick winner. Breaks contract: "bars[id] is authoritative state."

*Resolution*: Lifecycle split (WS = in-progress only; cron = closed only). Single writer per bar phase → CRDTs not needed → causality clear.

## Outputs

- Brainstorm report: `/Users/admin/workspace/_me/algo-trading/plans/reports/brainstorm-260506-1959-realtime-quote-bar-pipeline.md`
- Implementation plan (7 phases): `/Users/admin/workspace/_me/algo-trading/plans/260506-1959-realtime-quote-bar-pipeline/plan.md`

## Next Steps

1. Lead reviews architectural decisions (scope, single-writer matrix, v1 1m-only constraint).
2. Implement phase-by-phase per plan.
3. Integration test: WS subscribed → in-mem bars tick → Redis flush 200ms → SSE clients see quote:latest + bar:current live.
4. Validate: closed bars only from cron, no WS writes to MongoDB.

---

**Lessons for future work**: 
- Partial implementations are debt, not optionality. Kill or commit.
- Multi-writer systems need explicit conflict resolution rules from day 1; "backup" is not a rule.
- Mental models matter: test assumptions early (O(n) vs O(1), storing vs computing).
