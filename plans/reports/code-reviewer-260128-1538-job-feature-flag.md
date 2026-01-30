# Code Review: Job Feature Flag Implementation

**Date:** 2026-01-28
**Reviewer:** code-reviewer
**Score:** 7/10

## Scope
- Files: `src/config.py`, `src/main.py`, `.env.example`
- Lines: ~10 changed across 3 files
- Focus: Feature flag for background jobs

## Overall Assessment
Clean, minimal implementation. Flag correctly gates job initialization/shutdown. One **critical bug** found.

## Critical Issues

### ❌ `/system/jobs` Endpoint Returns Empty List When Jobs Disabled
**Location:** `src/main.py:170-172`

```python
@app.get(f"{settings.api_prefix}/system/jobs")
async def list_jobs() -> list[dict]:
    return JobScheduler.get_jobs()  # Returns [] if scheduler is None
```

**Problem:** Endpoint always returns 200 OK with empty list when `ENABLE_JOBS=false`. No indication jobs are disabled.

**Impact:** API consumers cannot distinguish between "no jobs scheduled" vs "jobs feature disabled".

**Fix Options:**
1. Return 503 Service Unavailable + message when jobs disabled
2. Add `jobs_enabled: bool` field to response
3. Conditional route registration (only expose endpoint when jobs enabled)

**Recommendation:** Option 3 (cleanest):
```python
if settings.enable_jobs:
    @app.get(f"{settings.api_prefix}/system/jobs")
    async def list_jobs() -> list[dict]:
        return JobScheduler.get_jobs()
```

## High Priority: None

## Medium Priority

### ⚠️ Missing Validation Logic
- No check preventing job-related API calls (trigger/remove jobs) when disabled
- If other endpoints exist that interact with `JobScheduler`, they need guards

### ⚠️ Documentation Gap
- `.env.example` comment too minimal: `# Background Jobs` + `ENABLE_JOBS=true`
- Should explain: "Set to false to disable scheduled background jobs (data sync, cleanup, etc.)"

## Low Priority

### 💡 Type Annotation Consistency
`enable_jobs: bool = True` - explicit default good, but no Field() descriptor like other settings might use. Consistent with current style.

### 💡 Log Message Quality
Lines 74-76: Clear distinction between enabled/disabled states. Good.

## Positive Observations
✅ Minimal changes adhering to YAGNI/KISS
✅ No syntax/compile errors
✅ Passes linter checks
✅ Proper shutdown order (jobs → cache → db)
✅ Conditional mediator setup (line 99-100) prevents null reference
✅ Settings accessed consistently via `get_settings()`

## Metrics
- Type Coverage: Full (mypy clean expected)
- Linting: All checks passed
- Security: No concerns (boolean config)
- Performance: No impact

## Recommended Actions
1. **[CRITICAL]** Fix `/system/jobs` endpoint behavior when jobs disabled
2. Improve `.env.example` documentation for `ENABLE_JOBS`
3. Audit codebase for other job-related endpoints needing guards

## Score Breakdown
- **Correctness:** -2 (critical endpoint bug)
- **Simplicity:** +1 (minimal, focused changes)
- **Security:** 0 (no issues)
- **Completeness:** -1 (missing endpoint guard)

**Final:** 7/10 - Good implementation with one critical fix needed.
