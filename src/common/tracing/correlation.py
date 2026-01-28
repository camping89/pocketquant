"""Correlation ID middleware for request tracing."""

from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.common.constants import HEADER_CORRELATION_ID
from src.common.tracing.context import request_id_contextvar


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Injects correlation ID into request context and response headers."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(HEADER_CORRELATION_ID) or str(uuid4())
        token = request_id_contextvar.set(request_id)

        try:
            response = await call_next(request)
            response.headers[HEADER_CORRELATION_ID] = request_id
            return response
        finally:
            request_id_contextvar.reset(token)
