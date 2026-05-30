from pydantic import BaseModel


class GetOptimizationQuery(BaseModel):
    """Query to get a specific optimization result by ID."""

    optimization_id: str
