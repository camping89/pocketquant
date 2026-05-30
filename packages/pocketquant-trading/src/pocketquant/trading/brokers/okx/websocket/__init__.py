"""OKX WebSocket submodule - private channel connection and message handling."""

from pocketquant.trading.brokers.okx.websocket.okx_auth import (
    build_login_message,
    generate_ws_signature,
    get_private_ws_url,
)
from pocketquant.trading.brokers.okx.websocket.okx_message_parser import OkxMessageParser
from pocketquant.trading.brokers.okx.websocket.okx_order_mapper import OkxOrderMapper
from pocketquant.trading.brokers.okx.websocket.okx_position_mapper import (
    OkxPositionMapper,
    PositionUpdate,
)
from pocketquant.trading.brokers.okx.websocket.okx_reconnection_handler import (
    OkxReconnectionHandler,
    OkxStateReconciler,
)
from pocketquant.trading.brokers.okx.websocket.okx_websocket_client import OkxWebSocketClient

__all__ = [
    "OkxWebSocketClient",
    "generate_ws_signature",
    "build_login_message",
    "get_private_ws_url",
    "OkxMessageParser",
    "OkxOrderMapper",
    "OkxPositionMapper",
    "PositionUpdate",
    "OkxReconnectionHandler",
    "OkxStateReconciler",
]
