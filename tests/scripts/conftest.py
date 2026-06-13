"""Conftest for scripts tests — ensures the workspace root is on sys.path.

The `scripts/` package lives at the workspace root and is NOT installed
as a Python package. This conftest inserts the workspace root into sys.path
before pytest collects test modules in this directory, enabling imports like:

    from scripts.audit_bar_quality import ...
"""

from __future__ import annotations

import sys
from pathlib import Path

# tests/scripts/conftest.py → tests/ → workspace root
_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]

if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

# If pytest already cached 'scripts' pointing to this test directory (tests/scripts/),
# evict that stale entry so the real scripts/ package at workspace root takes over.
if (
    "scripts" in sys.modules
    and sys.modules["scripts"].__file__
    and "tests" in sys.modules["scripts"].__file__
):
    del sys.modules["scripts"]
