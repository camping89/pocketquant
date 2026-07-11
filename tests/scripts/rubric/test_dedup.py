"""Pure dedup tests for collapse_duplicates — no DB."""

from __future__ import annotations

from scripts.rubric.data_access import collapse_duplicates


def test_singletons_pass_through():
    meta = {
        "a": ("engulfing", 100, 0.1),
        "b": ("hitnrun2", 200, -0.2),
    }
    out = collapse_duplicates(meta, {})
    assert out == [("a", []), ("b", [])]


def test_double_persist_collapses_to_canonical_plus_alias():
    # same strategy, same trade count + return, IDENTICAL entry_time set → merge.
    meta = {
        "019f1780-6b52": ("hitnrun2", 5406, -0.031),
        "019f1780-546f": ("hitnrun2", 5406, -0.031),
    }
    sig = frozenset({1, 2, 3})
    signatures = {"019f1780-6b52": sig, "019f1780-546f": sig}
    out = collapse_duplicates(meta, signatures)
    assert len(out) == 1
    canonical, aliases = out[0]
    # canonical = smallest id (546f < 6b52)
    assert canonical == "019f1780-546f"
    assert aliases == ["019f1780-6b52"]


def test_same_count_different_trades_not_merged():
    # identical meta key but DIFFERENT entry_time sets → must stay separate.
    meta = {
        "x": ("hitnrun2", 5406, -0.031),
        "y": ("hitnrun2", 5406, -0.031),
    }
    signatures = {"x": frozenset({1, 2, 3}), "y": frozenset({4, 5, 6})}
    out = collapse_duplicates(meta, signatures)
    assert len(out) == 2
    assert all(aliases == [] for _, aliases in out)


def test_result_sorted_by_canonical():
    meta = {
        "zzz": ("s", 1, 0.0),
        "aaa": ("t", 2, 0.0),
    }
    out = collapse_duplicates(meta, {})
    assert [c for c, _ in out] == ["aaa", "zzz"]
