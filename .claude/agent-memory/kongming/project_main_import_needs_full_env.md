---
name: main-import-needs-full-env
description: Importing pocketquant.app.main runs create_app() -> get_settings() at import; no .env exists locally or in CI, so a test that imports main must set the required env first
metadata:
  type: project
---

`src/pocketquant/app/main.py` builds the app at import time (`app = create_app()`), which calls `get_settings()`. There is no `.env` at the repo root locally (checked 2026-10-29) and the CI test job writes none, so any test module that imports `pocketquant.app.main` at top level fails collection with a Settings ValidationError. As of 2026-10-29 no test imports it; the Phase 07 lifespan handover test (plan 261028-0652) is the first that will.

**Why:** found while reviewing Phase 07; the plan text imports `main` directly.
**How to apply:** tests that need `main.lifespan` must `monkeypatch.setenv` the required Settings keys (or copy them from the `settings` fixture) and import `pocketquant.app.main` inside the test, then patch `main.get_settings`.
