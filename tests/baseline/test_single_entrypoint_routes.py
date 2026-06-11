"""Single-entrypoint contract: pocketquant.app.main serves every API route.

The app process is the only backend entrypoint — its route inventory must
equal the committed inventory snapshot verbatim (/health included, nothing
added, nothing lost).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SNAPSHOT_DIR = Path(__file__).parent


def _inventory_of(app) -> list[dict[str, Any]]:
    from fastapi.routing import APIRoute

    inventory: list[dict[str, Any]] = []
    for route in app.routes:
        if isinstance(route, APIRoute) and route.include_in_schema:
            inventory.append(
                {
                    "methods": sorted(route.methods),
                    "path": route.path,
                    "name": route.name,
                }
            )
    inventory.sort(key=lambda r: (r["path"], ",".join(r["methods"])))
    return inventory


def test_single_entrypoint_serves_all_routes() -> None:
    from pocketquant.app.main import create_app

    snapshot_path = SNAPSHOT_DIR / "route_inventory_app_snapshot.json"
    committed = json.loads(snapshot_path.read_text(encoding="utf-8"))
    current = _inventory_of(create_app())
    assert current == committed, (
        "app entrypoint route inventory must equal the committed snapshot verbatim"
    )
