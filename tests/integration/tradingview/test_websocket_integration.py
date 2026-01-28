"""Integration tests for TradingView WebSocket - connects to real server."""

import asyncio

import pytest

from src.infrastructure.tradingview.websocket import TradingViewWebSocketProvider


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_connection_and_subscribe():
    """Test real connection to TradingView and receive quotes.

    This test connects to TradingView WebSocket, subscribes to BTCUSD,
    and waits for real quote data.
    """
    provider = TradingViewWebSocketProvider()
    received_quotes = []

    def on_quote(data):
        received_quotes.append(data)
        print(f"Received: {data['symbol_key']} = {data.get('last_price')}")

    try:
        # Connect
        await provider.connect()
        assert provider.is_connected()
        print(f"Connected with session: {provider._session_id}")

        # Subscribe to BTC (crypto markets are 24/7)
        symbol_key = await provider.subscribe("BTCUSD", "CRYPTO", on_quote)
        assert symbol_key == "CRYPTO:BTCUSD"
        assert provider.subscription_count == 1
        print(f"Subscribed to {symbol_key}")

        # Run for a few seconds to receive quotes
        async def run_with_timeout():
            task = asyncio.create_task(provider.run_forever())
            try:
                await asyncio.wait_for(asyncio.sleep(5), timeout=10)
            finally:
                provider._running = False
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        await run_with_timeout()

        # Should have received at least one quote
        print(f"Received {len(received_quotes)} quotes")
        assert len(received_quotes) > 0, "Should receive at least one quote"

        # Verify quote structure
        quote = received_quotes[0]
        assert "symbol_key" in quote
        assert "timestamp" in quote
        assert quote["symbol_key"] == "CRYPTO:BTCUSD"

    finally:
        await provider.disconnect()
        assert not provider.is_connected()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multiple_symbols():
    """Test subscribing to multiple symbols."""
    provider = TradingViewWebSocketProvider()
    received = {"CRYPTO:BTCUSD": [], "CRYPTO:ETHUSD": []}

    def make_callback(symbol):
        def on_quote(data):
            received[symbol].append(data)
        return on_quote

    try:
        await provider.connect()

        await provider.subscribe("BTCUSD", "CRYPTO", make_callback("CRYPTO:BTCUSD"))
        await provider.subscribe("ETHUSD", "CRYPTO", make_callback("CRYPTO:ETHUSD"))

        assert provider.subscription_count == 2

        # Run briefly
        async def run_with_timeout():
            task = asyncio.create_task(provider.run_forever())
            try:
                await asyncio.wait_for(asyncio.sleep(5), timeout=10)
            finally:
                provider._running = False
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        await run_with_timeout()

        print(f"BTC quotes: {len(received['CRYPTO:BTCUSD'])}")
        print(f"ETH quotes: {len(received['CRYPTO:ETHUSD'])}")

        # At least one symbol should have data
        total = len(received["CRYPTO:BTCUSD"]) + len(received["CRYPTO:ETHUSD"])
        assert total > 0, "Should receive quotes for at least one symbol"

    finally:
        await provider.disconnect()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unsubscribe():
    """Test unsubscribing from a symbol."""
    provider = TradingViewWebSocketProvider()

    try:
        await provider.connect()

        await provider.subscribe("BTCUSD", "CRYPTO", lambda x: None)
        assert provider.subscription_count == 1

        await provider.unsubscribe("BTCUSD", "CRYPTO")
        assert provider.subscription_count == 0

    finally:
        await provider.disconnect()


if __name__ == "__main__":
    # Run manually: python -m pytest tests/integration/tradingview/test_websocket_integration.py -v -s
    asyncio.run(test_real_connection_and_subscribe())
