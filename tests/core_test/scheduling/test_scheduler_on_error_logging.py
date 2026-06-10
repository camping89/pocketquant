"""Unit tests for JobScheduler._on_error exception formatting.

Regression for the empty ``error=""`` rows that appeared in job_history when
APScheduler dispatched a CancelledError during a deploy. The old path called
``str(exc) if exc else None``, which collapsed empty-message exceptions to
``None`` and made bare ``""`` rows look like "unknown failure" in the dashboard.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from pocketquant.core.scheduling.scheduler import JobScheduler


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
