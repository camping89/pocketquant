"""Webhook configuration models."""

from dataclasses import dataclass, field


@dataclass
class WebhookEndpoint:
    """Single webhook endpoint configuration."""

    url: str
    secret: str = ""
    enabled: bool = True


@dataclass
class WebhookConfig:
    """Webhook configuration with event-type mapping."""

    endpoints: dict[str, list[WebhookEndpoint]] = field(default_factory=dict)

    def get_endpoints(self, event_type: str) -> list[WebhookEndpoint]:
        """Get enabled endpoints for an event type."""
        return [e for e in self.endpoints.get(event_type, []) if e.enabled]
