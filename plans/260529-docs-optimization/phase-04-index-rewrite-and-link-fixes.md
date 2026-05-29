---
phase: 4
title: "Index Rewrite and Link Fixes"
status: completed
priority: P1
effort: "1h"
dependencies: [1, 2, 3]
---

# Phase 4: Index Rewrite and Link Fixes

## Overview
Final reconciliation. Rewrite `docs/README.md` index to the new 12-file canonical set + an Archive section, then fix every inbound link across the repo that points at a deleted or moved doc. Ends with a repo-wide dangling-link verification.

## Requirements
- Functional: index lists exactly the canonical set + archive pointer; zero dangling links repo-wide.
- Non-functional: index reflects reality (currently misses strategy-lifecycle, websocket-architecture, feature-add-symbol).

## Architecture
### Index rewrite (`docs/README.md`)
New structure:
- Canonical Docs: Root README, run-and-test-guide, system-architecture, architecture-visual-map, handler-pipelines, code-standards, deployment, project-overview-pdr, project-changelog, strategy-lifecycle, websocket-architecture, feature-add-symbol.
- Remove dead entries: codebase-summary, ddd-strategic-map, debug-audit-order-execution, migration-doubts-and-notes (and the EN feature dup if it was ever listed).
- Add new section: `## Archive (historical, may be outdated)` → links into `docs/archive/` (debug-audit, security-redis, migration-doubts, journals/).
- Keep "Maintenance Note" + "Current Repo Shape" sections.

### Inbound link fixes (exact, from repo grep)

| File:line | Current ref | Action |
|---|---|---|
| `README.md:157` (root) | `[Codebase Summary](./docs/codebase-summary.md)` | Replace with system-architecture or remove (codebase-summary deleted) |
| `docs/README.md:16,64` | codebase-summary links | Removed in index rewrite |
| `docs/README.md:27` | ddd-strategic-map link | Removed in index rewrite |
| `docs/README.md:30` | debug-audit-order-execution | Repoint to `./archive/debug-audit-order-execution.md` (or drop from canonical, list under Archive) |
| `docs/README.md:31` | migration-doubts-and-notes | Repoint to `./archive/` |
| `CLAUDE.md:121` (project) | `docs/migration-doubts-and-notes.md` | Repoint to `docs/archive/migration-doubts-and-notes.md` |
| `docs/feature-add-symbol.md:172` | `./debug-audit-order-execution.md` | Repoint to `./archive/debug-audit-order-execution.md` |
| `docs/feature-add-symbol.md:175` | `./journals/strategy-subscriptions-cached-backtest-260505.md` | Repoint to `./archive/journals/...` |
| `docs/feature-add-symbol.md:3` | `journals/...` in frontmatter Related | Repoint to `archive/journals/...` |
| `plans/260529-bug-backlog-tick-count-and-yaml-path-context.md:12,62,69,112` | `docs/migration-doubts-and-notes.md` | Repoint to `docs/archive/migration-doubts-and-notes.md` |

### Self-references inside archived files (now same-dir)
- `docs/archive/journals/260529-prod-redis-...md:12,42,51` reference `docs/security-redis-exposure.md` → now `docs/archive/security-redis-exposure.md`. Update to correct path (these are prose mentions, not all clickable links, but fix for accuracy).
- `docs/archive/journals/binance-migration-cook-complete-260508.md:54` mentions `codebase-summary` in prose (historical changelog line) → leave as-is (historical record of what happened at that time; do NOT rewrite history). Document this exception.

## Related Code Files
- Modify: `docs/README.md` (full rewrite of index)
- Modify: `README.md` (root, docs section)
- Modify: `CLAUDE.md`
- Modify: `docs/feature-add-symbol.md`
- Modify: `plans/260529-bug-backlog-tick-count-and-yaml-path-context.md`
- Modify (accuracy): `docs/archive/journals/260529-prod-redis-requirepass-security-and-cicd-gate-breakdown.md`

## Implementation Steps
1. Rewrite `docs/README.md` per structure above.
2. Fix root `README.md:157`.
3. Fix `CLAUDE.md:121`.
4. Fix `docs/feature-add-symbol.md` (lines 3, 172, 175).
5. Fix `plans/260529-bug-backlog-...md` (4 refs).
6. Fix archive journal self-ref to security-redis-exposure path (accuracy).
7. Leave historical-prose mention of codebase-summary in the cook-complete journal untouched (it records a past event).
8. **Verification sweep** — run repo-wide grep for every removed/moved basename; confirm no canonical doc or config still points at an old path:
   ```bash
   grep -rn -e "codebase-summary" -e "ddd-strategic-map" -e "feature-add-symbol-en" \
     -e "docs/debug-audit-order-execution" -e "docs/security-redis-exposure" \
     -e "docs/migration-doubts-and-notes" -e "docs/journals/" \
     . --include="*.md" --include="*.py" --include="*.toml" \
     | grep -v "/.venv/" | grep -v "/.git/" | grep -v "/node_modules/" \
     | grep -v "plans/260529-docs-optimization/"
   ```
   Expected remaining hits: ONLY the intentional historical-prose line in the cook-complete journal (Step 7). Anything else = fix it.
9. Spot-check a few rewritten links resolve to existing files.

## Success Criteria
- [ ] `docs/README.md` lists the 12 canonical files + an Archive section; no links to deleted docs.
- [ ] Root `README.md` docs section has no dead links.
- [ ] `CLAUDE.md:121` points at archive path.
- [ ] `feature-add-symbol.md` + bug-backlog plan links repointed.
- [ ] Verification grep returns only the one documented historical-prose exception.
- [ ] Every link in `docs/README.md` resolves to an existing file.

## Risk Assessment
- **Risk:** miss an inbound link. **Mitigation:** Step 8 grep is exhaustive over md/py/toml; baseline was captured during planning.
- **Risk:** rewriting historical journal prose falsifies the record. **Mitigation:** Step 7 explicitly preserves the past-event mention; only path-accuracy fixes applied to archive self-refs.
- **Risk:** anchor-style links (`#heading`) to merged docs. **Mitigation:** none found in baseline grep; if any surface, repoint to system-architecture anchors.
