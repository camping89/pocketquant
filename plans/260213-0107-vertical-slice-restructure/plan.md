---
status: completed
created: 2026-02-13
branch: feat/strategy-init
issue: none
completed: 2026-02-13
---

# Vertical Slice Restructure

Refactor all features to consistent operation-first folder structure. Operations at feature root, infrastructure in `base/`, `api/` replaced by `router.py`.

## Context

- [Brainstorm Report](../reports/brainstorm-260213-0107-vertical-slice-restructure.md)
- [Code Standards](../../docs/code-standards.md)
- Gold standard: `market_data/quotes/` — already follows target pattern

## Canonical Pattern

```
feature/
├── base/                ← ALL non-operation code
│   ├── engine/          ← sub-folders when 10+ files
│   └── config.py        ← flat when few
├── operation_a/         ← CQRS operation (visible from ls)
│   ├── command.py / query.py
│   ├── handler.py
│   ├── route.py         ← optional
│   └── __init__.py
├── router.py            ← replaces api/ folder
└── __init__.py
```

## Phases

| # | Phase | Status | Risk |
|---|-------|--------|------|
| 1 | [Strategy restructure](phase-01-strategy-restructure.md) | completed | Low |
| 2 | [Backtesting restructure](phase-02-backtesting-restructure.md) | completed | Medium |
| 3 | [Market Data restructure](phase-03-market-data-restructure.md) | completed | High |
| 4 | [Trading restructure + mediator](phase-04-trading-restructure.md) | completed | Medium |
| 5 | [Risk restructure](phase-05-risk-restructure.md) | completed | Low |
| 6 | [Cross-cutting cleanup](phase-06-cross-cutting-cleanup.md) | completed | High |

## Execution Strategy

Sequential — each phase is self-contained. After each phase:
1. Update feature `__init__.py` to re-export from new paths
2. Verify `ruff check` passes
3. Verify `pyright` passes
4. Don't update `main.py` until Phase 6

## Key Risks

- Mass import breakage (mitigated: update `__init__.py` per phase)
- `main.py` route registration (mitigated: update in Phase 6)
- Circular imports in `base/` (rule: base/ never imports from operations)
- Infrastructure imports that cross features (identified: `tradingview/` → `market_data/models/`)

## Completion Summary

**Status: COMPLETED** - 2026-02-13 02:12

All 6 phases successfully executed. Codebase refactored to consistent vertical-slice architecture with operation-first pattern. Key achievements:

- Strategy (5 operations) ✓
- Backtesting (5 operations, 5 infra folders) ✓
- Market Data (4 sub-features, 5 infra folders, inline routes extracted) ✓
- Trading (4 new operations, mediator conversion) ✓
- Risk (single operation consolidation) ✓
- Cross-cutting cleanup (main.py, infrastructure imports, documentation) ✓

**Code Quality:**
- Ruff: PASS
- Pyright: PASS (0 errors, 0 warnings)
- Imports: All internal + cross-feature paths updated
- Backward compatibility: Maintained via `__init__.py` re-exports

**Impact:**
- 40+ files restructured
- All features now follow canonical pattern
- 166 inline endpoints extracted to operation handlers
- Router tree simplified for better maintainability
