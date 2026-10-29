from __future__ import annotations

import json
import textwrap
from pathlib import Path

from scripts.code_metrics import load_ceiling, main, measure


def _write(root: Path, source: str, name: str = "mod.py") -> Path:
    file = root / name
    file.write_text(textwrap.dedent(source), encoding="utf-8")
    return root


def test_docstring_is_not_counted_as_body(tmp_path: Path) -> None:
    _write(
        tmp_path,
        '''
        def f(x):
            """Doc."""
            y = x + 1
            z = y * 2
            return z
        ''',
    )
    m = measure(tmp_path)
    assert (m["functions_total"], m["functions_measured"], m["tiny"]) == (1, 1, 0)


def test_stub_property_and_dunder_are_excluded_from_measured_set(tmp_path: Path) -> None:
    _write(
        tmp_path,
        """
        import abc
        import functools

        class A:
            def __init__(self):
                self.a = 1

            @property
            def p(self):
                return self.a

            @p.setter
            def p(self, v):
                self.a = v

            @functools.cached_property
            def c(self):
                return 1

            @abc.abstractmethod
            def m(self):
                return 2

            def stub(self):
                ...

            def passing(self):
                \"\"\"Only a docstring and pass.\"\"\"
                pass

            def kept(self):
                return 3
        """,
    )
    m = measure(tmp_path)
    assert m["functions_total"] == 8
    assert m["functions_measured"] == 1
    assert m["tiny"] == 1
    assert m["tiny_share"] == 1.0


def test_attribute_calls_count_as_delegations(tmp_path: Path) -> None:
    _write(
        tmp_path,
        """
        class A:
            def r(self, x):
                return self.a.b(x)

            async def w(self):
                await self.a.b()

            def e(self, y):
                self.x.append(y)
        """,
    )
    assert measure(tmp_path)["delegations"] == 3


def test_plain_call_and_two_statements_are_not_delegations(tmp_path: Path) -> None:
    _write(
        tmp_path,
        """
        def f(x):
            return f(x)

        class A:
            def g(self, x):
                y = x
                return self.a.b(y)
        """,
    )
    assert measure(tmp_path)["delegations"] == 0


def test_function_over_60_lines_is_listed(tmp_path: Path) -> None:
    body = "\n".join(f"    x{i} = {i}" for i in range(60))
    (tmp_path / "long.py").write_text(f"def long_fn():\n{body}\n", encoding="utf-8")
    assert measure(tmp_path)["functions_over_60"] == ["long.py:1 long_fn 61"]


def test_out_writes_metrics_json(tmp_path: Path) -> None:
    _write(tmp_path, "def f(x):\n    return x\n")
    out = tmp_path / "o" / "m.json"
    assert main(["--path", str(tmp_path), "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == measure(tmp_path)


def test_load_ceiling_reads_pyproject_section(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[tool.code-metrics]\nmax_tiny_share = 0.45\nmax_delegations = 60\n",
        encoding="utf-8",
    )
    assert load_ceiling(pyproject) == {"max_tiny_share": 0.45, "max_delegations": 60}


def test_delegation_above_ceiling_exits_1(tmp_path: Path, capsys) -> None:
    src = tmp_path / "src"
    src.mkdir()
    _write(src, "class A:\n    def r(self):\n        return self.a.b()\n")
    assert main(["--path", str(src), "--max-delegations", "0"]) == 1
    assert "::error title=code-metrics::delegations 1 > 0" in capsys.readouterr().out


def test_ratchet_without_section_exits_2(tmp_path: Path, monkeypatch, capsys) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    _write(tmp_path, "def f():\n    return 1\n")
    monkeypatch.chdir(tmp_path)
    assert main(["--path", str(tmp_path), "--ratchet"]) == 2
    assert "code-metrics: no [tool.code-metrics] ceiling" in capsys.readouterr().out
