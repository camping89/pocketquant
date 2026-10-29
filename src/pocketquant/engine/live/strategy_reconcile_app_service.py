from __future__ import annotations

import asyncio

from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.risk import RiskConfig
from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY
from pocketquant.core.domain.strategy.value_objects import StrategyConfig
from pocketquant.core.domain.subscription import RunState, Subscription
from pocketquant.core.domain.symbol import LINEAR_SPEC
from pocketquant.core.infra.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.core.infra.persistence.symbol_lookup_helper import SymbolLookupHelper
from pocketquant.engine.strategy.strategy_app_service import StrategyAppService

logger = get_logger(__name__)


# Mongo is the source of truth. Routes only persist subscription docs, and
# add_symbol does not load an instance, so this loop owns load and unload.
# Backtests run in their own sandbox, so every key in this engine is a
# subscription id.
class StrategyReconcileAppService:
    def __init__(
        self,
        sub_repo: SubscriptionRepository,
        strategy_service: StrategyAppService,
        interval_s: float = 5.0,
        # Without symbol_lookup every instance loads linear, which is only right for crypto.
        symbol_lookup: SymbolLookupHelper | None = None,
        exness_risk: RiskConfig | None = None,
        futures_paper_risk: RiskConfig | None = None,
    ) -> None:
        self._sub_repo = sub_repo
        self._strategy_service = strategy_service
        self._interval_s = interval_s
        self._symbol_lookup = symbol_lookup
        self._exness_risk = exness_risk
        self._futures_paper_risk = futures_paper_risk
        # Subscriptions already reported as unloadable: the loop retries every
        # tick, so the failure is logged once, not every five seconds.
        self._reported: set[str] = set()

    # Runs in the trader role before the lease: brokers stay disconnected until the
    # lease is held. It reuses _ensure_instances so the boot path and the loop cannot
    # drift; actual_state is written only by the loop.
    async def bootstrap(self) -> None:
        subs = await self._sub_repo.list_all()
        if not subs:
            return
        await self._ensure_instances(subs)
        for sub in subs:
            if sub.desired_state != "running":
                continue
            try:
                await self._strategy_service.start_strategy(str(sub.id))
            except Exception as exc:
                logger.error("reconcile.sub_failed", sub_id=str(sub.id), error=str(exc))
        logger.info("live_instances_bootstrapped", subscriptions=len(subs))

    async def run(self) -> None:
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
        subs = await self._sub_repo.list_all()
        # RAM instance keys are strings — stringify ids once for membership tests.
        sub_ids = {str(sub.id) for sub in subs}

        await self._ensure_instances(subs)
        await self._unload_orphans(sub_ids)

        started = 0
        stopped = 0
        for sub in subs:
            sub_id = str(sub.id)
            # Per-sub isolation: a single failing sub must not starve the rest
            # of this tick. start/stop already lock + early-return on no-op.
            try:
                observed = await self._converge_one(sub_id, sub.desired_state)
            except Exception as exc:
                logger.error("reconcile.sub_failed", sub_id=sub_id, error=str(exc))
                continue

            # Mirror observed actual back to Mongo only when the stored value
            # drifts — keeps the loop idempotent (no per-tick write churn).
            if observed != sub.actual_state:
                await self._sub_repo.update_actual_state(sub_id, observed)
                if observed == "running":
                    started += 1
                else:
                    stopped += 1
                # A running sub whose instance still vanished after ensure —
                # genuine anomaly (e.g. unknown template). Warn ONCE on drift.
                if observed == "stopped" and sub.desired_state == "running":
                    logger.warning("reconcile.missing_instance", sub_id=sub_id)

        if started or stopped:
            logger.info("reconcile.converged", started=started, stopped=stopped)

    # load_strategy is _lock-guarded and raises if already loaded; the per-sub guard
    # and try/except keep one failure from starving the rest of the tick.
    async def _ensure_instances(self, subs: list[Subscription]) -> None:
        loaded = 0
        for sub in subs:
            sub_id = str(sub.id)
            if self._strategy_service.get_strategy(sub_id) is not None:
                continue
            strategy_class = STRATEGY_REGISTRY.get(sub.strategy_code)
            if strategy_class is None:
                if sub_id not in self._reported:
                    self._reported.add(sub_id)
                    logger.warning(
                        "reconcile.unknown_template",
                        sub_id=sub_id,
                        strategy_code=sub.strategy_code,
                    )
                continue
            try:
                contract_spec = (
                    await self._symbol_lookup.contract_spec(sub.symbol)
                    if self._symbol_lookup
                    else LINEAR_SPEC
                )
                risk = RiskConfig()
                if sub.broker == "exness" and self._exness_risk:
                    risk = self._exness_risk
                elif (
                    sub.broker == "paper" and contract_spec.is_contract and self._futures_paper_risk
                ):
                    risk = self._futures_paper_risk
                await self._strategy_service.load_strategy(
                    StrategyConfig(
                        id=sub_id,
                        name=sub.strategy_code,
                        symbol=sub.symbol,
                        interval=sub.interval.value,
                        contract_spec=contract_spec,
                        broker=sub.broker,
                        risk=risk,
                    ),
                    strategy_class=strategy_class,
                )
                loaded += 1
                self._reported.discard(sub_id)
            except Exception as exc:
                if sub_id not in self._reported:
                    self._reported.add(sub_id)
                    logger.error("reconcile.load_failed", sub_id=sub_id, error=str(exc))

        if loaded:
            logger.info("reconcile.instances_loaded", count=loaded)

    async def _unload_orphans(self, sub_ids: set[str]) -> None:
        unloaded = 0
        for key in self._strategy_service.loaded_strategy_ids():
            if key in sub_ids:
                continue
            try:
                await self._strategy_service.unload_strategy(key)
                unloaded += 1
            except Exception as exc:
                logger.error("reconcile.unload_failed", sub_id=key, error=str(exc))

        if unloaded:
            logger.info("reconcile.orphans_unloaded", count=unloaded)

    # After _ensure_instances a missing instance means an unknown template; it reports
    # stopped, and the caller surfaces the gap only on drift.
    async def _converge_one(self, sub_id: str, desired: RunState) -> RunState:
        strategy = self._strategy_service.get_strategy(sub_id)

        if strategy is None:
            return "stopped"

        if desired == "running" and not strategy.is_running:
            await self._strategy_service.start_strategy(sub_id)
        elif desired == "stopped" and strategy.is_running:
            await self._strategy_service.stop_strategy(sub_id)

        return "running" if strategy.is_running else "stopped"
