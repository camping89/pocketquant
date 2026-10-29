import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, MongoDsn, RedisDsn, SecretStr, field_validator, model_validator
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


APP_ROLE_NAMES = ("api", "worker", "trader")


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

    # Roles this process runs: api (routes, backtests), worker (scheduler and jobs under
    # the worker lease), trader (quote feed, strategies, brokers under the trader lease).
    # The default takes no lease, so a copied local profile never contends for a prod
    # lease; compose sets the roles per service.
    app_roles: str = "api"

    # Exness Trader API (optional). Every order call is refused while
    # exness_live_trading is false, which is the default.
    exness_api_base_url: str | None = None
    exness_account_id: str | None = None
    exness_api_key: SecretStr | None = None
    exness_secret_key: SecretStr | None = None
    exness_live_trading: bool = False
    # Share of the published request rate one process may use; the deep
    # backfill lowers it so it can run beside the app.
    exness_rate_fraction: float = Field(default=1.0, gt=0, le=1)
    # Live-order risk caps for the Exness broker; unset means the broker
    # refuses every order (no loss cap) or sends at most the minimum lot.
    # exness_leverage and exness_risk_per_trade size Exness entries only; the
    # defaults keep the paper sizing.
    exness_daily_loss_cap: float | None = None
    exness_max_lots: float | None = None
    exness_leverage: float = Field(default=1.0, ge=1)
    exness_risk_per_trade: float = Field(default=0.02, gt=0, le=0.10)

    # Admin API (v1 token auth — set in production; unset = dev mode, skip auth)
    # SecretStr prevents accidental logging/serialisation of the token value.
    admin_token: SecretStr | None = None

    # Strategy Engine
    paper_initial_balance: float = 10_000.0
    # Paper accounts for contract specs with a multiplier. One XAUUSD lot (100 oz)
    # is worth far more than the crypto balance, so that balance sizes it to zero.
    # Unset balance falls back to paper_initial_balance; leverage 1 is unleveraged.
    paper_futures_initial_balance: float | None = Field(default=None, gt=0)
    paper_futures_leverage: float = Field(default=1.0, ge=1)
    paper_slippage_bps: float = 0.5  # 0.5 bp = 0.005%
    paper_commission_bps: float = 3.0  # 3 bps
    reconcile_interval_seconds: float = 5.0

    @field_validator("app_roles")
    @classmethod
    def _canonical_roles(cls, value: str) -> str:
        names = {r.strip() for r in value.split(",") if r.strip()}
        if not names or names - set(APP_ROLE_NAMES):
            raise ValueError(f"APP_ROLES must list api, worker or trader; got {value!r}")
        return ",".join(r for r in APP_ROLE_NAMES if r in names)

    @model_validator(mode="before")
    @classmethod
    def _refuse_retired_job_switch(cls, data: object) -> object:
        # A silently ignored ENABLE_JOBS=false would let a local process take a prod lease.
        keys = {str(k).lower() for k in data} if isinstance(data, dict) else set()
        if "enable_jobs" in keys or "enable_jobs" in {k.lower() for k in os.environ}:
            raise ValueError("ENABLE_JOBS is retired; set APP_ROLES (api, worker, trader) instead")
        return data

    @property
    def roles(self) -> frozenset[str]:
        return frozenset(self.app_roles.split(","))


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]
