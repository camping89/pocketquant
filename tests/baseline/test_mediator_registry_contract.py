"""Mediator registration contract — the Phase-4 de-mediator migration checklist.

Reads the ``@handles`` request type off every handler class in the app and bff
DI handler lists (no container build → no Mongo/Redis needed) and snapshots the
request→handler mapping. Asserts the one-handler-per-request-type invariant the
Mediator enforces at runtime.

Regenerate with BASELINE_UPDATE=1 (just baseline).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

SNAPSHOT_PATH = Path(__file__).parent / "mediator_registry_snapshot.json"

_HANDLES_ATTR = "_handles_request_type"


def _registry_for(handler_types: list[type]) -> dict[str, str]:
    """Map request-type qualname → handler-type qualname; assert uniqueness."""
    mapping: dict[str, str] = {}
    for handler_type in handler_types:
        request_type = getattr(handler_type, _HANDLES_ATTR, None)
        assert request_type is not None, f"{handler_type.__name__} lacks @handles decoration"
        key = f"{request_type.__module__}.{request_type.__name__}"
        assert key not in mapping, (
            f"Duplicate handler for {key}: {mapping[key]} and {handler_type.__name__}"
        )
        mapping[key] = f"{handler_type.__module__}.{handler_type.__name__}"
    return mapping


def _current_registry() -> dict[str, dict[str, str]]:
    from pocketquant.app.di.handlers import ALL_HANDLER_TYPES
    from pocketquant.bff.di.handlers import ALL_BFF_HANDLER_TYPES

    return {
        "app": _registry_for(ALL_HANDLER_TYPES),
        "bff": _registry_for(ALL_BFF_HANDLER_TYPES),
    }


def test_mediator_registry_matches_snapshot() -> None:
    current = json.dumps(_current_registry(), sort_keys=True, indent=2) + "\n"

    if os.environ.get("BASELINE_UPDATE") == "1":
        SNAPSHOT_PATH.write_text(current, encoding="utf-8")

    assert SNAPSHOT_PATH.exists(), (
        "Baseline snapshot missing — the safety net is disarmed. "
        "Regenerate with `just baseline` and commit the file."
    )
    committed = SNAPSHOT_PATH.read_text(encoding="utf-8")
    assert current == committed, (
        "Mediator registry drifted from baseline. If intentional, regenerate "
        "with BASELINE_UPDATE=1 (just baseline) and review the diff."
    )


def test_every_handler_has_exactly_one_request_type() -> None:
    registry = _current_registry()
    for process, mapping in registry.items():
        assert mapping, f"{process}: empty handler registry"
        # uniqueness already enforced in _registry_for; recheck handler side
        handlers = list(mapping.values())
        assert len(handlers) == len(set(handlers)), (
            f"{process}: a handler class is registered for multiple request types"
        )
