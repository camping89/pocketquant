"""Persist safety tests — the top side-effect risk (invariant a).

Verifies the scorecard doc shape and that the write op touches ONLY a new
top-level ``scorecard`` field via ``$set`` (never verdict/metrics/equity_curve),
with no ``upsert``. Uses a fake collection — no real DB.
"""

from __future__ import annotations

from scripts.rubric.run_rubric import _persist, _scorecard_doc
from scripts.rubric.scoring import grade_from_score
from scripts.rubric.types import AxisScore, ScorecardResult


def _result(run_id: str, aliases=None) -> ScorecardResult:
    axes = {
        "performance": AxisScore("performance", 0.4, "F", []),
        "robustness": AxisScore("robustness", 0.15, "F", []),
        "design_integrity": AxisScore("design_integrity", 1.9, "C", []),
    }
    return ScorecardResult(
        run_id=run_id,
        strategy_code="engulfing",
        symbol="BTCUSDT:BINANCE",
        interval="1m",
        name=None,
        rubric_version="1.0.0",
        axes=axes,
        overall_score=0.15,
        overall_grade=grade_from_score(0.15),
        metrics={"calmar": -1.0},
        reconciliation={"gross_edge_bps": -0.7},
        excursions={"mae_to_stop_mean": 0.9},
        audit={"degrees_of_freedom": 4},
        diagnosis="no directional edge",
        aliases=aliases or [],
    )


def test_scorecard_doc_keys_are_stable():
    doc = _scorecard_doc(_result("run-1"))
    assert set(doc.keys()) == {
        "rubric_version",
        "generated_note",
        "axes",
        "overall_score",
        "overall_grade",
        "metrics",
        "reconciliation",
        "excursions",
        "audit",
        "diagnosis",
        "aliases",
    }
    # never carries the protected fields
    assert "verdict" not in doc
    assert "equity_curve" not in doc
    assert "config_snapshot" not in doc


class _FakeCollection:
    def __init__(self):
        self.calls: list[tuple[dict, dict, dict]] = []

    def update_one(self, filter_q, update, **kwargs):
        self.calls.append((filter_q, update, kwargs))


class _FakeClient:
    def __init__(self, coll):
        self._coll = coll

    def __getitem__(self, _db):
        return {"backtest_runs": self._coll}

    def close(self):
        pass


def test_persist_only_sets_scorecard(monkeypatch):
    coll = _FakeCollection()
    monkeypatch.setattr("scripts.rubric.run_rubric.MongoClient", lambda *a, **k: _FakeClient(coll))
    monkeypatch.setenv("MONGODB_URL", "mongodb://localhost:27017/pocketquant_test")

    written = _persist([_result("canon-1", aliases=["alias-1"])])

    assert written == 2  # canonical + one alias
    # every write is a single-$set on the scorecard field, no upsert
    for filter_q, update, kwargs in coll.calls:
        assert set(update.keys()) == {"$set"}
        assert set(update["$set"].keys()) == {"scorecard"}
        assert "upsert" not in kwargs  # never creates docs
    # alias write is a canonical_ref pointer, not a recomputed scorecard
    alias_call = [c for c in coll.calls if c[0]["_id"] == "alias-1"][0]
    assert alias_call[1]["$set"]["scorecard"]["canonical_ref"] == "canon-1"
    # canonical write targets the exact run id, not a broad query
    canon_call = [c for c in coll.calls if c[0]["_id"] == "canon-1"][0]
    assert canon_call[0] == {"_id": "canon-1"}
