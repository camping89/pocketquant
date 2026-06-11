"""OKX WebSocket authentication - HMAC-SHA256 signature generation."""

import base64
import hashlib
import hmac
import os
from datetime import UTC, datetime
from typing import Any


def generate_ws_signature(api_secret: str, timestamp: str | None = None) -> tuple[str, str]:
    """Generate OKX WebSocket authentication signature.

    OKX requires HMAC-SHA256 signature for private channel authentication.
    Signature = Base64(HMAC-SHA256(timestamp + "GET" + "/users/self/verify"))

    Args:
        api_secret: OKX API secret key.
        timestamp: Unix timestamp as string (auto-generated if not provided).

    Returns:
        Tuple of (timestamp, signature) for login message.
    """
    if timestamp is None:
        timestamp = str(int(datetime.now(UTC).timestamp()))

    # Pre-hash string format per OKX docs
    pre_hash = timestamp + "GET" + "/users/self/verify"

    signature = base64.b64encode(
        hmac.new(
            api_secret.encode("utf-8"),
            pre_hash.encode("utf-8"),
            hashlib.sha256,
        ).digest()
    ).decode("utf-8")

    return timestamp, signature


def build_login_message(
    api_key: str,
    api_secret: str,
    passphrase: str,
) -> dict[str, Any]:
    """Build complete WebSocket login message.

    Args:
        api_key: OKX API key.
        api_secret: OKX API secret.
        passphrase: OKX API passphrase.

    Returns:
        Login message dict ready to be sent as JSON.
    """
    timestamp, signature = generate_ws_signature(api_secret)

    return {
        "op": "login",
        "args": [
            {
                "apiKey": api_key,
                "passphrase": passphrase,
                "timestamp": timestamp,
                "sign": signature,
            }
        ],
    }


def get_private_ws_url(demo: bool = True) -> str:
    """Get OKX private WebSocket URL based on environment.

    Args:
        demo: Whether to use demo (paper trading) endpoint.

    Returns:
        WebSocket URL for private channels.
    """
    # Check environment variable override (validated requirement)
    env_demo = os.getenv("OKX_DEMO", "").lower()
    if env_demo == "false" or env_demo == "0":
        demo = False
    elif env_demo == "true" or env_demo == "1":
        demo = True

    if demo:
        return "wss://wspap.okx.com:8443/ws/v5/private?brokerId=9999"
    return "wss://ws.okx.com:8443/ws/v5/private"
