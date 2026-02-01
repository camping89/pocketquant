# Phase 1: Fix src/ Type Errors

## Context
- **Parent Plan:** [plan.md](./plan.md)
- **Mode:** standard (not strict)
- **Config:** pyrightconfig.json already updated

## Overview
- **Priority:** High
- **Status:** Pending
- **Description:** Fix ~115 type errors in src/ directory

## Files to Fix (by error count)

### High Priority (5+ errors)
| File | Errors |
|------|--------|
| src/features/market_data/quote/handler.py | 8 |
| src/infrastructure/scheduling/scheduler.py | 6 |
| src/infrastructure/brokers/okx/websocket/okx_reconnection_handler.py | 6 |
| src/main.py | 5 |
| src/infrastructure/brokers/okx/websocket/okx_websocket_client.py | 5 |
| src/features/backtesting/handlers/backtest_handlers.py | 5 |

### Medium Priority (3-4 errors)
| File | Errors |
|------|--------|
| src/infrastructure/tradingview/websocket.py | 4 |
| src/infrastructure/tradingview/provider.py | 3 |
| src/infrastructure/brokers/okx/okx_broker.py | 3 |
| src/infrastructure/brokers/factory.py | 3 |
| src/features/trading/managers/position_tracker.py | 3 |
| src/features/strategy/handlers/command_handlers.py | 3 |
| src/features/strategy/engine/strategy_engine.py | 3 |
| src/features/market_data/sync/handler.py | 3 |
| src/features/market_data/status/handler.py | 3 |
| src/common/tracing/request_logging.py | 3 |
| src/common/tracing/correlation.py | 3 |
| src/common/rate_limit/middleware.py | 3 |
| src/common/idempotency/middleware.py | 3 |

### Low Priority (1-2 errors)
- src/infrastructure/persistence/redis.py (2)
- src/infrastructure/persistence/mongodb.py (2)
- src/features/trading/api/routes.py (2)
- src/features/strategy/loader/yaml_loader.py (2)
- src/features/strategy/handlers/query_handlers.py (2)
- Various other files with 1 error each

## Common Error Types

1. **reportOptionalMemberAccess** - Accessing attribute on possibly None
   ```python
   # Error: "x" is not a known attribute of "None"
   self._client.send()  # _client could be None

   # Fix: Add None check
   if self._client:
       self._client.send()
   ```

2. **reportArgumentType** - Wrong argument type
   ```python
   # Fix: Cast or fix the type
   ```

3. **reportReturnType** - Return type mismatch
   ```python
   # Fix: Update return type annotation or fix return value
   ```

## Implementation Steps

1. Run `npx pyright src/` to get current error list
2. Fix files in order of error count (highest first)
3. After each file, run `npx pyright <file>` to verify
4. Commit after each major module is fixed

## Todo
- [ ] Fix src/features/market_data/quote/handler.py (8 errors)
- [ ] Fix src/infrastructure/scheduling/scheduler.py (6 errors)
- [ ] Fix src/infrastructure/brokers/okx/websocket/*.py (11 errors)
- [ ] Fix src/main.py (5 errors)
- [ ] Fix src/features/backtesting/handlers/*.py (5 errors)
- [ ] Fix remaining src/ files

## Success Criteria
- [ ] `npx pyright src/` shows 0 errors
- [ ] No `# type: ignore` comments added

## Next Steps
→ Phase 2: Fix tests/ type errors
