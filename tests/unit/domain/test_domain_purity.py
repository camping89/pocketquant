"""Test domain layer has no I/O dependencies."""

import ast
import os


FORBIDDEN_IMPORTS = [
    "pymongo",
    "motor",
    "redis",
    "aiohttp",
    "httpx",
    "src.infrastructure",
    "src.common.database",
    "src.common.cache",
    "src.common.jobs",
]


def test_domain_has_no_io_imports():
    """Verify domain layer has no external I/O dependencies."""
    domain_path = "src/domain"
    violations = []

    for root, _dirs, files in os.walk(domain_path):
        for file in files:
            if not file.endswith(".py") or file == "__pycache__":
                continue

            filepath = os.path.join(root, file)
            with open(filepath) as f:
                try:
                    tree = ast.parse(f.read())
                except SyntaxError:
                    continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if any(forbidden in alias.name for forbidden in FORBIDDEN_IMPORTS):
                            violations.append(f"{filepath}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    if node.module and any(
                        forbidden in node.module for forbidden in FORBIDDEN_IMPORTS
                    ):
                        violations.append(f"{filepath}: from {node.module}")

    assert (
        not violations
    ), f"Domain layer has forbidden I/O imports:\n" + "\n".join(violations)
