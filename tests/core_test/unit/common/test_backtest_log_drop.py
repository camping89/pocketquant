from __future__ import annotations

import pytest
import structlog

from pocketquant.core.common.logging import BACKTEST_RUN_ID
from pocketquant.core.common.logging.setup import drop_backtest_info


def test_info_inside_a_backtest_is_dropped() -> None:
    with pytest.raises(structlog.DropEvent):
        drop_backtest_info(None, "info", {"event": "order_filled", BACKTEST_RUN_ID: "r1"})  # pyright: ignore[reportArgumentType]


def test_warning_inside_a_backtest_and_live_info_pass() -> None:
    warning = {"event": "strategy_on_bar_error", BACKTEST_RUN_ID: "r1"}
    live = {"event": "order_filled"}
    assert drop_backtest_info(None, "warning", warning) is warning  # pyright: ignore[reportArgumentType]
    assert drop_backtest_info(None, "info", live) is live  # pyright: ignore[reportArgumentType]
