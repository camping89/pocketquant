# Drop dependency-injector → Pure Python DI

**Date:** 2026-03-13 | **Branch:** feat/strategy-init | **Status:** Complete
**Goal:** Replace `dependency-injector` with plain Python constructors + FastAPI `Depends()` for consistency, type safety, and simplicity.

## Why

- `dependency-injector` adds complexity (`resolve()` hack, `type: ignore`, Future handling) without proportional value
- We don't use `@inject`, `Provide[]`, or container overrides — just lifecycle + wiring
- Three injection patterns (Depends, app.state, resolve) → confuse contributors
- Plain Python constructors are fully typed, debuggable, greppable

## Phases

| # | Phase | Status | Effort |
|---|-------|--------|--------|
| 1 | Create `Services` registry dataclass | Done | S |
| 2 | Rewrite lifespan with explicit init/shutdown | Done | M |
| 3 | Unify `dependencies.py` with all `Depends()` | Done | S |
| 4 | Rewrite handler registration (explicit constructors) | Done | M |
| 5 | Update `main_extensions.py` (remove container refs) | Done | S |
| 6 | Remove `dependency-injector` from deps + cleanup | Done | S |
| 7 | Update tests + docs | Done | M |

## Key Decisions

- **`Services` dataclass** replaces `AppContainer` — typed fields, IDE autocomplete
- **Middleware hot-path** stays on `app.state.cache` / `app.state.database` — intentional perf optimization, not inconsistency
- **Handler registration** uses explicit constructor list — no string-based `getattr`
- **`app.state.services`** is the single root — all `Depends()` read from it
- **No lazy init** (same as current) — all services init at startup

## Risk

| Risk | Mitigation |
|------|-----------|
| Miss a provider during migration | Pyright catches missing fields on Services dataclass |
| Shutdown order wrong | Explicit reverse order in lifespan, same as current |
| Break middleware hot-path | app.state.cache/database unchanged |

## Files Modified

| File | Action |
|------|--------|
| `src/container.py` | **DELETE** → replaced by `src/services.py` |
| `src/services.py` | **CREATE** → Services dataclass |
| `src/dependencies.py` | **CREATE** → all Depends() functions |
| `src/handler_registration.py` | **CREATE** → explicit handler constructors |
| `src/main.py` | **MODIFY** → rewrite lifespan, remove container |
| `src/main_extensions.py` | **MODIFY** → remove resolve/container refs |
| `src/common/mediator/dependencies.py` | **DELETE** → merged into `src/dependencies.py` |
| `src/features/market_data/quotes/dependencies.py` | **DELETE** → merged into `src/dependencies.py` |
| `pyproject.toml` | **MODIFY** → remove dependency-injector |
| `docs/code-standards.md` | **MODIFY** → update DI section |
| `docs/system-architecture.md` | **MODIFY** → update DI section |
| `docs/codebase-summary.md` | **MODIFY** → update DI section |
