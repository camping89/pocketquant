# Phase 2: Remove mypy Config, Dependency, and Cache

## Context
- **Parent Plan:** [plan.md](./plan.md)
- **Depends On:** Phase 1

## Overview
- **Priority:** High
- **Status:** Pending
- **Description:** Clean up mypy config, dependency, and cache folder; add pyright dep

## Current State

**pyproject.toml:**
```toml
# Dev dependencies (line 53)
"mypy>=1.8.0",

# Mypy config (lines 72-81)
[tool.mypy]
python_version = "3.14"
strict = true
ignore_missing_imports = true
plugins = ["pydantic.mypy"]

[tool.pydantic-mypy]
init_forbid_extra = true
init_typed = true
warn_required_dynamic_aliases = true
```

**Cache folder:** `.mypy_cache/` exists (already in .gitignore)

## Related Files
- `pyproject.toml` - Edit
- `.mypy_cache/` - Delete

## Implementation Steps

1. Edit `pyproject.toml`:
   - Replace `"mypy>=1.8.0"` with `"pyright>=1.1.350"` in dev dependencies
   - Delete `[tool.mypy]` section (lines 72-76)
   - Delete `[tool.pydantic-mypy]` section (lines 78-81)
   - Keep `[tool.pyright]` section (lines 83-85) - already exists

2. Delete `.mypy_cache/` folder: `rm -rf .mypy_cache`

3. Sync dependencies: `uv sync` or `pip install -e ".[dev]"`

## Todo
- [ ] Replace mypy with pyright in dev deps
- [ ] Delete [tool.mypy] section
- [ ] Delete [tool.pydantic-mypy] section
- [ ] Delete .mypy_cache folder
- [ ] Sync dependencies

## Success Criteria
- [ ] No mypy references in pyproject.toml
- [ ] No .mypy_cache folder
- [ ] pyright installed in dev environment
- [ ] `pyright --version` works

## Next Steps
→ Phase 3: Update docs
