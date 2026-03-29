"""Parallel health check coordinator with timeout handling."""

import asyncio
from collections.abc import Callable
from typing import Any


class HealthCoordinator:
    """Manages parallel health checks for multiple dependencies."""

    def __init__(self, timeout: float = 5.0):
        self._checks: dict[str, Callable] = {}
        self._timeout: float = timeout

    def register(self, name: str, check_function: Callable) -> None:
        """Register a health check function."""
        self._checks[name] = check_function

    async def check_all(self) -> dict[str, Any]:
        """Run all health checks in parallel and aggregate results."""
        checks = [
            self._run_check(name, check_function)
            for name, check_function in self._checks.items()
        ]
        results = await asyncio.gather(*checks, return_exceptions=False)

        dependencies = dict(zip(self._checks.keys(), results))
        overall = (
            "healthy"
            if all(r.get("status") == "healthy" for r in dependencies.values())
            else "unhealthy"
        )

        return {"status": overall, "dependencies": dependencies}

    async def _run_check(self, name: str, check_function: Callable) -> dict[str, Any]:
        """Run a single health check with timeout."""
        try:
            result = await asyncio.wait_for(check_function(), timeout=self._timeout)
            return {"status": "healthy", **result}
        except TimeoutError:
            return {"status": "unhealthy", "error": "timeout"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
