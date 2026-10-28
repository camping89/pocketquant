import asyncio
import time
from types import SimpleNamespace

import pytest
import structlog

from pocketquant.app import main_extensions
from pocketquant.app.main_extensions import start_loop_lag_probe, stop_loop_lag_probe


async def test_blocked_loop_is_reported_and_warned_once(monkeypatch: pytest.MonkeyPatch) -> None:
    # A module logger cached by an earlier test ignores capture_logs; rebind a fresh one.
    monkeypatch.setattr(main_extensions, "logger", structlog.get_logger("test.loop_lag"))
    app = SimpleNamespace(state=SimpleNamespace())
    with structlog.testing.capture_logs() as logs:
        start_loop_lag_probe(app)  # type: ignore[arg-type]
        await asyncio.sleep(0.6)
        time.sleep(1.1)  # blocks the loop: the next sample is late by at least 0.6 s
        await asyncio.sleep(1.1)
        await stop_loop_lag_probe(app)  # type: ignore[arg-type]
    assert app.state.loop_lag_max_s >= 0.5
    assert [entry["event"] for entry in logs].count("event_loop.lag") == 1
