"""Pytest configuration for baseline regression tests.

Prod-DB guard and general env seeding live in the root ``tests/conftest.py``.
This conftest only pins the schema-affecting vars.
"""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    import os

    # Schema-affecting vars must be FORCED, not defaulted: app_version flows into
    # FastAPI(version=...) → openapi()["info"]["version"]. A direnv/.env shell
    # exporting APP_VERSION would otherwise produce spurious snapshot drift.
    os.environ["APP_NAME"] = "pocketquant-test"
    os.environ["APP_VERSION"] = "0.0.0"
