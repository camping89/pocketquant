"""Smoke test: the single backend entrypoint imports and constructs a FastAPI app.

No server start, no lifespan execution — only module import + app factory.
Proves the DI wiring and route registration survive structural refactors.
"""

from __future__ import annotations

from fastapi import FastAPI


def test_app_main_imports_and_builds_app() -> None:
    from pocketquant.app.main import app, create_app

    assert isinstance(app, FastAPI)
    rebuilt = create_app()
    assert isinstance(rebuilt, FastAPI)
    assert len(rebuilt.routes) > 0
