"""Resilient HTTP client with retry logic and correlation ID propagation."""

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from src.common.constants import HEADER_CORRELATION_ID
from src.common.logging import get_logger
from src.common.tracing import get_correlation_id

logger = get_logger(__name__)


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    timeout: float = 30.0


class ResilientHttpClient:
    """HTTP client with automatic retry and correlation ID injection."""

    def __init__(self, config: RetryConfig | None = None):
        self.config = config or RetryConfig()
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client instance."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.config.timeout)
        return self._client

    async def post(
        self,
        url: str,
        json: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """POST request with retry logic and correlation ID."""
        headers = headers or {}
        headers[HEADER_CORRELATION_ID] = get_correlation_id()

        last_error = None
        for attempt in range(self.config.max_retries + 1):
            try:
                client = await self._get_client()
                response = await client.post(url, json=json, headers=headers)
                response.raise_for_status()

                logger.info(
                    "http_request_success",
                    url=url,
                    status_code=response.status_code,
                    attempt=attempt + 1,
                )
                result: dict[str, Any] = response.json()
                return result

            except Exception as e:
                last_error = e
                if attempt < self.config.max_retries:
                    delay = min(
                        self.config.base_delay * (2**attempt),
                        self.config.max_delay,
                    )
                    logger.warning(
                        "http_retry",
                        url=url,
                        attempt=attempt + 1,
                        delay=delay,
                        error=str(e),
                    )
                    await asyncio.sleep(delay)

        logger.error(
            "http_request_failed",
            url=url,
            error=str(last_error),
            attempts=self.config.max_retries + 1,
        )
        if last_error:
            raise last_error
        raise RuntimeError(f"HTTP request failed: {url}")

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
