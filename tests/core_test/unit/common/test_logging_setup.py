from __future__ import annotations

import logging
from typing import Any

import pytest
import structlog

from pocketquant.core.common.logging import setup as logging_setup
from tests.core_test.infra.market_data.conftest import build_settings


# Its DEBUG handshake log prints the request headers, the Exness API key included.
def test_the_websockets_handshake_log_stays_off_at_debug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(structlog, "configure", lambda **_: None)
    monkeypatch.setattr(logging, "basicConfig", lambda **_: None)
    websockets_logger = logging.getLogger("websockets")
    previous = websockets_logger.level
    try:
        logging_setup.setup_logging(build_settings().model_copy(update={"log_level": "DEBUG"}))

        assert websockets_logger.level == logging.WARNING
    finally:
        websockets_logger.setLevel(previous)


# Prod tracebacks reach the public deploy output, and a local can hold a secret.
def test_console_tracebacks_print_no_local_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(structlog, "configure", lambda **kwargs: captured.update(kwargs))
    monkeypatch.setattr(logging, "basicConfig", lambda **_: None)
    logging_setup.setup_logging(build_settings())

    def fail() -> None:
        local_only = "-".join(["local", "only", "value"])
        raise ValueError(len(local_only))

    with pytest.raises(ValueError) as exc_info:
        fail()
    rendered = captured["processors"][-1](
        None, "error", {"event": "boom", "exc_info": exc_info.value}
    )

    assert "ValueError" in rendered
    assert "local-only-value" not in rendered
