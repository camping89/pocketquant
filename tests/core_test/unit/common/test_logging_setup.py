"""setup_logging keeps third-party loggers that would leak secrets quiet."""

from __future__ import annotations

import logging

import pytest
import structlog

from pocketquant.core.common.logging import setup as logging_setup
from tests.core_test.infra.market_data.conftest import build_settings


def test_the_websockets_handshake_log_stays_off_at_debug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Its DEBUG handshake log prints the request headers, the Exness API key included."""
    monkeypatch.setattr(structlog, "configure", lambda **_: None)
    monkeypatch.setattr(logging, "basicConfig", lambda **_: None)
    websockets_logger = logging.getLogger("websockets")
    previous = websockets_logger.level
    try:
        logging_setup.setup_logging(build_settings().model_copy(update={"log_level": "DEBUG"}))

        assert websockets_logger.level == logging.WARNING
    finally:
        websockets_logger.setLevel(previous)
