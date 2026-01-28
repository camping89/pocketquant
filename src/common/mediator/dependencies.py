"""FastAPI dependency injection for mediator."""

from fastapi import Request

from src.common.mediator.mediator import Mediator


def get_mediator(request: Request) -> Mediator:
    """Get the mediator from FastAPI app state."""
    return request.app.state.mediator
