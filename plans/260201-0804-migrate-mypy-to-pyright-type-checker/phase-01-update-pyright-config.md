# Phase 1: Update Pyright Configuration

## Context
- **Parent Plan:** [plan.md](./plan.md)
- **Current Config:** `pyrightconfig.json` with basic mode, src only

## Overview
- **Priority:** High
- **Status:** Pending
- **Description:** Update pyrightconfig.json to strict mode with full project scope

## Current State

```json
{
  "include": ["src"],
  "pythonVersion": "3.14",
  "typeCheckingMode": "basic"
}
```

## Target State

```json
{
  "include": ["src", "tests"],
  "pythonVersion": "3.14",
  "typeCheckingMode": "strict",
  "reportMissingImports": "warning"
}
```

## Related Files
- `pyrightconfig.json` - Update

## Implementation Steps

1. Edit `pyrightconfig.json`:
   - Change `typeCheckingMode` from `basic` to `strict`
   - Add `tests` to `include` array
   - Add `reportMissingImports: "warning"` for third-party libs without stubs

2. Run `pyright` to verify no breaking errors

## Todo
- [ ] Update pyrightconfig.json
- [ ] Run pyright and fix any errors

## Success Criteria
- [ ] `pyright` runs without errors on src/ and tests/
- [ ] Strict mode enabled

## Next Steps
→ Phase 2: Remove mypy, add pyright dependency
