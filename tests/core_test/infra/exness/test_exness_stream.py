"""ExnessStream: reconnect backoff, circuit breaker, signed handshake, handler isolation."""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import structlog
import structlog.testing
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from pocketquant.core.infra.exness import exness_stream
from pocketquant.core.infra.exness.exness_client import ExnessApiError
from pocketquant.core.infra.exness.exness_signer import sign_headers
from pocketquant.core.infra.exness.exness_stream import ExnessStream

PATH = "/v1/server-events/accounts/1/ws/ticks"


class _FakeSocket:
    """Yields scripted frames, then ends like a normal close."""

    def __init__(self, frames: list[str]) -> None:
        self._frames = frames
        self.state = exness_stream.websockets.State.OPEN
        self.sent: list[str] = []

    def __aiter__(self) -> _FakeSocket:
        return self

    async def __anext__(self) -> str:
        if not self._frames:
            raise StopAsyncIteration
        return self._frames.pop(0)

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def close(self) -> None:
        self.state = exness_stream.websockets.State.CLOSED


class _FakeConnect:
    """Fails ``failures`` times, then serves each script once; then cancels the run."""

    def __init__(self, failures: int, scripts: list[list[str]]) -> None:
        self.failures = failures
        self.scripts = scripts
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, url: str, **kwargs: Any) -> _FakeSocket:
        self.calls.append({"url": url, **kwargs})
        if self.failures:
            self.failures -= 1
            raise OSError("connect failed")
        if not self.scripts:
            raise asyncio.CancelledError
        return _FakeSocket(self.scripts.pop(0))


def _client() -> MagicMock:
    key = Ed25519PrivateKey.generate()
    client = MagicMock()
    client.ws_url = AsyncMock(return_value=f"wss://ap-1.exness.com{PATH}")
    client.sign_ws_headers = lambda path: sign_headers(
        api_key="k",
        private_key=key,
        method="GET",
        path_with_query=path,
        body=b"",
        idempotency_key="",
        timestamp_ms=1,
    )
    return client


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock()
    monkeypatch.setattr(exness_stream.asyncio, "sleep", mock)
    monkeypatch.setattr(exness_stream, "logger", structlog.get_logger("test.exness_stream"))
    return mock


def _install(monkeypatch: pytest.MonkeyPatch, connect: _FakeConnect) -> None:
    monkeypatch.setattr(exness_stream.websockets, "connect", connect)


async def _run(stream: ExnessStream) -> None:
    with pytest.raises(asyncio.CancelledError):
        await stream.run_forever()


async def test_failures_back_off_exponentially_then_connect(
    monkeypatch: pytest.MonkeyPatch, sleeps: AsyncMock
) -> None:
    connect = _FakeConnect(failures=3, scripts=[[]])
    _install(monkeypatch, connect)
    connected = AsyncMock()

    await _run(ExnessStream(_client(), PATH, AsyncMock(), connected, None))

    assert [c.args[0] for c in sleeps.await_args_list][:3] == [1, 2, 4]
    connected.assert_awaited_once()


async def test_ten_consecutive_failures_open_the_circuit_breaker(
    monkeypatch: pytest.MonkeyPatch, sleeps: AsyncMock
) -> None:
    _install(monkeypatch, _FakeConnect(failures=10, scripts=[]))

    await _run(ExnessStream(_client(), PATH, AsyncMock(), AsyncMock(), None))

    delays = [c.args[0] for c in sleeps.await_args_list]
    assert delays.count(300) == 1
    assert delays[-1] == 300


def _decoded(value: str) -> dict[str, Any]:
    return json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))


async def test_the_handshake_is_signed_over_the_path_with_the_subprotocol(
    monkeypatch: pytest.MonkeyPatch, sleeps: AsyncMock
) -> None:
    connect = _FakeConnect(failures=0, scripts=[[]])
    _install(monkeypatch, connect)

    await _run(ExnessStream(_client(), PATH, AsyncMock(), AsyncMock(), None))

    call = connect.calls[0]
    assert call["url"] == f"wss://ap-1.exness.com{PATH}"
    assert "EXN-SIGN" in call["additional_headers"]
    assert _decoded(call["additional_headers"]["EXN-DATA"])["path"] == PATH
    assert call["subprotocols"] == ["exness-ws-protocol"]


async def test_a_failing_handler_does_not_stop_the_stream(
    monkeypatch: pytest.MonkeyPatch, sleeps: AsyncMock
) -> None:
    _install(monkeypatch, _FakeConnect(failures=0, scripts=[['{"n": 1}', "not-json", '{"n": 2}']]))
    seen: list[dict[str, Any]] = []

    async def on_message(frame: dict[str, Any]) -> None:
        seen.append(frame)
        if frame["n"] == 1:
            raise RuntimeError("boom")

    stream = ExnessStream(_client(), PATH, on_message, AsyncMock(), None)
    with structlog.testing.capture_logs() as logs:
        await _run(stream)

    assert seen == [{"n": 1}, {"n": 2}]
    events = [e["event"] for e in logs]
    assert events.count("exness_ws.handler_failed") == 1
    assert events.count("exness_ws.invalid_json") == 1
    assert stream.last_frame_at is not None


async def test_an_access_point_error_is_retried_with_backoff(
    monkeypatch: pytest.MonkeyPatch, sleeps: AsyncMock
) -> None:
    connect = _FakeConnect(failures=0, scripts=[[]])
    _install(monkeypatch, connect)
    client = _client()
    client.ws_url = AsyncMock(
        side_effect=[ExnessApiError(404, "HTTP_404", ""), f"wss://ap-1.exness.com{PATH}"]
        + [f"wss://ap-1.exness.com{PATH}"] * 3
    )
    connected = AsyncMock()

    await _run(ExnessStream(client, PATH, AsyncMock(), connected, None))

    assert [c.args[0] for c in sleeps.await_args_list][0] == 1
    connected.assert_awaited_once()


async def test_send_reaches_the_socket_only_while_connected(
    monkeypatch: pytest.MonkeyPatch, sleeps: AsyncMock
) -> None:
    stream = ExnessStream(_client(), PATH, AsyncMock(), AsyncMock(), None)

    await stream.send({"id": "x"})
    socket = _FakeSocket([])
    stream._ws = socket
    await stream.send({"id": "y"})

    assert socket.sent == ['{"id": "y"}']
    assert stream.is_connected()
