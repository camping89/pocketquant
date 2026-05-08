"""Root conftest for tests/ directory.

Inserts the workspace root into sys.path so that the `scripts` package
(scripts/audit_bar_quality.py, scripts/backfill_1m_from_binance.py, etc.)
is importable as `scripts.<module>` in tests.

pytest's pythonpath=["."] in pyproject.toml is supposed to handle this,
but requires the path insertion to happen before package collection when
running from outside the workspace root. This conftest guarantees it.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Workspace root = parent of this file's directory (tests/)
_WORKSPACE_ROOT = Path(__file__).resolve().parent.parent

if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))
