"""Global exception handling for FastAPI.

Registers handlers for domain errors, validation errors, and unhandled exceptions.
Routes no longer need manual try/except → HTTPException conversion.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

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


def _error_response(status_code: int, error_code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": error_code, "message": message}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the FastAPI app."""

    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        logger.warning("app_error", error_code=exc.error_code, message=exc.message)
        return _error_response(exc.status_code, exc.error_code, exc.message)

    @app.exception_handler(ValueError)
    async def handle_value_error(_request: Request, exc: ValueError) -> JSONResponse:
        logger.warning("value_error", message=str(exc))
        return _error_response(400, "VALIDATION_ERROR", str(exc))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = exc.errors()
        message = "; ".join(
            f"{'.'.join(str(loc) for loc in e.get('loc', []))}: {e.get('msg', '')}" for e in errors
        )
        return _error_response(422, "VALIDATION_ERROR", message)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled_exception", error=str(exc), exc_type=type(exc).__name__)
        return _error_response(500, "INTERNAL_ERROR", "An unexpected error occurred")
