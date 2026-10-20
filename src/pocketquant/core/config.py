import os
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, MongoDsn, RedisDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from pocketquant.core.domain.shared.enums import (
    TradingViewCapabilities,
    TradingViewPlan,
    capabilities_for,
)


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

    # TradingView (index futures data source).
    #
    # Entitlement is ONE knob. The three values this used to carry — bar cap,
    # poll interval and a delayed-data flag — are consequences of the plan the
    # account holds, and setting them independently lets an operator express
    # states that cannot exist, such as real-time data on a free account.
    # Set these from ../pocketquant-config/, never here.
    tradingview_username: str | None = None
    tradingview_password: SecretStr | None = None
    # A token supplied directly, which bypasses username/password login. The
    # scraper's login is its most fragile part, and it is NOT a constructor
    # argument upstream — the client assigns it after construction.
    tradingview_auth_token: SecretStr | None = None
    tradingview_plan: TradingViewPlan = TradingViewPlan.FREE
    # Explicit overrides. Each may only make a request GENTLER than the plan
    # allows, never more aggressive — see ``tradingview_capabilities``. Bounded
    # above zero because 0 is not "unset": it would make every request ask for
    # no bars and every sync silently insert nothing.
    tradingview_max_bars: int | None = Field(default=None, gt=0)
    tradingview_poll_seconds: int | None = Field(default=None, gt=0)

    @property
    def tradingview_capabilities(self) -> TradingViewCapabilities:
        """What the configured plan permits, with explicit overrides applied.

        An override may only make a request gentler. A lower bar count is
        operator caution; a higher one would claim an entitlement the account
        does not hold, which is the impossible state this single knob exists to
        prevent. ``min_poll_seconds`` is a floor for the same reason and is
        never overridden — ``tradingview_poll_seconds`` is the configured
        interval, which callers clamp with ``max(configured, min_poll_seconds)``.
        """
        base = capabilities_for(self.tradingview_plan)
        if self.tradingview_max_bars is None:
            return base
        return replace(base, max_bars=min(self.tradingview_max_bars, base.max_bars))

    @property
    def tradingview_effective_poll_seconds(self) -> int:
        """The quote poll interval: the configured one, never below the plan floor."""
        floor = self.tradingview_capabilities.min_poll_seconds
        return max(self.tradingview_poll_seconds or floor, floor)

    # OKX Broker (optional, for live trading)
    okx_api_key: str | None = None
    okx_api_secret: str | None = None
    okx_passphrase: str | None = None
    okx_demo_mode: bool = True

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
    exness_daily_loss_cap: float | None = None
    exness_max_lots: float | None = None

    # Admin API (v1 token auth — set in production; unset = dev mode, skip auth)
    # SecretStr prevents accidental logging/serialisation of the token value.
    admin_token: SecretStr | None = None

    # Strategy Engine
    paper_initial_balance: float = 10_000.0
    paper_slippage_bps: float = 0.5  # 0.5 bp = 0.005%
    paper_commission_bps: float = 3.0  # 3 bps
    reconcile_interval_seconds: float = 5.0


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]
