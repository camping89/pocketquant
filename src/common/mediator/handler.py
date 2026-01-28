"""Base handler for CQRS commands and queries."""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

TRequest = TypeVar("TRequest")
TResponse = TypeVar("TResponse")


class Handler(ABC, Generic[TRequest, TResponse]):
    """Base handler for commands and queries."""

    @abstractmethod
    async def handle(self, request: TRequest) -> TResponse:
        """Handle the request and return a response."""
        ...
