import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import MongoDsn, RedisDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_project_root() -> Path:
    if root := os.environ.get("POCKETQUANT_ROOT"):
        return Path(root)
    current = Path.cwd()
    for parent in [current, *current.parents]:
        pyproject = parent / "pyproject.toml"
        if pyproject.exists() and 'name = "pocketquant"' in pyproject.read_text():
            return parent
    raise FileNotFoundError(
        "Cannot find project root. Set POCKETQUANT_ROOT env var or run from workspace."
    )


def _resolve_env_file() -> str:
    try:
        return str(_find_project_root() / ".env")
    except FileNotFoundError:
        return ""


class Settings(BaseSettings):
    """Application settings. All values must be provided via .env file."""

    model_config = SettingsConfigDict(
        env_file=_resolve_env_file(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str
    app_version: str
    environment: Literal["development", "staging", "production"]

    api_prefix: str = "/api/v1"

    mongodb_url: MongoDsn
    mongodb_database: str
    mongodb_min_pool_size: int
    mongodb_max_pool_size: int

    redis_url: RedisDsn
    redis_cache_ttl: int

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    log_format: Literal["json", "console"]

    enable_jobs: bool = True

    # OKX Broker (optional, for live trading)
    okx_api_key: str | None = None
    okx_api_secret: str | None = None
    okx_passphrase: str | None = None
    okx_demo_mode: bool = True

    # Admin API (v1 token auth — set in production; unset = dev mode, skip auth)
    # SecretStr prevents accidental logging/serialisation of the token value.
    admin_token: SecretStr | None = None

    # Strategy Engine
    default_broker: Literal["paper", "okx"] = "paper"
    paper_initial_balance: float = 100_000.0
    paper_slippage_percent: float = 0.001
    reconcile_interval_seconds: float = 5.0


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]
