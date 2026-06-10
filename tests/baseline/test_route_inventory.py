"""Route inventory snapshot for the bff app.

Records (methods, path, name) for every route. Coarser than the OpenAPI
snapshot but survives schema-only churn — catches lost/renamed endpoints fast.
Regenerate with BASELINE_UPDATE=1 (just baseline).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

SNAPSHOT_PATH = Path(__file__).parent / "route_inventory_bff_snapshot.json"


def _current_inventory() -> list[dict[str, Any]]:
    from fastapi.routing import APIRoute
    from pocketquant.bff.main import create_app

    inventory: list[dict[str, Any]] = []
    for route in create_app().routes:
        if isinstance(route, APIRoute):
            inventory.append(
                {
                    "methods": sorted(route.methods),
                    "path": route.path,
                    "name": route.name,
                }
            )
    inventory.sort(key=lambda r: (r["path"], ",".join(r["methods"])))
    return inventory


def test_bff_route_inventory_matches_snapshot() -> None:
    current = json.dumps(_current_inventory(), sort_keys=True, indent=2) + "\n"

    if os.environ.get("BASELINE_UPDATE") == "1":
        SNAPSHOT_PATH.write_text(current, encoding="utf-8")

    assert SNAPSHOT_PATH.exists(), (
        "Baseline snapshot missing — the safety net is disarmed. "
        "Regenerate with `just baseline` and commit the file."
    )
    committed = SNAPSHOT_PATH.read_text(encoding="utf-8")
    assert current == committed, (
        "bff route inventory drifted from baseline. If intentional, "
        "regenerate with BASELINE_UPDATE=1 (just baseline) and review the diff."
    )
