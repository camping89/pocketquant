"""Webhook dispatcher with HMAC signatures and retry logic."""

import hashlib
import hmac
import json
from dataclasses import asdict
from typing import Any

from src.common.logging import get_logger
from src.domain.shared.events import DomainEvent
from src.infrastructure.http_client.client import ResilientHttpClient
from src.infrastructure.webhooks.config import WebhookConfig

logger = get_logger(__name__)


class WebhookDispatcher:
    """Dispatch domain events to configured webhook endpoints."""

    def __init__(
        self, config: WebhookConfig, client: ResilientHttpClient | None = None
    ):
        self.config = config
        self.client = client or ResilientHttpClient()

    async def dispatch(self, event: DomainEvent) -> None:
        """Dispatch event to all registered endpoints."""
        event_type = type(event).__name__
        endpoints = self.config.get_endpoints(event_type)

        if not endpoints:
            return

        payload = self._build_payload(event)

        for endpoint in endpoints:
            try:
                headers = {}
                if endpoint.secret:
                    headers["X-Webhook-Signature"] = self._sign(payload, endpoint.secret)

                await self.client.post(endpoint.url, payload, headers)
                logger.info(
                    "webhook_sent",
                    event_type=event_type,
                    url=endpoint.url,
                )
            except Exception as e:
                logger.error(
                    "webhook_failed",
                    event_type=event_type,
                    url=endpoint.url,
                    error=str(e),
                )

    def _build_payload(self, event: DomainEvent) -> dict[str, Any]:
        """Build webhook payload from domain event."""
        return {
            "event_type": type(event).__name__,
            "data": self._serialize_event(event),
            "event_id": str(event.event_id),
            "occurred_at": event.occurred_at.isoformat(),
        }

    def _serialize_event(self, event: DomainEvent) -> dict[str, Any]:
        """Serialize event data, excluding base fields."""
        data = asdict(event)
        data.pop("event_id", None)
        data.pop("occurred_at", None)
        return data

    def _sign(self, payload: dict[str, Any], secret: str) -> str:
        """Generate HMAC SHA256 signature for webhook payload."""
        body = json.dumps(payload, sort_keys=True)
        return hmac.new(
            secret.encode(),
            body.encode(),
            hashlib.sha256,
        ).hexdigest()

    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.close()
