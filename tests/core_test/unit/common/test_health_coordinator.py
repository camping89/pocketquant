"""A degraded dependency is reported, but never fails the whole instance."""

from __future__ import annotations

import pytest

from pocketquant.core.common.health import HealthCoordinator


async def _ok() -> dict:
    return {}


async def _degraded() -> dict:
    return {"status": "degraded"}


async def _broken() -> dict:
    raise RuntimeError("down")


@pytest.mark.asyncio
async def test_degraded_dependency_keeps_overall_healthy() -> None:
    hc = HealthCoordinator()
    hc.register("database", _ok)
    hc.register("market_data_providers", _degraded)

    result = await hc.check_all()

    assert result["status"] == "healthy"
    assert result["dependencies"]["market_data_providers"]["status"] == "degraded"


@pytest.mark.asyncio
async def test_failing_dependency_makes_overall_unhealthy() -> None:
    hc = HealthCoordinator()
    hc.register("database", _broken)
    hc.register("market_data_providers", _degraded)

    result = await hc.check_all()

    assert result["status"] == "unhealthy"
