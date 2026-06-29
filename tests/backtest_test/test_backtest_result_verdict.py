"""Unit — `BacktestResult.verdict` survives the mongo round-trip and tolerates
legacy docs that predate the field (missing key → None)."""

from __future__ import annotations

from pocketquant.core.domain.backtest import BacktestResult

_CONFIG = {"strategy_code": "engulfing", "symbol": "BTCUSDT:BINANCE", "interval": "1m"}


def _started() -> BacktestResult:
    return BacktestResult.started("019f141c-a437-70a9-8d2a-d748b773d9e7", _CONFIG)


def test_verdict_defaults_none_and_round_trips() -> None:
    run = _started()
    assert run.verdict is None  # default

    run.verdict = "Fee-killed: negative edge, pf 0.095."
    doc = run.to_mongo()
    assert doc["verdict"] == "Fee-killed: negative edge, pf 0.095."

    restored = BacktestResult.from_mongo(doc)
    assert restored.verdict == "Fee-killed: negative edge, pf 0.095."


def test_from_mongo_tolerates_missing_verdict_key() -> None:
    doc = _started().to_mongo()
    doc.pop("verdict")  # simulate a pre-field document
    assert BacktestResult.from_mongo(doc).verdict is None
