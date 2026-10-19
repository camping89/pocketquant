"""ExnessQuoteAdapter: callback contract, instrument validation, subscribe and idle path."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import structlog
import structlog.testing

from pocketquant.core.domain.market_data.realtime_quote_provider_port import (
    IRealtimeQuoteProviderPort,
)
from pocketquant.core.infra.exness import exness_quote_adapter
from pocketquant.core.infra.exness.exness_quote_adapter import ExnessQuoteAdapter

FIXTURES = Path(__file__).parent / "fixtures"
TICKS: list[dict[str, Any]] = json.loads((FIXTURES / "ticks_sample.json").read_text("utf-8"))
INSTRUMENTS: list[str] = json.loads((FIXTURES / "instruments.json").read_text("utf-8"))[
    "instruments"
]
XAU_TICK = next(t for t in TICKS if t.get("instrument") == "XAUUSD")


@pytest.fixture(autouse=True)
def _capturable_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exness_quote_adapter, "logger", structlog.get_logger("test.exness_quote"))


def _client(configured: bool = True) -> MagicMock:
    client = MagicMock()
    client.is_configured = configured
    client.account_id = "1"
    client.instruments = AsyncMock(return_value=INSTRUMENTS)
    return client


def _connected(adapter: ExnessQuoteAdapter) -> MagicMock:
    stream = MagicMock()
    stream.is_connected = MagicMock(return_value=True)
    stream.send = AsyncMock()
    adapter._stream = stream
    return stream


def test_it_satisfies_the_realtime_port() -> None:
    assert isinstance(ExnessQuoteAdapter(_client()), IRealtimeQuoteProviderPort)


async def test_a_tick_reaches_the_subscriber_as_a_quote() -> None:
    adapter = ExnessQuoteAdapter(_client())
    callback = MagicMock()
    await adapter.subscribe("XAUUSD:EXNESS", callback)

    await adapter._on_frame({"id": "spike-ticks-all", "code": 200})
    await adapter._on_frame(XAU_TICK)

    callback.assert_called_once()
    quote = callback.call_args.args[0]
    assert quote["symbol"] == "XAUUSD:EXNESS"
    assert quote["last_price"] == XAU_TICK["bid"]
    assert adapter.last_tick_at is not None


async def test_other_instruments_and_failing_callbacks_are_contained() -> None:
    adapter = ExnessQuoteAdapter(_client())
    callback = AsyncMock(side_effect=RuntimeError("boom"))
    await adapter.subscribe("XAUUSD:EXNESS", callback)

    await adapter._on_frame(next(t for t in TICKS if t.get("instrument") == "EURUSD"))
    callback.assert_not_awaited()
    with structlog.testing.capture_logs() as logs:
        await adapter._on_frame(XAU_TICK)

    callback.assert_awaited_once()
    assert [e["event"] for e in logs] == ["exness_ws.callback_failed"]


async def test_an_unknown_instrument_never_reaches_the_socket() -> None:
    adapter = ExnessQuoteAdapter(_client())
    stream = _connected(adapter)

    with structlog.testing.capture_logs() as logs:
        for _ in range(3):
            assert await adapter.subscribe("ZZZ:EXNESS", MagicMock()) == "ZZZ:EXNESS"

    stream.send.assert_not_awaited()
    assert "ZZZ:EXNESS" not in adapter.subscriptions
    assert [e["event"] for e in logs].count("exness_ws.unknown_instrument") == 1


async def test_an_instrument_the_account_lacks_is_rejected() -> None:
    client = _client()
    client.instruments = AsyncMock(return_value=["EURUSD"])
    adapter = ExnessQuoteAdapter(client)
    stream = _connected(adapter)

    await adapter.subscribe("XAUUSD:EXNESS", MagicMock())

    stream.send.assert_not_awaited()
    assert adapter.subscription_count == 0


async def test_a_later_subscribe_sends_only_the_new_instrument() -> None:
    adapter = ExnessQuoteAdapter(_client())
    stream = _connected(adapter)

    await adapter.subscribe("XAUUSD:EXNESS", MagicMock())
    await adapter.subscribe("EURUSD:EXNESS", MagicMock())

    sent = [c.args[0] for c in stream.send.await_args_list]
    assert len(sent) == 2
    assert sent[1]["subscribe"] == {"event": "ticks", "instruments": ["EURUSD"]}


async def test_a_reconnect_resubscribes_every_stored_instrument() -> None:
    adapter = ExnessQuoteAdapter(_client())
    await adapter.subscribe("XAUUSD:EXNESS", MagicMock())
    await adapter.subscribe("EURUSD:EXNESS", MagicMock())
    stream = _connected(adapter)

    await adapter._resubscribe_all()

    message = stream.send.await_args.args[0]
    assert message["subscribe"]["instruments"] == ["XAUUSD", "EURUSD"]


async def test_an_error_frame_is_logged_not_raised() -> None:
    adapter = ExnessQuoteAdapter(_client())

    with structlog.testing.capture_logs() as logs:
        await adapter._on_frame(
            {"id": "sub-XAUUSD", "code": 403, "error_message": "MARKET_TRADE_DISABLED"}
        )
        await adapter._on_frame({"id": "sub-X", "code": 400, "error_message": "OTHER"})

    assert [e["event"] for e in logs] == ["exness_ws.trading_disabled", "exness_ws.error_frame"]


async def test_an_unconfigured_client_idles_without_a_stream() -> None:
    adapter = ExnessQuoteAdapter(_client(configured=False))

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(adapter.run_forever(), 0.05)

    assert adapter._stream is None
    assert adapter.is_connected() is False
