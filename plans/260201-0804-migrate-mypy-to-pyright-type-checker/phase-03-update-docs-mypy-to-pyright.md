# Phase 3: Update Documentation - mypy to Pyright

## Context
- **Parent Plan:** [plan.md](./plan.md)
- **Depends On:** Phases 1-2

## Overview
- **Priority:** Medium
- **Status:** Pending
- **Description:** Replace all mypy references with pyright/Pylance, add rationale

## Files to Update

### 1. docs/code-standards.md
Lines with mypy references:
- 370: `mypy src/` → `pyright src/`
- 512-516: Type Checking section → update commands
- 638: Checklist item

### 2. docs/README.md
Lines with mypy references:
- 143: `mypy compliance` → `pyright compliance`
- 147: `ruff, mypy, pytest` → `ruff, pyright, pytest`
- 318: `mypy src/` → `pyright src/`

### 3. docs/project-overview-pdr.md
Lines with mypy references:
- 359: `mypy compliant` → `pyright compliant`
- 449: `mypy` → `pyright`

## Rationale to Add (in code-standards.md Type Checking section)

```markdown
### Type Checking (Pyright)

We use **Pyright** (via Pylance in VSCode) instead of mypy:
- **3-5x faster** than mypy for large codebases
- **Native VSCode integration** via Pylance extension
- **Better type inference** for complex patterns
- **Pydantic v2 native support** (no plugin needed)

Commands:
pyright src/                 # Type check entire source
pyright src/features/market_data/services/  # Check specific module
```

## Implementation Steps

1. Edit `docs/code-standards.md`:
   - Replace mypy → pyright in commands
   - Update Type Checking section with rationale
   - Update checklist item

2. Edit `docs/README.md`:
   - Replace mypy references with pyright

3. Edit `docs/project-overview-pdr.md`:
   - Replace mypy references with pyright

## Todo
- [ ] Update code-standards.md with pyright commands and rationale
- [ ] Update README.md
- [ ] Update project-overview-pdr.md

## Success Criteria
- [ ] No mypy references in docs/
- [ ] Rationale for pyright choice documented
- [ ] All type checking commands reference pyright

## Next Steps
→ Migration complete, commit changes
