"""FastAPI dependency injection for mediator."""

from fastapi import Request

from src.common.mediator.mediator import Mediator


def get_mediator(request: Request) -> Mediator:
    """Get Mediator from DI container."""
    return request.app.state.container.mediator()
