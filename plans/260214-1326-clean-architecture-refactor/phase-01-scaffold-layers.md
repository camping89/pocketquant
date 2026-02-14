# Phase 1: Scaffold Layers & Shared Contracts

## Overview
- **Priority:** P1 (blocking all other phases)
- **Status:** Completed
- **Effort:** 1h
- **Description:** Create `src/application/` layer structure and extend `src/infrastructure/persistence/` with repositories directory. Set up `__init__.py` files and shared base classes.

## Key Insights
- `src/infrastructure/persistence/` only has DB clients (mongodb.py, redis.py) — no repositories
- `src/domain/` is well-structured with aggregates, needs `backtest/` aggregate added
- Application layer doesn't exist yet — create per-feature subdirectories

## Requirements
- Create `src/application/` with per-feature subdirectories
- Create `src/infrastructure/persistence/repositories/` for repo implementations
- Create `src/infrastructure/persistence/schemas/` for document mappers
- Create `src/domain/backtest/` aggregate (new)
- All `__init__.py` files for proper Python package structure

## Related Code Files

### Create
- `src/application/__init__.py`
- `src/application/backtesting/__init__.py`
- `src/application/market_data/__init__.py`
- `src/application/strategy/__init__.py`
- `src/application/trading/__init__.py`
- `src/infrastructure/persistence/repositories/__init__.py`
- `src/infrastructure/persistence/schemas/__init__.py`
- `src/domain/backtest/__init__.py`
- `src/domain/backtest/services/__init__.py`

### Verify exist
- `src/domain/strategy/` (exists, will receive new files in phase 3)
- `src/domain/ohlcv/services/` (exists, has bar_builder.py already)

## Implementation Steps

1. Create `src/application/` directory with `__init__.py`
2. Create subdirectories: `backtesting/`, `market_data/`, `strategy/`, `trading/` each with `__init__.py`
3. Create `src/infrastructure/persistence/repositories/__init__.py`
4. Create `src/infrastructure/persistence/schemas/__init__.py`
5. Create `src/domain/backtest/__init__.py` and `src/domain/backtest/services/__init__.py`
6. Verify existing domain directories have proper `__init__.py` files
7. Run `python -c "import src.application; import src.infrastructure.persistence.repositories"` to verify package resolution

## Todo List
- [ ] Create application layer directories
- [ ] Create infrastructure persistence subdirectories
- [ ] Create domain backtest aggregate directory
- [ ] Verify all __init__.py files
- [ ] Verify import resolution

## Success Criteria
- All new directories importable as Python packages
- No existing imports broken
- `python -m py_compile src/application/__init__.py` succeeds
