---
phase: 1
title: "Architecture Consolidation"
status: completed
priority: P2
effort: "2h"
dependencies: []
---

# Phase 1: Architecture Consolidation

## Overview
Collapse the 5-doc architecture cluster into 2 canonical docs. Keep `system-architecture.md` (deep reference) and `architecture-visual-map.md` (diagrams). Fold the unique content of `codebase-summary.md` and `ddd-strategic-map.md` into them, move DDD classification rules into `code-standards.md`, then delete the two merged-away files.

## Requirements
- Functional: every unique fact in `codebase-summary.md` and `ddd-strategic-map.md` survives in a canonical doc; nothing valuable lost.
- Non-functional: no duplicated content reintroduced; single source per fact.
- Correctness: fix the wrong path during the merge (do not copy it verbatim).

## Architecture
Content routing (source → destination):

| Source content | From | Destination |
|---|---|---|
| "Where Does X Live?" table | `codebase-summary.md` §Where Does X Live | `system-architecture.md` (new top-level section, e.g. after Layer Breakdown) — **verbatim**, but FIX row 143 |
| Config / env-var table | `codebase-summary.md` §Configuration | `system-architecture.md` — only if not already present; else drop |
| Dependencies table | `codebase-summary.md` §Dependencies | `system-architecture.md` §Performance & Security or a new §Dependencies — only if not already present |
| Current Strategies table | `codebase-summary.md` §Current Strategies | `system-architecture.md` — only if not already present (also in root README + PDR; prefer drop if duplicated) |
| Known Limitations list | `codebase-summary.md` §Known Limitations | `system-architecture.md` §Recent Significant Changes neighbourhood — only if not already covered |
| 6 Bounded Contexts table | `ddd-strategic-map.md` | `architecture-visual-map.md` (near §2 Domain Three-Tier / §11 Naming Glossary) |
| Context Map ASCII diagram | `ddd-strategic-map.md` | `architecture-visual-map.md` (alongside other diagrams) |
| Ubiquitous Language table | `ddd-strategic-map.md` | `architecture-visual-map.md` §11 Naming Glossary (merge, dedupe) |
| DDD Classification Guide (when/when-not aggregate, project rules) | `ddd-strategic-map.md` | `code-standards.md` (naming/structure rules section) |
| Open Strategic Questions | `ddd-strategic-map.md` | DROP (stale speculation; git history retains) — or move to PDR §Roadmap if user wants kept |
| Package Overview, dep graph, runtime model, DI quick-ref, deep-dives table | `codebase-summary.md` | DROP — already fully covered by system-architecture + architecture-visual-map (verify before dropping) |

**De-dup discipline:** before copying any block into a destination, grep the destination for an existing equivalent. If present, do not duplicate — keep the better-written one.

## Related Code Files
- Modify: `docs/system-architecture.md`
- Modify: `docs/architecture-visual-map.md`
- Modify: `docs/code-standards.md`
- Delete: `docs/codebase-summary.md` (after content folded in)
- Delete: `docs/ddd-strategic-map.md` (after content folded in)

## Implementation Steps
1. Re-read `docs/system-architecture.md` and `docs/architecture-visual-map.md` fully to know what already exists (avoid re-adding duplicates).
2. Verify the corrected handler paths against the live tree:
   `ls packages/pocketquant-trading/src/pocketquant/trading/handlers`,
   `ls packages/pocketquant-backtest/src/pocketquant/backtest/handlers` (confirm exists),
   `ls packages/pocketquant-api/src/pocketquant/api/market_data`.
3. Insert the "Where Does X Live?" table into `system-architecture.md` verbatim, with the `api/features/{backtesting,market_data,strategy,trading,risk}/` row corrected to the real locations (`trading/handlers/`, `backtest/handlers/`, `api/market_data/`).
4. For each remaining `codebase-summary.md` table (config, dependencies, strategies, limitations): grep system-architecture; fold in only what is missing.
5. Fold `ddd-strategic-map.md` bounded-contexts table + context-map diagram + ubiquitous-language into `architecture-visual-map.md` (merge glossary, dedupe terms).
6. Move the DDD Classification Guide + Project Rules into `code-standards.md` under the existing naming/DDD section.
7. Decide Open Strategic Questions: drop (default) unless user flagged keep.
8. `git rm docs/codebase-summary.md docs/ddd-strategic-map.md` (or `rm` — repo tracks history either way).
9. Leave inbound links dangling for now; Phase 4 fixes them. (Do NOT touch README/index here.)

## Success Criteria
- [ ] `system-architecture.md` contains the "Where Does X Live?" table with corrected paths (no `api/features/`).
- [ ] `architecture-visual-map.md` contains bounded-contexts + context-map + merged ubiquitous-language.
- [ ] `code-standards.md` contains the DDD aggregate-classification rules.
- [ ] `codebase-summary.md` and `ddd-strategic-map.md` deleted.
- [ ] No duplicated tables introduced (spot-check: each fact appears once).
- [ ] `grep -rn "api/features" docs/` returns nothing.

## Risk Assessment
- **Risk:** a unique detail silently lost in merge. **Mitigation:** route via the table above; diff old file against destination before `rm`; the two highest-value blocks (Where-X-Lives, env table) preserved verbatim.
- **Risk:** reintroduce duplication. **Mitigation:** grep destination before each insert.
- **Risk:** copy the wrong path forward. **Mitigation:** Step 2 verifies real tree before Step 3.
