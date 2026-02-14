# Phase 3: Cleanup Old Path and Final Verification

## Priority: P1 | Status: pending

## Overview
Delete the old `src/infrastructure/persistence/` directory, verify no stale references remain, run full test suite, and lint check.

## Prerequisites
- Phase 1 complete: all imports point to `src.persistence`
- Phase 2 complete: all raw DB calls replaced with repository methods

## Files to DELETE
```
src/infrastructure/persistence/__init__.py
src/infrastructure/persistence/mongodb.py
src/infrastructure/persistence/redis.py
src/infrastructure/persistence/repositories/__init__.py
src/infrastructure/persistence/repositories/order_repository.py
src/infrastructure/persistence/repositories/position_repository.py
src/infrastructure/persistence/repositories/backtest_repository.py
src/infrastructure/persistence/schemas/__init__.py
src/infrastructure/persistence/schemas/ohlcv_schema.py
src/infrastructure/persistence/schemas/order_schema.py
src/infrastructure/persistence/schemas/position_schema.py
src/infrastructure/persistence/schemas/quote_schema.py
src/infrastructure/persistence/schemas/symbol_schema.py
```

Total: 13 files, 2 subdirectories, 1 parent directory removed.

## Files to VERIFY (no modification expected)
- `src/infrastructure/__init__.py` -- should already import from `src.persistence` (Phase 1)
- `src/infrastructure/` directory still contains: `brokers/`, `tradingview/`, `http_client/`, `scheduling/`, `webhooks/`

## Implementation Steps

1. **Grep for any remaining `infrastructure.persistence` references**
   ```bash
   rg "infrastructure\.persistence" src/
   rg "infrastructure/persistence" .
   ```
   Must return zero matches. If any found, fix them first.

2. **Delete `src/infrastructure/persistence/` directory tree**
   ```bash
   rm -rf src/infrastructure/persistence/
   ```

3. **Verify `src/infrastructure/__init__.py`** still imports correctly:
   ```python
   from src.persistence import Cache, Database
   ```

4. **Run linter**
   ```bash
   ruff check src/
   ```
   No import errors allowed.

5. **Run full test suite**
   ```bash
   pytest -v --tb=short
   ```
   60/60 pass.

6. **Spot-check key import chains work end-to-end**
   ```bash
   python -c "from src.persistence import Database, Cache; print('OK')"
   python -c "from src.common.database import Database; print('OK')"
   python -c "from src.common.cache import Cache; print('OK')"
   python -c "from src.persistence.repositories.ohlcv_repository import OHLCVRepository; print('OK')"
   ```

## Todo
- [ ] Grep for stale `infrastructure.persistence` references -- zero matches
- [ ] Delete `src/infrastructure/persistence/` directory
- [ ] Run `ruff check src/` -- clean
- [ ] Run `pytest` -- 60/60 pass
- [ ] Spot-check import chains

## Success Criteria
- `src/infrastructure/persistence/` does not exist
- `src/infrastructure/` still contains brokers, tradingview, etc.
- Zero references to `infrastructure.persistence` anywhere in codebase
- 60/60 tests pass
- Linter clean

## Risk
- If any test or file was missed in Phase 1/2, deletion breaks it. Mitigation: grep check before delete, git makes it reversible.
