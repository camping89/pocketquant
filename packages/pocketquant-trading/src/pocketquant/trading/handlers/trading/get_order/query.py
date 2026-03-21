"""Get order query."""

from pydantic import BaseModel


class GetOrderQuery(BaseModel):
    """Query to get a specific order."""

    order_id: str
