from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


async def test_health_reports_role_and_no_lease_for_api_only(app_client) -> None:  # noqa: ANN001
    response = await app_client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "api"
    assert body["lease"] == "none"
    assert body["lease_renewed_age_s"] is None
