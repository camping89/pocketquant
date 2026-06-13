"""Unit tests for scripts/backfill/binance_bars.py — mock httpx + BarRepository.

Lives beside the script (not under tests/) and is excluded from the default
`just test` run by pyproject's testpaths=["tests"]. Run explicitly:
    uv run python -m pytest scripts/backfill/test_binance_bars.py

Covers:
- Arg parsing: window XOR days, inverted range, unknown interval, replace/cascade flags
- Rolling window math: end = floor(now,1min) - 1s; start = end - days
- Checkpoint: load missing/valid/corrupt, atomic save roundtrip
- Dry-run: no DB writes, plan printed, only tracked BINANCE symbols listed
- Bulk orchestration: delete -> fetch -> insert -> cascade order, --replace gate,
  --no-cascade skip, delete uses full CANONICAL_TFS, checkpoint resume
- Symbol filtering: non-BINANCE skipped, --symbols subset narrows the work-list
- In-progress bar filter: bars at/after end dropped before insert
- Targeted single-symbol mode: one symbol, insert-only (no checkpoint)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pocketquant.core.domain.shared.enums import Interval
from scripts.backfill.binance_bars import (
    CANONICAL_TFS,
    _estimate_wall_time,
    _load_checkpoint,
    _rolling_window,
    _save_checkpoint,
    parse_args,
    run_backfill,
)

_MODULE = "scripts.backfill.binance_bars"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tracked_symbol(symbol: str = "BTCUSDT", exchange: str = "BINANCE") -> MagicMock:
    ts = MagicMock()
    ts.symbol = symbol
    ts.exchange = exchange
    return ts


def _make_bar(symbol: str = "BTCUSDT", dt: datetime | None = None) -> MagicMock:
    bar = MagicMock()
    bar.symbol = symbol
    bar.datetime = dt if dt is not None else datetime(2020, 1, 1, tzinfo=UTC)
    return bar


def _bulk_mocks(tracked: list[MagicMock], fetch_bars: list | None = None):
    """Build the (db, tracked_repo, bar_repo, http) mock bundle for a bulk run."""
    mock_db = MagicMock()
    mock_db.connect = AsyncMock()
    mock_db.disconnect = AsyncMock()

    mock_tracked_repo = MagicMock()
    mock_tracked_repo.list_all = AsyncMock(return_value=tracked)

    mock_bar_repo = MagicMock()
    mock_bar_repo.ensure_indexes = AsyncMock()
    mock_bar_repo.delete_many_by_range = AsyncMock(return_value=0)
    mock_bar_repo.insert_many = AsyncMock(return_value=len(fetch_bars or [_make_bar()]))

    return mock_db, mock_tracked_repo, mock_bar_repo


def _patches(
    *,
    db: MagicMock,
    tracked_repo: MagicMock,
    bar_repo: MagicMock,
    klines: list[list] | None = None,
    cascade: AsyncMock | None = None,
    ckpt_path: Path | None = None,
):
    """Common patch context. `klines` feeds fetch_klines; cascade defaults to no-op."""
    cascade = cascade or AsyncMock(return_value={})
    klines = klines if klines is not None else []
    ctx = [
        patch(f"{_MODULE}.get_settings", return_value=MagicMock()),
        patch(f"{_MODULE}.setup_logging"),
        patch(f"{_MODULE}.Database", return_value=db),
        patch(f"{_MODULE}.TrackedSymbolRepository", return_value=tracked_repo),
        patch(f"{_MODULE}.BarRepository", return_value=bar_repo),
        patch(f"{_MODULE}.fetch_klines", new_callable=AsyncMock, return_value=klines),
        patch(f"{_MODULE}.cascade_for_symbol", cascade),
    ]
    if ckpt_path is not None:
        ctx.append(patch(f"{_MODULE}.CHECKPOINT_PATH", ckpt_path))
    return ctx


def _enter(ctx: list):
    for c in ctx:
        c.start()


def _exit(ctx: list):
    for c in reversed(ctx):
        c.stop()


# ---------------------------------------------------------------------------
# parse_args — window selection + validation
# ---------------------------------------------------------------------------


class TestParseArgs:
    def test_days_window_is_bulk_by_default(self) -> None:
        cfg = parse_args(["--days", "730"])
        assert cfg.is_bulk is True
        assert cfg.symbol is None
        assert cfg.replace is False
        assert cfg.cascade is True

    def test_symbol_is_targeted_mode(self) -> None:
        cfg = parse_args(
            [
                "--symbol",
                "btcusdt",
                "--start",
                "2026-04-30T08:54:00Z",
                "--end",
                "2026-05-03T21:34:00Z",
            ]
        )
        assert cfg.is_bulk is False
        assert cfg.symbol == "BTCUSDT"
        assert cfg.exchange == "BINANCE"
        assert cfg.interval == Interval.MINUTE_1
        assert cfg.start == datetime(2026, 4, 30, 8, 54, 0, tzinfo=UTC)
        assert cfg.end == datetime(2026, 5, 3, 21, 34, 0, tzinfo=UTC)

    def test_replace_and_no_cascade_flags(self) -> None:
        cfg = parse_args(["--days", "365", "--replace", "--no-cascade"])
        assert cfg.replace is True
        assert cfg.cascade is False

    def test_symbols_filter_parsed_to_frozenset(self) -> None:
        cfg = parse_args(["--days", "730", "--symbols", "btcusdt,ethusdt"])
        assert cfg.symbols_filter == frozenset({"BTCUSDT", "ETHUSDT"})

    def test_requires_window_xor_days(self) -> None:
        with pytest.raises(SystemExit):
            parse_args(["--symbol", "BTCUSDT"])  # neither --days nor --start/--end

    def test_rejects_both_window_and_days(self) -> None:
        with pytest.raises(SystemExit):
            parse_args(
                [
                    "--days",
                    "730",
                    "--start",
                    "2026-01-01T00:00:00Z",
                    "--end",
                    "2026-01-02T00:00:00Z",
                ]
            )

    def test_rejects_inverted_range(self) -> None:
        with pytest.raises(SystemExit):
            parse_args(
                [
                    "--symbol",
                    "BTCUSDT",
                    "--start",
                    "2026-05-03T21:34:00Z",
                    "--end",
                    "2026-04-30T08:54:00Z",
                ]
            )

    def test_rejects_nonpositive_days(self) -> None:
        with pytest.raises(SystemExit):
            parse_args(["--days", "0"])

    def test_unknown_interval_rejected(self) -> None:
        with pytest.raises(SystemExit):
            parse_args(["--symbol", "BTCUSDT", "--interval", "7m", "--days", "730"])

    def test_default_interval_is_1m(self) -> None:
        assert parse_args(["--days", "730"]).interval == Interval.MINUTE_1


# ---------------------------------------------------------------------------
# _rolling_window
# ---------------------------------------------------------------------------


class TestRollingWindow:
    _FROZEN_NOW = datetime(2026, 5, 8, 14, 30, 45, 123456, tzinfo=UTC)

    def test_end_is_floored_minute_minus_1_second(self) -> None:
        with patch(f"{_MODULE}.datetime") as mock_dt:
            mock_dt.now.return_value = self._FROZEN_NOW
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            _start, end = _rolling_window(730)
        assert end == self._FROZEN_NOW.replace(second=0, microsecond=0) - timedelta(seconds=1)

    def test_start_is_end_minus_days(self) -> None:
        with patch(f"{_MODULE}.datetime") as mock_dt:
            mock_dt.now.return_value = self._FROZEN_NOW
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            start, end = _rolling_window(730)
        assert end - start == timedelta(days=730)

    def test_30_day_window(self) -> None:
        with patch(f"{_MODULE}.datetime") as mock_dt:
            mock_dt.now.return_value = self._FROZEN_NOW
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            start, end = _rolling_window(30)
        assert end - start == timedelta(days=30)


# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------


class TestCheckpoint:
    def test_load_missing_returns_empty(self, tmp_path: Path) -> None:
        with patch(f"{_MODULE}.CHECKPOINT_PATH", tmp_path / "ckpt.json"):
            assert _load_checkpoint() == {}

    def test_load_valid(self, tmp_path: Path) -> None:
        ckpt = tmp_path / "ckpt.json"
        ckpt.write_text(json.dumps({"BTCUSDT": "done"}))
        with patch(f"{_MODULE}.CHECKPOINT_PATH", ckpt):
            assert _load_checkpoint() == {"BTCUSDT": "done"}

    def test_load_corrupt_returns_empty(self, tmp_path: Path) -> None:
        ckpt = tmp_path / "ckpt.json"
        ckpt.write_text("not valid json{{")
        with patch(f"{_MODULE}.CHECKPOINT_PATH", ckpt):
            assert _load_checkpoint() == {}

    def test_save_reload_roundtrip(self, tmp_path: Path) -> None:
        ckpt = tmp_path / "ckpt.json"
        data = {"BTCUSDT": "done", "ETHUSDT": "done"}
        with patch(f"{_MODULE}.CHECKPOINT_PATH", ckpt):
            _save_checkpoint(data)
            assert _load_checkpoint() == data

    def test_save_atomic_no_tmp_remains(self, tmp_path: Path) -> None:
        ckpt = tmp_path / "ckpt.json"
        tmp_file = ckpt.with_suffix(".tmp")
        tmp_file.write_text(json.dumps({"STALE": "done"}))  # simulate prior crashed run
        with patch(f"{_MODULE}.CHECKPOINT_PATH", ckpt):
            _save_checkpoint({"BTCUSDT": "done"})
        assert json.loads(ckpt.read_text()) == {"BTCUSDT": "done"}
        assert not tmp_file.exists()


# ---------------------------------------------------------------------------
# _estimate_wall_time
# ---------------------------------------------------------------------------


class TestEstimateWallTime:
    def test_returns_min_string(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2026, 1, 1, tzinfo=UTC)
        assert "min" in _estimate_wall_time(50, start, end)

    def test_single_symbol_shorter_than_fifty(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2026, 1, 1, tzinfo=UTC)
        one = float(_estimate_wall_time(1, start, end).replace("~", "").replace(" min", ""))
        fifty = float(_estimate_wall_time(50, start, end).replace("~", "").replace(" min", ""))
        assert one < fifty


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------


class TestDryRun:
    @pytest.mark.asyncio
    async def test_makes_no_db_writes(self) -> None:
        cfg = parse_args(["--days", "730", "--replace", "--dry-run"])
        db, tracked_repo, bar_repo = _bulk_mocks([_make_tracked_symbol("BTCUSDT")])
        ctx = _patches(db=db, tracked_repo=tracked_repo, bar_repo=bar_repo)
        _enter(ctx)
        try:
            result = await run_backfill(cfg)
        finally:
            _exit(ctx)
        assert result == 0
        bar_repo.delete_many_by_range.assert_not_called()
        bar_repo.insert_many.assert_not_called()

    @pytest.mark.asyncio
    async def test_prints_plan(self, capsys) -> None:
        cfg = parse_args(["--days", "365", "--dry-run"])
        tracked = [_make_tracked_symbol("BTCUSDT"), _make_tracked_symbol("ETHUSDT")]
        db, tracked_repo, bar_repo = _bulk_mocks(tracked)
        ctx = _patches(db=db, tracked_repo=tracked_repo, bar_repo=bar_repo)
        _enter(ctx)
        try:
            await run_backfill(cfg)
        finally:
            _exit(ctx)
        out = capsys.readouterr().out
        assert "DRY RUN" in out
        assert "BTCUSDT" in out
        assert "365" in out


# ---------------------------------------------------------------------------
# Bulk orchestration
# ---------------------------------------------------------------------------


class TestBulkOrchestration:
    @pytest.mark.asyncio
    async def test_replace_call_order_delete_fetch_insert_cascade(self, tmp_path: Path) -> None:
        cfg = parse_args(["--days", "730", "--replace"])
        call_order: list[str] = []

        db, tracked_repo, bar_repo = _bulk_mocks([_make_tracked_symbol("BTCUSDT")])

        async def _del(*a, **kw):
            call_order.append("delete")
            return 500

        async def _ins(*a, **kw):
            call_order.append("insert")
            return 100

        bar_repo.delete_many_by_range = _del
        bar_repo.insert_many = _ins

        async def _fetch(*a, **kw):
            call_order.append("fetch")
            return [[0] * 12]  # one kline row; mapped to a bar below

        async def _casc(*a, **kw):
            call_order.append("cascade")
            return {}

        ctx = [
            patch(f"{_MODULE}.get_settings", return_value=MagicMock()),
            patch(f"{_MODULE}.setup_logging"),
            patch(f"{_MODULE}.Database", return_value=db),
            patch(f"{_MODULE}.TrackedSymbolRepository", return_value=tracked_repo),
            patch(f"{_MODULE}.BarRepository", return_value=bar_repo),
            patch(f"{_MODULE}.fetch_klines", _fetch),
            patch(f"{_MODULE}.kline_to_bar", return_value=_make_bar()),
            patch(f"{_MODULE}.cascade_for_symbol", side_effect=_casc),
            patch(f"{_MODULE}.CHECKPOINT_PATH", tmp_path / "ckpt.json"),
        ]
        _enter(ctx)
        try:
            result = await run_backfill(cfg)
        finally:
            _exit(ctx)
        assert result == 0
        assert call_order == ["delete", "fetch", "insert", "cascade"], call_order

    @pytest.mark.asyncio
    async def test_no_replace_skips_delete(self, tmp_path: Path) -> None:
        cfg = parse_args(["--days", "730"])  # no --replace
        db, tracked_repo, bar_repo = _bulk_mocks([_make_tracked_symbol("BTCUSDT")])
        ctx = _patches(
            db=db,
            tracked_repo=tracked_repo,
            bar_repo=bar_repo,
            klines=[[0] * 12],
            ckpt_path=tmp_path / "ckpt.json",
        )
        ctx.append(patch(f"{_MODULE}.kline_to_bar", return_value=_make_bar()))
        _enter(ctx)
        try:
            await run_backfill(cfg)
        finally:
            _exit(ctx)
        bar_repo.delete_many_by_range.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_cascade_skips_cascade(self, tmp_path: Path) -> None:
        cfg = parse_args(["--days", "730", "--replace", "--no-cascade"])
        db, tracked_repo, bar_repo = _bulk_mocks([_make_tracked_symbol("BTCUSDT")])
        mock_cascade = AsyncMock(return_value={})
        ctx = _patches(
            db=db,
            tracked_repo=tracked_repo,
            bar_repo=bar_repo,
            klines=[[0] * 12],
            cascade=mock_cascade,
            ckpt_path=tmp_path / "ckpt.json",
        )
        ctx.append(patch(f"{_MODULE}.kline_to_bar", return_value=_make_bar()))
        _enter(ctx)
        try:
            await run_backfill(cfg)
        finally:
            _exit(ctx)
        mock_cascade.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_uses_full_canonical_tfs(self, tmp_path: Path) -> None:
        cfg = parse_args(["--days", "730", "--replace"])
        db, tracked_repo, bar_repo = _bulk_mocks([_make_tracked_symbol("BTCUSDT")])
        ctx = _patches(
            db=db,
            tracked_repo=tracked_repo,
            bar_repo=bar_repo,
            klines=[[0] * 12],
            ckpt_path=tmp_path / "ckpt.json",
        )
        ctx.append(patch(f"{_MODULE}.kline_to_bar", return_value=_make_bar()))
        _enter(ctx)
        try:
            await run_backfill(cfg)
        finally:
            _exit(ctx)
        delete_call = bar_repo.delete_many_by_range.call_args
        # signature: (composite_symbol, intervals, start, end)
        assert delete_call.args[0] == "BTCUSDT:BINANCE"
        assert set(delete_call.args[1]) == set(CANONICAL_TFS)

    @pytest.mark.asyncio
    async def test_checkpoint_resume_skips_done(self, tmp_path: Path) -> None:
        cfg = parse_args(["--days", "730", "--replace"])
        ckpt = tmp_path / "ckpt.json"
        ckpt.write_text(json.dumps({"BTCUSDT": "done"}))
        tracked = [_make_tracked_symbol("BTCUSDT"), _make_tracked_symbol("ETHUSDT")]
        db, tracked_repo, bar_repo = _bulk_mocks(tracked)
        ctx = _patches(
            db=db,
            tracked_repo=tracked_repo,
            bar_repo=bar_repo,
            klines=[[0] * 12],
            ckpt_path=ckpt,
        )
        ctx.append(patch(f"{_MODULE}.kline_to_bar", return_value=_make_bar("ETHUSDT")))
        _enter(ctx)
        try:
            await run_backfill(cfg)
        finally:
            _exit(ctx)
        # Only ETHUSDT processed (BTCUSDT already done)
        assert bar_repo.delete_many_by_range.await_count == 1
        assert bar_repo.delete_many_by_range.call_args.args[0] == "ETHUSDT:BINANCE"


# ---------------------------------------------------------------------------
# Symbol filtering
# ---------------------------------------------------------------------------


class TestSymbolFiltering:
    @pytest.mark.asyncio
    async def test_non_binance_skipped(self, tmp_path: Path) -> None:
        cfg = parse_args(["--days", "730", "--replace"])
        tracked = [
            _make_tracked_symbol("BTCUSDT", "BINANCE"),
            _make_tracked_symbol("BTCUSDT", "OKX"),
        ]
        db, tracked_repo, bar_repo = _bulk_mocks(tracked)
        ctx = _patches(
            db=db,
            tracked_repo=tracked_repo,
            bar_repo=bar_repo,
            klines=[[0] * 12],
            ckpt_path=tmp_path / "ckpt.json",
        )
        ctx.append(patch(f"{_MODULE}.kline_to_bar", return_value=_make_bar()))
        _enter(ctx)
        try:
            await run_backfill(cfg)
        finally:
            _exit(ctx)
        assert bar_repo.delete_many_by_range.await_count == 1

    @pytest.mark.asyncio
    async def test_symbols_filter_narrows(self, tmp_path: Path) -> None:
        cfg = parse_args(["--days", "730", "--replace", "--symbols", "BTCUSDT"])
        tracked = [_make_tracked_symbol("BTCUSDT"), _make_tracked_symbol("ETHUSDT")]
        db, tracked_repo, bar_repo = _bulk_mocks(tracked)
        ctx = _patches(
            db=db,
            tracked_repo=tracked_repo,
            bar_repo=bar_repo,
            klines=[[0] * 12],
            ckpt_path=tmp_path / "ckpt.json",
        )
        ctx.append(patch(f"{_MODULE}.kline_to_bar", return_value=_make_bar("BTCUSDT")))
        _enter(ctx)
        try:
            await run_backfill(cfg)
        finally:
            _exit(ctx)
        assert bar_repo.delete_many_by_range.await_count == 1
        assert bar_repo.delete_many_by_range.call_args.args[0] == "BTCUSDT:BINANCE"


# ---------------------------------------------------------------------------
# In-progress bar filter
# ---------------------------------------------------------------------------


class TestInProgressBarFilter:
    @pytest.mark.asyncio
    async def test_bars_at_or_after_end_filtered(self, tmp_path: Path) -> None:
        cfg = parse_args(["--days", "730", "--replace"])
        _, end_dt = cfg.start, cfg.end

        bar_valid = _make_bar(dt=end_dt - timedelta(minutes=1))
        bar_at_end = _make_bar(dt=end_dt)
        bar_past_end = _make_bar(dt=end_dt + timedelta(minutes=1))

        inserted: list = []
        db, tracked_repo, bar_repo = _bulk_mocks([_make_tracked_symbol("BTCUSDT")])

        async def _capture_insert(bars, *, source):
            inserted.extend(bars)
            return len(bars)

        bar_repo.insert_many = _capture_insert

        # fetch_klines returns 3 raw rows; kline_to_bar maps them to the 3 bars in order.
        ctx = [
            patch(f"{_MODULE}.get_settings", return_value=MagicMock()),
            patch(f"{_MODULE}.setup_logging"),
            patch(f"{_MODULE}.Database", return_value=db),
            patch(f"{_MODULE}.TrackedSymbolRepository", return_value=tracked_repo),
            patch(f"{_MODULE}.BarRepository", return_value=bar_repo),
            patch(f"{_MODULE}.fetch_klines", new_callable=AsyncMock, return_value=[[0] * 12] * 3),
            patch(f"{_MODULE}.kline_to_bar", side_effect=[bar_valid, bar_at_end, bar_past_end]),
            patch(f"{_MODULE}.cascade_for_symbol", new_callable=AsyncMock, return_value={}),
            patch(f"{_MODULE}.CHECKPOINT_PATH", tmp_path / "ckpt.json"),
        ]
        _enter(ctx)
        try:
            await run_backfill(cfg)
        finally:
            _exit(ctx)
        assert inserted == [bar_valid]
        assert bar_at_end not in inserted
        assert bar_past_end not in inserted


# ---------------------------------------------------------------------------
# Targeted single-symbol mode
# ---------------------------------------------------------------------------


class TestTargetedMode:
    @pytest.mark.asyncio
    async def test_single_symbol_inserts_without_checkpoint(self, tmp_path: Path) -> None:
        cfg = parse_args(
            [
                "--symbol",
                "BTCUSDT",
                "--start",
                "2026-04-30T00:00:00Z",
                "--end",
                "2026-05-01T00:00:00Z",
            ]
        )
        assert cfg.is_bulk is False

        db, tracked_repo, bar_repo = _bulk_mocks([])  # tracked repo unused in targeted mode
        bar_repo.insert_many = AsyncMock(return_value=10)

        valid_bar = _make_bar(dt=datetime(2026, 4, 30, 12, 0, tzinfo=UTC))
        ckpt = tmp_path / "ckpt.json"
        ctx = _patches(
            db=db,
            tracked_repo=tracked_repo,
            bar_repo=bar_repo,
            klines=[[0] * 12],
            ckpt_path=ckpt,
        )
        ctx.append(patch(f"{_MODULE}.kline_to_bar", return_value=valid_bar))
        _enter(ctx)
        try:
            result = await run_backfill(cfg)
        finally:
            _exit(ctx)
        assert result == 0
        # Insert-only (no --replace): no delete; tracked repo never queried.
        bar_repo.delete_many_by_range.assert_not_called()
        tracked_repo.list_all.assert_not_called()
        # No checkpoint written for a single-symbol run.
        assert not ckpt.exists()


# ---------------------------------------------------------------------------
# Mongo connection failure
# ---------------------------------------------------------------------------


class TestConnectionFailure:
    @pytest.mark.asyncio
    async def test_returns_1_on_mongo_connection_failure(self) -> None:
        cfg = parse_args(["--days", "730"])
        db = MagicMock()
        db.connect = AsyncMock(side_effect=ConnectionError("Mongo unreachable"))
        db.disconnect = AsyncMock()
        tracked_repo = MagicMock()
        bar_repo = MagicMock()
        ctx = _patches(db=db, tracked_repo=tracked_repo, bar_repo=bar_repo)
        _enter(ctx)
        try:
            result = await run_backfill(cfg)
        finally:
            _exit(ctx)
        assert result == 1
