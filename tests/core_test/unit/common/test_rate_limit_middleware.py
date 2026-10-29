"""The rate limiter caps each client, including the public safeguards read.

It never limits the pause and resume writes.
"""

from __future__ import annotations

from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from pocketquant.core.common.rate_limit import RateLimitMiddleware


class _DictCache:
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def get(self, key: str) -> Any:
        return self._data.get(key)

    async def set(self, key: str, value: Any, ttl: int) -> None:
        self._data[key] = value


async def _ok(_: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


def _client() -> TestClient:
    app = Starlette(
        routes=[
            Route("/api/v1/x", _ok),
            Route("/api/v1/admin/safeguards", _ok, methods=["GET"]),
            Route("/api/v1/admin/safeguards/pause", _ok, methods=["POST"]),
        ]
    )
    app.add_middleware(RateLimitMiddleware, capacity=1)
    app.state.cache = _DictCache()
    return TestClient(app)


def test_a_client_over_its_bucket_gets_429() -> None:
    client = _client()

    assert client.get("/api/v1/x").status_code == 200
    assert client.get("/api/v1/x").status_code == 429


def test_pause_is_never_rate_limited() -> None:
    client = _client()

    codes = [client.post("/api/v1/admin/safeguards/pause").status_code for _ in range(3)]

    assert codes == [200, 200, 200]


def test_a_safeguards_read_flood_gets_429() -> None:
    client = _client()

    codes = [client.get("/api/v1/admin/safeguards").status_code for _ in range(2)]

    assert codes == [200, 429]
