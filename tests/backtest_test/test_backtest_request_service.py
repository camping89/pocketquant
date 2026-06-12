"""Pin BacktestCommandService + BacktestQueryService behavior.

Mirrors the old handler.handle() bodies so net behavior is preserved:
  - run: persists pending ``single`` BacktestRequest, returns request_id
  - optimize: builds OptimizationConfig, calls optimizer, saves result, returns it
  - run_all: enqueues one uuid7-keyed request per sub (dedup lives in the repo
    upsert on (sub_id, status=pending), not in the id)
  - run_all: raises 404 when no subscriptions found
  - get_result: returns BacktestResult or raises 404
  - list_results: delegates to backtest_repo.list_by_strategy_code
  - get_optimization: returns OptimizationResult or raises 404
  - get_request_status: returns poll dict or raises 404
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pocketquant.backtest.backtest_command_service import (
    BacktestCommandService,
    RunAllBacktestsCommand,
    RunBacktestCommand,
    RunOptimizationCommand,
)
from pocketquant.backtest.backtest_query_service import (
    BacktestQueryService,
    GetBacktestQuery,
    GetOptimizationQuery,
    ListBacktestsQuery,
)
from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.uuid import UUID

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cmd_svc(
    *,
    request_repo: Any = None,
    sub_repo: Any = None,
    event_bus: Any = None,
    backtest_repo: Any = None,
    bar_repo: Any = None,
    optimization_repo: Any = None,
) -> BacktestCommandService:
    return BacktestCommandService(
        backtest_request_repository=request_repo or MagicMock(),
        subscription_repository=sub_repo or MagicMock(),
        event_bus=event_bus or MagicMock(),
        backtest_repository=backtest_repo or MagicMock(),
        bar_repository=bar_repo or MagicMock(),
        optimization_repository=optimization_repo or MagicMock(),
    )


def _query_svc(
    *,
    backtest_repo: Any = None,
    request_repo: Any = None,
    optimization_repo: Any = None,
) -> BacktestQueryService:
    return BacktestQueryService(
        backtest_repository=backtest_repo or MagicMock(),
        backtest_request_repository=request_repo or MagicMock(),
        optimization_repository=optimization_repo or MagicMock(),
    )


def _run_cmd() -> RunBacktestCommand:
    return RunBacktestCommand(
        strategy_id="hitnrun2",
        symbol="BTCUSDT:BINANCE",
        interval="1h",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 6, 1),
        initial_capital=10_000.0,
        slippage_bps=10.0,
        commission_bps=10.0,
        parameters={"fast": 5},
    )


def _optimize_cmd() -> RunOptimizationCommand:
    return RunOptimizationCommand(
        strategy_id="hitnrun2",
        symbol="BTCUSDT:BINANCE",
        interval="1h",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 6, 1),
        parameter_grid={"fast": [5, 10]},
    )


def _fake_sub(sub_id: str = "sub-1", strategy_code: str = "hitnrun2") -> MagicMock:
    sub = MagicMock()
    sub.id = sub_id
    sub.strategy_code = strategy_code
    return sub


def _fake_backtest_result(run_id: str = "run-1") -> MagicMock:
    result = MagicMock()
    result.id = run_id
    return result


def _fake_optimization_result(opt_id: str = "opt-1") -> MagicMock:
    result = MagicMock()
    result.id = opt_id
    return result


def _fake_request(request_id: str = "req-1", status: str = "pending") -> MagicMock:
    req = MagicMock()
    req.id = request_id
    req.status = status
    req.result = None
    req.error = None
    return req


# ---------------------------------------------------------------------------
# BacktestCommandService.run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_enqueues_single_request_and_returns_request_id() -> None:
    request_repo = MagicMock()
    request_repo.enqueue = AsyncMock(side_effect=lambda r: str(r.id))
    svc = _cmd_svc(request_repo=request_repo)

    result = await svc.run(_run_cmd())

    request_repo.enqueue.assert_awaited_once()
    persisted = request_repo.enqueue.await_args.args[0]
    assert persisted.kind == "single"
    assert persisted.status == "pending"
    assert persisted.strategy_code == "hitnrun2"
    assert persisted.config is not None
    # FE contract: request_id is the uuid string form of the persisted id.
    assert result["request_id"] == str(persisted.id)


@pytest.mark.asyncio
async def test_run_serialises_dates_to_iso_strings() -> None:
    request_repo = MagicMock()
    request_repo.enqueue = AsyncMock(side_effect=lambda r: str(r.id))
    svc = _cmd_svc(request_repo=request_repo)

    await svc.run(_run_cmd())

    config = request_repo.enqueue.await_args.args[0].config
    assert config["start_date"] == "2024-01-01"
    assert config["end_date"] == "2024-06-01"


@pytest.mark.asyncio
async def test_run_defaults_empty_parameters_to_dict() -> None:
    request_repo = MagicMock()
    request_repo.enqueue = AsyncMock(side_effect=lambda r: str(r.id))
    svc = _cmd_svc(request_repo=request_repo)

    cmd = RunBacktestCommand(
        strategy_id="hitnrun2",
        symbol="BTCUSDT:BINANCE",
        interval="1h",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 6, 1),
        parameters=None,
    )
    await svc.run(cmd)

    config = request_repo.enqueue.await_args.args[0].config
    assert config["parameters"] == {}


# ---------------------------------------------------------------------------
# BacktestCommandService.optimize
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_optimize_saves_result_and_returns_it() -> None:
    optimization_repo = MagicMock()
    optimization_repo.save = AsyncMock()

    fake_result = _fake_optimization_result()

    with patch(
        "pocketquant.backtest.backtest_command_service.GridOptimizationAppService"
    ) as mock_optimizer:
        instance = mock_optimizer.return_value
        instance.optimize = AsyncMock(return_value=fake_result)

        svc = _cmd_svc(optimization_repo=optimization_repo)
        result = await svc.optimize(_optimize_cmd())

    optimization_repo.save.assert_awaited_once_with(fake_result)
    assert result is fake_result


@pytest.mark.asyncio
async def test_optimize_builds_correct_config() -> None:
    optimization_repo = MagicMock()
    optimization_repo.save = AsyncMock()
    fake_result = _fake_optimization_result()

    with patch(
        "pocketquant.backtest.backtest_command_service.GridOptimizationAppService"
    ) as mock_optimizer:
        instance = mock_optimizer.return_value
        instance.optimize = AsyncMock(return_value=fake_result)

        svc = _cmd_svc(optimization_repo=optimization_repo)
        await svc.optimize(_optimize_cmd())

        assert instance.optimize.await_args is not None
        received_config = instance.optimize.await_args.args[0]

    assert received_config.strategy_code == "hitnrun2"
    assert received_config.parameter_grid == {"fast": [5, 10]}
    assert received_config.target_metric == "sharpe_ratio"


# ---------------------------------------------------------------------------
# BacktestCommandService.run_all
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_all_enqueues_one_request_per_subscription() -> None:
    sub_repo = MagicMock()
    sub_repo.list_by_strategy_code = AsyncMock(
        return_value=[_fake_sub("sub-1"), _fake_sub("sub-2")]
    )
    request_repo = MagicMock()
    # Repo returns the persisted doc's id (may differ from the candidate when
    # an existing pending doc absorbs the enqueue) — run_all echoes it to FE.
    request_repo.enqueue = AsyncMock(side_effect=lambda r: str(r.id))

    svc = _cmd_svc(sub_repo=sub_repo, request_repo=request_repo)
    result = await svc.run_all(RunAllBacktestsCommand(strategy_id="hitnrun2"))

    assert request_repo.enqueue.await_count == 2
    assert len(result["job_ids"]) == 2
    for job_id in result["job_ids"]:
        assert UUID(job_id).version == 7


@pytest.mark.asyncio
async def test_run_all_uses_uuid_ids_no_bt_prefix() -> None:
    """Request ids are uuid7 — dedup is the repo's (sub_id, pending) upsert,
    not a deterministic id."""
    sub_repo = MagicMock()
    sub_repo.list_by_strategy_code = AsyncMock(return_value=[_fake_sub("sub-abc")])
    request_repo = MagicMock()
    request_repo.enqueue = AsyncMock(side_effect=lambda r: str(r.id))

    svc = _cmd_svc(sub_repo=sub_repo, request_repo=request_repo)
    result = await svc.run_all(RunAllBacktestsCommand(strategy_id="hitnrun2"))

    persisted = request_repo.enqueue.await_args.args[0]
    assert not str(persisted.id).startswith("bt:")
    assert UUID(str(persisted.id)).version == 7
    assert persisted.kind == "subscription"
    assert persisted.sub_id == "sub-abc"
    # job_ids echo the id the repo persisted, not the candidate.
    assert result["job_ids"] == [str(persisted.id)]


@pytest.mark.asyncio
async def test_run_all_raises_404_when_no_subscriptions() -> None:
    sub_repo = MagicMock()
    sub_repo.list_by_strategy_code = AsyncMock(return_value=[])
    svc = _cmd_svc(sub_repo=sub_repo)

    with pytest.raises(NotFoundError):
        await svc.run_all(RunAllBacktestsCommand(strategy_id="unknown"))


# ---------------------------------------------------------------------------
# BacktestQueryService.get_result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_result_returns_backtest_result() -> None:
    backtest_repo = MagicMock()
    backtest_repo.get = AsyncMock(return_value=_fake_backtest_result("run-1"))
    svc = _query_svc(backtest_repo=backtest_repo)

    result = await svc.get_result(GetBacktestQuery(run_id="run-1"))

    backtest_repo.get.assert_awaited_once_with("run-1")
    assert result.id == "run-1"


@pytest.mark.asyncio
async def test_get_result_raises_404_when_not_found() -> None:
    backtest_repo = MagicMock()
    backtest_repo.get = AsyncMock(return_value=None)
    svc = _query_svc(backtest_repo=backtest_repo)

    with pytest.raises(NotFoundError):
        await svc.get_result(GetBacktestQuery(run_id="missing"))


# ---------------------------------------------------------------------------
# BacktestQueryService.list_results
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_results_delegates_to_repo() -> None:
    backtest_repo = MagicMock()
    backtest_repo.list_by_strategy_code = AsyncMock(
        return_value=[_fake_backtest_result("r1"), _fake_backtest_result("r2")]
    )
    svc = _query_svc(backtest_repo=backtest_repo)

    results = await svc.list_results(
        ListBacktestsQuery(strategy_id="hitnrun2", limit=5, include_failed=True)
    )

    backtest_repo.list_by_strategy_code.assert_awaited_once_with(
        strategy_code="hitnrun2", limit=5, include_failed=True
    )
    assert len(results) == 2


# ---------------------------------------------------------------------------
# BacktestQueryService.get_optimization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_optimization_returns_result() -> None:
    optimization_repo = MagicMock()
    optimization_repo.get = AsyncMock(return_value=_fake_optimization_result("opt-1"))
    svc = _query_svc(optimization_repo=optimization_repo)

    result = await svc.get_optimization(GetOptimizationQuery(optimization_id="opt-1"))

    optimization_repo.get.assert_awaited_once_with("opt-1")
    assert result.id == "opt-1"


@pytest.mark.asyncio
async def test_get_optimization_raises_404_when_not_found() -> None:
    optimization_repo = MagicMock()
    optimization_repo.get = AsyncMock(return_value=None)
    svc = _query_svc(optimization_repo=optimization_repo)

    with pytest.raises(NotFoundError):
        await svc.get_optimization(GetOptimizationQuery(optimization_id="missing"))


# ---------------------------------------------------------------------------
# BacktestQueryService.get_request_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_request_status_returns_poll_dict() -> None:
    request_repo = MagicMock()
    request_repo.get = AsyncMock(return_value=_fake_request("req-1", "done"))
    svc = _query_svc(request_repo=request_repo)

    result = await svc.get_request_status("req-1")

    assert result["request_id"] == "req-1"
    assert result["status"] == "done"
    assert result["result"] is None
    assert result["error"] is None


@pytest.mark.asyncio
async def test_get_request_status_raises_404_when_not_found() -> None:
    request_repo = MagicMock()
    request_repo.get = AsyncMock(return_value=None)
    svc = _query_svc(request_repo=request_repo)

    with pytest.raises(NotFoundError):
        await svc.get_request_status("missing")
