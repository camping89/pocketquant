"""Admin authentication dependency for mutation endpoints.

Uses X-Admin-Token header compared against Settings.admin_token (SecretStr).
If admin_token is unset (dev mode), auth is skipped with a warning log.
Comparison uses hmac.compare_digest to prevent timing-side-channel attacks.
"""

import hmac

from fastapi import Header, HTTPException
from pocketquant.core.common.logging import get_logger
from pocketquant.core.config import get_settings

logger = get_logger(__name__)


async def verify_admin_token(x_admin_token: str | None = Header(default=None)) -> None:
    """FastAPI dependency — validate X-Admin-Token header.

    Attach via Depends(verify_admin_token) on POST/PUT/DELETE routes.
    Raises 401 if token configured and header is missing or wrong.
    Uses timing-safe comparison to prevent secret enumeration via timing attacks.
    """
    settings = get_settings()
    expected_secret = settings.admin_token

    if expected_secret is None:
        # Dev mode: no token configured — allow all, log warning once per request
        logger.warning("admin_auth.skipped_dev_mode")
        return

    expected = expected_secret.get_secret_value()

    # Reject missing token or perform timing-safe comparison
    if not x_admin_token or not hmac.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Admin-Token")
