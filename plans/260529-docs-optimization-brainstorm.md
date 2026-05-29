# Brainstorm: Docs Optimization (pocketquant/docs)

**Date:** 2026-05-29 | **Status:** Approved, ready for /ck:plan | **Type:** docs-only reorg

## Problem
`pocketquant/docs/` = 28 files / ~6,980 lines. Two bloat sources:
1. Architecture cluster redescribes layers/DI/package-map/data-flow 5 ways: `system-architecture` (818L), `handler-pipelines` (831L), `codebase-summary` (278L), `architecture-visual-map` (413L), `ddd-strategic-map` (108L). Drift already produced wrong path at `codebase-summary.md:143` (`api/features/...` does not exist).
2. Historical snapshots live in canonical folder: debug-audit, security-redis, migration-doubts, 10 journals, + stale EN dup.

Index (`docs/README.md`) already out of sync (misses strategy-lifecycle, websocket-architecture, security-redis, feature-add-symbol-en, all journals).

## Decisions (user-locked)
- Aggressiveness: **aggressive prune** (merge + delete redundant, rely on git history)
- Historical docs: **move to `docs/archive/`**
- Arch merge: **one canonical (`system-architecture`) + one visual (`architecture-visual-map`)**
- feature-add-symbol: **keep VI**, delete EN dup
- handler-pipelines: **trim** to remove flow overlap with system-architecture (keep per-handler detail)
- Archive location: **`docs/archive/`** (+ `archive/journals/`)

## Target: 28 → 12 canonical files

### Merge (5 → 2)
- KEEP `system-architecture.md` — fold in codebase-summary unique tables: "Where Does X Live?", config/env table, dependencies table, current-strategies, known-limitations. Fix `api/features/...` → real `trading/handlers/`, `backtest/handlers/`, `api/market_data/`.
- KEEP `architecture-visual-map.md` — fold in ddd-strategic-map: context-map diagram, ubiquitous-language table, bounded-contexts table.
- DELETE `codebase-summary.md` (after merge).
- DELETE `ddd-strategic-map.md` — DDD classification rules move to `code-standards.md`.

### Trim
- `handler-pipelines.md` (831L, biggest file) — strip ~40% flow-narrative overlapping system-architecture (Data Pipelines, Request Flow sections); keep per-handler pipeline detail unique to this doc; replace removed narrative with single link back to system-architecture.

### Archive → `docs/archive/`
- `debug-audit-order-execution.md`
- `security-redis-exposure.md`
- `migration-doubts-and-notes.md`
- `journals/*` → `docs/archive/journals/`

### Delete
- `feature-add-symbol-en.md` (stale EN dup; May 5, old OKX flow vs current Binance).

### Rewrite
- `docs/README.md` index → new 12-file set + "Archive (historical, may be outdated)" section.

### Link fixes (grep + rewrite all refs)
- `CLAUDE.md:121` → migration-doubts archive path.
- root `README.md` docs section.
- cross-doc links to: codebase-summary, ddd-strategic-map, feature-add-symbol-en, journals/*.

### Untouched canonical
`deployment`, `run-and-test-guide`, `code-standards` (+DDD rules), `project-overview-pdr`, `project-changelog`, `strategy-lifecycle`, `websocket-architecture`, `feature-add-symbol` (VI).

## Result
~6,980 → ~5,400 canonical lines (~22% cut). Single source for arch facts → no 5-way drift. Index matches reality. History preserved via git + archive/.

## Risks / mitigations
- Merge drops unique detail → diff carefully; "Where X Lives" + env tables are highest-value, preserve verbatim.
- Inbound links break → grep every ref to deleted/moved files before deleting.
- Verify no other code/docs import these paths.

## Open questions
None — all resolved.
