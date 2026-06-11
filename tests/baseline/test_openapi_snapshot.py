"""OpenAPI schema snapshot for the app entrypoint.

Canonical JSON (sorted keys) of ``app.openapi()`` compared against the
committed baseline. Regenerate with:

    BASELINE_UPDATE=1 .venv/bin/python -m pytest tests/baseline/test_openapi_snapshot.py
    # or: just baseline
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

SNAPSHOT_PATH = Path(__file__).parent / "openapi_app_snapshot.json"


def _canonical(schema: dict[str, Any]) -> str:
    return json.dumps(schema, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def _current_schema() -> dict[str, Any]:
    from pocketquant.app.main import create_app

    return create_app().openapi()


def test_app_openapi_matches_snapshot() -> None:
    current = _canonical(_current_schema())

    if os.environ.get("BASELINE_UPDATE") == "1":
        SNAPSHOT_PATH.write_text(current, encoding="utf-8")

    assert SNAPSHOT_PATH.exists(), (
        "Baseline snapshot missing — the safety net is disarmed. "
        "Regenerate with `just baseline` and commit the file."
    )
    committed = SNAPSHOT_PATH.read_text(encoding="utf-8")
    assert current == committed, (
        "app OpenAPI schema drifted from baseline snapshot. "
        "If intentional, regenerate with BASELINE_UPDATE=1 (just baseline) "
        "and review the diff."
    )
