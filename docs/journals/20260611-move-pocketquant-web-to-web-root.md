# Relocate pocketquant-web: packages/ → web/

**Date**: 2026-06-11 12:31  
**Severity**: Architecture  
**Component**: Package structure, build config, path routing  
**Status**: Resolved

## What Happened

Post-lean-monorepo-restructure (260610-1726), `packages/` contained exactly one artifact: the npm SPA `pocketquant-web`. The wrapper directory served no purpose — no uv workspace, no sibling packages. User approved brainstorm (3 options debated, `web/` at root chosen) and execution: `git mv packages/pocketquant-web → web`, sweep all references (config, docs, CI/CD), tighten layout contract, verify build + tests.

## The Brutal Truth

The move felt surgical — git history preserved, commits clean, tests passed. But scout missed a LIVE code reference deep in the FastAPI stack, and the layout contract test became vacuous without intentional rework. That stung: we promoted ourselves for a "complete" sweep only to find a path embedded in running code 6 hours after landing. The catch by post-move grep guard felt like cleanup, not discovery. And the layout test that claimed to protect the invariant was a no-op — it passed when packages/ existed OR was absent, carving out pocketquant-web regardless. Both lessons: path moves need source-code grep, not config/docs sweep alone; and contracts that don't break on violation aren't contracts.

## Technical Details

**Reference catches (post-move discovery)**

1. `src/pocketquant/bff/main_extensions.py:134` — Flask static-serving path:
   ```python
   spa_path = parents[3] / "packages" / "pocketquant-web" / "dist"
   ```
   Hardcoded. Found by grep `grep -r "packages.*pocketquant-web" src/`. Corrected to:
   ```python
   spa_path = parents[3] / "web" / "dist"
   ```

2. `test_no_python_packages_dir_remnants` — layout contract became vacuous:
   - Old test: early-return if `packages/` missing; carve-out if `pocketquant-web` exists
   - Result: passed whether packages/ was present, absent, or restructured — not a guard
   - Reworked to `test_no_packages_dir`: asserts `packages/` absent + `web/package.json` present
   - Now breaks if invariant violated

**Config sweep (verified)**
- `justfile`: fe recipe `working-directory` → `web`
- `cicd.yml`: docker build context `./web`
- `.gitignore`: `!web/src/lib/` carve-out preserved

**Bonus legacy fixes**
- `docs/code-standards.md:pyright`: stale `pyright packages/` (obsolete since 260610 package merge)
- `docs/project-overview-pdr.md:3`: stale "5 Python packages in uv workspace" → updated to 1 + subpackages

**Stale not fixed** (left for follow-up)
- `.run/main.py.run.xml`: IDE config references dead `pocketquant-api` (unrelated to this move; broader cleanup task)
- `justfile:11` comment: "workspace packages" wording — stale reference, low priority

**Verification**
- web npm build: green
- backend 555 tests + 9 baseline: passed
- import-linter 10 contracts: all pass
- ruff + pyright: clean

## Root Cause Analysis

Scout phase focused on config + docs + structure, treated code paths as secondary. Path embedding in running code (Flask static routing) fell outside config/docs scope. Lesson: path moves must assume code paths exist; source grep for literal strings (`"packages"`, directory separators in path algebra) is non-optional.

Layout test inherited carve-out logic from prior, heterogeneous refactors. Test design conflated "packages dir is gone" with "pocketquant-web carve-out is acceptable" instead of enforcing a single invariant (packages/ absent). Early return bypassed assertion, creating a false pass.

## Lessons Learned

1. **Path moves: three-layer verification.** Config/docs sweep (layer 1) insufficient. Scout code for embedded paths (layer 2: literal string grep). Build + test (layer 3: integration). Skip layer 2 → miss production bugs.

2. **Layout contracts must be monolithic.** Carve-outs invite logic decay. Replace with tight, single-failure-mode assertions. Old: "packages absent OR pocketquant-web exists" → New: "packages absent AND web present". Guards don't delegate.

3. **Post-move grep guard catches low-hanging fruit, not comprehensive.** It found one reference; we got lucky. Proper fix: pre-move audit of patterns (`Path("packages")`, `parents[N]/"packages"`, import strings) in source tree.

## Next Steps

1. Note for team: path moves require source code audit (grep patterns) before execution. Add to "refactoring checklist" if one exists.
2. Watch for stale IDE configs (`.run/*.xml`) in future cleanups — broader issue, not urgent.
3. Monitor imports after this move (import-linter already running; keep contracts enabled).

---

**Status:** DONE  
**Summary:** Moved npm SPA from `packages/pocketquant-web/` to `web/` at root; discovered FastAPI path reference via post-move grep and tightened layout contract test to prevent regression.
