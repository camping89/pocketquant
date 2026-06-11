"""Package layout contract — single `pocketquant` package at repo-root src/.

Target layout: one backend pyproject.toml, subpackages
core / engine / backtest / app, no legacy execution subpackage,
no packages/ dir (the npm SPA lives at repo-root web/).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

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
    for sub in ("core", "engine", "backtest", "app"):
        spec = importlib.util.find_spec(f"pocketquant.{sub}")
        assert spec is not None, f"pocketquant.{sub} not importable"
        # Regular packages expose origin (__init__.py); namespace packages (PEP 420)
        # expose only submodule_search_locations.
        locations = [spec.origin] if spec.origin else list(spec.submodule_search_locations or [])
        assert locations and all(str(src_root) in loc for loc in locations), (
            f"pocketquant.{sub} resolves to {locations}, expected under {src_root}"
        )


@pytest.mark.xfail(reason="4-subpackage end-state lands at phase 3", strict=True)
def test_dissolved_subpackages_are_gone() -> None:
    assert importlib.util.find_spec("pocketquant.trading") is None, (
        "pocketquant.trading must be dissolved into engine/core"
    )
    assert importlib.util.find_spec("pocketquant.bff") is None, (
        "pocketquant.bff must be merged into app"
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


def test_no_packages_dir() -> None:
    packages_dir = REPO_ROOT / "packages"
    assert not packages_dir.exists(), (
        "packages/ must not exist: backend lives in src/pocketquant, the npm SPA in web/"
    )
    assert (REPO_ROOT / "web" / "package.json").is_file(), (
        "npm SPA expected at repo-root web/"
    )


def test_no_dishka_fastapi_integration_outside_app_bff() -> None:
    """import-linter can't forbid external subpackages, so the fastapi-containment
    contract misses `dishka.integrations.fastapi` — this grep closes that hole."""
    src_root = REPO_ROOT / "src" / "pocketquant"
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for sub in ("core", "engine", "backtest")
        for path in (src_root / sub).rglob("*.py")
        if "dishka.integrations.fastapi" in path.read_text()
    ]
    assert offenders == [], f"dishka.integrations.fastapi only allowed in app/bff: {offenders}"
