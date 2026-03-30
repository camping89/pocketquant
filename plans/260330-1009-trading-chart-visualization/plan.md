---
status: complete
created: 2026-03-30
branch: develop
blockedBy: []
blocks: []
---

# Trading Chart Visualization

TradingView-like charting SPA for PocketQuant using Lightweight Charts v5 + React + Vite + TypeScript.

## Context

- **Brainstorm:** [brainstorm report](../reports/brainstorm-260330-1009-trading-chart-visualization.md)
- **Research:** [LC v5 research](../reports/researcher-260330-1018-tradingview-lightweight-charts-v4.md), [API exploration](../reports/Explore-260330-1016-api-charting.md)
- **Existing API:** OHLCV endpoint ready, CORS configured, symbols endpoint ready, quote endpoints ready
- **Key finding:** Lightweight Charts **v5** (not v4) — native multi-pane support for indicators

## Package Location

`packages/pocketquant-web/` — new package in monorepo, no Python dependency.

## Phases

| # | Phase | Status | Priority | Effort |
|---|-------|--------|----------|--------|
| 1 | [Project scaffolding](phase-01-project-scaffolding.md) | complete | P0 | S |
| 2 | [API client layer](phase-02-api-client-layer.md) | complete | P0 | S |
| 3 | [Candlestick + Volume chart](phase-03-candlestick-volume-chart.md) | complete | P0 | M |
| 4 | [Technical indicators](phase-04-technical-indicators.md) | complete | P1 | M |
| 5 | [Real-time WebSocket updates](phase-05-realtime-websocket.md) | complete | P1 | M |
| 6 | [UI controls](phase-06-ui-controls.md) | complete | P0 | S |

## Dependency Chain

```
Phase 1 (scaffold) → Phase 2 (API) → Phase 3 (chart) → Phase 6 (controls)
                                   → Phase 4 (indicators)
                                   → Phase 5 (real-time)
```

Phases 4, 5, 6 can run in parallel after Phase 3.

## Tech Stack

| Tool | Version | Purpose |
|------|---------|---------|
| React | 19 | UI framework |
| Vite | 6 | Build tool |
| TypeScript | 5.7+ | Type safety |
| lightweight-charts | 5.x | Financial charting |
| TanStack Query | 5.x | Data fetching + caching |

## API Endpoints Used

| Endpoint | Purpose |
|----------|---------|
| `GET /api/v1/market-data/ohlcv/{exchange}/{symbol}` | Historical OHLCV bars |
| `GET /api/v1/market-data/symbols` | Symbol list for dropdown |
| `POST /api/v1/quotes/subscribe` | Subscribe to real-time quotes |
| `GET /api/v1/quotes/latest/{exchange}/{symbol}` | Latest quote |
| `POST /api/v1/quotes/start-feed` / `stop-feed` | WebSocket feed control |

## Success Criteria

- [x] Candlestick + volume chart renders OHLCV data from API
- [x] Symbol/interval dropdowns switch chart data
- [x] At least 4 indicators (MA, RSI, MACD, Bollinger) render in separate panes
- [x] Real-time bar updates via WebSocket without page refresh
- [x] Responsive layout, dark theme
- [x] `npm run build` produces deployable static assets
