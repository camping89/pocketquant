# The client is created inside each loader, never at import time. Tests under
# tests/scripts/rubric/ import this module while direnv may hold a prod MONGODB_URL, and a
# module-level connect would trip the conftest prod guard.

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import numpy as np
from pymongo import MongoClient

from scripts.rubric.types import RunData, TradeRow

_RUNS = "backtest_runs"
_TRADES = "backtest_trades"
_BARS = "bars"

# Struct dtype for the projected bar window (o/h/l/c + epoch-seconds datetime).
# datetime as float epoch-seconds keeps the array homogeneous for bisect slicing
# in trade-path analysis without an object column.
_BAR_DTYPE = np.dtype(
    [
        ("datetime", "f8"),
        ("open", "f8"),
        ("high", "f8"),
        ("low", "f8"),
        ("close", "f8"),
    ]
)


def _client() -> MongoClient:
    url = os.environ.get("MONGODB_URL")
    if not url:
        raise RuntimeError("MONGODB_URL must be set in the environment")
    return MongoClient(url, serverSelectionTimeoutMS=10_000)


def _db(client: MongoClient):
    return client[os.environ.get("MONGODB_DATABASE", "pocketquant")]


# Config-snapshot and Decimal128 values arrive as str or Decimal.
def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _opt_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def list_finished_runs() -> list[str]:
    client = _client()
    try:
        cursor = (
            _db(client)[_RUNS]
            .find({"status": "finished"}, {"_id": 1})
            .sort("started_at", 1)
        )
        return [doc["_id"] for doc in cursor]
    finally:
        client.close()


def load_run(run_id: str) -> RunData:
    client = _client()
    try:
        doc = _db(client)[_RUNS].find_one({"_id": run_id})
    finally:
        client.close()
    if doc is None:
        raise KeyError(f"run not found: {run_id}")

    snap = doc.get("config_snapshot", {}) or {}
    params = snap.get("parameters", {})
    if isinstance(params, str):
        import json

        try:
            params = json.loads(params) if params else {}
        except json.JSONDecodeError:
            params = {}

    return RunData(
        run_id=doc["_id"],
        strategy_code=doc["strategy_code"],
        symbol=(doc.get("symbol") or snap.get("symbol", "")).upper(),
        interval=doc.get("interval") or snap.get("interval", ""),
        name=doc.get("name"),
        initial_capital=_to_float(snap.get("initial_capital"), 0.0),
        slippage_bps=_to_float(snap.get("slippage_bps"), 0.0),
        commission_bps=_to_float(snap.get("commission_bps"), 0.0),
        start_date=_parse_dt(snap.get("start_date")),
        end_date=_parse_dt(snap.get("end_date")),
        parameters=params if isinstance(params, dict) else {},
        metrics=doc.get("metrics", {}) or {},
        equity_curve=doc.get("equity_curve", []) or [],
    )


def load_trades(run_id: str) -> list[TradeRow]:
    client = _client()
    try:
        cursor = _db(client)[_TRADES].find({"run_id": run_id}).sort("entry_time", 1)
        docs = list(cursor)
    finally:
        client.close()

    rows: list[TradeRow] = []
    for d in docs:
        rows.append(
            TradeRow(
                trade_id=d["_id"],
                direction=d["direction"],
                entry_price=_to_float(d.get("entry_price")),
                exit_price=_to_float(d.get("exit_price")),
                sl_price=_opt_float(d.get("sl_price")),
                tp_price=_opt_float(d.get("tp_price")),
                quantity=_to_float(d.get("quantity")),
                pnl=_to_float(d.get("pnl")),
                commission=_to_float(d.get("commission")),
                duration_seconds=_to_float(d.get("duration_seconds")),
                entry_time=d["entry_time"],
                exit_time=d["exit_time"],
            )
        )
    return rows


# Projects only the price fields (the 1m collection holds over 1M docs) and filters to the
# run's window, so one run never scans the collection.
def load_bars(
    symbol: str, interval: str, start: datetime, end: datetime
) -> np.ndarray:
    client = _client()
    try:
        cursor = (
            _db(client)[_BARS]
            .find(
                {
                    "symbol": symbol.upper(),
                    "interval": interval,
                    "datetime": {"$gte": start, "$lte": end},
                },
                {"_id": 0, "open": 1, "high": 1, "low": 1, "close": 1, "datetime": 1},
            )
            .sort("datetime", 1)
        )
        docs = list(cursor)
    finally:
        client.close()

    arr = np.empty(len(docs), dtype=_BAR_DTYPE)
    for i, d in enumerate(docs):
        dt = d["datetime"]
        arr[i] = (
            dt.timestamp(),
            _to_float(d.get("open")),
            _to_float(d.get("high")),
            _to_float(d.get("low")),
            _to_float(d.get("close")),
        )
    return arr


# Collapses double-persist duplicates. A matching meta key alone is not enough: the trade
# entry_time sets must also be identical, so two different runs that share a trade count are
# never merged.
def dedup_runs(run_ids: list[str]) -> list[tuple[str, list[str]]]:
    client = _client()
    try:
        db = _db(client)
        meta: dict[str, tuple[str, int, float]] = {}
        for rid in run_ids:
            doc = db[_RUNS].find_one(
                {"_id": rid},
                {"strategy_code": 1, "metrics.total_trades": 1, "metrics.total_return": 1},
            )
            if doc is None:
                continue
            m = doc.get("metrics", {}) or {}
            meta[rid] = (
                doc["strategy_code"],
                int(m.get("total_trades", 0)),
                round(_to_float(m.get("total_return")), 10),
            )

        # entry_time set per candidate — only fetched for ids that share a meta key.
        signatures: dict[str, frozenset] = {}
        for ids in _group_by_meta(meta).values():
            if len(ids) < 2:
                continue
            for rid in ids:
                signatures[rid] = frozenset(
                    d["entry_time"]
                    for d in db[_TRADES].find({"run_id": rid}, {"entry_time": 1})
                )
    finally:
        client.close()

    return collapse_duplicates(meta, signatures)


def _group_by_meta(meta: dict[str, tuple[str, int, float]]) -> dict[tuple, list[str]]:
    groups: dict[tuple, list[str]] = {}
    for rid, key in meta.items():
        groups.setdefault(key, []).append(rid)
    return groups


# The canonical is the smallest id (UUIDv7, so the oldest run). `signatures` holds
# entry_time sets only for ids in a multi-member meta group.
def collapse_duplicates(
    meta: dict[str, tuple[str, int, float]],
    signatures: dict[str, frozenset],
) -> list[tuple[str, list[str]]]:
    result: list[tuple[str, list[str]]] = []
    for ids in _group_by_meta(meta).values():
        if len(ids) == 1:
            result.append((ids[0], []))
            continue
        clusters: dict[frozenset, list[str]] = {}
        for rid in ids:
            clusters.setdefault(signatures.get(rid, frozenset()), []).append(rid)
        for cluster in clusters.values():
            canonical = min(cluster)
            aliases = sorted(x for x in cluster if x != canonical)
            result.append((canonical, aliases))
    return sorted(result, key=lambda t: t[0])


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None
