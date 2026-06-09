"""StrategyReconcileService — converges desired_state (Mongo) toward actual (RAM).

A Kubernetes-style controller loop: every ``interval_s`` it reads each
subscription's ``desired_state`` from Mongo, compares against the live
``StrategyAppService`` instance's run-state, and calls ``start_strategy`` /
``stop_strategy`` to converge. Observed actual is mirrored back to Mongo only on
drift (no per-tick write churn).

Subscription-driven by construction: it iterates ``sub_repo.list_all()`` and
only ever touches instances keyed by ``sub.id``. It never enumerates RAM, so
injected backtest strategies (synthetic ids, no sub row) are invisible to it.

Reconcile never loads strategies — instance creation stays in rehydrate /
add_symbol. A ``desired=running`` sub with no RAM instance is a warning, not a
load attempt; its actual is recorded as ``stopped`` so the gap is observable.
"""

from __future__ import annotations

import asyncio

from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.subscription import RunState
from pocketquant.execution.app_services.strategy_app_service import StrategyAppService
from pocketquant.infrastructure.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)

logger = get_logger(__name__)


class StrategyReconcileService:
    """Poll loop reconciling subscription desired_state vs live engine state.

    Args:
        sub_repo: Subscription persistence (desired_state source, actual_state sink).
        strategy_service: Live engine; start/stop are ``_lock``-guarded + idempotent.
        interval_s: Seconds between reconcile ticks (default 5.0).
    """

    def __init__(
        self,
        sub_repo: SubscriptionRepository,
        strategy_service: StrategyAppService,
        interval_s: float = 5.0,
    ) -> None:
        self._sub_repo = sub_repo
        self._strategy_service = strategy_service
        self._interval_s = interval_s

    async def run(self) -> None:
        """Reconcile loop. Runs until cancelled by lifespan shutdown."""
        logger.info("reconcile.started", interval_s=self._interval_s)

        while True:
            try:
                await self._reconcile()
            except asyncio.CancelledError:
                logger.info("reconcile.cancelled")
                raise
            except Exception as exc:
                # Per-tick backstop — never crash the app; retry next tick.
                logger.error("reconcile.failed", error=str(exc))

            await asyncio.sleep(self._interval_s)

    async def _reconcile(self) -> None:
        """One convergence pass over all subscriptions."""
        subs = await self._sub_repo.list_all()

        started = 0
        stopped = 0
        for sub in subs:
            # Per-sub isolation: a single failing sub must not starve the rest
            # of this tick. start/stop already lock + early-return on no-op.
            try:
                observed = await self._converge_one(sub.id, sub.desired_state)
            except Exception as exc:
                logger.error("reconcile.sub_failed", sub_id=sub.id, error=str(exc))
                continue

            # Mirror observed actual back to Mongo only when the stored value
            # drifts — keeps the loop idempotent (no per-tick write churn).
            if observed != sub.actual_state:
                await self._sub_repo.update_actual_state(sub.id, observed)
                if observed == "running":
                    started += 1
                else:
                    stopped += 1
                # A running sub whose instance vanished is a genuine anomaly —
                # warn ONCE on the drift, not every tick (a legacy sub that never
                # had an instance already reads desired=running/actual=stopped via
                # the API, so it needs no per-tick log).
                if observed == "stopped" and sub.desired_state == "running":
                    logger.warning("reconcile.missing_instance", sub_id=sub.id)

        if started or stopped:
            logger.info("reconcile.converged", started=started, stopped=stopped)

    async def _converge_one(self, sub_id: str, desired: RunState) -> RunState:
        """Drive one subscription toward ``desired``; return observed actual after.

        Missing RAM instance → observed stays stopped (reconcile never loads;
        rehydrate/add_symbol own instance creation). The missing-instance anomaly
        is surfaced by the caller, on drift only.
        """
        strategy = self._strategy_service.get_strategy(sub_id)

        if strategy is None:
            return "stopped"

        if desired == "running" and not strategy.is_running:
            await self._strategy_service.start_strategy(sub_id)
        elif desired == "stopped" and strategy.is_running:
            await self._strategy_service.stop_strategy(sub_id)

        return "running" if strategy.is_running else "stopped"
