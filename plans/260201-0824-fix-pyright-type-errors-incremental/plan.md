---
title: "Fix Pyright Type Errors (Standard Mode)"
description: "Fix 134 pyright errors using community best practices"
status: completed
priority: P2
effort: 2-3h
branch: feat/strategy-init
tags: [type-checking, pyright, code-quality]
created: 2026-02-01
---

# Fix Pyright Type Errors (Standard Mode)

## Overview

Fix 134 pyright errors to achieve zero errors in standard mode (community best practice).

## Key Decisions Made

### Why Standard Mode (Not Strict)

Based on research from [Pyright docs](https://github.com/microsoft/pyright/blob/main/docs/configuration.md), [Python Typing Best Practices](https://typing.python.org/en/latest/reference/best_practices.html), and [PyCon US 2025](https://us.pycon.org/2025/schedule/presentation/13/):

| Mode | Adoption | Errors in This Codebase |
|------|----------|------------------------|
| strict | ~10% | 2020 errors |
| **standard** | ~30% | **134 errors** |
| basic | ~60% | ~50 errors |

**Standard mode** catches real bugs without being pedantic about third-party libs and minor issues.

### Configuration Applied

**pyrightconfig.json:**
```json
{
  "include": ["src", "tests"],
  "pythonVersion": "3.14",
  "typeCheckingMode": "standard",
  "reportMissingImports": "error",
  "reportMissingModuleSource": "error",
  "reportUnusedImport": "error",
  "reportUnusedVariable": "error",
  "reportMissingTypeStubs": "none",
  "reportPrivateUsage": "error",
  "executionEnvironments": [
    {
      "root": "tests",
      "reportPrivateUsage": "none"
    }
  ]
}
```

**Key settings:**
- `reportMissingTypeStubs`: "none" - 3rd-party libs without stubs are OK
- `reportPrivateUsage`: "error" in src/, "none" in tests/ (per [Pyright best practice](https://github.com/microsoft/pyright/discussions/8193))
- All warnings converted to errors (zero tolerance)

### VS Code Settings

**.vscode/settings.json:**
```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/Scripts/python.exe",
  "python.analysis.typeCheckingMode": "standard",
  "python.analysis.diagnosticMode": "workspace",
  "python.analysis.autoSearchPaths": true,
  "python.analysis.extraPaths": ["${workspaceFolder}/src"]
}
```

## Current State

**0 errors, 0 warnings** - All fixed!

Run `npx pyright src/ tests/` to see current errors.

## Phases

| Phase | Description | Status |
|-------|-------------|--------|
| [Phase 1](./phase-01-fix-src-type-errors.md) | Fix src/ type errors | ✅ Complete |
| [Phase 2](./phase-02-fix-tests-type-errors.md) | Fix tests/ type errors | ✅ Complete |

## Success Criteria

- [x] `npx pyright src/ tests/` exits with 0 errors, 0 warnings
- [x] Minimal `# type: ignore` comments (documented below)
- [ ] CI/CD pyright check passes

### Type Ignore Comments Used

1. `src/common/logging/setup.py` - structlog processor type mismatch (lib issue)
2. `src/infrastructure/tradingview/provider.py` - pandas DataFrame iteration types
3. `tests/conftest.py` - pydantic URL type coercion

## Commands

```bash
# Check current errors
npx pyright src/ tests/

# Check specific file
npx pyright src/common/health/checks.py
```

## Notes

- Fix imports first to resolve cascading unknown type errors
- Use `Any` sparingly - prefer concrete types
- Run pyright after each file fix to verify progress
