"""Query for GET /quotes/status — WS feed observability."""

from dataclasses import dataclass


@dataclass
class GetQuotesStatusQuery:
    """Query to retrieve real-time WS feed status metrics."""

    pass
