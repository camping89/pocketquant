"""Core package layout contract: domain / infra / common.

Domain models and services live under core.domain, concrete adapters under
core.infra, cross-cutting utilities under core.common. Old flat adapter dirs
and the concepts/ split must not resurrect.
"""

import importlib
import os

import pytest

# Every subpackage that must exist in the new layout.
NEW_MODULES = [
    # ex-concepts merged into domain
    "pocketquant.core.domain.quote",
    "pocketquant.core.domain.risk",
    "pocketquant.core.domain.strategy",
    "pocketquant.core.domain.strategy.services.hitnrun2_strategy_service",
    # adapters gathered under infra
    "pocketquant.core.infra.brokers.paper",
    "pocketquant.core.infra.binance",
    "pocketquant.core.infra.persistence",
    "pocketquant.core.infra.persistence.repositories",
    "pocketquant.core.infra.scheduling",
    "pocketquant.core.infra.http_client",
    # untouched
    "pocketquant.core.common",
    "pocketquant.core.domain",
]

# Old paths that must be gone.
DEAD_MODULES = [
    "pocketquant.core.concepts",
    "pocketquant.core.brokers",
    "pocketquant.core.market_data",
    "pocketquant.core.persistence",
    "pocketquant.core.scheduling",
    "pocketquant.core.http_client",
]


@pytest.mark.parametrize("module", NEW_MODULES)
def test_new_layout_module_imports(module: str):
    importlib.import_module(module)


@pytest.mark.parametrize("module", DEAD_MODULES)
def test_old_layout_module_gone(module: str):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module)


def test_no_stale_references_to_old_paths():
    """No source/test file may reference the retired module paths (incl. string literals)."""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    old_fragments = [
        f"core.{name}"
        for name in (
            "concepts",
            "brokers",
            "market_data",
            "persistence",
            "scheduling",
            "http_client",
        )
    ]
    offenders = []
    for top in ("src", "tests", "scripts"):
        for root, dirs, files in os.walk(os.path.join(repo_root, top)):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for file in files:
                if not file.endswith(".py") or file == os.path.basename(__file__):
                    continue
                path = os.path.join(root, file)
                with open(path) as f:
                    content = f.read()
                for fragment in old_fragments:
                    if fragment in content:
                        offenders.append(f"{path}: {fragment}")
    assert not offenders, "Stale old-layout references:\n" + "\n".join(offenders)
