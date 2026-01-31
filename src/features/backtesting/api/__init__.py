"""Backtest API submodule - REST endpoints for backtesting."""

from src.features.backtesting.api.backtest_routes import router as backtest_router

__all__ = ["backtest_router"]
