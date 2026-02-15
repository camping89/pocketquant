# Phase 1: Install dependency-injector + Create Container Skeleton

## Context Links

- [Plan overview](./plan.md)
- [Current main.py](../../src/main.py)
- [Current main_extensions.py](../../src/main_extensions.py)
- [Settings config](../../src/config.py)
- [System Architecture](../../docs/system-architecture.md)

## Overview

- **Priority:** P1 (foundation for all subsequent phases)
- **Status:** pending
- **Effort:** 1h
- **Description:** Install `dependency-injector`, create `src/container.py` with `AppContainer`, register Settings as first Singleton provider, wire container into FastAPI app factory.

## Key Insights

- `dependency-injector` uses declarative `providers.Singleton()`, `providers.Resource()`, `providers.Factory()` pattern
- Container must be created before FastAPI app so lifespan can call `container.init_resources()` / `container.shutdown_resources()`
- Settings already uses `@lru_cache` in `get_settings()` -- Singleton provider wraps this cleanly
- Python 3.14 compatibility must be verified (library uses C extensions)
- Container wiring (`container.wire()`) auto-injects `Provide[]` annotations in modules -- but we'll use explicit `Depends()` in FastAPI routes for clarity

## Requirements

### Functional
- Install `dependency-injector` package
- Create `AppContainer` class with Settings provider
- Wire container into `create_app()` factory
- Existing functionality unchanged (no behavioral changes)

### Non-Functional
- Container file under 200 LOC (will grow in later phases)
- Type hints on all providers
- No circular imports

## Architecture

### Container Structure (Phase 1 only -- grows in later phases)

```python
# src/container.py
from dependency_injector import containers, providers
from src.config import Settings, get_settings

class AppContainer(containers.DeclarativeContainer):
    """Application dependency injection container."""

    wiring_config = containers.WiringConfiguration(
        modules=[]  # populated in later phases
    )

    # Configuration
    config = providers.Configuration()

    # Settings (singleton, immutable config)
    settings = providers.Singleton(get_settings)
```

### App Factory Integration

```python
# src/main.py (modified)
from src.container import AppContainer

def create_app() -> FastAPI:
    container = AppContainer()
    settings = container.settings()

    setup_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        ...
        lifespan=lifespan,
    )

    # Store container on app for lifespan access
    app.state.container = container

    configure_middleware(app, settings)
    register_routes(app, settings)

    return app
```

## Related Code Files

| File | Action | Notes |
|------|--------|-------|
| `pyproject.toml` | modify | Add `dependency-injector` to dependencies |
| `src/container.py` | **create** | AppContainer with Settings provider |
| `src/main.py` | modify | Create container in `create_app()`, pass to lifespan |
| `src/config.py` | no change | `get_settings()` stays as-is, wrapped by Singleton provider |

## Implementation Steps

<!-- Red Team: Python 3.14 compatibility is plan blocker — 2026-02-15 -->
0. **PRE-PHASE SPIKE (BLOCKING)**: Verify `dependency-injector` builds on Python 3.14 BEFORE any implementation:
   - `uv pip install dependency-injector` in clean venv
   - If C extension fails: check GitHub issues, try `--no-binary :all:`
   - If incompatible: STOP — plan must be redesigned for alternative library (APIs differ fundamentally)
   - Document result in plan before proceeding

1. **Verify compatibility**: Run `uv pip install dependency-injector` in venv, check it installs on Python 3.14
   - If C extension fails, try `dependency-injector --no-binary :all:` or check for pre-built wheel
   - Fallback: use pure-Python mode if available

2. **Add to pyproject.toml**: Add `"dependency-injector>=4.41.0"` to `dependencies` list

3. **Create `src/container.py`**:
   ```python
   """Application dependency injection container."""

   from dependency_injector import containers, providers

   from src.config import get_settings


   class AppContainer(containers.DeclarativeContainer):
       """IoC container for the PocketQuant application.

       All application services registered here.
       Lifecycle: Singleton (app-lifetime), Resource (async init/shutdown),
       Factory (new instance per resolution).
       """

       # Settings (singleton, immutable config from .env)
       settings = providers.Singleton(get_settings)
   ```

4. **Modify `src/main.py`**:
   - Import `AppContainer`
   - In `create_app()`, instantiate container
   - Store `app.state.container = container`
   - Use `container.settings()` instead of `get_settings()` in lifespan
   - Keep all existing lifespan/shutdown logic unchanged for now

5. **Run smoke test**: `python -c "from src.container import AppContainer; c = AppContainer(); print(c.settings())"` -- should print Settings object

6. **Run existing tests**: Ensure nothing breaks

## Todo List

- [ ] Install `dependency-injector` and verify Python 3.14 compat
- [ ] Add to `pyproject.toml` dependencies
- [ ] Create `src/container.py` with AppContainer + Settings provider
- [ ] Modify `src/main.py` to instantiate container in `create_app()`
- [ ] Store container on `app.state.container`
- [ ] Run smoke test
- [ ] Run `ruff check src/container.py`
- [ ] Run `pyright src/container.py`
- [ ] Run existing test suite

## Success Criteria

- `dependency-injector` installed and importable
- `AppContainer` instantiates without errors
- `container.settings()` returns same Settings object as `get_settings()`
- All existing tests pass unchanged
- No import errors or circular dependencies

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Python 3.14 incompatibility | Blocker | Check issues/PyPI; fallback to `python-inject` or `lagom` |
| C extension build failure on Windows | High | Use `--no-binary` or pure-Python mode |
| Circular import with config.py | Low | config.py has no local imports, safe |

## Next Steps

- Phase 2: Convert Database/Cache/Repositories to instance-based DI
- Container grows to include persistence providers
