# Brainstorm Report: Type Checker Decision (Mypy vs Pyright)

**Date:** 2026-02-01
**Decision:** Migrate to Pyright-only setup

---

## Problem Statement

Project had both mypy and pyright configured with conflicting settings:
- mypy: `strict = true`, Pydantic plugin, entire project
- pyright: `basic` mode, `src/` only, no dependencies

Neither enforced in CI/CD. Dual config caused confusion.

---

## Evaluated Approaches

### Option A: Pyright Only ✅ SELECTED
**Pros:**
- 3-5x faster than mypy (critical for CI)
- Native VSCode/Cursor integration via Pylance
- Pydantic v2 has built-in pyright support
- Single tool = simpler maintenance
- Better type inference for complex patterns

**Cons:**
- Loses mypy's `init_forbid_extra` enforcement
- No mypy plugin ecosystem access

### Option B: Both (Pylance + Mypy CI)
**Pros:** Best-of-both-worlds coverage
**Cons:** Dual config maintenance, potential inconsistencies

### Option C: Mypy Only
**Pros:** Pydantic plugin extras, mature ecosystem
**Cons:** Slower CI, less smooth VSCode experience

---

## Final Recommendation

**Migrate to Pyright strict mode as single type checker.**

### Implementation Steps

1. **Update pyrightconfig.json**
   ```json
   {
     "include": ["src", "tests"],
     "pythonVersion": "3.14",
     "typeCheckingMode": "strict",
     "reportMissingImports": "warning"
   }
   ```

2. **Remove mypy config** from `pyproject.toml`
   - Delete `[tool.mypy]` section
   - Delete `[tool.pydantic-mypy]` section

3. **Update dependencies**
   - Remove `mypy>=1.8.0` from dev deps
   - Add `pyright>=1.1.350` to dev deps

4. **Add CI/CD enforcement**
   - Create GitHub Actions workflow with `pyright src/`
   - Add to pre-commit config

5. **Update documentation**
   - Update `code-standards.md` to reference pyright
   - Update README type checking commands

6. **Add pre-commit hook**
   ```yaml
   - repo: https://github.com/RobertCraiworthy/pyright-python
     rev: v1.1.350
     hooks:
       - id: pyright
   ```

---

## Success Criteria

- [ ] All code passes `pyright --typeCheckingMode=strict`
- [ ] CI/CD blocks merges on type errors
- [ ] Pre-commit hook prevents local commits with type errors
- [ ] Single type checker config (no mypy)

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Pyright stricter than mypy basic | Run pyright first, fix errors incrementally |
| Missing mypy plugin features | Pydantic v2 native support covers most cases |
| Team unfamiliar with pyright | Same experience via Pylance already |

---

## Security Considerations

None. Type checking is development-time only.

---

## Sources

- [Python Type Checking Survey 2024 - Meta Engineering](https://engineering.fb.com/2024/12/09/developer-tools/typed-python-2024-survey-meta/)
- [Pyright vs Mypy Comparison - Microsoft](https://github.com/microsoft/pyright/blob/main/docs/mypy-comparison.md)
- [Mypy vs Pyright Performance - Medium](https://medium.com/@asma.shaikh_19478/python-type-checking-mypy-vs-pyright-performance-battle-fce38c8cb874)
- [Python.org Discussion](https://discuss.python.org/t/mypy-vs-pyright-in-practice/75984)
