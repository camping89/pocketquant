"""FastAPI dependency injection for quote services."""

from fastapi import Request

from src.application.market_data.quote_service import QuoteService
from src.container import resolve


async def get_quote_service(request: Request) -> QuoteService:
    """Resolve QuoteService from DI container — typed for IDE support."""
    return await resolve(request.app.state.container.quote_service)
