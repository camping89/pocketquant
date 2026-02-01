# Phase 2: Fix Unused Imports

## Overview
- **Priority**: P2
- **Status**: pending
- **Effort**: 10m

Auto-fix 5 unused imports using ruff.

## Imports to Remove (F401 violations)

| Import | File | Line |
|--------|------|------|
| `ReplayStats` | `src/features/backtesting/engine/backtest_runner.py` | 14 |
| `typing.Any` | `src/features/backtesting/metrics/result_collector.py` | 4 |
| `dataclasses.field` | `src/features/backtesting/models/optimization_config.py` | 3 |
| `dataclasses.field` | `src/features/backtesting/models/optimization_result.py` | 3 |
| `typing.Any` | `src/infrastructure/brokers/okx/websocket/okx_message_parser.py` | 3 |

## Implementation Steps

1. Run ruff auto-fix:
   ```bash
   ruff check --fix --select=F401 src/
   ```

2. Verify changes applied to all 5 files

## Command
```bash
cd D:\w\_me\pocketquant && ruff check --fix --select=F401 src/
```

## Expected Output
```
Found 5 errors (5 fixed, 0 remaining).
```

## Success Criteria
- [ ] All 5 F401 errors auto-fixed
- [ ] No remaining F401 errors in codebase
