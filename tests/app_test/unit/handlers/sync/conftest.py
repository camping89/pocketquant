"""Fixtures for sync-handler unit tests.

These tests assert log output via ``structlog.testing.capture_logs``. Production
logging uses ``cache_logger_on_first_use=True``, so a module-level logger that
already emitted during an earlier test keeps its cached processor chain and
ignores the capture configuration. Rebinding a fresh lazy proxy per test makes
log capture order-independent.
"""

from __future__ import annotations

import pytest
import structlog


@pytest.fixture(autouse=True)
def fresh_structlog_module_loggers(monkeypatch: pytest.MonkeyPatch) -> None:
    from pocketquant.engine.market_data import sync_service
    from pocketquant.engine.market_data.sync_internals import (
        anomaly_log,
        bar_filters,
        provider_fetch,
    )

    for module in (bar_filters, provider_fetch, anomaly_log, sync_service):
        monkeypatch.setattr(module, "logger", structlog.get_logger(module.__name__))
