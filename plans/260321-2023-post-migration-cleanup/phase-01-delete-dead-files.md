# Phase 1: Delete Dead Files

**Priority:** High | **Status:** Complete | **Effort:** 10m

## Overview

Remove stale artifacts from the monolith migration: completed plan dirs, generated XML, cached bytecode.

## Files to Delete

### Completed plan directories
- `plans/260321-0902-monorepo-package-split/` (7 files -- migration plan, done)
- `plans/260321-1849-migration-doubts-cleanup/` (6 files -- doubts plan, done)

### Completed plan reports
- `plans/reports/researcher-260321-0847-python-monorepo-research.md`
- `plans/reports/brainstorm-260321-0902-monorepo-package-split.md`
- `plans/reports/project-manager-260321-1935-migration-doubts-cleanup.md`
- `plans/reports/code-review-260321-1927-migration-doubts-cleanup.md`

### Generated artifacts
- `repomix-output.xml` (already in .gitignore, just delete from disk)

### Cached bytecode (tracked despite .gitignore)
- `testscripts/__pycache__/` (entire dir -- will be moved in Phase 3 anyway, but clean first)

## Implementation Steps

1. `rm -rf plans/260321-0902-monorepo-package-split/`
2. `rm -rf plans/260321-1849-migration-doubts-cleanup/`
3. `rm plans/reports/researcher-260321-0847-python-monorepo-research.md`
4. `rm plans/reports/brainstorm-260321-0902-monorepo-package-split.md`
5. `rm plans/reports/project-manager-260321-1935-migration-doubts-cleanup.md`
6. `rm plans/reports/code-review-260321-1927-migration-doubts-cleanup.md`
7. `rm repomix-output.xml`
8. `rm -rf testscripts/__pycache__/`
9. `git rm --cached` any tracked __pycache__ files if needed

## Success Criteria

- [x] No completed plan directories remain
- [x] No stale reports remain
- [x] `repomix-output.xml` gone from working tree
- [x] No `__pycache__` in `testscripts/`
