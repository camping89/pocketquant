"""StrategyReconcileService — owns instance lifecycle + converges run-state.

A Kubernetes-style controller loop: every ``interval_s`` it reads each
subscription from Mongo and drives RAM toward it in three steps per tick:

  1. **Ensure instance** — a subscription with a valid template but no RAM
     instance gets one loaded (keyed by ``sub.id``).
  2. **Unload orphan** — a RAM instance keyed like a subscription id whose
     subscription doc is gone gets unloaded.
  3. **Converge run-state** — start/stop the instance to match ``desired_state``;
     mirror observed actual back to Mongo only on drift (no per-tick write churn).

Mongo is the single source of truth. Writers (bff) only persist subscription
docs; this loop materializes and tears down the RAM instances. That is why the
loop owns load/unload — after the app/bff split, ``add_symbol`` no longer loads,
so a continuous control-plane must.

Orphan-unload is shape-guarded: it only unloads keys matching the subscription
``deterministic_id`` shape (16 lowercase hex). Synthetic backtest instances
(``{code}::bt::{sub_id}``) never match, so concurrent backtests are never
clobbered.
"""

from __future__ import annotations

import asyncio
import re

from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY
from pocketquant.core.domain.strategy.value_objects import StrategyConfig
from pocketquant.core.domain.subscription import RunState, Subscription
from pocketquant.core.infra.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.engine.app_services.strategy_app_service import StrategyAppService

logger = get_logger(__name__)

# Subscription ids are 16 lowercase hex chars (Subscription.deterministic_id).
# Synthetic backtest ids ("{code}::bt::{sub_id}") never match this shape, so the
# orphan-unload pass that filters on it can never clobber a running backtest.
_SUB_ID_SHAPE = re.compile(r"^[0-9a-f]{16}$")


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
        """One pass: ensure instances, unload orphans, converge run-state."""
        subs = await self._sub_repo.list_all()
        sub_ids = {sub.id for sub in subs}

        await self._ensure_instances(subs)
        await self._unload_orphans(sub_ids)

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
                # A running sub whose instance still vanished after ensure —
                # genuine anomaly (e.g. unknown template). Warn ONCE on drift.
                if observed == "stopped" and sub.desired_state == "running":
                    logger.warning("reconcile.missing_instance", sub_id=sub.id)

        if started or stopped:
            logger.info("reconcile.converged", started=started, stopped=stopped)

    async def _ensure_instances(self, subs: list[Subscription]) -> None:
        """Load one instance per subscription that lacks a RAM instance.

        After the app/bff split, ``add_symbol`` only persists the subscription
        doc — this loop materializes the instance. Subscriptions whose template
        is unknown are skipped with a warning (mirrors rehydrate). ``load_strategy``
        is ``_lock``-guarded and raises if already loaded; a per-sub guard +
        try/except keeps one failure from starving the rest of the tick.
        """
        loaded = 0
        for sub in subs:
            if self._strategy_service.get_strategy(sub.id) is not None:
                continue
            strategy_class = STRATEGY_REGISTRY.get(sub.strategy_code)
            if strategy_class is None:
                logger.warning(
                    "reconcile.unknown_template",
                    sub_id=sub.id,
                    strategy_code=sub.strategy_code,
                )
                continue
            try:
                await self._strategy_service.load_strategy(
                    StrategyConfig(
                        id=sub.id,
                        name=sub.strategy_code,
                        symbol=sub.symbol,
                        interval=sub.interval.value,
                    ),
                    strategy_class=strategy_class,
                )
                loaded += 1
            except Exception as exc:
                logger.error("reconcile.load_failed", sub_id=sub.id, error=str(exc))

        if loaded:
            logger.info("reconcile.instances_loaded", count=loaded)

    async def _unload_orphans(self, sub_ids: set[str]) -> None:
        """Unload RAM instances whose subscription doc no longer exists.

        Shape-guarded: only keys matching the subscription ``deterministic_id``
        shape are eligible. Synthetic backtest instances (``{code}::bt::{sub_id}``)
        never match ``_SUB_ID_SHAPE``, so a concurrent backtest is never unloaded.
        """
        unloaded = 0
        for key in self._strategy_service.loaded_strategy_ids():
            if key in sub_ids:
                continue
            if not _SUB_ID_SHAPE.match(key):
                continue  # synthetic backtest id or other non-subscription key
            try:
                await self._strategy_service.unload_strategy(key)
                unloaded += 1
            except Exception as exc:
                logger.error("reconcile.unload_failed", sub_id=key, error=str(exc))

        if unloaded:
            logger.info("reconcile.orphans_unloaded", count=unloaded)

    async def _converge_one(self, sub_id: str, desired: RunState) -> RunState:
        """Drive one subscription toward ``desired``; return observed actual after.

        Missing RAM instance → observed stays stopped. After ``_ensure_instances``
        this only happens for an unknown-template sub; the gap is surfaced by the
        caller on drift only.
        """
        strategy = self._strategy_service.get_strategy(sub_id)

        if strategy is None:
            return "stopped"

        if desired == "running" and not strategy.is_running:
            await self._strategy_service.start_strategy(sub_id)
        elif desired == "stopped" and strategy.is_running:
            await self._strategy_service.stop_strategy(sub_id)

        return "running" if strategy.is_running else "stopped"
