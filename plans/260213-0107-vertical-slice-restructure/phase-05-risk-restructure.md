# Phase 5: Risk Restructure

## Priority: Low | Effort: Low | Risk: Low

Trivial — single handler file. Just reorganize into canonical pattern.

## Context

- [Plan](plan.md) | Depends on: Phase 4

## Current → Target

```
risk/                              risk/
├── handlers/                      ├── check_risk/
│   ├── __init__.py                │   ├── __init__.py
│   └── risk_check_handler.py      │   └── handler.py
└── __init__.py                    └── __init__.py
```

No `base/` needed — no infra code. No `router.py` — not HTTP-exposed (internal handler only).

## Files to Modify

**Move (git mv):**
- `handlers/risk_check_handler.py` → `check_risk/handler.py`

**Create:**
- `check_risk/__init__.py` — re-export RiskCheckHandler

**Delete:**
- `handlers/` folder

**Update:**
- `risk/__init__.py` — `from src.features.risk.check_risk import RiskCheckHandler`

## Implementation Steps

1. `mkdir check_risk/`
2. `git mv handlers/risk_check_handler.py check_risk/handler.py`
3. Create `check_risk/__init__.py`
4. Update `risk/__init__.py`
5. Delete `handlers/` folder
6. Run `ruff check` + `pyright`

## Todo

- [x] Move handler to check_risk/
- [x] Update __init__.py
- [x] Delete handlers/ folder
- [x] Verify ruff + pyright pass

## Success Criteria

- `from src.features.risk import RiskCheckHandler` still works
- `ls risk/` shows: check_risk/, __init__.py
