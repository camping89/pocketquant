# Report: debug-audit-order-execution.md trim

**Date:** 2026-05-25 | **Item:** docs audit #13

## Line Count

| | Lines |
|-|-------|
| Before | 401 |
| After | 195 |
| Reduction | 51% |

## Sections Kept (Golden Path)

All 7 steps preserved with factual content intact:
1. Load Strategy — route → YAML parse → CQRS handler → in-memory store
2. Start Strategy — broker connect → event subscriptions
3. Market Data In — tick → bar → BarCompletedEvent → EventBus dispatch
4. Strategy Signal — on_bar() → risk check → position sizer
5. Submit Order — write-ahead persist → OKX REST → broker map
6. Fill → Position — OrderFilledEvent → PositionAggregate → persist
7. Verify Persistence — mongosh + redis-cli spot checks

## Sections Moved to Appendix

- **Appendix A (edge cases):** partial fills, OKX error codes table (51000/51001/51008/51010), race condition on concurrent bars, strategy restart / orphan order recovery, paper broker quote-cache dependency
- **Appendix B (diagnostic commands):** mongosh queries (order detail, stuck orders, P&L, bars), redis-cli inspection, log grep patterns

## Sections Removed

- Verbose "Why X?" design rationale paragraphs (CQRS/Mediator justification, in-memory EventBus YAGNI note, write-ahead rationale, weighted avg entry explanation, etc.) — architecture decisions table at end of original
- Full sample YAML block (30 lines) — belongs in run-and-test-guide, not debug doc
- 24-row verification checklist — condensed into per-step "Expected / Unexpected" lines
- 21-row key files table — path references kept inline per step, not as a separate section
- "Big Picture" flow diagram — redundant with step headers

## Stale Code References Found

| Reference in Doc | Status |
|-----------------|--------|
| `concepts/risk/risk_check_handler.py` (Step 4b in original) | STALE — `RiskCheckHandler` lives in `trading/handlers/risk/check_risk/`, not `core/concepts/risk/`. Rewritten doc references by class name only, no path. |
| `core/persistence/repositories/*` (Step 7 in original) | STALE — order/position repos are in `trading/persistence/`, not `core/persistence/repositories/` (core repos = bar, symbol, sync_status only). Rewritten doc references `trading/persistence/position_repository.py` correctly. |

All other referenced files verified present:
`trading/handlers/strategy/load/route.py`, `load/handler.py`, `app_services/yaml_strategy_loader.py`, `app_services/strategy_app_service.py`, `app_services/order_app_service.py`, `app_services/position_app_service.py`, `brokers/okx/okx_broker.py`, `core/common/messaging/event_registry.py`, `core/common/messaging/event_bus.py`, `api/market_data/app_services/quote_app_service.py`, `api/market_data/app_services/bar_app_service.py`, `core/domain/order/entities.py`, `core/domain/position/entities.py`, `core/concepts/risk/services/position_sizer.py`
