"""Query to get all active quotes across subscribed symbols."""

from pydantic import BaseModel


class GetAllQuotesQuery(BaseModel):
    """Get all active quotes across subscribed symbols."""

    pass
