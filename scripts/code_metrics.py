"""Measure tiny functions and pure delegations, optionally against a ceiling.

Definitions (pinned so numbers stay comparable across commits):

- Population: every ``def`` / ``async def`` under ``--path`` (methods and nested
  functions included). ``body`` is the function body minus a leading docstring.
- Measured set (for the tiny share) drops stubs (empty body, or only ``...`` /
  ``pass``), ``property`` / ``setter`` / ``cached_property`` / ``abstractmethod``
  decorated functions, and dunders.
- ``tiny``: measured functions with ``len(body) <= 2``.
- ``delegations``: population functions whose body is a single ``return`` or
  expression whose value (after one ``await``) is a call on an attribute.

Usage:
    uv run python scripts/code_metrics.py --json
    uv run python scripts/code_metrics.py --out .cache/metrics.json
    uv run python scripts/code_metrics.py --ratchet   # ceiling from [tool.code-metrics]

Exit codes: 0 = within ceiling, 1 = a metric is above its ceiling,
2 = ``--ratchet`` without a ``[tool.code-metrics]`` section.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import tomllib
from pathlib import Path

_EXCLUDED_DECORATORS = {"property", "setter", "cached_property", "abstractmethod"}
_LONG_FUNCTION_LINES = 60

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


def _body(fn: FunctionNode) -> list[ast.stmt]:
    body = fn.body
    first = body[0] if body else None
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return body[1:]
    return body


def _is_stub(body: list[ast.stmt]) -> bool:
    return all(
        isinstance(s, ast.Pass)
        or (
            isinstance(s, ast.Expr)
            and isinstance(s.value, ast.Constant)
            and s.value.value is Ellipsis
        )
        for s in body
    )


def _decorator_name(dec: ast.expr) -> str | None:
    if isinstance(dec, ast.Call):
        dec = dec.func
    if isinstance(dec, ast.Name):
        return dec.id
    if isinstance(dec, ast.Attribute):
        return dec.attr
    return None


def _is_measured(fn: FunctionNode, body: list[ast.stmt]) -> bool:
    if _is_stub(body):
        return False
    if any(_decorator_name(d) in _EXCLUDED_DECORATORS for d in fn.decorator_list):
        return False
    return not (fn.name.startswith("__") and fn.name.endswith("__"))


def _is_delegation(body: list[ast.stmt]) -> bool:
    if len(body) != 1 or not isinstance(body[0], ast.Return | ast.Expr):
        return False
    value = body[0].value
    if isinstance(value, ast.Await):
        value = value.value
    return isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)


def measure(path: Path) -> dict:
    total = measured = tiny = delegations = 0
    over_60: list[str] = []
    for file in sorted(path.rglob("*.py")):
        tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        rel = file.relative_to(path).as_posix()
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            total += 1
            body = _body(fn)
            if _is_measured(fn, body):
                measured += 1
                if len(body) <= 2:
                    tiny += 1
            if _is_delegation(body):
                delegations += 1
            length = (fn.end_lineno or fn.lineno) - fn.lineno + 1
            if length > _LONG_FUNCTION_LINES:
                over_60.append(f"{rel}:{fn.lineno} {fn.name} {length}")
    return {
        "functions_total": total,
        "functions_measured": measured,
        "tiny": tiny,
        "tiny_share": round(tiny / measured, 4) if measured else 0.0,
        "delegations": delegations,
        "functions_over_60": over_60,
    }


def load_ceiling(pyproject: Path) -> dict:
    """Return ``[tool.code-metrics]`` from ``pyproject`` (empty dict when absent)."""
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return data.get("tool", {}).get("code-metrics", {})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--path", type=Path, default=Path("src/pocketquant"))
    parser.add_argument("--json", action="store_true", help="print the metrics dict")
    parser.add_argument("--out", type=Path, help="write the metrics JSON to this file")
    parser.add_argument("--max-tiny-share", type=float)
    parser.add_argument("--max-delegations", type=int)
    parser.add_argument(
        "--ratchet", action="store_true", help="read ceilings from [tool.code-metrics]"
    )
    args = parser.parse_args(argv)

    metrics = measure(args.path)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    elif args.json:
        print(json.dumps(metrics, indent=2))

    ceilings = {"tiny_share": args.max_tiny_share, "delegations": args.max_delegations}
    if args.ratchet:
        frozen = load_ceiling(Path("pyproject.toml"))
        if not frozen:
            print("code-metrics: no [tool.code-metrics] ceiling")
            return 2
        ceilings["tiny_share"] = frozen.get("max_tiny_share", ceilings["tiny_share"])
        ceilings["delegations"] = frozen.get("max_delegations", ceilings["delegations"])

    exit_code = 0
    for metric, ceiling in ceilings.items():
        if ceiling is not None and metrics[metric] > ceiling:
            print(f"::error title=code-metrics::{metric} {metrics[metric]} > {ceiling}")
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
