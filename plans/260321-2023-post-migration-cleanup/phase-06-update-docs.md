# Phase 6: Update Docs

**Priority:** Medium | **Status:** Complete | **Effort:** 30m

## Overview

README.md still describes monolith `src/` structure and `uvicorn src.main:app`. Update to reflect monorepo reality.

## Files to Modify

### 1. `README.md`

**Problems:**
- "Latest: DDD refactoring complete" -- outdated, now monorepo
- Quick Start: `uvicorn src.main:app --reload` -- old path
- Architecture section: entire `src/` tree -- no longer exists
- Development section: `uvicorn src.main:app`, `pyright src/` -- old paths
- API port `8765` -- now `41920`

**Fix:** Rewrite to reflect monorepo. Key changes:
- Update "Latest" blurb to mention monorepo migration
- Quick Start: `just dev` or `uvicorn pocketquant.api.main:app --reload`
- Replace `src/` architecture tree with `packages/` structure from CLAUDE.md
- Fix all port references to 41920
- Update Development commands to use justfile recipes
- Keep Features, API Examples, Configuration, Documentation sections (update ports)

### 2. `docs/migration-doubts-and-notes.md`

- Review for resolved items -- mark as resolved or delete
- Keep only unresolved items

### 3. `.vscode/tasks.json` (optional, create if useful)

- Add tasks for `just test`, `just lint`, `just dev`
- Low priority -- skip if time-constrained

## Implementation Steps

1. Rewrite README.md:
   - Update header/latest status
   - Fix Quick Start (just install, just up, just dev)
   - Replace architecture tree with monorepo packages
   - Fix all `src.main:app` -> `pocketquant.api.main:app`
   - Fix all port 8765 -> 41920
   - Update Development section to use just recipes
2. Review `docs/migration-doubts-and-notes.md`, prune resolved items
3. (Optional) Create `.vscode/tasks.json`

## Success Criteria

- [x] README.md has no `src/` or `src.main` references
- [x] All port references are 41920
- [x] Quick Start works with copy-paste
- [x] Architecture section shows `packages/` structure
- [x] `migration-doubts-and-notes.md` has only unresolved items
