# Code Review: Post-Migration Monorepo Cleanup

**Date:** 2026-03-21 | **Branch:** `feat/strategy-init` | **Reviewer:** code-reviewer

## Scope

- **Files changed:** ~164 (diff vs HEAD~1)
- **Net delta:** +448 / -3502 lines (mostly plan deletions + ruff fixes)
- **Focus areas:** Dockerfile, justfile, configs, stale path references, DI wiring, ruff/lint cleanup
- **Validation:** ruff check 0 issues, pyright 4 errors (2 pre-existing in unchanged file)

## Overall Assessment

Solid cleanup. Dockerfile rewrite is correct for monorepo layout, justfile covers all common dev workflows, configs point to the right monorepo paths, and the ruff sweep is thorough. A handful of stale references survive in secondary files (manual test scripts, docs, DI docstrings, startup error panel). None are blocking for runtime correctness.

---

## Critical Issues

None.

---

## High Priority

### H1. `tests/manual/run_stream_quotes.py` — broken import (line 18)

```python
from src.infrastructure.tradingview.tradingview_websocket_client import TradingViewWebSocketClient
```

Old monolith import. Should be:

```python
from pocketquant.core.infrastructure.tradingview.tradingview_websocket_client import TradingViewWebSocketClient
```

Script also has stale docstring paths (`testscripts/run_stream_quotes.py`) on lines 8-10. Not blocking CI, but the file will crash on import.

### H2. `tests/manual/api-test.http` — wrong port throughout

All 50+ URLs reference `localhost:8765` (old port). Should be `localhost:41920`. File is purely manual, but copy-pasting any request will 404.

Also line 15 has stale reference: `uvicorn src.main:app --reload`.

### H3. `main_extensions.py` — startup failure panel shows old paths (lines 101-102)

```python
console.print("  -> [cyan]src/main.py[/] in lifespan")
console.print("  -> [cyan]src/common/database/connection.py[/] in connect")
```

Should reference the new monorepo paths:
```python
console.print("  -> [cyan]pocketquant.api.main[/] in lifespan")
console.print("  -> [cyan]pocketquant.core.persistence.mongodb[/] in connect")
```

These are user-facing error messages during startup failures. Incorrect paths will mislead debugging.

---

## Medium Priority

### M1. `handlers.py` — stale docstring references to `src/container.py`

Lines 4 and 80:
```
with Mediator in src/container.py:register_handlers().
# All handler types — used by register_handlers() in src/container.py
```

Should reference `pocketquant.api.di.container` instead.

### M2. `docs/` still contain many `src.` references

Searched `src.main`, `src.config`, `src.common`, `from src.` across docs/:

| File | Stale refs |
|------|-----------|
| `docs/code-standards.md` | 10+ `from src.` import examples |
| `docs/codebase-summary.md` | `from src.domain.bar.entities`, `python -m src.main`, etc. |
| `docs/deployment-guide.md` | `uvicorn src.main:app`, port 8765 |
| `docs/project-overview-pdr.md` | `uvicorn src.main:app --reload`, `python -m src.main` |

These are documentation, not runtime code, so not blocking -- but any developer reading the docs will get wrong import paths and wrong ports.

### M3. Dockerfile uses `python:3.14-rc-slim`

The `-rc` (release candidate) tag is volatile. When Python 3.14 reaches GA, the `3.14-rc-slim` tag will stop getting updates. Consider using `python:3.14-slim` once GA lands, or pin to a specific version (e.g., `python:3.14.0a6-slim`).

### M4. Dockerfile does not copy `uv.lock` explicitly

Line 17 copies `pyproject.toml uv.lock README.md` -- this is correct and working since `uv.lock` exists. However, note that `uv sync --frozen` will fail hard if the lockfile is missing or stale, which is actually desirable behavior for CI reproducibility. No action needed, just documenting.

### M5. Dockerfile layer invalidation could be optimized

Lines 20-23 copy individual `pyproject.toml` files, then line 26 copies all of `packages/`. Since `COPY packages/ packages/` on line 26 invalidates whenever ANY source file changes, the pyproject.toml caching on lines 20-23 is partially effective -- it only helps if the dependency resolution step is separated from `uv sync`. Currently `uv sync` on line 29 runs after the full source copy, so the layer cache for dependency resolution is not leveraged.

**Suggestion:** Split into two steps:
```dockerfile
# Step 1: resolve deps (cached unless pyproject.toml/lockfile changes)
RUN uv sync --frozen --no-dev --no-install-workspace

# Step 2: copy source + install workspace packages
COPY packages/ packages/
RUN uv sync --frozen --no-dev
```

This gives a meaningful Docker cache hit for dependency downloads when only source code changes.

---

## Low Priority

### L1. `.vscode/settings.json` — Windows-only `defaultInterpreterPath`

```json
"python.defaultInterpreterPath": "${workspaceFolder}/.venv/Scripts/python.exe"
```

Uses `Scripts/python.exe` (Windows). If anyone develops on Linux/Mac, they'd need `bin/python`. VS Code typically auto-detects the venv, so this is a minor portability note.

### L2. `justfile` `dev` recipe lacks `--log-level info`

The `dev` recipe on line 56 runs bare `uvicorn pocketquant.api.main:app --reload`. Consider adding `--log-level info` for consistency, though structlog handles most logging anyway.

### L3. Docker `HEALTHCHECK` and `CMD` use same port (41920)

Correctly consistent. No issue, just confirming alignment between Dockerfile, compose.prod.yml, and deploy.yml.

---

## Edge Cases Found by Scout

1. **`tests/manual/run_stream_quotes.py`** will crash on import due to stale `from src.infrastructure...` import (H1 above)
2. **All 50+ URLs in `api-test.http`** point to port 8765 instead of 41920 (H2 above)
3. **`docs/deployment-guide.md`** references port 8765 and `src.main:app` -- stale after migration
4. **`handlers.py` docstrings** reference `src/container.py` -- misleading for future developers
5. **`handle_startup_failure`** error panel shows paths that no longer exist
6. **Pre-existing pyright errors** in `historical_replay_app_service.py:74,94` -- `datetime | None` passed where `datetime` expected (not introduced by this change)

---

## Positive Observations

- **Dockerfile** is well-structured: multi-stage, non-root user, health check, minimal runtime image
- **justfile** is clean and covers the full dev workflow (install, up/down, test, lint, types, QA)
- **pyrightconfig.json** correctly includes all 4 package src + test directories with appropriate `reportPrivateUsage: none` for tests
- **`pyproject.toml`** ruff config is properly split into `[tool.ruff]` and `[tool.ruff.lint]` sections
- **`import-linter` contracts** enforce dependency boundaries (core <- backtest/trading <- api)
- **`run()` entrypoint** in `main.py` is clean, lazy-imports uvicorn, and is correctly wired via `[project.scripts]`
- **`check_env.py`** import fixed from `src.config` to `pocketquant.core.config` -- correct
- **Trading repos** properly moved to `pocketquant-trading/persistence/` with clean `__init__.py`
- **Core repos `__init__.py`** correctly exports only core-owned repos (Bar, Symbol, SyncStatus)
- **Ruff** is fully clean (0 issues); 133 auto-fixed + 8 manual fixes is a good cleanup

---

## Recommended Actions

1. **[High]** Fix import in `tests/manual/run_stream_quotes.py` and update docstring paths
2. **[High]** Fix port 8765 -> 41920 in `tests/manual/api-test.http` and remove stale `src.main` reference
3. **[High]** Fix stale paths in `main_extensions.py:handle_startup_failure()` error panel
4. **[Medium]** Fix `handlers.py` docstring references from `src/container.py` to actual module path
5. **[Medium]** Update `docs/` files to use monorepo import paths and correct port (batch update in follow-up)
6. **[Medium]** Plan Dockerfile base image migration from `3.14-rc-slim` when Python 3.14 goes GA
7. **[Low]** Consider Dockerfile layer optimization (split `uv sync` into dep-resolve + workspace-install)

---

## Metrics

| Metric | Value |
|--------|-------|
| Ruff issues | 0 |
| Pyright errors | 4 (2 pre-existing, not introduced) |
| Stale `src.` refs in code | 3 files (H1, H3, M1) |
| Stale `src.` refs in docs | 4 files (M2) |
| Port mismatches | 1 file: `api-test.http` (H2) |

---

## Unresolved Questions

1. Should `tests/manual/api-test.http` be converted to Bruno `.bru` format (matching `tests/http/`) or kept as a curl cheatsheet?
2. Strategy YAML path resolution uses CWD-relative (noted in `migration-doubts-and-notes.md`) -- does the Docker CMD (which sets WORKDIR `/app`) handle this correctly, or will strategies fail to load in container?
3. The `3.14-rc-slim` Docker base is appropriate for now, but when does the team plan to track GA?

---

**Status:** DONE
**Summary:** Cleanup is solid. 3 high-priority stale references in executable code/messages, 4 medium-priority doc updates. No blocking runtime issues for the main application path.
**Concerns:** Manual test scripts and startup error panel still reference old `src/` paths and port 8765.
