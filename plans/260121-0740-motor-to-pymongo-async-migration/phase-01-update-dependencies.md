# Phase 1: Update Dependencies

## Context Links
- [Plan Overview](plan.md)
- [PyMongo Async Research](research/researcher-pymongo-async-api.md)
- [pyproject.toml](../../pyproject.toml)

## Overview
- **Priority:** P1 (blocking)
- **Status:** pending
- **Effort:** 15m
- **Description:** Remove Motor dependency, ensure PyMongo >= 4.16 for Python 3.14 support

## Key Insights
- Motor 3.7.1 fails on Python 3.14 (auth handshake issues)
- PyMongo 4.16+ includes native async API with full Python 3.14 wheels
- Motor was a wrapper; PyMongo async is direct asyncio implementation

## Requirements

### Functional
- Remove `motor>=3.3.0` from dependencies
- Ensure `pymongo>=4.16.0` (not just `>=4.6.0`)
- Maintain Python 3.14 compatibility

### Non-Functional
- No runtime errors on import
- Package installs without conflicts

## Architecture
Simple dependency update. No structural changes.

## Related Code Files

### Files to Modify
| File | Line | Current | New |
|------|------|---------|-----|
| `pyproject.toml` | 18 | `"motor>=3.3.0",` | Remove line |
| `pyproject.toml` | 19 | `"pymongo>=4.6.0",` | `"pymongo>=4.16.0",` |

## Implementation Steps

1. **Edit pyproject.toml**
   ```toml
   # BEFORE (lines 18-19)
   "motor>=3.3.0",           # Async MongoDB driver
   "pymongo>=4.6.0",

   # AFTER
   "pymongo>=4.16.0",        # Async MongoDB driver (native async API)
   ```

2. **Reinstall dependencies**
   ```bash
   pip install -e ".[dev]"
   ```

3. **Verify installation**
   ```bash
   pip show pymongo | grep Version
   # Should show 4.16.0 or higher

   pip show motor
   # Should show "not found" or can be uninstalled
   ```

4. **Uninstall Motor if still present**
   ```bash
   pip uninstall motor -y
   ```

## Todo List
- [ ] Remove motor dependency line from pyproject.toml
- [ ] Update pymongo version to >=4.16.0
- [ ] Update comment to reflect "native async API"
- [ ] Run pip install -e ".[dev]"
- [ ] Verify pymongo version >= 4.16.0
- [ ] Verify motor is uninstalled

## Success Criteria
- `pip show pymongo` shows version >= 4.16.0
- `pip show motor` returns "not found"
- `python -c "from pymongo.asynchronous import AsyncMongoClient"` succeeds
- No import errors when running application (will fail on Motor imports until Phase 2)

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| PyMongo 4.16 not available | Low | High | Check PyPI first; fallback to 4.14 if needed |
| Dependency conflicts | Low | Medium | Review pip resolver output |
| Motor still imported elsewhere | Medium | Low | Phase 2 will catch import errors |

## Security Considerations
- No security impact (dependency version bump only)
- Ensure downloading from official PyPI

## Next Steps
After completion, proceed to [Phase 2: Migrate Database Connection](phase-02-migrate-database-connection.md)
