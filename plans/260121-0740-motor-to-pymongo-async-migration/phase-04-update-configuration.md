# Phase 4: Update Configuration

## Context Links
- [Plan Overview](plan.md)
- [Phase 3: Repository Types](phase-03-update-repository-types.md)
- [config.py](../../src/config.py)
- [.env.example](../../.env.example)

## Overview
- **Priority:** P3 (verification)
- **Status:** pending
- **Effort:** 10m
- **Description:** Review and verify configuration compatibility with PyMongo Async API

## Key Insights
- Connection string format unchanged (MongoDB DSN)
- Pool settings (`minPoolSize`, `maxPoolSize`) identical between Motor and PyMongo
- `serverSelectionTimeoutMS` supported in both
- No Motor-specific configuration exists in current codebase

## Requirements

### Functional
- Connection string works with AsyncMongoClient
- Pool settings respected

### Non-Functional
- No unused Motor-specific settings remain

## Architecture
No changes required. Configuration already compatible.

## Related Code Files

### Files to Review (No Changes Expected)
| File | Status | Notes |
|------|--------|-------|
| `src/config.py` | Review | MongoDB settings lines 32-37 |
| `.env.example` | Review | MONGODB_URL format |

## Implementation Steps

### Step 1: Verify config.py Settings (Lines 32-37)

Current settings already compatible:
```python
# MongoDB
mongodb_url: MongoDsn = Field(
    default="mongodb://pocketquant:pocketquant_dev@localhost:27018/pocketquant?authSource=admin"
)
mongodb_database: str = "pocketquant"
mongodb_min_pool_size: int = 5
mongodb_max_pool_size: int = 50
```

**Verification:**
- `MongoDsn` type: Compatible (standard MongoDB connection string)
- `minPoolSize`: Supported by PyMongo (default 0 in PyMongo, we set 5)
- `maxPoolSize`: Supported by PyMongo (default 100 in PyMongo, we set 50)
- No `io_loop` reference: Correct (never existed)

### Step 2: Review .env.example

```bash
# Verify MONGODB_URL format is standard
MONGODB_URL=mongodb://user:pass@host:27018/database?authSource=admin
```

**No changes needed** - Standard MongoDB connection string works with both Motor and PyMongo.

### Step 3: Check for Motor-Specific Environment Variables

Search for any Motor-specific settings:
```bash
grep -r "MOTOR" .env* src/config.py
# Expected: No results
```

### Step 4: Verify Pool Size Recommendations

| Setting | Current | PyMongo Default | Recommendation |
|---------|---------|-----------------|----------------|
| minPoolSize | 5 | 0 | Keep 5 (good for FastAPI concurrency) |
| maxPoolSize | 50 | 100 | Keep 50 (reasonable limit) |
| serverSelectionTimeoutMS | 5000 | 30000 | Keep 5000 (fast fail) |

**Research Note:** PyMongo docs recommend `minPoolSize > 0` for high-concurrency apps like FastAPI. Current value of 5 is appropriate.

## Todo List
- [ ] Review config.py MongoDB settings (no changes expected)
- [ ] Review .env.example MONGODB_URL format
- [ ] Grep for any "MOTOR" references in config
- [ ] Document pool settings as verified compatible

## Success Criteria
- No Motor-specific configuration found
- Pool settings documented as compatible
- Connection string format verified standard

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Pool size behavior different | Very Low | Low | PyMongo uses same semantics |
| Auth mechanism change | Very Low | Medium | Same `authSource` handling |
| TLS/SSL config different | Very Low | Medium | Not using TLS in current config |

## Security Considerations
- Connection credentials still from environment variables
- No new configuration exposure
- Same auth mechanism (SCRAM)

## Next Steps
After completion, proceed to [Phase 5: Code Quality & Docs](phase-05-code-quality-docs.md)
