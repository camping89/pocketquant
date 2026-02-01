# Phase 3: Verification & Sync

## Overview
- **Priority**: P2
- **Status**: pending
- **Effort**: 10m

Verify cleanup was successful and sync lock file.

## Implementation Steps

### Step 1: Sync Lock File
```bash
cd D:\w\_me\pocketquant && uv sync
```
Updates `uv.lock` to reflect removed dependencies.

### Step 2: Verify No F401 Errors
```bash
cd D:\w\_me\pocketquant && ruff check src/ --select=F401
```
Expected: No output (no errors)

### Step 3: Verify No DEP002 Errors
```bash
cd D:\w\_me\pocketquant && deptry src/ 2>&1 | grep DEP002
```
Expected: No output (no unused dependency errors)

Note: Ignore DEP003 (transitive deps) and DEP001 (missing deps) - those are separate issues.

### Step 4: Verify App Imports Work
```bash
cd D:\w\_me\pocketquant && python -c "from src.main import app; print('OK')"
```
Expected: `OK`

## Success Criteria
- [ ] `uv sync` completes without error
- [ ] `ruff check --select=F401` returns no errors
- [ ] `deptry | grep DEP002` returns no errors
- [ ] App imports successfully

## Rollback
If verification fails:
1. `git checkout pyproject.toml uv.lock`
2. `git checkout src/` (for import changes)
3. `uv sync`
