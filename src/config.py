from functools import lru_cache
from typing import Literal

from pydantic import Field, MongoDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "PocketQuant"
    app_version: str = "0.1.0"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False

    api_host: str = "0.0.0.0"
    api_port: int = 8765
    api_prefix: str = "/api/v1"

    mongodb_url: MongoDsn = Field(
        default="mongodb://pocketquant:pocketquant_dev@localhost:27018/pocketquant?authSource=admin"
    )
    mongodb_database: str = "pocketquant"
    mongodb_min_pool_size: int = 5
    mongodb_max_pool_size: int = 50

    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")
    redis_cache_ttl: int = 3600

    tradingview_username: str | None = None
    tradingview_password: str | None = None

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "console"] = "json"

    job_worker_count: int = 4


@lru_cache
def get_settings() -> Settings:
    return Settings()
