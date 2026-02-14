# Phase 3: Migrate Strategy

## Context
- [Brainstorm](../reports/brainstorm-260214-1326-clean-architecture-refactor.md)
- [Phase 2](./phase-02-migrate-trading.md) must complete first (validates pattern)

## Overview
- **Priority:** P1
- **Status:** Completed
- **Effort:** 3h
- **Description:** Migrate `features/strategy/base/` — mix of pure domain (interface, config, ma_crossover) and I/O orchestration (engine, yaml_loader).

## Key Insights
- `strategy_config.py` — PURE dataclass → `domain/strategy/value_objects.py`
- `strategy_interface.py` — PURE abstract class → `domain/strategy/interfaces.py`
- `ma_crossover.py` — PURE strategy implementation → `domain/strategy/strategies/ma_crossover.py`
- `strategy_engine.py` — I/O heavy (EventBus, brokers, managers) → `application/strategy/`
- `yaml_loader.py` — File I/O (yaml, pathlib) → `infrastructure/strategy/yaml_strategy_loader.py`
- Domain already has `src/domain/strategy/` with `value_objects.py` (Signal, Direction) and `strategy_event.py`

## Architecture

```
BEFORE:                              AFTER:
features/strategy/                   features/strategy/
├── base/                            ├── router.py
│   ├── strategy_config.py           ├── get_all/   {query, handler, route}
│   ├── strategy_interface.py        ├── get_one/   {query, handler, route}
│   ├── strategy_engine.py           ├── load/      {command, handler, route}
│   ├── ma_crossover.py              ├── start/     {command, handler, route}
│   └── yaml_loader.py               └── stop/      {command, handler, route}
├── router.py
├── get_all/                         domain/strategy/
├── get_one/                         ├── value_objects.py  (+ StrategyConfig)
├── load/                            ├── interfaces.py     (IStrategy)
├── start/                           ├── strategies/
└── stop/                            │   └── ma_crossover.py
                                     └── ...existing...

                                     application/strategy/
                                     ├── strategy_engine.py
                                     └── yaml_strategy_loader.py
```

## Related Code Files

### Move to domain
- `src/features/strategy/base/strategy_config.py` → merge `StrategyConfig` into `src/domain/strategy/value_objects.py`
- `src/features/strategy/base/strategy_interface.py` → `src/domain/strategy/interfaces.py`
- `src/features/strategy/base/ma_crossover.py` → `src/domain/strategy/strategies/ma_crossover.py`

### Move to application
- `src/features/strategy/base/strategy_engine.py` → `src/application/strategy/strategy_engine.py`

### Move to infrastructure
- `src/features/strategy/base/yaml_loader.py` → `src/application/strategy/yaml_strategy_loader.py` (kept in application since it's a loader used by handlers, not a persistence adapter)

### Modify (update imports)
- `src/features/strategy/load/handler.py`
- `src/features/strategy/start/handler.py`
- `src/features/strategy/stop/handler.py`
- `src/features/strategy/get_all/handler.py`
- `src/features/strategy/get_one/handler.py`
- `src/features/strategy/router.py`
- `src/application/trading/order_manager.py` (if it references strategy base)
- `src/application/strategy/strategy_engine.py` (internal imports after move)
- `src/features/backtesting/base/engine/backtest_runner.py` (if it imports strategy)

### Create
- `src/domain/strategy/interfaces.py`
- `src/domain/strategy/strategies/__init__.py`
- `src/domain/strategy/strategies/ma_crossover.py`

### Delete
- `src/features/strategy/base/` (entire directory)

## Implementation Steps

1. **Move pure domain: StrategyConfig**
   - Read existing `src/domain/strategy/value_objects.py` — contains Signal, Direction, SignalType
   - Append `StrategyConfig` dataclass from `strategy_config.py` into it
   - It imports `RiskConfig, RiskModel` from `src.domain.risk` — valid domain→domain dep
   - Update `__init__.py` exports

2. **Move pure domain: IStrategy interface**
   - Create `src/domain/strategy/interfaces.py`
   - Move `IStrategy` abstract class
   - Update imports: `strategy_config.StrategyConfig` → `src.domain.strategy.value_objects.StrategyConfig`
   - Keep domain imports: `OrderAggregate`, `Signal` (both in domain already)

3. **Move pure domain: ma_crossover**
   - Create `src/domain/strategy/strategies/` directory with `__init__.py`
   - Move `MACrossover` class to `src/domain/strategy/strategies/ma_crossover.py`
   - Update imports: `StrategyConfig` → `src.domain.strategy.value_objects`, `IStrategy` → `src.domain.strategy.interfaces`
   - Verify: only imports from domain + stdlib (deque, datetime)

4. **Move strategy_engine to application**
   - Copy to `src/application/strategy/strategy_engine.py`
   - Update internal imports:
     - `src.features.strategy.base.strategy_config` → `src.domain.strategy.value_objects`
     - `src.features.strategy.base.strategy_interface` → `src.domain.strategy.interfaces`
     - `src.features.trading.base.managers.order_manager` → `src.application.trading.order_manager` (already moved in phase 2)
     - `src.features.trading.base.managers.position_tracker` → `src.application.trading.position_tracker` (already moved in phase 2)
     - `src.features.risk.check_risk.handler` → keep as-is (features→features is allowed for risk handler)

5. **Move yaml_loader to application**
   - Copy to `src/application/strategy/yaml_strategy_loader.py`
   - Update imports: `strategy_config.StrategyConfig` → `src.domain.strategy.value_objects.StrategyConfig`
   - Has I/O deps: `pathlib.Path`, `yaml` — belongs in application layer

6. **Update all handler imports**
   - All 5 handlers: replace `from src.features.strategy.base` references
   - `load/handler.py`: likely uses yaml_loader → `from src.application.strategy.yaml_strategy_loader`
   - `start/handler.py`: likely uses strategy_engine → `from src.application.strategy.strategy_engine`
   - `stop/handler.py`: likely uses strategy_engine → `from src.application.strategy.strategy_engine`
   - `get_all/handler.py`, `get_one/handler.py`: likely query strategy_engine state

7. **Search & fix ALL remaining references**
   - `grep -r "features.strategy.base" src/` — must return zero results
   - Check backtesting handlers (may import strategy models)

8. **Delete `features/strategy/base/`**

9. **Verify**
   - Import checks for all moved modules
   - Run strategy tests
   - Verify domain purity: `grep -r "import.*common\|import.*infrastructure" src/domain/strategy/` → should return nothing

## Todo List
- [ ] Merge StrategyConfig into domain/strategy/value_objects.py
- [ ] Create domain/strategy/interfaces.py (IStrategy)
- [ ] Create domain/strategy/strategies/ma_crossover.py
- [ ] Move strategy_engine to application/strategy/
- [ ] Move yaml_loader to application/strategy/
- [ ] Update all 5 handler imports
- [ ] Fix cross-feature references
- [ ] Delete features/strategy/base/
- [ ] Verify domain purity (no I/O imports)
- [ ] Run tests

## Success Criteria
- `features/strategy/` contains ONLY: router.py, 5 operation dirs
- Pure domain: `domain/strategy/` has interfaces.py, strategies/, updated value_objects.py
- Application: `application/strategy/` has strategy_engine.py, yaml_strategy_loader.py
- Zero `features.strategy.base` references in codebase
- Domain layer has no I/O imports
- All tests pass

## Risk Assessment
- **StrategyConfig merge conflict** — value_objects.py already has content. Carefully append, don't overwrite.
- **Circular: strategy_engine ↔ risk handler** — Engine imports risk handler from features. Acceptable (application→features for handler dispatch).
- **Strategy registration** — If strategies auto-register, loader path changes may break discovery.
