---
phase: 1
title: "Pre-flight cleanup & audit"
status: pending
priority: P1
effort: "30m"
dependencies: []
---

# Phase 1: Pre-flight cleanup & audit

## Overview

Remove stale code from `deploy.sh` and grep-audit all references to old paths. Establishes the exhaustive list of files touched by later phases — no surprises mid-move.

## Requirements

- Functional: deploy.sh no longer invokes deleted `scripts.one_time_purge_legacy_strategies`. Complete reference inventory produced.
- Non-functional: zero false positives in grep (filter `.venv`, `node_modules`, `__pycache__`).

## Architecture

Pure audit + small surgical edit. No structural change.

## Related Code Files

- Modify: `deploy.sh` (remove lines ~52–65)
- Read-only: `**/*.sh`, `**/*.yml`, `**/*.yaml`, `Dockerfile`, `**/Dockerfile`, `**/*.py`, `**/*.md`, `justfile`, `.run/**`

## Implementation Steps

1. **Remove stale block from `deploy.sh`** (lines ~52–65, the "One-time migrations" section ending at `... || true`):
   - Delete the entire `# ─── One-time migrations ───` block including the 30-iteration health wait loop and the `docker compose ... exec -T app python -m scripts.one_time_purge_legacy_strategies || true` line.
   - Keep `# ─── Cleaning old images ───` and below intact.
2. **Reference audit**: produce a single inventory file at `plans/260524-1805-deploy-folder-consolidation/reports/reference-audit.md` listing every match for these patterns:
   - `docker/compose` (yml, py, sh, md)
   - `docker/\.env`
   - `docker/scripts/`
   - `docker/mongo-init`
   - `^Dockerfile\b` or `\bDockerfile\b` at repo root (not packages/)
   - `\bdeploy\.sh\b` (root)
   - `\bverify\.sh\b` (root)
   - `\.dockerignore` (refs, not the file itself)
   - `scripts/one_time_` (stale refs)
   - `\.env` paths in shell/yml/Dockerfile
3. **Exclude** `.venv`, `node_modules`, `__pycache__`, `htmlcov`, `.git`, `.pytest_cache`, `.ruff_cache`, `.import_linter_cache`.
4. **Categorize each match** as: `MUST UPDATE` (active code/config) or `SKIP` (historical journal, stale plan file, comment in deleted code).
5. Save inventory; phases 3–6 will consume it.

## Success Criteria

- [ ] `deploy.sh` no longer contains `one_time_purge_legacy_strategies` text
- [ ] `deploy.sh` still has `# ─── Cleaning old images ───` block and exits cleanly when traced visually
- [ ] `reports/reference-audit.md` exists with `MUST UPDATE` / `SKIP` columns
- [ ] Spot-check: at least these known-positives appear in audit — `justfile` (4×), `scripts/check_env.py:50`, `Dockerfile` (COPY), `.github/workflows/ci.yml`, `docs/deployment-guide.md`, `docs/project-overview-pdr.md`

## Risk Assessment

- **Risk:** Audit misses a reference → later phase finds it during validation. **Mitigation:** Phase 8 validation re-greps and fails if old paths remain.
- **Risk:** Removing the migration block silently breaks future re-deploys that expected it. **Mitigation:** Block was already a no-op (`|| true` + missing script); removal is net-positive.
