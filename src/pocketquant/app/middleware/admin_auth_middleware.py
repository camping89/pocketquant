import hmac

from fastapi import Header, HTTPException, Request

from pocketquant.core.common.logging import get_logger
from pocketquant.core.config import get_settings

logger = get_logger(__name__)

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


# Safe methods skip the check because the SPA's EventSource streams cannot send
# headers. With no token configured, production fails closed (503); other
# environments skip auth with a warning.
async def verify_admin_token(
    request: Request, x_admin_token: str | None = Header(default=None)
) -> None:
    if request.method in _SAFE_METHODS:
        return
    _check_token(x_admin_token)


# Reads that expose positions, orders and strategy state need the token too; none of them
# is an EventSource stream.
async def require_admin_token(x_admin_token: str | None = Header(default=None)) -> None:
    _check_token(x_admin_token)


def _check_token(x_admin_token: str | None) -> None:
    settings = get_settings()
    expected_secret = settings.admin_token

    if expected_secret is None:
        if settings.environment == "production":
            raise HTTPException(status_code=503, detail="ADMIN_TOKEN not configured")
        # Dev mode: no token configured — allow all, log warning once per request
        logger.warning("admin_auth.skipped_dev_mode")
        return

    expected = expected_secret.get_secret_value()

    if not x_admin_token or not hmac.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Admin-Token")
