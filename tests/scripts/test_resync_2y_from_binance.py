"""Unit tests for resync_2y_from_binance.py — mock BinanceClient + BarRepository.

Covers:
- Window calculation: end_dt = floor(now,1min) - 1s; start_dt = end - 730d
- Checkpoint resume: pre-populated checkpoint causes symbol to be skipped
- Dry-run: no delete_many_by_range / insert_many calls made
- Per-symbol orchestration: call order delete → fetch → insert → cascade
- Cascade skip with --no-cascade
- Non-Binance symbols skipped with warning
- Symbol filter (--symbols) narrows processing set
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.resync_2y_from_binance import (
    CANONICAL_TFS,
    _compute_window,
    _estimate_wall_time,
    _load_checkpoint,
    _save_checkpoint,
    parse_args,
    run_resync,
)


def _make_tracked_symbol(symbol: str = "BTCUSDT", exchange: str = "BINANCE") -> MagicMock:
    ts = MagicMock()
    ts.symbol = symbol
    ts.exchange = exchange
    return ts


def _make_bar(
    symbol: str = "BTCUSDT",
    dt: datetime | None = None,
) -> MagicMock:
    bar = MagicMock()
    bar.symbol = symbol
    # Default: well in the past so it always passes the end_dt filter
    bar.datetime = dt if dt is not None else datetime(2020, 1, 1, tzinfo=UTC)
    return bar


_FROZEN_NOW = datetime(2026, 5, 8, 14, 30, 45, 123456, tzinfo=UTC)


class TestComputeWindow:
    def test_end_dt_is_floored_minute_minus_1_second(self) -> None:
        with patch("scripts.resync_2y_from_binance.datetime") as mock_dt:
            mock_dt.now.return_value = _FROZEN_NOW
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            start_dt, end_dt = _compute_window(730)

        # end = floor(now,1min) - 1s = 2026-05-08T14:30:00Z - 1s = 2026-05-08T14:29:59Z
        expected_end = _FROZEN_NOW.replace(second=0, microsecond=0) - timedelta(seconds=1)
        assert end_dt == expected_end

    def test_start_dt_is_end_minus_days(self) -> None:
        with patch("scripts.resync_2y_from_binance.datetime") as mock_dt:
            mock_dt.now.return_value = _FROZEN_NOW
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            start_dt, end_dt = _compute_window(730)

        assert end_dt - start_dt == timedelta(days=730)

    def test_30_day_window(self) -> None:
        with patch("scripts.resync_2y_from_binance.datetime") as mock_dt:
            mock_dt.now.return_value = _FROZEN_NOW
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            start_dt, end_dt = _compute_window(30)

        assert end_dt - start_dt == timedelta(days=30)


class TestCheckpoint:
    def test_load_missing_checkpoint_returns_empty_dict(self, tmp_path: Path) -> None:
        with patch("scripts.resync_2y_from_binance.CHECKPOINT_PATH", tmp_path / "ckpt.json"):
            result = _load_checkpoint()
        assert result == {}

    def test_load_valid_checkpoint(self, tmp_path: Path) -> None:
        ckpt = tmp_path / "ckpt.json"
        ckpt.write_text(json.dumps({"BTCUSDT": "done"}))
        with patch("scripts.resync_2y_from_binance.CHECKPOINT_PATH", ckpt):
            result = _load_checkpoint()
        assert result == {"BTCUSDT": "done"}

    def test_load_corrupt_checkpoint_returns_empty_dict(self, tmp_path: Path) -> None:
        ckpt = tmp_path / "ckpt.json"
        ckpt.write_text("not valid json{{")
        with patch("scripts.resync_2y_from_binance.CHECKPOINT_PATH", ckpt):
            result = _load_checkpoint()
        assert result == {}

    def test_save_and_reload_roundtrip(self, tmp_path: Path) -> None:
        ckpt = tmp_path / "ckpt.json"
        data = {"BTCUSDT": "done", "ETHUSDT": "done"}
        with patch("scripts.resync_2y_from_binance.CHECKPOINT_PATH", ckpt):
            _save_checkpoint(data)
            loaded = _load_checkpoint()
        assert loaded == data


class TestDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_makes_no_db_calls(self, tmp_path: Path, capsys) -> None:
        args = parse_args(["--dry-run", "--days", "730"])

        mock_tracked = [_make_tracked_symbol("BTCUSDT", "BINANCE")]
        mock_db = MagicMock()
        mock_db.connect = AsyncMock()
        mock_db.disconnect = AsyncMock()

        mock_tracked_repo = MagicMock()
        mock_tracked_repo.list_all = AsyncMock(return_value=mock_tracked)

        mock_bar_repo = MagicMock()
        mock_bar_repo.delete_many_by_range = AsyncMock()
        mock_bar_repo.insert_many = AsyncMock()

        with (
            patch("scripts.resync_2y_from_binance.get_settings", return_value=MagicMock()),
            patch("scripts.resync_2y_from_binance.setup_logging"),
            patch("scripts.resync_2y_from_binance.Database", return_value=mock_db),
            patch(
                "scripts.resync_2y_from_binance.TrackedSymbolRepository",
                return_value=mock_tracked_repo,
            ),
            patch("scripts.resync_2y_from_binance.BarRepository", return_value=mock_bar_repo),
        ):
            result = await run_resync(args)

        assert result == 0
        mock_bar_repo.delete_many_by_range.assert_not_called()
        mock_bar_repo.insert_many.assert_not_called()

    @pytest.mark.asyncio
    async def test_dry_run_prints_plan(self, capsys) -> None:
        args = parse_args(["--dry-run", "--days", "365"])

        mock_tracked = [
            _make_tracked_symbol("BTCUSDT", "BINANCE"),
            _make_tracked_symbol("ETHUSDT", "BINANCE"),
        ]
        mock_db = MagicMock()
        mock_db.connect = AsyncMock()
        mock_db.disconnect = AsyncMock()
        mock_tracked_repo = MagicMock()
        mock_tracked_repo.list_all = AsyncMock(return_value=mock_tracked)

        with (
            patch("scripts.resync_2y_from_binance.get_settings", return_value=MagicMock()),
            patch("scripts.resync_2y_from_binance.setup_logging"),
            patch("scripts.resync_2y_from_binance.Database", return_value=mock_db),
            patch(
                "scripts.resync_2y_from_binance.TrackedSymbolRepository",
                return_value=mock_tracked_repo,
            ),
        ):
            await run_resync(args)

        out = capsys.readouterr().out
        assert "DRY RUN" in out
        assert "BTCUSDT" in out
        assert "365" in out


class TestCheckpointResume:
    @pytest.mark.asyncio
    async def test_done_symbol_is_skipped(self, tmp_path: Path) -> None:
        """Symbol marked 'done' in checkpoint must not trigger delete/fetch/insert."""
        args = parse_args(["--days", "730"])
        ckpt_path = tmp_path / "ckpt.json"
        ckpt_path.write_text(json.dumps({"BTCUSDT": "done"}))

        mock_tracked = [
            _make_tracked_symbol("BTCUSDT", "BINANCE"),
            _make_tracked_symbol("ETHUSDT", "BINANCE"),
        ]

        mock_db = MagicMock()
        mock_db.connect = AsyncMock()
        mock_db.disconnect = AsyncMock()

        mock_tracked_repo = MagicMock()
        mock_tracked_repo.list_all = AsyncMock(return_value=mock_tracked)

        mock_bar_repo = MagicMock()
        mock_bar_repo.ensure_indexes = AsyncMock()
        mock_bar_repo.delete_many_by_range = AsyncMock(return_value=0)
        mock_bar_repo.insert_many = AsyncMock(return_value=100)

        mock_binance = MagicMock()
        mock_binance.fetch_ohlcv = AsyncMock(return_value=[_make_bar("ETHUSDT")])
        mock_binance.close = AsyncMock()

        with (
            patch("scripts.resync_2y_from_binance.get_settings", return_value=MagicMock()),
            patch("scripts.resync_2y_from_binance.setup_logging"),
            patch("scripts.resync_2y_from_binance.Database", return_value=mock_db),
            patch(
                "scripts.resync_2y_from_binance.TrackedSymbolRepository",
                return_value=mock_tracked_repo,
            ),
            patch("scripts.resync_2y_from_binance.BarRepository", return_value=mock_bar_repo),
            patch("scripts.resync_2y_from_binance.BinanceClient", return_value=mock_binance),
            patch("scripts.resync_2y_from_binance.CHECKPOINT_PATH", ckpt_path),
            patch(
                "scripts.resync_2y_from_binance.cascade_for_symbol",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            await run_resync(args)

        # delete_many_by_range called once (ETHUSDT only — BTCUSDT was done)
        assert mock_bar_repo.delete_many_by_range.await_count == 1
        delete_call = mock_bar_repo.delete_many_by_range.call_args
        assert delete_call.args[0] == "ETHUSDT"


class TestSymbolOrchestration:
    @pytest.mark.asyncio
    async def test_call_order_delete_fetch_insert_cascade(self, tmp_path: Path) -> None:
        """Per-symbol call order: delete_many_by_range → fetch_ohlcv → insert_many → cascade."""
        args = parse_args(["--days", "730"])
        ckpt_path = tmp_path / "ckpt.json"

        mock_tracked = [_make_tracked_symbol("BTCUSDT", "BINANCE")]
        call_order: list[str] = []

        mock_db = MagicMock()
        mock_db.connect = AsyncMock()
        mock_db.disconnect = AsyncMock()

        mock_tracked_repo = MagicMock()
        mock_tracked_repo.list_all = AsyncMock(return_value=mock_tracked)

        mock_bar_repo = MagicMock()
        mock_bar_repo.ensure_indexes = AsyncMock()

        async def _fake_delete(*a, **kw):
            call_order.append("delete")
            return 500

        async def _fake_insert(*a, **kw):
            call_order.append("insert")
            return 100

        mock_bar_repo.delete_many_by_range = _fake_delete
        mock_bar_repo.insert_many = _fake_insert

        async def _fake_fetch(*a, **kw):
            call_order.append("fetch")
            return [_make_bar()]

        async def _fake_cascade(*a, **kw):
            call_order.append("cascade")
            return {}

        mock_binance = MagicMock()
        mock_binance.fetch_ohlcv = _fake_fetch
        mock_binance.close = AsyncMock()

        with (
            patch("scripts.resync_2y_from_binance.get_settings", return_value=MagicMock()),
            patch("scripts.resync_2y_from_binance.setup_logging"),
            patch("scripts.resync_2y_from_binance.Database", return_value=mock_db),
            patch(
                "scripts.resync_2y_from_binance.TrackedSymbolRepository",
                return_value=mock_tracked_repo,
            ),
            patch("scripts.resync_2y_from_binance.BarRepository", return_value=mock_bar_repo),
            patch("scripts.resync_2y_from_binance.BinanceClient", return_value=mock_binance),
            patch("scripts.resync_2y_from_binance.CHECKPOINT_PATH", ckpt_path),
            patch("scripts.resync_2y_from_binance.cascade_for_symbol", side_effect=_fake_cascade),
        ):
            result = await run_resync(args)

        assert result == 0
        assert call_order == ["delete", "fetch", "insert", "cascade"], (
            f"Unexpected order: {call_order}"
        )

    @pytest.mark.asyncio
    async def test_no_cascade_skips_cascade_step(self, tmp_path: Path) -> None:
        """--no-cascade flag prevents cascade_for_symbol from being called."""
        args = parse_args(["--days", "730", "--no-cascade"])
        ckpt_path = tmp_path / "ckpt.json"

        mock_tracked = [_make_tracked_symbol("BTCUSDT", "BINANCE")]
        mock_db = MagicMock()
        mock_db.connect = AsyncMock()
        mock_db.disconnect = AsyncMock()

        mock_tracked_repo = MagicMock()
        mock_tracked_repo.list_all = AsyncMock(return_value=mock_tracked)

        mock_bar_repo = MagicMock()
        mock_bar_repo.ensure_indexes = AsyncMock()
        mock_bar_repo.delete_many_by_range = AsyncMock(return_value=0)
        mock_bar_repo.insert_many = AsyncMock(return_value=10)

        mock_binance = MagicMock()
        mock_binance.fetch_ohlcv = AsyncMock(return_value=[_make_bar()])
        mock_binance.close = AsyncMock()

        mock_cascade = AsyncMock(return_value={})

        with (
            patch("scripts.resync_2y_from_binance.get_settings", return_value=MagicMock()),
            patch("scripts.resync_2y_from_binance.setup_logging"),
            patch("scripts.resync_2y_from_binance.Database", return_value=mock_db),
            patch(
                "scripts.resync_2y_from_binance.TrackedSymbolRepository",
                return_value=mock_tracked_repo,
            ),
            patch("scripts.resync_2y_from_binance.BarRepository", return_value=mock_bar_repo),
            patch("scripts.resync_2y_from_binance.BinanceClient", return_value=mock_binance),
            patch("scripts.resync_2y_from_binance.CHECKPOINT_PATH", ckpt_path),
            patch("scripts.resync_2y_from_binance.cascade_for_symbol", mock_cascade),
        ):
            await run_resync(args)

        mock_cascade.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_uses_all_canonical_tfs(self, tmp_path: Path) -> None:
        """delete_many_by_range must be called with the full CANONICAL_TFS list."""
        args = parse_args(["--days", "730"])
        ckpt_path = tmp_path / "ckpt.json"

        mock_tracked = [_make_tracked_symbol("BTCUSDT", "BINANCE")]
        mock_db = MagicMock()
        mock_db.connect = AsyncMock()
        mock_db.disconnect = AsyncMock()

        mock_tracked_repo = MagicMock()
        mock_tracked_repo.list_all = AsyncMock(return_value=mock_tracked)

        mock_bar_repo = MagicMock()
        mock_bar_repo.ensure_indexes = AsyncMock()
        mock_bar_repo.delete_many_by_range = AsyncMock(return_value=0)
        mock_bar_repo.insert_many = AsyncMock(return_value=5)

        mock_binance = MagicMock()
        mock_binance.fetch_ohlcv = AsyncMock(return_value=[_make_bar()])
        mock_binance.close = AsyncMock()

        with (
            patch("scripts.resync_2y_from_binance.get_settings", return_value=MagicMock()),
            patch("scripts.resync_2y_from_binance.setup_logging"),
            patch("scripts.resync_2y_from_binance.Database", return_value=mock_db),
            patch(
                "scripts.resync_2y_from_binance.TrackedSymbolRepository",
                return_value=mock_tracked_repo,
            ),
            patch("scripts.resync_2y_from_binance.BarRepository", return_value=mock_bar_repo),
            patch("scripts.resync_2y_from_binance.BinanceClient", return_value=mock_binance),
            patch("scripts.resync_2y_from_binance.CHECKPOINT_PATH", ckpt_path),
            patch(
                "scripts.resync_2y_from_binance.cascade_for_symbol",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            await run_resync(args)

        delete_call = mock_bar_repo.delete_many_by_range.call_args
        intervals_passed = delete_call.args[2]
        assert set(intervals_passed) == set(CANONICAL_TFS)


class TestNonBinanceFiltering:
    @pytest.mark.asyncio
    async def test_non_binance_symbol_skipped(self, tmp_path: Path) -> None:
        """Symbols with exchange != BINANCE are skipped; only BINANCE processed."""
        args = parse_args(["--days", "730"])
        ckpt_path = tmp_path / "ckpt.json"

        mock_tracked = [
            _make_tracked_symbol("BTCUSDT", "BINANCE"),
            _make_tracked_symbol("BTCUSDT", "OKX"),  # non-Binance
        ]
        mock_db = MagicMock()
        mock_db.connect = AsyncMock()
        mock_db.disconnect = AsyncMock()

        mock_tracked_repo = MagicMock()
        mock_tracked_repo.list_all = AsyncMock(return_value=mock_tracked)

        mock_bar_repo = MagicMock()
        mock_bar_repo.ensure_indexes = AsyncMock()
        mock_bar_repo.delete_many_by_range = AsyncMock(return_value=0)
        mock_bar_repo.insert_many = AsyncMock(return_value=5)

        mock_binance = MagicMock()
        mock_binance.fetch_ohlcv = AsyncMock(return_value=[_make_bar()])
        mock_binance.close = AsyncMock()

        with (
            patch("scripts.resync_2y_from_binance.get_settings", return_value=MagicMock()),
            patch("scripts.resync_2y_from_binance.setup_logging"),
            patch("scripts.resync_2y_from_binance.Database", return_value=mock_db),
            patch(
                "scripts.resync_2y_from_binance.TrackedSymbolRepository",
                return_value=mock_tracked_repo,
            ),
            patch("scripts.resync_2y_from_binance.BarRepository", return_value=mock_bar_repo),
            patch("scripts.resync_2y_from_binance.BinanceClient", return_value=mock_binance),
            patch("scripts.resync_2y_from_binance.CHECKPOINT_PATH", ckpt_path),
            patch(
                "scripts.resync_2y_from_binance.cascade_for_symbol",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            await run_resync(args)

        # Only one delete call (BTCUSDT/BINANCE); OKX skipped
        assert mock_bar_repo.delete_many_by_range.await_count == 1


class TestSymbolsFilter:
    @pytest.mark.asyncio
    async def test_symbols_filter_limits_processing(self, tmp_path: Path) -> None:
        """--symbols BTCUSDT processes only BTCUSDT even if ETHUSDT is tracked."""
        args = parse_args(["--days", "730", "--symbols", "BTCUSDT"])
        ckpt_path = tmp_path / "ckpt.json"

        mock_tracked = [
            _make_tracked_symbol("BTCUSDT", "BINANCE"),
            _make_tracked_symbol("ETHUSDT", "BINANCE"),
        ]
        mock_db = MagicMock()
        mock_db.connect = AsyncMock()
        mock_db.disconnect = AsyncMock()

        mock_tracked_repo = MagicMock()
        mock_tracked_repo.list_all = AsyncMock(return_value=mock_tracked)

        mock_bar_repo = MagicMock()
        mock_bar_repo.ensure_indexes = AsyncMock()
        mock_bar_repo.delete_many_by_range = AsyncMock(return_value=0)
        mock_bar_repo.insert_many = AsyncMock(return_value=5)

        mock_binance = MagicMock()
        mock_binance.fetch_ohlcv = AsyncMock(return_value=[_make_bar("BTCUSDT")])
        mock_binance.close = AsyncMock()

        with (
            patch("scripts.resync_2y_from_binance.get_settings", return_value=MagicMock()),
            patch("scripts.resync_2y_from_binance.setup_logging"),
            patch("scripts.resync_2y_from_binance.Database", return_value=mock_db),
            patch(
                "scripts.resync_2y_from_binance.TrackedSymbolRepository",
                return_value=mock_tracked_repo,
            ),
            patch("scripts.resync_2y_from_binance.BarRepository", return_value=mock_bar_repo),
            patch("scripts.resync_2y_from_binance.BinanceClient", return_value=mock_binance),
            patch("scripts.resync_2y_from_binance.CHECKPOINT_PATH", ckpt_path),
            patch(
                "scripts.resync_2y_from_binance.cascade_for_symbol",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            await run_resync(args)

        assert mock_bar_repo.delete_many_by_range.await_count == 1
        delete_call = mock_bar_repo.delete_many_by_range.call_args
        assert delete_call.args[0] == "BTCUSDT"


class TestParseArgs:
    def test_default_days_is_730(self) -> None:
        args = parse_args([])
        assert args.days == 730

    def test_dry_run_default_false(self) -> None:
        args = parse_args([])
        assert args.dry_run is False

    def test_no_cascade_default_false(self) -> None:
        args = parse_args([])
        assert args.no_cascade is False

    def test_symbols_parsed_as_string(self) -> None:
        args = parse_args(["--symbols", "BTCUSDT,ETHUSDT"])
        assert args.symbols == "BTCUSDT,ETHUSDT"


class TestEstimateWallTime:
    def test_returns_string_with_min(self) -> None:
        result = _estimate_wall_time(50, 730)
        assert "min" in result

    def test_single_symbol_shorter_than_50(self) -> None:
        single = _estimate_wall_time(1, 730)
        fifty = _estimate_wall_time(50, 730)
        # Extract numeric value for comparison
        single_min = float(single.replace("~", "").replace(" min", ""))
        fifty_min = float(fifty.replace("~", "").replace(" min", ""))
        assert single_min < fifty_min


class TestInProgressBarFilter:
    @pytest.mark.asyncio
    async def test_bars_at_or_after_end_dt_are_filtered_before_insert(self, tmp_path: Path) -> None:
        """BinanceClient may return in-progress (partial) bar with datetime == end_dt
        or datetime > end_dt. These must be dropped before insert_many to prevent
        partial bar persisting permanently (unique index silently skips later full bar).
        """
        args = parse_args(["--days", "730"])
        ckpt_path = tmp_path / "ckpt.json"

        # Compute the actual end_dt the script will use
        _, end_dt = _compute_window(args.days)

        # Build bars: one valid, one exactly at end_dt, one past end_dt
        bar_valid = MagicMock()
        bar_valid.datetime = end_dt - timedelta(minutes=1)  # strictly before end_dt
        bar_valid.symbol = "BTCUSDT"

        bar_at_end = MagicMock()
        bar_at_end.datetime = end_dt  # equal to end_dt → must be filtered
        bar_at_end.symbol = "BTCUSDT"

        bar_past_end = MagicMock()
        bar_past_end.datetime = end_dt + timedelta(minutes=1)  # after end_dt → must be filtered
        bar_past_end.symbol = "BTCUSDT"

        inserted_bars: list = []

        mock_tracked = [_make_tracked_symbol("BTCUSDT", "BINANCE")]
        mock_db = MagicMock()
        mock_db.connect = AsyncMock()
        mock_db.disconnect = AsyncMock()

        mock_tracked_repo = MagicMock()
        mock_tracked_repo.list_all = AsyncMock(return_value=mock_tracked)

        mock_bar_repo = MagicMock()
        mock_bar_repo.ensure_indexes = AsyncMock()
        mock_bar_repo.delete_many_by_range = AsyncMock(return_value=0)

        async def _capture_insert(bars, *, source):
            inserted_bars.extend(bars)
            return len(bars)

        mock_bar_repo.insert_many = _capture_insert

        mock_binance = MagicMock()
        mock_binance.fetch_ohlcv = AsyncMock(return_value=[bar_valid, bar_at_end, bar_past_end])
        mock_binance.close = AsyncMock()

        with (
            patch("scripts.resync_2y_from_binance.get_settings", return_value=MagicMock()),
            patch("scripts.resync_2y_from_binance.setup_logging"),
            patch("scripts.resync_2y_from_binance.Database", return_value=mock_db),
            patch(
                "scripts.resync_2y_from_binance.TrackedSymbolRepository",
                return_value=mock_tracked_repo,
            ),
            patch("scripts.resync_2y_from_binance.BarRepository", return_value=mock_bar_repo),
            patch("scripts.resync_2y_from_binance.BinanceClient", return_value=mock_binance),
            patch("scripts.resync_2y_from_binance.CHECKPOINT_PATH", ckpt_path),
            patch(
                "scripts.resync_2y_from_binance.cascade_for_symbol",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            await run_resync(args)

        # Only bar_valid should reach insert_many
        assert inserted_bars == [bar_valid], f"Expected only bar_valid, got {inserted_bars}"
        assert bar_at_end not in inserted_bars, "bar at end_dt must be filtered"
        assert bar_past_end not in inserted_bars, "bar past end_dt must be filtered"


class TestAtomicCheckpoint:
    def test_checkpoint_written_atomically_no_tmp_remains(self, tmp_path: Path) -> None:
        """_save_checkpoint uses os.replace for atomicity; no .tmp file remains after write."""
        ckpt_path = tmp_path / "ckpt.json"
        tmp_path_file = ckpt_path.with_suffix(".tmp")

        # Simulate prior crashed run: pre-existing .tmp with stale content
        tmp_path_file.write_text(json.dumps({"STALE": "done"}))

        with patch("scripts.resync_2y_from_binance.CHECKPOINT_PATH", ckpt_path):
            _save_checkpoint({"BTCUSDT": "done"})

        # Final file has new content
        assert ckpt_path.exists(), "checkpoint file must exist after save"
        content = json.loads(ckpt_path.read_text())
        assert content == {"BTCUSDT": "done"}, f"Unexpected content: {content}"

        # No .tmp file remains
        assert not tmp_path_file.exists(), ".tmp file must be removed after atomic replace"
