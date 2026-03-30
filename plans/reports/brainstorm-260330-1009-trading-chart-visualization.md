# Brainstorm: Trading Chart Visualization

**Date:** 2026-03-30 | **Status:** Approved

## Problem Statement

PocketQuant has OHLCV bar data in MongoDB with API endpoints ready, but no visualization. Need TradingView-like charting UI.

## Decisions

| Aspect | Choice | Rationale |
|--------|--------|-----------|
| Deploy | Standalone SPA | Scalable, independent deployment |
| Chart lib | TradingView Lightweight Charts v4 | ~40KB, native financial charts, closest to TradingView |
| Framework | React + Vite + TypeScript | Mature ecosystem, good LC wrappers |
| Location | `packages/pocketquant-web/` | Consistent with monorepo structure |
| Features | OHLCV + indicators + real-time | Full feature set from start |
| UI Controls | Symbol + interval dropdowns | Full interactivity |

## Architecture

```
packages/pocketquant-web/
├── src/
│   ├── api/              # API client, WebSocket
│   ├── components/
│   │   ├── chart/        # LC wrapper, indicators overlay
│   │   ├── controls/     # Symbol/interval selectors
│   │   └── layout/       # App shell
│   ├── hooks/            # useOHLCV, useWebSocket, useIndicators
│   ├── types/            # Bar, Symbol, Interval
│   └── App.tsx
├── package.json
├── tsconfig.json
└── vite.config.ts
```

### Data Flow

- Historical: MongoDB → FastAPI `/ohlcv` → fetch → Lightweight Charts
- Real-time: Redis → FastAPI WebSocket → `useWebSocket` → `series.update()`
- Indicators: Client-side computation from OHLCV data

### Technical Indicators (client-side)

- MA, EMA, SMA
- RSI
- MACD (line + signal + histogram)
- Bollinger Bands

Rendered as additional `LineSeries`/`HistogramSeries` on Lightweight Charts.

## Risks

1. **LC drawing tools** — not built-in; custom work needed if required later
2. **Large datasets** — client-side indicator calc OK for <10K bars; backend fallback if needed
3. **WebSocket reconnection** — must handle gracefully
4. **CORS** — FastAPI needs CORS middleware for frontend origin

## Next Steps

Create implementation plan via `/ck:plan`.
