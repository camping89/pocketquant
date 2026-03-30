---
phase: 2
priority: P0
effort: S
status: complete
depends_on: [1]
---

# Phase 2: API Client Layer

## Overview

Type-safe API client + TanStack Query hooks for OHLCV, symbols, and quotes endpoints.

## Context

- [plan.md](plan.md)
- OHLCV endpoint: `GET /api/v1/market-data/ohlcv/{exchange}/{symbol}?interval=1d&start_date=&end_date=&limit=1000`
- Symbols endpoint: `GET /api/v1/market-data/symbols?exchange=`
- Quote endpoints: `POST /api/v1/quotes/subscribe`, `GET /api/v1/quotes/latest/{exchange}/{symbol}`
- Response shapes documented in [API exploration report](../reports/Explore-260330-1016-api-charting.md)

## Requirements

### Functional
- Fetch OHLCV bars with interval/date range/limit params
- Fetch symbol list for dropdowns
- Transform API response → Lightweight Charts data format
- Error handling with retry

### Non-Functional
- Type-safe: full TypeScript types for API responses
- Cached: TanStack Query with staleTime for bars (5min), symbols (30min)

## Architecture

```
src/
├── types/
│   └── market-data.ts        # Bar, Symbol, Interval, Quote types
├── api/
│   ├── api-client.ts          # Base fetch wrapper
│   └── market-data-api.ts     # OHLCV + symbols + quotes fetch functions
└── hooks/
    ├── use-ohlcv.ts           # useQuery for OHLCV bars
    └── use-symbols.ts         # useQuery for symbol list
```

## Key Types

```typescript
// Matches API response shape
interface OHLCVBar {
  datetime: string;   // ISO8601
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

// Lightweight Charts format
interface CandlestickData {
  time: UTCTimestamp;  // Unix seconds
  open: number;
  high: number;
  low: number;
  close: number;
}

interface VolumeData {
  time: UTCTimestamp;
  value: number;
  color: string;  // green/red based on close vs open
}

type Interval = '1' | '3' | '5' | '15' | '30' | '45' | '60' | '120' | '180' | '240' | '1D' | '1W' | '1M';

interface Symbol {
  id: string;
  code: string;
  exchange: string;
  name: string;
  asset_type: string;
  is_active: boolean;
}
```

## Implementation Steps

1. Create `src/types/market-data.ts` — API response types + LC data types
2. Create `src/api/api-client.ts` — base fetch with error handling:
   ```typescript
   async function apiFetch<T>(path: string, params?: Record<string, string>): Promise<T> {
     const url = new URL(path, window.location.origin);
     if (params) Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
     const res = await fetch(url);
     if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
     return res.json();
   }
   ```
3. Create `src/api/market-data-api.ts`:
   - `fetchOHLCV(exchange, symbol, interval, startDate?, endDate?, limit?)` → transforms datetime to UTCTimestamp
   - `fetchSymbols(exchange?)` → returns Symbol[]
4. Create `src/hooks/use-ohlcv.ts`:
   ```typescript
   function useOHLCV(exchange: string, symbol: string, interval: Interval) {
     return useQuery({
       queryKey: ['ohlcv', exchange, symbol, interval],
       queryFn: () => fetchOHLCV(exchange, symbol, interval),
       staleTime: 5 * 60 * 1000,
     });
   }
   ```
5. Create `src/hooks/use-symbols.ts`:
   ```typescript
   function useSymbols(exchange?: string) {
     return useQuery({
       queryKey: ['symbols', exchange],
       queryFn: () => fetchSymbols(exchange),
       staleTime: 30 * 60 * 1000,
     });
   }
   ```
6. **Data transform** — convert ISO datetime → UTCTimestamp (seconds since epoch):
   ```typescript
   function toUTCTimestamp(iso: string): UTCTimestamp {
     return (new Date(iso).getTime() / 1000) as UTCTimestamp;
   }
   ```

## Related Code Files

- **Create:** `src/types/market-data.ts`, `src/api/api-client.ts`, `src/api/market-data-api.ts`, `src/hooks/use-ohlcv.ts`, `src/hooks/use-symbols.ts`
- **Read:** API route handlers in `packages/pocketquant-api/` for response shape verification

## Todo

- [x] Define TypeScript types for API responses + LC data
- [x] Create base fetch wrapper
- [x] Implement OHLCV fetch + transform
- [x] Implement symbols fetch
- [x] Create useOHLCV hook
- [x] Create useSymbols hook
- [x] Verify data loads from running API

## Success Criteria

- `useOHLCV('OKX', 'BTCUSDT', '1D')` returns candlestick + volume data arrays
- `useSymbols()` returns symbol list
- Types are strict — no `any`
- Network errors handled gracefully (TanStack Query retry)
