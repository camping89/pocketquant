# Phase 3: Move Misplaced Files

**Priority:** Medium | **Status:** Complete | **Effort:** 15m

## Overview

Relocate files that ended up in wrong locations post-migration.

## Moves

| Source | Destination | Reason |
|--------|------------|--------|
| `http/` (35 files) | `tests/http/` | Bruno API collection belongs with tests |
| `testscripts/run_stream_quotes.py` | `tests/manual/run_stream_quotes.py` | Manual test script |
| `testscripts/api-test.http` | `tests/manual/api-test.http` | Manual test file |
| `scripts/cleanup.sh` | `docker/scripts/cleanup.sh` | Docker ops script |
| `scripts/server-setup.sh` | `docker/scripts/server-setup.sh` | Server provisioning script |

## Files to Keep in `scripts/`

- `scripts/check_env.py` -- dev tooling, stays (fixed in Phase 4)

## Implementation Steps

1. `mkdir -p tests/http tests/manual docker/scripts`
2. `git mv http/ tests/http/` -- preserves Bruno collection structure
3. `git mv testscripts/run_stream_quotes.py tests/manual/`
4. `git mv testscripts/api-test.http tests/manual/`
5. `git mv scripts/cleanup.sh docker/scripts/`
6. `git mv scripts/server-setup.sh docker/scripts/`
7. Remove empty `testscripts/` directory
8. Update `.gitignore` if any patterns reference old paths (none expected)

## Post-Move Verification

```bash
# Verify moves
ls tests/http/bruno.json
ls tests/manual/run_stream_quotes.py
ls docker/scripts/cleanup.sh
# Verify old dirs empty/gone
ls testscripts/  # should not exist
ls scripts/      # should only have check_env.py
```

## Success Criteria

- [x] `http/` moved to `tests/http/` with all 35 Bruno files intact
- [x] `testscripts/` removed, contents in `tests/manual/`
- [x] Ops scripts in `docker/scripts/`
- [x] `scripts/` contains only `check_env.py`
- [x] `testscripts/` directory no longer exists
