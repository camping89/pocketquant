"""OKX WebSocket message parser - routes messages by channel type."""


class OkxMessageParser:
    """Parse and route OKX WebSocket messages.

    OKX message format:
    - Event messages: {"event": "login|subscribe|error", ...}
    - Data messages: {"arg": {"channel": "orders", ...}, "data": [...]}
    """

    @staticmethod
    def is_event(message: dict) -> bool:
        """Check if message is an event (login, subscribe, error)."""
        return "event" in message

    @staticmethod
    def is_data(message: dict) -> bool:
        """Check if message contains channel data."""
        return "arg" in message and "data" in message

    @staticmethod
    def get_channel(message: dict) -> str:
        """Extract channel name from data message."""
        return message.get("arg", {}).get("channel", "")

    @staticmethod
    def get_data(message: dict) -> list[dict]:
        """Extract data array from message."""
        return message.get("data", [])

    @staticmethod
    def parse(message: dict) -> tuple[str, list[dict]]:
        """Parse message and return (channel, data_items).

        Args:
            message: Parsed JSON message from WebSocket.

        Returns:
            Tuple of (channel_name, list_of_data_items).
            Returns ("", []) for event messages.
        """
        if OkxMessageParser.is_event(message):
            return "", []

        if not OkxMessageParser.is_data(message):
            return "", []

        channel = OkxMessageParser.get_channel(message)
        data = OkxMessageParser.get_data(message)

        return channel, data

    @staticmethod
    def get_event_type(message: dict) -> str:
        """Get event type from event message."""
        return message.get("event", "")

    @staticmethod
    def get_event_code(message: dict) -> str:
        """Get event code (for login/error responses)."""
        return message.get("code", "")

    @staticmethod
    def get_event_message(message: dict) -> str:
        """Get event message/error description."""
        return message.get("msg", "")
