# Phase 1: Remove Unused Dependencies

## Overview
- **Priority**: P2
- **Status**: pending
- **Effort**: 10m

Remove 3 unused dependencies from `pyproject.toml`.

## Dependencies to Remove

| Package | Line | Reason |
|---------|------|--------|
| `arq>=0.25.0` | 24 | Async redis queue - project uses APScheduler instead |
| `python-json-logger>=2.0.0` | 39 | Project uses structlog for logging |
| `python-dateutil>=2.8.0` | 43 | Not imported anywhere in codebase |

## Implementation Steps

1. Open `pyproject.toml`
2. Remove lines 24, 39, and 43 (the three packages above)
3. Save file

## File to Modify
- `D:\w\_me\pocketquant\pyproject.toml`

## Before (lines 24-44)
```toml
    "arq>=0.25.0",            # Async Redis Queue for background jobs
    "apscheduler>=3.10.0",    # For scheduled jobs
    ...
    "structlog>=24.1.0",      # Structured logging
    "python-json-logger>=2.0.0",
    ...
    "httpx>=0.26.0",          # Async HTTP client
    "python-dateutil>=2.8.0",
    "rich>=13.0.0",           # Rich console output for error messages
```

## After
```toml
    "apscheduler>=3.10.0",    # For scheduled jobs
    ...
    "structlog>=24.1.0",      # Structured logging
    ...
    "httpx>=0.26.0",          # Async HTTP client
    "rich>=13.0.0",           # Rich console output for error messages
```

## Success Criteria
- [ ] Three dependency lines removed from pyproject.toml
- [ ] File saves without syntax errors
