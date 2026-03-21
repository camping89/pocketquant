# Phase 3: Verify All DI Provider Imports

## Overview
- **Priority:** P1
- **Status:** completed
- **Risk:** Low — validation pass, fixes already applied in phases 1-2

After phases 1 and 2, run full import validation to catch any missed references.

## DI Provider Files to Audit

All in `packages/pocketquant-api/src/pocketquant/api/di/`:

| File | Expected State After Phase 1-2 |
|------|-------------------------------|
| `core.py` | No changes needed — imports only from `pocketquant.core` |
| `persistence.py` | OrderRepository/PositionRepository now from `pocketquant.trading.persistence` |
| `trading.py` | OrderRepository/PositionRepository now from `pocketquant.trading.persistence` |
| `infrastructure.py` | No changes needed |
| `market_data.py` | No changes needed |
| `handlers.py` | No changes needed — handler imports unchanged |
| `broker_factory.py` | No changes needed |
| `container.py` | No changes needed |

## Additional Files to Verify

- `packages/pocketquant-api/src/pocketquant/api/main_extensions.py` — imports updated in phase 2
- `packages/pocketquant-trading/src/pocketquant/trading/handlers/trading/*.py` — check if any handler imports repos directly

## Verification Steps

```bash
# 1. Import linter — architectural contracts
uv run lint-imports

# 2. Pyright type check — catch broken imports
uv run pyright packages/pocketquant-api/src/pocketquant/api/di/

# 3. Grep for stale imports — should return nothing
grep -r "pocketquant.core.persistence.repositories.order_repository" packages/
grep -r "pocketquant.core.persistence.repositories.position_repository" packages/
```

## Todo
- [x] Run lint-imports — verify all contracts pass
- [x] Run pyright on DI directory
- [x] Grep for stale order/position repo imports
- [x] Fix any remaining issues
