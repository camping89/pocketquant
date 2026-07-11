"""Static AST audit of a strategy's SOURCE (not its DB result).

Resolves the strategy class via ``STRATEGY_REGISTRY``, reads its source file, and
parses it with ``ast`` to extract design properties: degrees of freedom (tunable
params), SL/TP geometry shape, entry-frequency class, lookahead safety, and
direction bias. Every field falls back to ``"unknown"`` rather than raising —
the audit is a heuristic on a handful of strategies, not formal verification.

Importing ``STRATEGY_REGISTRY`` pulls in the core domain to resolve the class
path only; strategies are never instantiated or run.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Any

from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY


def audit_strategy(strategy_code: str) -> dict[str, Any]:
    """Return the static audit for one strategy code."""
    cls = STRATEGY_REGISTRY.get(strategy_code)
    if cls is None:
        return _unknown(strategy_code, reason="not in STRATEGY_REGISTRY")

    try:
        src_file = inspect.getsourcefile(cls)
        source = Path(src_file).read_text() if src_file else ""
        tree = ast.parse(source)
    except (OSError, SyntaxError, TypeError) as exc:
        return _unknown(strategy_code, reason=f"parse failed: {exc}")

    defaults = _find_defaults(tree)
    return {
        "strategy_code": strategy_code,
        "degrees_of_freedom": len(defaults),
        "params": sorted(defaults.keys()),
        "direction_bias": _direction_bias(defaults),
        "sl_tp_geometry": _sl_tp_geometry(tree),
        "entry_frequency_class": _entry_frequency_class(tree),
        "lookahead_safety": _lookahead_safety(source),
    }


def _find_defaults(tree: ast.Module) -> dict[str, Any]:
    """Extract the module-level ``_DEFAULTS`` dict literal (keys = tunable params)."""
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "_DEFAULTS":
                if isinstance(node.value, ast.Dict):
                    return {
                        _literal(k): _literal(v)
                        for k, v in zip(node.value.keys, node.value.values, strict=False)
                        if isinstance(k, ast.Constant)
                    }
    return {}


def _direction_bias(defaults: dict[str, Any]) -> str:
    d = defaults.get("direction")
    return str(d) if d in ("long", "short", "both") else "unknown"


def _sl_tp_geometry(tree: ast.Module) -> str:
    """Heuristic: recognise the pattern-extreme SL + max/min(R, key-level) TP shape
    common to these strategies. Falls back to ``custom`` when unrecognised.
    """
    assigns_to_sl = False
    tp_uses_key_level = False
    sl_uses_buffer = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            names = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if "sl" in names:
                assigns_to_sl = True
                src = ast.dump(node.value)
                if "buffer" in src or "buf" in src or "Mult" in src or "Sub" in src:
                    sl_uses_buffer = True
            if "tp" in names:
                src = ast.dump(node.value)
                if "max" in src.lower() or "min" in src.lower() or "key" in src.lower():
                    tp_uses_key_level = True
    if assigns_to_sl and tp_uses_key_level and sl_uses_buffer:
        return "pattern_extreme_sl + max/min(R, key_level)_tp"
    if assigns_to_sl:
        return "explicit_sl_tp"
    return "custom"


def _entry_frequency_class(tree: ast.Module) -> str:
    """Heuristic: a stateful armed/deque setup (arms then resolves) is a rarer,
    higher-selectivity entry than a fire-every-bar breakout.
    """
    has_deque = False
    has_armed = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in ("_armed", "_prev_bar"):
            has_armed = True
        if isinstance(node, ast.Name) and node.id == "deque":
            has_deque = True
    if has_armed:
        return "stateful_setup"
    if has_deque:
        return "windowed_continuation"
    return "per_bar"


def _lookahead_safety(source: str) -> str:
    """Confirm the safe ``prev_bar`` + snapshot-before-append pattern; flag if a
    forward index (``[i+1]``, ``[i + k]``) into a bar array appears.
    """
    safe_markers = ("prev_bar", "_prev_bar", "snapshot", "BEFORE appending", "before append")
    has_safe = any(m in source for m in safe_markers)
    # A crude forward-index probe: "[i+" or "[i +" or "+1]" adjacent to indexing.
    forward = any(tok in source for tok in ("[i+1]", "[i + 1]", "[idx+1]", "[i+k]"))
    if forward:
        return "forward_index_flagged"
    if has_safe:
        return "safe"
    return "unknown"


def _literal(node: ast.expr) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return None


def _unknown(strategy_code: str, reason: str) -> dict[str, Any]:
    return {
        "strategy_code": strategy_code,
        "degrees_of_freedom": None,
        "params": [],
        "direction_bias": "unknown",
        "sl_tp_geometry": "unknown",
        "entry_frequency_class": "unknown",
        "lookahead_safety": "unknown",
        "note": reason,
    }
