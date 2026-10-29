# Regression for empty error="" rows in job_history when APScheduler dispatched a
# CancelledError during a deploy: `str(exc) if exc else None` collapsed empty-message
# exceptions, so the dashboard showed them as unknown failures.

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from pocketquant.core.infra.scheduling.scheduler import JobScheduler


@pytest.mark.parametrize(
    "exc, expected_err",
    [
        (None, "unknown_error_no_exception"),
        (Exception("real msg"), "Exception: real msg"),
        (Exception(""), "Exception(no message)"),
        (ValueError(""), "ValueError(no message)"),
        (asyncio.CancelledError(), "CancelledError(no message)"),
    ],
)
def test_on_error_formats_exception(exc, expected_err) -> None:
    scheduler = JobScheduler()
    captured: dict = {}
    # Bypass the dispatch path entirely — we only care about the err string
    # the handler synthesizes for the listener-write call.
    scheduler._dispatch_skip = lambda jid, t, s, err: captured.update(  # type: ignore[method-assign]
        job_id=jid, status=s, err=err
    )

    event = MagicMock(job_id="x", scheduled_run_time=None, exception=exc)
    scheduler._on_error(event)

    assert captured["err"] == expected_err
    assert captured["status"] == "failed"
    assert captured["job_id"] == "x"
