from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from pocketquant.core.common.constants import HEADER_CORRELATION_ID
from pocketquant.core.common.tracing.context import request_id_contextvar
from pocketquant.core.common.uuid import generate_id_str


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(HEADER_CORRELATION_ID) or generate_id_str()
        token = request_id_contextvar.set(request_id)

        try:
            response = await call_next(request)
            response.headers[HEADER_CORRELATION_ID] = request_id
            return response
        finally:
            request_id_contextvar.reset(token)
