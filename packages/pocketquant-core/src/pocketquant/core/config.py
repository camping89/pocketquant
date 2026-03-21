import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import MongoDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_project_root() -> Path:
    """Find workspace root by walking up to pyproject.toml with [tool.uv.workspace]."""
    if root := os.environ.get("POCKETQUANT_ROOT"):
        return Path(root)
    current = Path.cwd()
    for parent in [current, *current.parents]:
        pyproject = parent / "pyproject.toml"
        if pyproject.exists() and "[tool.uv.workspace]" in pyproject.read_text():
            return parent
    raise FileNotFoundError(
        "Cannot find project root. Set POCKETQUANT_ROOT env var or run from workspace."
    )


def _resolve_env_file() -> str:
    """Lazily resolve .env path — tolerates missing root (returns empty string)."""
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

    tradingview_username: str | None = None
    tradingview_password: str | None = None

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    log_format: Literal["json", "console"]

    job_worker_count: int
    enable_jobs: bool = True

    # OKX Broker (optional, for live trading)
    okx_api_key: str | None = None
    okx_api_secret: str | None = None
    okx_passphrase: str | None = None
    okx_demo_mode: bool = True

    # Strategy Engine
    default_broker: Literal["paper", "okx"] = "paper"
    paper_initial_balance: float = 100_000.0
    paper_slippage_percent: float = 0.001


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]
