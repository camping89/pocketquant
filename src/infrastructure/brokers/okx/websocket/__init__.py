"""OKX WebSocket submodule - private channel connection and message handling."""

from src.infrastructure.brokers.okx.websocket.okx_auth import (
    build_login_message,
    generate_ws_signature,
    get_private_ws_url,
)
from src.infrastructure.brokers.okx.websocket.okx_message_parser import OkxMessageParser
from src.infrastructure.brokers.okx.websocket.okx_order_mapper import OkxOrderMapper
from src.infrastructure.brokers.okx.websocket.okx_position_mapper import (
    OkxPositionMapper,
    PositionUpdate,
)
from src.infrastructure.brokers.okx.websocket.okx_reconnection_handler import (
    OkxReconnectionHandler,
    OkxStateReconciler,
)
from src.infrastructure.brokers.okx.websocket.okx_websocket_client import OkxWebSocketClient

__all__ = [
    # Client
    "OkxWebSocketClient",
    # Auth
    "generate_ws_signature",
    "build_login_message",
    "get_private_ws_url",
    # Parsers
    "OkxMessageParser",
    "OkxOrderMapper",
    "OkxPositionMapper",
    "PositionUpdate",
    # Reconnection
    "OkxReconnectionHandler",
    "OkxStateReconciler",
]
