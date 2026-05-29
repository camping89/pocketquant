---
phase: 3
title: "Archive and Delete"
status: completed
priority: P2
effort: "30m"
dependencies: [1]
---

# Phase 3: Archive and Delete

## Overview
Move point-in-time / historical docs out of canonical `docs/` into `docs/archive/`, and delete the stale EN duplicate of feature-add-symbol. Pure file moves + one delete; no content edits (links fixed in Phase 4).

## Requirements
- Functional: historical content remains readable under `docs/archive/`; stale EN dup removed.
- Non-functional: canonical `docs/` listing no longer mixes snapshots with living reference.

## Architecture
Moves (use `git mv` to preserve history):

| File | → Destination |
|---|---|
| `docs/debug-audit-order-execution.md` | `docs/archive/debug-audit-order-execution.md` |
| `docs/security-redis-exposure.md` | `docs/archive/security-redis-exposure.md` |
| `docs/migration-doubts-and-notes.md` | `docs/archive/migration-doubts-and-notes.md` |
| `docs/journals/` (entire dir, 10 files) | `docs/archive/journals/` |

Delete:

| File | Reason |
|---|---|
| `docs/feature-add-symbol-en.md` | Stale EN dup (2026-05-05, old OKX flow). VI `feature-add-symbol.md` (2026-05-26, current) is kept. |

## Related Code Files
- Move: 3 files + `journals/` dir into `docs/archive/`
- Delete: `docs/feature-add-symbol-en.md`
- Create: `docs/archive/` directory (implicit via git mv)

## Implementation Steps
1. `mkdir -p docs/archive`
2. `git mv docs/debug-audit-order-execution.md docs/archive/`
3. `git mv docs/security-redis-exposure.md docs/archive/`
4. `git mv docs/migration-doubts-and-notes.md docs/archive/`
5. `git mv docs/journals docs/archive/journals`
6. `git rm docs/feature-add-symbol-en.md`
7. Confirm `docs/` top level no longer contains the moved files; `docs/archive/journals/` has all 10 journal files.

## Success Criteria
- [ ] `docs/archive/` contains debug-audit, security-redis, migration-doubts, and `journals/` (10 files).
- [ ] `docs/feature-add-symbol-en.md` gone.
- [ ] `docs/` canonical level has no historical snapshots remaining.
- [ ] Moves preserve git history (`git log --follow` resolves).

## Risk Assessment
- **Risk:** inbound links now dangle (CLAUDE.md, feature-add-symbol.md, journals self-refs). **Mitigation:** intentional — all reconciled in Phase 4, which greps repo-wide.
- **Risk:** `feature-add-symbol-en.md` had unique content not in VI version. **Mitigation:** brainstorm verified EN is an older subset of VI; nothing unique lost. (git retains if needed.)
- **Note:** journal internal references to `docs/security-redis-exposure.md` become same-dir relative once both are under archive/ — verify in Phase 4.
