from __future__ import annotations

import asyncio
import logging

import pytest
from starlette.requests import Request
from starlette.responses import StreamingResponse

from pocketquant.app.middleware.request_logging_middleware import RequestLoggingMiddleware


def _request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 1234),
        }
    )


# Any SSE route, not only the bars stream: the quote stream was once held back.
@pytest.mark.asyncio
async def test_an_endless_event_stream_is_returned_without_reading_it() -> None:
    chunks_read = 0

    async def endless():
        nonlocal chunks_read
        chunks_read += 1
        yield b"data: {}\n\n"
        await asyncio.Event().wait()

    stream = StreamingResponse(endless(), media_type="text/event-stream")

    async def call_next(_: Request) -> StreamingResponse:
        return stream

    middleware = RequestLoggingMiddleware(app=None)  # pyright: ignore[reportArgumentType]
    response = await asyncio.wait_for(
        middleware.dispatch(_request("/api/v1/quotes/stream/XAUUSD:EXNESS"), call_next), 1.0
    )

    assert response is stream
    assert chunks_read == 0


@pytest.mark.asyncio
async def test_a_body_is_not_read_when_debug_is_off(caplog: pytest.LogCaptureFixture) -> None:
    chunks_read = 0

    async def body():
        nonlocal chunks_read
        chunks_read += 1
        yield b"{}"

    plain = StreamingResponse(body(), media_type="application/json")

    async def call_next(_: Request) -> StreamingResponse:
        return plain

    caplog.set_level(logging.INFO, logger="pocketquant.app.middleware.request_logging_middleware")
    middleware = RequestLoggingMiddleware(app=None)  # pyright: ignore[reportArgumentType]
    response = await middleware.dispatch(_request("/api/v1/symbols"), call_next)

    assert response is plain
    assert chunks_read == 0
