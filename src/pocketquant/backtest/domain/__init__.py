"""Backtest domain — non-persisted calculation services.

Persisted entities/value objects (BacktestResult, Order, Trade, …) now live in
``pocketquant.core.domain.backtest``. This package retains only stateless
domain services (e.g. PerformanceCalculator).
"""
