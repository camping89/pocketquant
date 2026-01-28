"""Stream real-time quotes from TradingView.

Usage:
    python scripts/stream_quotes.py                     # Default: BTCUSD
    python scripts/stream_quotes.py AAPL NASDAQ        # Single symbol
    python scripts/stream_quotes.py BTCUSD,ETHUSD CRYPTO  # Multiple symbols
"""

import asyncio
import signal
import sys
from datetime import datetime

from src.infrastructure.tradingview.websocket import TradingViewWebSocketProvider


def on_quote(data: dict) -> None:
    """Print quote data."""
    symbol = data.get("symbol_key", "?")
    price = data.get("last_price")
    change = data.get("change_percent")
    bid = data.get("bid")
    ask = data.get("ask")
    ts = data.get("timestamp", datetime.now()).strftime("%H:%M:%S")

    if price is None:
        return

    change_str = f"{change:+.2f}%" if change else ""
    spread_str = f"bid={bid:.2f} ask={ask:.2f}" if bid and ask else ""

    print(f"[{ts}] {symbol}: ${price:,.2f} {change_str} {spread_str}")


async def main(symbols: list[str], exchange: str, duration: int | None = None):
    provider = TradingViewWebSocketProvider()

    # Handle Ctrl+C
    stop_event = asyncio.Event()

    def signal_handler():
        print("\nStopping...")
        stop_event.set()
        provider._running = False

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            signal.signal(sig, lambda s, f: signal_handler())

    try:
        await provider.connect()
        print(f"Connected! Session: {provider._session_id}")

        for symbol in symbols:
            key = await provider.subscribe(symbol, exchange, on_quote)
            print(f"Subscribed: {key}")

        print(f"\nStreaming quotes... (Ctrl+C to stop)\n")

        # Run with optional duration
        async def run_stream():
            task = asyncio.create_task(provider.run_forever())
            try:
                if duration:
                    await asyncio.wait_for(stop_event.wait(), timeout=duration)
                else:
                    await stop_event.wait()
            except asyncio.TimeoutError:
                pass
            finally:
                provider._running = False
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        await run_stream()

    finally:
        await provider.disconnect()
        print("Disconnected.")


if __name__ == "__main__":
    # Parse args
    symbols = ["BTCUSD"]
    exchange = "CRYPTO"

    if len(sys.argv) >= 2:
        symbols = sys.argv[1].split(",")
    if len(sys.argv) >= 3:
        exchange = sys.argv[2]

    print(f"Symbols: {symbols}")
    print(f"Exchange: {exchange}")
    print("-" * 40)

    asyncio.run(main(symbols, exchange))
