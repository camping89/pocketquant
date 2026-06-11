"""Domain exceptions and global HTTP exception handling.

Starlette-only (like the sibling tracing/rate_limit/idempotency middleware) so
core honours the "fastapi only in app" import contract. Callers pass their
framework's request-validation error class at registration time.
"""

from typing import Any, Protocol, cast

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from pocketquant.core.common.logging import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    """Base application error with HTTP status code."""

    def __init__(self, message: str, *, status_code: int = 400, error_code: str = "APP_ERROR"):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(message)


class NotFoundError(AppError):
    """Resource not found (404)."""

    def __init__(self, message: str = "Resource not found", *, error_code: str = "NOT_FOUND"):
        super().__init__(message, status_code=404, error_code=error_code)


class DomainError(AppError):
    """Domain rule violation (400)."""

    def __init__(self, message: str, *, error_code: str = "DOMAIN_ERROR"):
        super().__init__(message, status_code=400, error_code=error_code)


class _ValidationError(Protocol):
    """Shape of framework validation errors (e.g. fastapi RequestValidationError)."""

    def errors(self) -> list[dict[str, Any]]: ...


def _error_response(status_code: int, error_code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": error_code, "message": message}},
    )


def register_exception_handlers(app: Starlette, *, validation_error_cls: type[Exception]) -> None:
    """Register global exception handlers on the ASGI app.

    Routes no longer need manual try/except → HTTPException conversion.
    ``validation_error_cls`` is the framework's request-validation error
    (must expose ``.errors()``), injected so this module stays fastapi-free.
    """

    async def handle_app_error(_request: Request, exc: Exception) -> Response:
        err = cast(AppError, exc)
        logger.warning("app_error", error_code=err.error_code, message=err.message)
        return _error_response(err.status_code, err.error_code, err.message)

    async def handle_value_error(_request: Request, exc: Exception) -> Response:
        logger.warning("value_error", message=str(exc))
        return _error_response(400, "VALIDATION_ERROR", str(exc))

    async def handle_validation_error(_request: Request, exc: Exception) -> Response:
        errors = cast(_ValidationError, exc).errors()
        message = "; ".join(
            f"{'.'.join(str(loc) for loc in e.get('loc', []))}: {e.get('msg', '')}" for e in errors
        )
        return _error_response(422, "VALIDATION_ERROR", message)

    async def handle_unexpected_error(_request: Request, exc: Exception) -> Response:
        logger.error("unhandled_exception", error=str(exc), exc_type=type(exc).__name__)
        return _error_response(500, "INTERNAL_ERROR", "An unexpected error occurred")

    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(ValueError, handle_value_error)
    app.add_exception_handler(validation_error_cls, handle_validation_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
