# Phase 6: Cleanup, Verify & Update Docs

## Context
- [Brainstorm](../reports/brainstorm-260214-1326-clean-architecture-refactor.md)
- All phases 1-5 must complete first

## Overview
- **Priority:** P1
- **Status:** Completed
- **Effort:** 1h
- **Description:** Final sweep — remove all empty `base/` dirs, verify dependency direction, run full test suite, update architecture docs.

## Implementation Steps

1. **Verify no `base/` directories remain in features**
   ```bash
   find src/features -name "base" -type d
   # Must return empty
   ```

2. **Verify no old import references**
   ```bash
   grep -r "features\..*\.base" src/
   grep -r "features\.market_data\.repositories" src/
   grep -r "features\.trading\.base" src/
   grep -r "features\.strategy\.base" src/
   grep -r "features\.backtesting\.base" src/
   # All must return empty
   ```

3. **Verify domain purity (CRITICAL)**
   ```bash
   # Domain must NOT import from common (I/O), infrastructure, application, or features
   grep -rn "from src\.common\." src/domain/
   grep -rn "from src\.infrastructure\." src/domain/
   grep -rn "from src\.application\." src/domain/
   grep -rn "from src\.features\." src/domain/
   # Allowed exceptions: src.domain.shared (internal domain cross-ref)
   ```

4. **Verify dependency direction**
   ```bash
   # Infrastructure must NOT import from features or application
   grep -rn "from src\.features\." src/infrastructure/
   grep -rn "from src\.application\." src/infrastructure/
   # Must return empty

   # Application must NOT import from features (except risk handler — document exception)
   grep -rn "from src\.features\." src/application/
   # Only allowed: strategy_engine → risk handler (if still needed)
   ```

5. **Run full test suite**
   - Run all tests
   - Fix any failures
   - Ensure no test imports from deleted paths

6. **Clean up empty __init__.py re-exports**
   - Check `features/trading/__init__.py` — remove base/ re-exports
   - Check `features/strategy/__init__.py` — remove base/ re-exports
   - Check `features/backtesting/__init__.py` — remove base/ re-exports
   - Check `features/market_data/__init__.py` — remove base/ re-exports

7. **Update documentation**
   - `docs/system-architecture.md` — update layer diagram, add application layer
   - `docs/code-standards.md` — update directory structure, remove `base/` pattern, document new layer rules
   - `docs/codebase-summary.md` — update file counts, directory structure

## Todo List
- [ ] Verify no base/ dirs in features
- [ ] Verify no old import references
- [ ] Verify domain purity
- [ ] Verify dependency direction
- [ ] Run full test suite
- [ ] Clean up __init__.py re-exports
- [ ] Update system-architecture.md
- [ ] Update code-standards.md
- [ ] Update codebase-summary.md

## Success Criteria
- Zero `base/` directories in `features/`
- Zero old import references in entire codebase
- Domain has zero I/O imports
- Dependency direction strictly enforced
- All tests pass
- Docs reflect new architecture
