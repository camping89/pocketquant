# Phase 6 Implementation Report: Cross-Cutting Cleanup

## Executed Phase
- Phase: phase-06-cross-cutting-cleanup
- Plan: D:/w/_me/pocketquant/plans/260213-0107-vertical-slice-restructure/
- Status: completed

## Summary

Final cleanup phase for vertical slice restructure. Updated docs, fixed remaining imports, verified compilation. All 5 features now use canonical operation-centric structure.

## Files Modified

### Updated (3 files)
1. `src/features/strategy/base/strategy_engine.py` (1 line)
   - Fixed TYPE_CHECKING import: `risk.handlers.risk_check_handler` → `risk.check_risk.handler`

2. `src/infrastructure/tradingview/websocket.py` (7 lines)
   - Fixed line length violation (E501) by splitting heartbeat message construction

3. `docs/code-standards.md` (35 lines)
   - Updated "Vertical Slice Architecture" section with canonical operation-centric pattern
   - Replaced old `api/`, `handlers/` structure with `base/`, `operation_name/`, `router.py`
   - Updated file size targets for new structure

## Tasks Completed

- [x] Fixed remaining `handlers/` import in strategy_engine.py
- [x] Fixed line length violation in tradingview/websocket.py
- [x] Updated docs/code-standards.md with new canonical structure
- [x] Verified no old path references remain (`.api.`, `.handlers.`)
- [x] Verified ruff check (1 warning only - Generic style, not critical)
- [x] Verified pyright passes (0 errors, 0 warnings)
- [x] Verified main.py imports successfully

## Verification Results

### Static Analysis
```bash
# Ruff check
1 warning (UP046: Generic class style - Python 3.12+ recommendation, not critical)
0 errors

# Pyright
0 errors, 0 warnings, 0 informations

# Import test
SUCCESS: main.py imports OK
```

### Path Verification
```bash
# Old .api. references: 0
# Old .handlers. references: 0
```

### Infrastructure Updates
- `infrastructure/tradingview/provider.py` - Already updated to `base.models.ohlcv`
- `infrastructure/tradingview/base.py` - Already updated to `base.models.ohlcv`

### Main.py Status
All imports already correct from previous phases:
- Routers: Using new paths (`backtesting.router`, `strategy.router`, etc.)
- Handlers: Using feature `__init__.py` re-exports (backward compatible)
- Repositories: Using new `base.repositories` paths
- Trading mediator: Already registered

## Documentation Updates

### code-standards.md
Updated canonical structure template:
```
features/feature_name/
├── base/                # Shared infrastructure
│   ├── models/          # Pydantic DTOs
│   ├── repositories/    # Data access
│   └── managers/        # Stateful services
├── operation_name/      # Each operation is a folder
│   ├── dto.py
│   ├── command.py
│   └── handler.py
└── router.py            # FastAPI routes
```

Removed references to deprecated structure:
- ~~api/~~ → router.py
- ~~handlers/~~ → operation folders
- ~~models/~~ → base/models/

## New Canonical Structure

All features now follow operation-centric pattern:

### Strategy
```
strategy/
├── base/
│   ├── strategy_config.py
│   ├── strategy_interface.py
│   └── strategy_engine.py
├── get_all/
├── get_one/
├── load/
├── start/
├── stop/
└── router.py
```

### Backtesting
```
backtesting/
├── base/
│   ├── models/
│   ├── repository/
│   ├── engine/
│   ├── metrics/
│   └── optimizer/
├── run/
├── get_result/
├── list_results/
├── optimize/
├── get_optimization/
└── router.py
```

### Market Data
```
market_data/
├── base/
│   ├── models/
│   └── jobs/
├── ohlcv/
│   └── get_ohlcv/
├── quotes/
│   ├── get_all/
│   ├── get_latest/
│   ├── start_feed/
│   ├── stop_feed/
│   ├── subscribe/
│   ├── unsubscribe/
│   └── router.py
├── status/
│   ├── get_quote_service_status/
│   ├── get_sync_status/
│   └── get_symbol_sync_status/
├── sync/
│   ├── sync_bulk/
│   └── sync_one/
├── list_symbols/
└── router.py (top-level)
```

### Trading
```
trading/
├── base/
│   ├── managers/
│   ├── models/
│   └── repositories/
├── list_orders/
├── get_order/
├── list_positions/
├── get_position/
└── router.py
```

### Risk
```
risk/
└── check_risk/
    └── handler.py
```

## Issues Encountered

None. All previous phases handled restructuring cleanly.

## Next Steps

### Immediate
1. Run pytest suite (requires MongoDB/Redis running)
2. Test API endpoints manually via Swagger UI
3. Verify WebSocket connections work

### Follow-up
1. Consider adding operation-level README.md files for complex operations
2. Monitor file sizes as features grow (target <200 LOC per handler)
3. Extract shared utilities from operations to base/ if duplication appears

### Future Improvements
1. Add OpenAPI tags per operation for better Swagger organization
2. Consider operation-level validation schemas in dto.py
3. Add operation-level tests in tests/features/{feature}/{operation}/

## Validation Summary

- ✓ Type checking passes (pyright)
- ✓ Linting passes (ruff, 1 non-critical warning)
- ✓ Main.py imports successfully
- ✓ No old path references remain
- ✓ Documentation updated
- ⚠ Tests not run (requires infra)

## Conclusion

Phase 6 completed successfully. All cross-cutting concerns addressed:
- Documentation reflects new canonical structure
- All imports use new paths (direct or via backward-compatible re-exports)
- Static analysis passes
- No orphaned files or references

Vertical slice restructure is complete across all 5 features. Each feature now has clear operation boundaries, shared infrastructure in base/, and consistent structure.
