# Phase 5: Cleanup and Verify

## Context
- All migrations complete
- Repository folder should be empty of dependencies
- Final cleanup and verification

## Overview
- **Priority:** P2
- **Status:** Pending
- **Effort:** 20 min
- **Depends on:** Phase 4 completed

## Key Insights
- Delete entire `repositories/` folder
- Run full test suite
- Verify LOC limits

## Requirements

### Functional
- Delete `repositories/` folder completely
- All tests pass
- Application starts successfully

### Non-functional
- No orphan imports
- All files < 200 LOC

## Files

### Delete
- `src/features/market_data/repositories/ohlcv_repository.py`
- `src/features/market_data/repositories/symbol_repository.py`
- `src/features/market_data/repositories/__init__.py`
- `src/features/market_data/repositories/` (folder)

## Implementation Steps

### Step 1: Verify no remaining imports
```bash
grep -r "from src.features.market_data.repositories" src/
# Should return empty
```

### Step 2: Delete repository folder
```bash
rm -rf src/features/market_data/repositories/
```

### Step 3: Run linting
```bash
ruff check src/features/market_data/
ruff format src/features/market_data/
```

### Step 4: Run type checking
```bash
mypy src/features/market_data/
```

### Step 5: Run full test suite
```bash
pytest tests/ -v
```

### Step 6: Verify LOC limits
```bash
wc -l src/features/market_data/services/*.py
wc -l src/features/market_data/managers/*.py
wc -l src/features/market_data/api/*.py
# All should be < 200
```

### Step 7: Start application
```bash
python -m src.main
# Verify health check
curl http://localhost:8000/health
```

## Verification Checklist

### File Structure
- [ ] `repositories/` folder deleted
- [ ] `managers/bar_manager.py` exists
- [ ] `providers/base.py` exists

### Code Quality
- [ ] ruff check passes
- [ ] mypy passes
- [ ] No bare except without logging

### Tests
- [ ] All unit tests pass
- [ ] All integration tests pass

### Runtime
- [ ] Application starts
- [ ] `/health` returns 200
- [ ] `/api/v1/market-data/symbols` works
- [ ] `/api/v1/quotes/status` works

## Todo

- [ ] Run grep to verify no repository imports
- [ ] Delete repositories folder
- [ ] Run ruff check/format
- [ ] Run mypy
- [ ] Run pytest
- [ ] Verify LOC < 200 for all files
- [ ] Manual smoke test endpoints

## Success Criteria
- [ ] No `repositories/` folder
- [ ] All tests pass
- [ ] Application runs
- [ ] All files < 200 LOC

## Risks
- Missed import causing runtime error
- Mitigation: Grep check + full test suite
