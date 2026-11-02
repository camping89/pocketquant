# Production logging uses cache_logger_on_first_use=True, so a module-level logger that
# already emitted in an earlier test keeps its cached processor chain and ignores
# structlog.testing.capture_logs. A fresh lazy proxy per test makes log capture
# order-independent.

from __future__ import annotations

import pytest
import structlog

from pocketquant.core.infra.brokers.exness import exness_broker_adapter as adapter_module


@pytest.fixture(autouse=True)
def _fresh_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adapter_module, "logger", structlog.get_logger("test.exness"))


# Keeps the operation watcher from outliving a test unless the test drives it.
@pytest.fixture(autouse=True)
def _no_watch_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adapter_module, "_STATUS_POLLS", 0)
    monkeypatch.setattr(adapter_module, "_FILL_TIMEOUT_S", 3600)
