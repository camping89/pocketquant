from functools import lru_cache
from typing import Literal

from pydantic import MongoDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings. All values must be provided via .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str
    app_version: str
    environment: Literal["development", "staging", "production"]
    debug: bool

    api_host: str
    api_port: int
    api_prefix: str

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


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]
