# Lean Monorepo — Phase 5 Execution: FastAPI Containment + Docs Sync

**Date**: 2026-06-11  
**Severity**: Completion  
**Component**: Core module, app/bff, exceptions handler, import enforcement, documentation  
**Status**: DONE

## Session Scope

Phase 5 (final) của plan 260610-1726-lean-monorepo-restructure. Tất cả 5 phases done. Commit 65a056a.

| Thành phần | Kết quả |
|-----------|---------|
| FastAPI isolation | import-linter contract "fastapi only in app/bff" passed after rewrite exceptions.py |
| Boot resilience | Config bug (pyproject marker) fixed; .env loading healed for off-repo cwd |
| Import enforcement | 10/10 contracts passing; grep guard test added for integration imports |
| Tests | 555 passed / 5 skipped; pyright 0 errors; ruff clean |
| E2E gates | OpenAPI snapshot unchanged; app+bff boot OK; Mongo+Redis sync/backtest/subscription e2e smoke passed |
| Docs sweep | handler-pipelines.md deleted; new service-and-route-conventions.md added; 6 stale mediator/package refs swept |

## Technical Details

**TDD entry (red → green):**  
1. Import-linter contract `[fastapi only in app.bff]` — red on `core/common/exceptions.py` (only straggler)
2. exceptions.py rewrite: `register_exception_handlers(app, *, validation_error_cls)` — starlette-only. FastAPI's RequestValidationError injected by app/bff main_extensions module (dependency inversion).
3. Code reviewer verified: FastAPI decorator `@app.exception_handler()` literally delegates to `app.add_exception_handler()` (Starlette native); JSONResponse is Starlette re-export. Behavior byte-identical, E2E smoke on 422 VALIDATION_ERROR body unchanged.

**Boot bug from Phase 2 — latent until this session:**  
- Root cause: `config.py::_find_project_root()` searched pyproject for `[tool.uv.workspace]` marker. Phase 2 package-merge deleted this section; marker never found.
- Result: `.env` silently ignored when `cwd != repo_root` (e.g., test runner from different dir).
- Fix: matched string to current name = "pocketquant" entry → .env loads.
- **Lesson**: grep for string-literal config marker refs, not just import statements. Stale markers hide in function bodies.

**Import-linter limitation (grimp-level):**  
- Goal: forbid external subpackage `dishka.integrations.fastapi` in core/engine/backtest/trading.
- Reality: grimp squashes externals to root module → `[forbid fastapi]` does NOT transitively catch integration subpackages.
- Workaround: grep test in `tests/baseline/test_package_layout_contract.py` — whitelist exceptions, fail if new fastapi imports appear.
- **Lesson**: import-linter ≠ perfect; external subpackages slip through grimp. Guard test is essential.

**Carry-overs from Phase 2 (all resolved):**  
- pyrightconfig extended: all test dirs included (~125 pre-existing type errors fixed mechanically)
  - Fixture Generator annotations
  - None guards on potential-None returns
  - dict[str, Any] splat builders
  - Narrow pyright-ignores on duck-typed fakes (conftest builders)
- Deleted `tests/app_test/integration/test_realtime_pipeline.py` (100% skipped; signature changed in Phase 2)
- Added `bff.spa_not_mounted` log at entrypoint (debugging hint if routes absent)
- Fixed stale backtest_jobs comment (→ execution-queue)
- Prefixed justfile cmds: `lint/fmt/types` now `uv run` wrapped

**Docs sweep:**  
- Deleted: `docs/handler-pipelines.md` (984 lines, mediator-era narrative)
- Added: `docs/service-and-route-conventions.md` (recipe: route → service → repository; VN prose)
- Swept 6 stale refs: README, CLAUDE.md, system-architecture, architecture-visual-map, code-standards, PDR, websocket-architecture, feature docs
- Fixed broken links; verified Mermaid/ASCII render

## Code Review Notes

**Status: DONE_WITH_CONCERNS**  
- False transitivity comment in exceptions.py (fixed + guard test now prevents regression)
- 4 residual stale docs refs in code comments (swept in final pass)
- Prod image still pinned to known hash (user decision; deferred)
- Single deploy event now unblocked

## Emotional Reality

Clean finish. No surprises at gates — the "latent .env bug" actually felt like a win: caught before production, one-liner fix, added confidence in config loading. Import-linter limitation was expected and grimp isn't dumb; grep guard is pragmatic.

Code review came back tight (2 fixable findings + context clarification). No shame in 2 false positives over 555 passing tests + 125 type-fixed tests. The FastAPI isolation felt genuinely cleaner; exceptions.py now reads as pure Starlette concern that app/bff can inject into. That's the architecture working.

No exhaustion. This was methodical, not rushed.

## Validation Gates Passed

- ✅ 555 tests passed / 5 skipped (unchanged)
- ✅ pyright 0 errors whole repo
- ✅ ruff clean
- ✅ 10/10 import-linter contracts
- ✅ OpenAPI snapshot unchanged
- ✅ app + bff import bootstrap OK (stale imports healed)
- ✅ E2E manual vs real Mongo/Redis: /health, sync, backtest enqueue→worker→done, subscription CRUD + reconcile convergence

## Lessons

1. **Config marker refs hide in function bodies, not just imports.** String-literal searches for deleted markers catch residual config state bugs before runtime.
2. **grimp ≠ perfect for external subpackages.** Flattens hierarchy; transitive bans don't flow to integrations. Guard tests fill the gap.
3. **Stale comments in code >> docs for accumulating drift.** Phase 2 sweep didn't catch backtest_jobs comment because it wasn't a broken import. Docs are ephemeral; code comments linger.
4. **False transitivity findings are data, not shame.** 2 false positives over 555 tests = healthy scrutiny. Guard test prevents regression.

## Next Steps

- Prod image unpin (user decision confirmed; operator's deploy event)
- Monitor backtest job state after deploy (reconcile loop under load)
- Phase 6 brainstorm (if any): module perf, async patterns, caching strategy

---

**Status:** DONE  
**Summary:** Phase 5 completed; 5-phase plan delivered. FastAPI isolated to app/bff via starlette rewrite. Boot .env bug fixed. Docs swept. All 555 tests pass; pyright clean; 10/10 import contracts holding. E2E gates green.
