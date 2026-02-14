"""CQRS Mediator for command/query dispatch."""

from src.common.mediator.exceptions import DuplicateHandlerError, HandlerNotFoundError
from src.common.mediator.handler import Handler
from src.common.mediator.handler_registry import HandlerRegistry, handles
from src.common.mediator.mediator import Mediator

__all__ = [
    "Mediator",
    "Handler",
    "HandlerNotFoundError",
    "DuplicateHandlerError",
    "HandlerRegistry",
    "handles",
]
