# Plan Report: Persistence Layer Consolidation

**Plan path:** `D:\w\_me\pocketquant\plans\260214-1532-persistence-layer\`
**Effort:** ~3h across 3 phases
**Risk:** Low -- all changes are import rewiring + method extraction

## Summary

Consolidate all persistence code from `src/infrastructure/persistence/` into new top-level `src/persistence/` package. Create 4 missing repositories to eliminate 30 raw `Database.get_collection()` calls scattered across 13 handler/application files. Add minimal BaseRepository mixin for DRY collection access.

## Scope Analysis

**30 raw `Database.get_collection()` calls** found in:
- 3 existing repositories (order, position, backtest) -- 18 calls
- 5 feature handlers (sync_one, get_ohlcv, list_symbols, get_sync_status, get_symbol_sync_status, optimize, get_optimization) -- 9 calls
- 2 application services (bar_manager, sync_jobs, backtest_runner) -- 3 calls

**35+ import statements** referencing `src.infrastructure.persistence` across codebase.

**0 test files** import directly from infrastructure.persistence -- low test breakage risk.

## Phases

| # | Phase | Files touched | Key risk |
|---|-------|--------------|----------|
| 1 | Scaffold `src/persistence/`, move files, update all imports | ~25 modify, 14 create | Import chain breakage -- mitigated by updating shims first |
| 2 | Create 4 new repos + base mixin, rewire handlers | 4 create, ~12 modify | backtest_runner needs async iterator streaming method |
| 3 | Delete old `src/infrastructure/persistence/` | 13 delete | Missed reference -- mitigated by grep before delete |

## Key Decisions
- **No ABC interface** -- BaseRepository is a plain mixin with `_collection()` helper, not abstract
- **Static method pattern preserved** -- matches existing repo conventions
- **Constants stay in `src/common/constants.py`** -- non-persistence constants (HEADER_*, LIMIT_*, INTERVAL_*) live there too; splitting would create import confusion
- **Re-export shims preserved** -- `src/common/database/` and `src/common/cache/` continue to work

## Artifacts
- `plans/260214-1532-persistence-layer/plan.md` -- overview
- `plans/260214-1532-persistence-layer/phase-01-scaffold-and-move.md` -- file moves + import rewiring
- `plans/260214-1532-persistence-layer/phase-02-new-repositories.md` -- new repos + handler refactoring (includes exact line-by-line extraction map)
- `plans/260214-1532-persistence-layer/phase-03-cleanup-and-verify.md` -- delete old path + verification
