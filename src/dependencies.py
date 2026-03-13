"""FastAPI Depends() functions — single source for all route injection."""

from typing import Annotated

from fastapi import Depends, Request

from src.application.market_data.quote_service import QuoteService
from src.common.mediator.mediator import Mediator
from src.services import Services


def get_services(request: Request) -> Services:
    """Get the Services registry from app state."""
    return request.app.state.services


def get_mediator(request: Request) -> Mediator:
    """Get Mediator instance for CQRS dispatch."""
    return request.app.state.services.mediator


def get_quote_service(request: Request) -> QuoteService:
    """Get QuoteService for quote operations."""
    return request.app.state.services.quote_service


# Type aliases for clean route signatures
MediatorDep = Annotated[Mediator, Depends(get_mediator)]
QuoteServiceDep = Annotated[QuoteService, Depends(get_quote_service)]
ServicesDep = Annotated[Services, Depends(get_services)]
