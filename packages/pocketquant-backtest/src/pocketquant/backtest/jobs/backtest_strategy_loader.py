"""Helpers for backtest_jobs.py — build BacktestConfig and inject strategy into engine.

Extracted to keep backtest_jobs.py under 200 lines. Not intended for use outside jobs/.
"""

from __future__ import annotations

from datetime import date, timedelta

from pocketquant.backtest.optimization.models.backtest_config import BacktestConfig
from pocketquant.core.brokers.paper.paper_broker import PaperBroker
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.concepts.strategy.services import STRATEGY_REGISTRY
from pocketquant.core.concepts.strategy.value_objects import StrategyConfig
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.persistence.repositories.bar_repository import BarRepository
from pocketquant.execution.app_services.strategy_app_service import StrategyAppService

logger = get_logger(__name__)


async def resolve_date_range(
    bar_repo: BarRepository,
    symbol: str,
    interval: str,
) -> tuple[date, date]:
    """Return (start_date, end_date) from bar history, falling back to 365d window.

    ``symbol`` is composite ``{code}:{exchange}``.
    """
    try:
        docs = await bar_repo.find_datetimes(symbol, Interval(interval), None, None)
        if docs:
            start_dt = docs[0]["datetime"]
            end_dt = docs[-1]["datetime"]
            start = start_dt.date() if hasattr(start_dt, "date") else start_dt
            end = end_dt.date() if hasattr(end_dt, "date") else end_dt
            return start, end
    except Exception as exc:
        logger.warning("backtest_jobs.date_range_fallback", error=str(exc))

    today = date.today()
    return today - timedelta(days=365), today


def build_backtest_config(
    base_config: StrategyConfig,
    strategy_id: str,
    symbol: str,
    interval: str,
    start_date: date,
    end_date: date,
) -> BacktestConfig:
    """Build a BacktestConfig from base strategy config overriding symbol/interval.

    ``symbol`` is composite ``{code}:{exchange}``.
    """
    return BacktestConfig(
        strategy_code=strategy_id,
        symbol=symbol,
        interval=interval,
        start_date=start_date,
        end_date=end_date,
        initial_capital=10_000.0,
        parameters=dict(base_config.parameters) if base_config.parameters else {},
    )


async def load_strategy_for_backtest(
    strategy_app_service: StrategyAppService,
    base_config: StrategyConfig,
    strategy_id: str,
    sub_id: str,
    symbol: str,
    interval: str,
    event_bus: EventBus | None = None,
) -> tuple[PaperBroker, str]:
    """Resolve strategy class, create instance, inject into StrategyAppService.

    ``symbol`` is composite ``{code}:{exchange}``.

    Uses a synthetic strategy_id scoped to this subscription so concurrent jobs
    never clobber each other and the user's live strategy entry is untouched.

    Returns (broker, synthetic_id) so the caller can pass broker to BacktestAppService
    and later call unload_strategy(synthetic_id) for cleanup.

    Raises ValueError if strategy_id is not in STRATEGY_REGISTRY.
    """
    strategy_class = STRATEGY_REGISTRY.get(strategy_id)
    if strategy_class is None:
        raise ValueError(
            f"Unknown strategy '{strategy_id}' in STRATEGY_REGISTRY. "
            f"Available: {list(STRATEGY_REGISTRY.keys())}"
        )

    # Unique per-job id — prevents concurrent jobs from clobbering each other
    synthetic_id = f"{strategy_id}::bt::{sub_id}"

    bt_strategy_cfg = StrategyConfig(
        id=synthetic_id,
        name=base_config.name,
        symbol=symbol,
        interval=interval,
        trigger=base_config.trigger,
        broker="paper",
        parameters=dict(base_config.parameters) if base_config.parameters else {},
    )

    broker = PaperBroker(initial_balance=10_000.0, event_bus=event_bus)
    strategy_instance = strategy_class(bt_strategy_cfg)

    # Clean up any stale run for this synthetic id (e.g. previous failed cleanup)
    if strategy_app_service.get_strategy(synthetic_id) is not None:
        await strategy_app_service.unload_strategy(synthetic_id)

    await strategy_app_service.inject_prepared_strategy(
        synthetic_id, strategy_instance, broker, bt_strategy_cfg
    )

    return broker, synthetic_id
