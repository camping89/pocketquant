"""Package layout contract — single `pocketquant` package at repo-root src/.

Target layout: one backend pyproject.toml, subpackages
core / engine / backtest / trading / app / bff, no legacy execution subpackage,
no uv workspace packages left under packages/ (except pocketquant-web).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_engine_subpackage_exists_and_execution_is_gone() -> None:
    legacy = "pocketquant." + "execution"  # split literal: repo-wide renames must not touch this
    assert importlib.util.find_spec("pocketquant.engine") is not None, (
        "pocketquant.engine must be importable (renamed from the legacy execution subpackage)"
    )
    assert importlib.util.find_spec(legacy) is None, (
        "legacy execution subpackage must no longer exist after the engine rename"
    )


def test_all_subpackages_importable_from_single_src_tree() -> None:
    src_root = REPO_ROOT / "src" / "pocketquant"
    for sub in ("core", "engine", "backtest", "trading", "app", "bff"):
        spec = importlib.util.find_spec(f"pocketquant.{sub}")
        assert spec is not None, f"pocketquant.{sub} not importable"
        # Regular packages expose origin (__init__.py); namespace packages (PEP 420)
        # expose only submodule_search_locations.
        locations = [spec.origin] if spec.origin else list(spec.submodule_search_locations or [])
        assert locations and all(str(src_root) in loc for loc in locations), (
            f"pocketquant.{sub} resolves to {locations}, expected under {src_root}"
        )


def test_single_backend_pyproject() -> None:
    pyprojects = [
        p
        for p in REPO_ROOT.rglob("pyproject.toml")
        if ".venv" not in p.parts and "node_modules" not in p.parts
    ]
    assert pyprojects == [REPO_ROOT / "pyproject.toml"], (
        f"Expected exactly one backend pyproject.toml at repo root, found: {pyprojects}"
    )


def test_no_python_packages_dir_remnants() -> None:
    packages_dir = REPO_ROOT / "packages"
    if not packages_dir.exists():
        return
    leftovers = [
        d.name for d in packages_dir.iterdir() if d.is_dir() and d.name != "pocketquant-web"
    ]
    assert leftovers == [], f"Python packages must be merged into src/: {leftovers}"
