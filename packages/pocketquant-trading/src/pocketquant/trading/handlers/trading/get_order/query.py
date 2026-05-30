"""Get order query."""

from pydantic import BaseModel


class GetOrderQuery(BaseModel):
    order_id: str
