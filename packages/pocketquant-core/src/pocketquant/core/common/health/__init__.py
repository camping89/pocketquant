"""Health check coordination.

``HealthCoordinator`` is the pure parallel-check aggregator (no infra deps).
The concrete dependency checks (``check_database``/``check_redis``) live in
``pocketquant.infrastructure.persistence.health_checks`` because they import
``Database``/``Cache``.
"""

from pocketquant.core.common.health.coordinator import HealthCoordinator

__all__ = ["HealthCoordinator"]
