"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, MongoDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "PocketQuant"
    app_version: str = "0.1.0"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_prefix: str = "/api/v1"

    # MongoDB
    mongodb_url: MongoDsn = Field(
        default="mongodb://pocketquant:pocketquant_dev@localhost:27017/pocketquant?authSource=admin"
    )
    mongodb_database: str = "pocketquant"
    mongodb_min_pool_size: int = 5
    mongodb_max_pool_size: int = 50

    # Redis
    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")
    redis_cache_ttl: int = 3600  # Default cache TTL in seconds

    # TradingView
    tradingview_username: str | None = None
    tradingview_password: str | None = None

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "console"] = "json"

    # Background Jobs
    job_worker_count: int = 4


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
