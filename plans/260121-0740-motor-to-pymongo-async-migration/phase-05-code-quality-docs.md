# Phase 5: Code Quality & Documentation

## Context Links
- [Plan Overview](plan.md)
- [Phase 4: Configuration](phase-04-update-configuration.md)
- [codebase-summary.md](../../docs/codebase-summary.md)
- [system-architecture.md](../../docs/system-architecture.md)

## Overview
- **Priority:** P2 (quality assurance)
- **Status:** pending
- **Effort:** 30m
- **Description:** Run type checking, linting, and update documentation to reflect PyMongo Async

## Key Insights
- mypy should pass after type hint updates
- ruff will catch any formatting issues
- Documentation references "Motor" in multiple places
- CLAUDE.md also references Motor

## Requirements

### Functional
- All type checks pass
- All linting passes
- Documentation accurate

### Non-Functional
- Clean codebase state before testing
- Docs help future developers understand the stack

## Architecture
Quality assurance phase. No code changes except documentation.

## Related Code Files

### Files to Update
| File | Lines | Change Description |
|------|-------|-------------------|
| `docs/codebase-summary.md` | 12, 33, 225-226, 229 | Motor → PyMongo Async references |
| `docs/system-architecture.md` | 70-80, 377-382 | Motor → PyMongo Async references |
| `CLAUDE.md` | N/A | Review if Motor mentioned |

## Implementation Steps

### Step 1: Run Type Checking

```bash
mypy src/
```

**Expected:** Pass (or only pre-existing unrelated errors)

**If type errors occur:**
- `AsyncCollection` may need generic: `AsyncCollection[dict]`
- Add `# type: ignore` only as last resort

### Step 2: Run Linting

```bash
ruff check .
ruff format .
```

**Expected:** Pass after format fixes applied

### Step 3: Update codebase-summary.md

**Line 12:**
```markdown
# BEFORE
│   ├── database/        # MongoDB (Motor async driver)

# AFTER
│   ├── database/        # MongoDB (PyMongo Async API)
```

**Line 33:**
```markdown
# BEFORE
- **Driver:** Motor (async MongoDB)

# AFTER
- **Driver:** PyMongo (native async API)
```

**Lines 225-226:**
```markdown
# BEFORE
- **motor** - Async MongoDB driver

# AFTER
- **pymongo** - MongoDB driver (native async API)
```

**Line 229 (remove if exists):**
Remove any standalone `motor` reference in dependencies list.

### Step 4: Update system-architecture.md

**Lines 70-80 (Database section):**
```markdown
# BEFORE
### Database (Motor + MongoDB)
...
- `_client: motor.motor_asyncio.AsyncClient` - MongoDB connection
- `_database: motor.motor_asyncio.AsyncDatabase` - Default database reference

# AFTER
### Database (PyMongo Async + MongoDB)
...
- `_client: pymongo.asynchronous.AsyncMongoClient` - MongoDB connection
- `_database: pymongo.asynchronous.AsyncDatabase` - Default database reference
```

**Lines 377-382 (MongoDB Integration):**
```markdown
# BEFORE
### MongoDB
- **Driver:** Motor (async)

# AFTER
### MongoDB
- **Driver:** PyMongo (native async API)
```

### Step 5: Review CLAUDE.md

Search for Motor references:
```bash
grep -i "motor" CLAUDE.md
```

If found, update to PyMongo Async.

### Step 6: Final Grep Check

```bash
# Ensure no Motor references remain in src/
grep -r "motor" src/
# Expected: No results

# Check docs
grep -ri "motor" docs/
# Expected: No results after updates
```

## Todo List
- [ ] Run `mypy src/` and fix any type errors
- [ ] Run `ruff check .` and fix any lint errors
- [ ] Run `ruff format .` to auto-format
- [ ] Update codebase-summary.md Motor → PyMongo Async
- [ ] Update system-architecture.md Motor → PyMongo Async
- [ ] Review CLAUDE.md for Motor references
- [ ] Final grep to ensure no Motor references remain
- [ ] Commit documentation changes

## Success Criteria
- `mypy src/` exits with 0 or only pre-existing errors
- `ruff check .` exits with 0
- `grep -r "motor" src/` returns no results
- `grep -ri "motor" docs/` returns no results
- Documentation accurately describes PyMongo Async

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| mypy errors from generics | Medium | Low | Add explicit generic params |
| Missed Motor reference | Low | Low | Grep catches most; review manually |
| Doc formatting breaks | Very Low | Very Low | Preview in editor |

## Security Considerations
- No security impact (documentation and tooling only)

## Next Steps
After completion, proceed to [Phase 6: Manual Testing](phase-06-manual-testing.md)
