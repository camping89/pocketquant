---
phase: 5
priority: P1
effort: M
status: complete
depends_on: [3]
---

# Phase 5: Real-time WebSocket Updates

## Overview

Live bar updates via the existing quote system. Subscribe to symbol → receive price updates → update last candle or append new candle on the chart.

## Context

- [plan.md](plan.md)
- Existing API flow: `POST /quotes/start-feed` → `POST /quotes/subscribe` → `GET /quotes/latest/{exchange}/{symbol}` (polling) or WebSocket
- Backend: TradingViewWebSocketClient → QuoteAppService → Redis cache → BarAppService aggregates ticks into bars
- Current bar (incomplete) available at: `GET /api/v1/market-data/current-bar/{exchange}/{symbol}?interval=1m`
- No direct WebSocket endpoint to frontend yet — need to add or use polling

## Key Decision: Polling vs WebSocket

**Option A: Polling** (recommended for MVP)
- Poll `GET /quotes/latest/{exchange}/{symbol}` every 1-2 seconds
- Simpler, works with existing API, no backend changes
- Slightly higher latency (1-2s vs ~100ms)

**Option B: Server-Sent Events / WebSocket** (future)
- Requires new endpoint in FastAPI
- Better UX for real-time
- More complex

**Decision: Start with polling (Option A), add WebSocket endpoint later.**

## Architecture

```
src/
├── hooks/
│   └── use-realtime-bar.ts    # Poll latest quote, update chart series
└── api/
    └── market-data-api.ts     # Add fetchLatestQuote(), fetchCurrentBar()
```

## Implementation Steps

1. Add `fetchLatestQuote(exchange, symbol)` to `market-data-api.ts`
2. Add `fetchCurrentBar(exchange, symbol, interval)` to `market-data-api.ts`
3. Create `src/hooks/use-realtime-bar.ts`:
   ```typescript
   function useRealtimeBar(
     exchange: string,
     symbol: string,
     interval: Interval,
     candleSeries: ISeriesApi<'Candlestick'> | null,
     volumeSeries: ISeriesApi<'Histogram'> | null,
   ) {
     useEffect(() => {
       if (!candleSeries || !volumeSeries) return;

       const id = setInterval(async () => {
         const bar = await fetchCurrentBar(exchange, symbol, interval);
         if (!bar) return;

         candleSeries.update({
           time: toUTCTimestamp(bar.datetime),
           open: bar.open,
           high: bar.high,
           low: bar.low,
           close: bar.close,
         });

         volumeSeries.update({
           time: toUTCTimestamp(bar.datetime),
           value: bar.volume,
           color: bar.close >= bar.open
             ? 'rgba(38, 166, 154, 0.3)'
             : 'rgba(239, 83, 80, 0.3)',
         });
       }, 2000);

       return () => clearInterval(id);
     }, [exchange, symbol, interval, candleSeries, volumeSeries]);
   }
   ```
4. Expose series refs from `TradingChart` for the hook to consume
5. Start/stop feed on symbol change:
   - On mount/symbol change: `POST /quotes/start-feed` + `POST /quotes/subscribe`
   - On unmount/symbol change: `POST /quotes/unsubscribe` + `POST /quotes/stop-feed`
6. Handle bar rollover: when new bar time > last bar time, it becomes a new candle (LC handles this automatically with `update()`)

## Feed Lifecycle

```
Symbol selected → POST /quotes/subscribe → setInterval poll
                                         → candleSeries.update()
Symbol changed  → POST /quotes/unsubscribe (old)
                → POST /quotes/subscribe (new)
                → Restart polling
Unmount         → POST /quotes/unsubscribe → clearInterval
```

## Related Code Files

- **Create:** `src/hooks/use-realtime-bar.ts`
- **Modify:** `src/api/market-data-api.ts` (add quote/current-bar fetchers), `src/components/chart/trading-chart.tsx` (expose series refs, integrate hook)
- **Read:** `packages/pocketquant-api/src/pocketquant/api/market_data/routes/quote_routes.py`

## Todo

- [x] Add fetchLatestQuote + fetchCurrentBar to API client
- [x] Create useRealtimeBar hook with polling
- [x] Integrate with TradingChart series refs
- [x] Handle subscribe/unsubscribe lifecycle
- [x] Test: verify last candle updates in real-time
- [x] Handle bar rollover (new candle appears)

## Success Criteria

- Last candle updates every 2s with latest price
- New candle appears when bar interval completes
- Volume updates in sync with price
- No stale data after symbol switch
- Clean unsubscribe on unmount

## Risk Assessment

- **Polling overhead**: 1 request/2s is negligible; backend already caches in Redis
- **Race condition on symbol switch**: clearInterval before new subscribe; stale responses ignored via symbol check
- **Feed not started**: Need to ensure `start-feed` called before subscribing; handle 400 errors gracefully
