import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PY_ROOTS = ("src", "scripts", "tests")
TS_ROOT = REPO / "web" / "src"


def _python_docstrings() -> list[str]:
    found = []
    for root in PY_ROOTS:
        for path in (REPO / root).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            # Any bare string statement counts, including one under a class field.
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Expr)
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                ):
                    found.append(f"{path.relative_to(REPO)}:{node.lineno}")
    return found


def _jsdoc_blocks() -> list[str]:
    found = []
    for path in TS_ROOT.rglob("*"):
        if path.suffix not in (".ts", ".tsx"):
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("/**"):
                found.append(f"{path.relative_to(REPO)}:{number}")
    return found


def test_no_python_docstrings():
    # Guard against a silent pass when the roots move.
    assert (REPO / "src" / "pocketquant").is_dir()
    assert _python_docstrings() == []


def test_no_jsdoc_blocks():
    assert TS_ROOT.is_dir()
    assert _jsdoc_blocks() == []
