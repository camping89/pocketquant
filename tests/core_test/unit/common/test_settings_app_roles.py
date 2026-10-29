from __future__ import annotations

from pathlib import Path

import pydantic
import pytest

from pocketquant.core.config import Settings

_REQUIRED = {
    "app_name": "pocketquant-test",
    "app_version": "0.0.1",
    "environment": "development",
    "mongodb_url": "mongodb://localhost:27017",
    "mongodb_database": "pocketquant_test",
    "mongodb_min_pool_size": 1,
    "mongodb_max_pool_size": 10,
    "redis_url": "redis://localhost:6379/1",
    "redis_cache_ttl": 3600,
    "log_level": "DEBUG",
    "log_format": "console",
}


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **{**_REQUIRED, **overrides})  # pyright: ignore[reportCallIssue]


def test_app_roles_default_is_api_only() -> None:
    settings = _settings()
    assert settings.roles == frozenset({"api"})
    assert settings.app_roles == "api"


def test_app_roles_parses_a_comma_list() -> None:
    assert _settings(app_roles="worker, api").app_roles == "api,worker"


def test_app_roles_rejects_an_unknown_role() -> None:
    with pytest.raises(pydantic.ValidationError):
        _settings(app_roles="api,bogus")


def test_app_roles_rejects_an_empty_list() -> None:
    with pytest.raises(pydantic.ValidationError):
        _settings(app_roles=" , ")


def test_retired_job_switch_in_the_environment_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_JOBS", "false")
    with pytest.raises(pydantic.ValidationError, match="APP_ROLES"):
        _settings()


def test_retired_job_switch_in_the_env_file_fails(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    lines = [f"{key.upper()}={value}" for key, value in _REQUIRED.items()]
    path.write_text("\n".join([*lines, "ENABLE_JOBS=false"]) + "\n", encoding="utf-8")
    with pytest.raises(pydantic.ValidationError, match="APP_ROLES"):
        Settings(_env_file=str(path))  # pyright: ignore[reportCallIssue]
