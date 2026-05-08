"""Unit tests for audit_bar_quality.py — mock Mongo, no real DB connections.

Covers:
- Pipeline construction: correct $match filter stages (date range, symbol, exchange)
- Markdown render: correct table rows from sample aggregation results
- Exit 1 on Mongo connection failure
- --symbol / --exchange filter propagation into pipeline
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.audit_bar_quality import (
    ABNORMAL_VOLUME_THRESHOLD,
    _build_pipeline,
    _render_markdown,
    parse_args,
    run_audit,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_agg_row(
    symbol: str = "BTCUSDT",
    exchange: str = "BINANCE",
    interval: str = "1m",
    total: int = 1000,
    flat_bars: int = 50,
    zero_volume: int = 10,
    abnormal_volume: int = 2,
) -> dict:
    return {
        "_id": {"symbol": symbol, "exchange": exchange, "interval": interval},
        "total": total,
        "flat_bars": flat_bars,
        "zero_volume": zero_volume,
        "abnormal_volume": abnormal_volume,
    }


_NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)
_START = _NOW - timedelta(days=730)


# ---------------------------------------------------------------------------
# Pipeline construction
# ---------------------------------------------------------------------------

class TestBuildPipeline:
    def test_match_stage_includes_date_range(self) -> None:
        pipeline = _build_pipeline(_START, _NOW, symbol=None, exchange=None)
        match = pipeline[0]["$match"]
        assert "$gte" in match["datetime"]
        assert "$lt" in match["datetime"]
        assert match["datetime"]["$gte"] == _START
        assert match["datetime"]["$lt"] == _NOW

    def test_match_stage_filters_symbol_and_exchange(self) -> None:
        pipeline = _build_pipeline(_START, _NOW, symbol="BTCUSDT", exchange="BINANCE")
        match = pipeline[0]["$match"]
        assert match["symbol"] == "BTCUSDT"
        assert match["exchange"] == "BINANCE"

    def test_no_symbol_filter_omits_symbol_key(self) -> None:
        pipeline = _build_pipeline(_START, _NOW, symbol=None, exchange=None)
        match = pipeline[0]["$match"]
        assert "symbol" not in match
        assert "exchange" not in match

    def test_group_stage_counts_flat_bars(self) -> None:
        pipeline = _build_pipeline(_START, _NOW, symbol=None, exchange=None)
        group = pipeline[1]["$group"]
        # flat_bars uses $cond with O==H==L==C checks
        flat_expr = group["flat_bars"]
        assert "$sum" in flat_expr
        cond = flat_expr["$sum"]["$cond"]
        condition = cond[0]
        assert "$and" in condition
        # Three equality checks
        assert len(condition["$and"]) == 3

    def test_group_stage_counts_zero_volume(self) -> None:
        pipeline = _build_pipeline(_START, _NOW, symbol=None, exchange=None)
        group = pipeline[1]["$group"]
        zero_expr = group["zero_volume"]
        assert "$sum" in zero_expr

    def test_group_stage_counts_abnormal_volume(self) -> None:
        pipeline = _build_pipeline(_START, _NOW, symbol=None, exchange=None)
        group = pipeline[1]["$group"]
        abnormal_expr = group["abnormal_volume"]
        assert "$sum" in abnormal_expr
        # Must reference ABNORMAL_VOLUME_THRESHOLD constant
        cond = abnormal_expr["$sum"]["$cond"]
        gt_condition = cond[0]
        assert gt_condition == {"$gt": ["$volume", ABNORMAL_VOLUME_THRESHOLD]}

    def test_sort_stage_present(self) -> None:
        pipeline = _build_pipeline(_START, _NOW, symbol=None, exchange=None)
        sort = pipeline[2]["$sort"]
        assert "_id.exchange" in sort
        assert "_id.symbol" in sort

    def test_pipeline_has_three_stages(self) -> None:
        pipeline = _build_pipeline(_START, _NOW, symbol=None, exchange=None)
        assert len(pipeline) == 3  # $match, $group, $sort

    def test_symbol_uppercased_in_filter(self) -> None:
        pipeline = _build_pipeline(_START, _NOW, symbol="btcusdt", exchange="binance")
        match = pipeline[0]["$match"]
        assert match["symbol"] == "BTCUSDT"
        assert match["exchange"] == "BINANCE"


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

class TestRenderMarkdown:
    def test_renders_header_and_table(self) -> None:
        rows = [_sample_agg_row()]
        md = _render_markdown(rows, _START, _NOW, days=730)
        assert "# Bar Quality Audit" in md
        assert "| Symbol |" in md
        assert "BTCUSDT" in md
        assert "BINANCE" in md

    def test_flat_percentage_calculated_correctly(self) -> None:
        rows = [_sample_agg_row(total=1000, flat_bars=50)]
        md = _render_markdown(rows, _START, _NOW, days=730)
        assert "5.0%" in md

    def test_zero_volume_percentage_calculated_correctly(self) -> None:
        rows = [_sample_agg_row(total=200, zero_volume=10)]
        md = _render_markdown(rows, _START, _NOW, days=730)
        assert "5.0%" in md

    def test_empty_rows_renders_placeholder(self) -> None:
        md = _render_markdown([], _START, _NOW, days=730)
        assert "—" in md

    def test_multiple_rows_all_present(self) -> None:
        rows = [
            _sample_agg_row(symbol="BTCUSDT", interval="1m"),
            _sample_agg_row(symbol="ETHUSDT", interval="5m"),
        ]
        md = _render_markdown(rows, _START, _NOW, days=730)
        assert "BTCUSDT" in md
        assert "ETHUSDT" in md
        assert "5m" in md

    def test_window_info_in_header(self) -> None:
        md = _render_markdown([], _START, _NOW, days=730)
        assert "730d" in md

    def test_abnormal_volume_threshold_in_header(self) -> None:
        md = _render_markdown([], _START, _NOW, days=730)
        assert str(int(ABNORMAL_VOLUME_THRESHOLD)) in md


# ---------------------------------------------------------------------------
# run_audit: exit 1 on Mongo connection failure
# ---------------------------------------------------------------------------

class TestRunAuditErrorHandling:
    @pytest.mark.asyncio
    async def test_exit_1_on_mongo_connection_failure(self, tmp_path: Path) -> None:
        """run_audit returns 1 when Database.connect() raises."""
        args = parse_args(["--days", "730", "--output", str(tmp_path / "out.md")])

        mock_settings = MagicMock()
        mock_settings.mongodb_url = "mongodb://localhost:27017"
        mock_settings.mongodb_database = "test"
        mock_settings.mongodb_min_pool_size = 1
        mock_settings.mongodb_max_pool_size = 5

        with (
            patch("scripts.audit_bar_quality.get_settings", return_value=mock_settings),
            patch("scripts.audit_bar_quality.setup_logging"),
            patch(
                "scripts.audit_bar_quality.Database.connect",
                new_callable=AsyncMock,
                side_effect=ConnectionError("Mongo unreachable"),
            ),
        ):
            result = await run_audit(args)

        assert result == 1

    @pytest.mark.asyncio
    async def test_exit_0_and_saves_report_on_success(self, tmp_path: Path) -> None:
        """run_audit returns 0 and writes report when aggregation succeeds."""
        output_path = tmp_path / "out.md"
        args = parse_args(["--days", "30", "--output", str(output_path)])

        mock_settings = MagicMock()
        sample_rows = [_sample_agg_row()]

        class _FakeCursor:
            """Async iterable cursor — awaiting aggregate() returns this."""

            def __aiter__(self):
                return self

            async def __anext__(self):
                if not self._items:
                    raise StopAsyncIteration
                return self._items.pop(0)

            def __init__(self, items: list) -> None:
                self._items = list(items)

        # aggregate() is awaited in production code (pymongo 4.16 coroutine pattern)
        mock_collection = MagicMock()
        mock_collection.aggregate = AsyncMock(return_value=_FakeCursor(sample_rows))

        mock_db = MagicMock()
        mock_db.connect = AsyncMock()
        mock_db.disconnect = AsyncMock()
        mock_db.get_collection.return_value = mock_collection

        with (
            patch("scripts.audit_bar_quality.get_settings", return_value=mock_settings),
            patch("scripts.audit_bar_quality.setup_logging"),
            patch("scripts.audit_bar_quality.Database", return_value=mock_db),
        ):
            result = await run_audit(args)

        assert result == 0
        assert output_path.exists()
        content = output_path.read_text()
        assert "BTCUSDT" in content

    @pytest.mark.asyncio
    async def test_symbol_filter_passed_to_pipeline(self, tmp_path: Path) -> None:
        """--symbol arg propagates into the aggregation pipeline $match."""
        output_path = tmp_path / "out.md"
        args = parse_args(
            ["--symbol", "ETHUSDT", "--exchange", "BINANCE", "--output", str(output_path)]
        )

        called_pipelines: list[list] = []

        class _EmptyCursor:
            def __aiter__(self):
                return aiter([])

        async def _fake_aggregate(pipeline, **_kw):
            # aggregate() is awaited — must be a coroutine returning an async iterable
            called_pipelines.append(pipeline)
            return _EmptyCursor()

        mock_collection = MagicMock()
        mock_collection.aggregate = _fake_aggregate

        mock_db = MagicMock()
        mock_db.connect = AsyncMock()
        mock_db.disconnect = AsyncMock()
        mock_db.get_collection.return_value = mock_collection

        with (
            patch("scripts.audit_bar_quality.get_settings", return_value=MagicMock()),
            patch("scripts.audit_bar_quality.setup_logging"),
            patch("scripts.audit_bar_quality.Database", return_value=mock_db),
        ):
            await run_audit(args)

        assert called_pipelines, "aggregate must have been called"
        match_stage = called_pipelines[0][0]["$match"]
        assert match_stage["symbol"] == "ETHUSDT"
        assert match_stage["exchange"] == "BINANCE"


# ---------------------------------------------------------------------------
# parse_args defaults
# ---------------------------------------------------------------------------

class TestParseArgs:
    def test_default_days_is_730(self) -> None:
        args = parse_args([])
        assert args.days == 730

    def test_custom_days(self) -> None:
        args = parse_args(["--days", "90"])
        assert args.days == 90

    def test_symbol_and_exchange_defaults_to_none(self) -> None:
        args = parse_args([])
        assert args.symbol is None
        assert args.exchange is None
