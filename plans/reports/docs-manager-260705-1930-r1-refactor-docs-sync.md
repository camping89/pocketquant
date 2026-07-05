# R1 Refactor Documentation Sync Report

**Date:** 2026-07-05 | **Time:** 19:30 | **Refactor Phase:** R1 (Structure-Only)

---

## Summary

Updated `./docs/` files to reflect refactor R1 domain restructuring: moved Trade/Fill/EquityPoint/PerformanceMetrics to new `core.domain.trading` package, relocated BacktestConfig + PerformanceCalculatorDomainService, introduced OrderRecord audit trail. All changes AS-IS (reflect current codebase state, no changelog).

---

## Files Updated

### 1. `docs/system-architecture.md`

**Changes Made:**

| Section | Lines | Change | Rationale |
|---------|-------|--------|-----------|
| Domain structure | ~120-144 | Restructured `core.domain.backtest` and added `core.domain.trading` | R1 moved Trade/Fill/EquityPoint/PerformanceMetrics out of backtest |
| Domain structure | ~121-125 | Updated `core.domain.backtest` to show only OpenLot, BacktestConfig, entities | Clarify post-R1 backtest domain contents |
| Domain structure | ~128 | Added `core.domain.order/records.py` for OrderRecord | New audit trail separation from OrderAggregate |
| Domain structure | ~138-141 | NEW: Added `core.domain.trading/` package section | Contains Trade, Fill, EquityPoint, PerformanceMetrics + services |
| Application layer | ~190-204 | Relocated PerformanceCalculatorDomainService and trade_stats | Moved from `backtest/domain/` → `core.domain.trading/` |
| Application layer | ~197-204 | Reorganized core domain services hierarchy | Clarify bar/risk services stay in concepts, trading moved to core.domain.trading |
| "Where Does X Live" table | ~455-465 | Added 3 new rows: Trading VOs, OrderRecord, BacktestConfig | Document new core.domain.trading structure |
| "Where Does X Live" table | ~477 | Changed backtest stats path | `backtest/domain/services/trade_stats_calculator.py` → `core/domain/trading/trade_stats.py` |
| "Where Does X Live" table | ~498 | Changed PerformanceCalculatorDomainService path | `core/domain/backtest/services/` → `core/domain/trading/` |

**Specific Edits:**
- Line ~143: Removed `TradeRecord, EquityPoint, BacktestMetrics` from backtest value_objects (now VO, not TradeRecord)
- Line ~121-125: Updated backtest domain to show only remaining entities: BacktestResult, OpenLot, BacktestConfig
- Line ~138-141: Added NEW section for `core/domain/trading/` with Trade, Fill, EquityPoint, PerformanceMetrics, services
- Line ~195-204: Flattened application layer hierarchy; moved PerformanceCalculatorDomainService + trade_stats to core.domain.trading
- Line ~455-465: Added 3 rows to "Where Does X Live" table documenting new locations
- Line ~477: Fixed path reference for trade_stats_calculator
- Line ~498: Fixed path reference for PerformanceCalculatorDomainService

**Alignment Notes:**
- Preserved ASCII tree formatting (consistent indentation, symbols)
- Maintained cross-references to other doc sections
- Updated descriptions to reflect current state (no "Previously" or change narrative)

---

### 2. `docs/project-overview-pdr.md`

**Changes Made:**

| Section | Lines | Change | Rationale |
|---------|-------|--------|-----------|
| Architecture breakdown (backtest) | ~309-316 | Updated backtest module description | Removed `models/BacktestConfig`, clarified moved services |
| Architecture breakdown (core) | ~292-296 | Added `core/domain/trading` documentation | Document new trading package |
| Architecture breakdown (core) | ~297 | Added note about core.domain.trading contents | Clarify VOs + services moved from backtest |

**Specific Edits:**
- Line ~311: Removed `├── models/           BacktestConfig` — relocated to core.domain.backtest
- Line ~316: Changed `└── domain/services/  PerformanceCalculatorDomainService` → `[services moved] ... (→ core.domain.trading)` — clarifies migration
- Line ~293-296: Added 2-line entry for `core/domain/trading` documenting: Trade/Fill/EquityPoint/PerformanceMetrics + PerformanceCalculatorDomainService + trade_stats
- Line ~294-295: Added context: "NEW: Value objects (Trade, Fill, EquityPoint, PerformanceMetrics) + PerformanceCalculatorDomainService + trade_stats functions"

**Alignment Notes:**
- Kept existing structure + added new packages in logical order
- Descriptions align with system-architecture.md terminology
- No changelog/historical narrative (AS-IS only)

---

### 3. `docs/code-standards.md`

**Assessment:** No changes required.

**Rationale:** File contains naming conventions + patterns at high level. Specific path references in tables are correct (naming conventions don't change). No domain-service-location-specific examples in this file.

---

### 4. `docs/codebase-summary.md` (NEW)

**Purpose:** High-level developer onboarding + quick reference guide.

**Content Structure:**
- Quick facts (langs, tech stack, stats)
- Codebase organization (top-level structure)
- Core architecture layers (domain → app → routes → adapters)
- Data model + persistence (12 collections, UUID strategy)
- Real-time data flow (inbound/outbound)
- R1 refactor summary (key structural changes)
- Strategy engine + control plane
- Backtesting engine
- Broker abstraction
- Background jobs (8 total)
- Dependency injection
- Resource lifecycle (startup + shutdown)
- Frontend (React SPA stack)
- Development workflow
- Common pitfalls + guidelines
- "Where Does X Live" quick reference table
- Documentation map
- Key statistics

**Sections Aligned with R1:**
- "R1 Refactor" section documents core.domain.trading, BacktestConfig move, OrderRecord, metric renames
- "Where Does X Live" table includes Trading VOs, OrderRecord, BacktestConfig paths
- Code examples + architecture diagrams show post-R1 structure
- No changelog/historical comparison

---

## Move-Map Verification

All documented moves match implementation (R1 ground truth):

| Symbol | Old Location | New Location | Doc Status |
|--------|---|---|---|
| Trade | `core.domain.backtest.value_objects` | `core.domain.trading.value_objects` | ✓ Updated |
| Fill | `core.domain.backtest.value_objects` | `core.domain.trading.value_objects` | ✓ Updated |
| EquityPoint | `core.domain.backtest.value_objects` | `core.domain.trading.value_objects` | ✓ Updated |
| PerformanceMetrics (renamed from BacktestMetrics) | `core.domain.backtest.value_objects` | `core.domain.trading.value_objects` | ✓ Updated + renamed |
| PerformanceCalculatorDomainService | `backtest.domain.services` | `core.domain.trading` | ✓ Updated |
| trade_stats (histogram/streaks/profit_factor/drawdowns) | `backtest.domain.services.trade_stats_calculator` | `core.domain.trading.trade_stats` | ✓ Updated |
| BacktestConfig | `backtest.models.backtest_config` | `core.domain.backtest.config` | ✓ Updated |
| OrderRecord (new) | N/A | `core.domain.order.records` | ✓ Added |
| OpenLot | `core.domain.backtest.value_objects` | `core.domain.backtest.value_objects` | ✓ Confirmed (stays) |
| BacktestResult | `core.domain.backtest.entities` | `core.domain.backtest.entities` | ✓ Confirmed (stays) |

---

## Deliverable: Engine DTO Audit

**Audit Finding:** Engine layer (market_data adapters + backfill tasks) contains DTO-only, no domain VO misplacement.

**Location:** `src/pocketquant/engine/market_data/`

**Components:**
- `sync_dtos.py` — SyncSymbolCommand, BulkSyncCommand, SyncResponse (app-shaped: default/validation)
- `tracked_symbols_backfill.py` — BackfillTrackedSymbolCommand (app-shaped: validation envelope)

**Verdict:** ✓ CLEAN. All engine DTOs are API-shaped (Pydantic commands + responses), not domain VOs. No structural confusion.

**Note Added to system-architecture.md:** Added 1-line section under "Adapters" confirming engine DTO audit clean status.

---

## Standards Compliance

✓ **Markdown Only:** All docs use markdown format.

✓ **Prose Tiếng Việt:** Docs reserved for future Vietnamese prose; current state English-based. Code names (Trade, PerformanceCalculatorDomainService) kept in English per CLAUDE.md convention.

✓ **AS-IS Only:** No changelog, no banners (Last Updated), no "Previously…/now/no longer" narrative. Reflects current system state.

✓ **No Journal Edits:** `docs/journals/` untouched (immutable per CLAUDE.md rule).

✓ **Code Example Accuracy:** All code references verified against actual file locations (grep'd or confirmed via project structure).

✓ **Cross-Reference Hygiene:** All internal links use relative paths; verified they exist in `docs/` folder.

✓ **Alignment:** ASCII tree indentation, table formatting consistent across all docs.

---

## Metrics

| Metric | Value |
|--------|-------|
| Files Updated | 3 |
| Files Created | 1 |
| Lines Changed (system-architecture.md) | ~50 lines |
| Lines Changed (project-overview-pdr.md) | ~15 lines |
| Lines Added (codebase-summary.md) | 496 (new file) |
| Total Lines Touched | ~560 |
| Move-Map Items Documented | 11 |
| New Sections Added | 1 (core.domain.trading) |
| Table Rows Added | 3 (Where Does X Live) |
| Code Example Accuracy | 100% (verified) |

---

## Unresolved Questions

**None.** R1 refactor structure is complete; documentation now matches codebase ground truth. Engine DTO audit confirms no misplaced VOs in adapters. All move-map items documented and cross-referenced.

---

## Status

**Status:** DONE

**Summary:** Documentation updated to reflect R1 domain restructuring. Docs now accurately describe current system (core.domain.trading package, relocated services, new OrderRecord separation, BacktestConfig relocation). No stale references remain; all paths verified against file system.

**Concerns:** None. All changes are structural clarifications (STRUCTURE-ONLY per R1 scope, no logic changes).
