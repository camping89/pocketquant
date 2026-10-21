"""X-Admin-Token guard on the ``api`` router.

Every mutation route under the API prefix carries the guard; safe methods never
need the token; production without a token fails closed with 503.
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient
from pydantic import SecretStr

from pocketquant.app.middleware import admin_auth_middleware
from pocketquant.app.middleware.admin_auth_middleware import verify_admin_token
from pocketquant.core.config import Settings

from .app_factory import make_test_app

_MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_TOKEN = "test-admin-token"


def _guard_settings(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, **update: object
) -> None:
    patched = settings.model_copy(update=update)
    monkeypatch.setattr(admin_auth_middleware, "get_settings", lambda: patched)


def _create_sub_path(settings: Settings) -> str:
    # Empty body → 422 once past the guard; never touches a broker.
    return f"{settings.api_prefix}/strategies/engulfing/subscriptions"


def _list_subs_path(settings: Settings) -> str:
    return f"{settings.api_prefix}/subscriptions/"


def test_every_mutation_route_carries_the_guard(settings: Settings) -> None:
    app = make_test_app(settings)
    routes = [
        r
        for r in app.routes
        if isinstance(r, APIRoute)
        and r.path.startswith(settings.api_prefix)
        and r.methods & _MUTATION_METHODS
    ]
    for route in routes:
        calls = [d.call for d in route.dependant.dependencies]
        assert verify_admin_token in calls, f"{route.methods} {route.path} is unguarded"
    assert len(routes) == 19


@pytest.mark.asyncio
async def test_token_set_rejects_missing_or_wrong_header_and_accepts_right_one(
    app_client: AsyncClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _guard_settings(monkeypatch, settings, admin_token=SecretStr(_TOKEN))
    path = _create_sub_path(settings)

    assert (await app_client.post(path, json={})).status_code == 401
    wrong = await app_client.post(path, json={}, headers={"X-Admin-Token": "wrong"})
    assert wrong.status_code == 401
    right = await app_client.post(path, json={}, headers={"X-Admin-Token": _TOKEN})
    assert right.status_code != 401
    assert (await app_client.get(_list_subs_path(settings))).status_code == 200


@pytest.mark.asyncio
async def test_production_without_token_fails_closed_on_mutations_only(
    app_client: AsyncClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _guard_settings(monkeypatch, settings, admin_token=None, environment="production")

    assert (await app_client.post(_create_sub_path(settings), json={})).status_code == 503
    assert (await app_client.get(_list_subs_path(settings))).status_code == 200


@pytest.mark.asyncio
async def test_development_without_token_lets_mutations_through(
    app_client: AsyncClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _guard_settings(monkeypatch, settings, admin_token=None, environment="development")

    resp = await app_client.post(_create_sub_path(settings), json={})
    assert resp.status_code not in (401, 503)
