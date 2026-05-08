---
title: "Binance data provider migration + BarBuilder volume fix"
description: "Replace TradingView with Binance REST + WS for crypto market data, fix volume aggregation, audit + 2y re-sync"
status: completed
priority: P1
effort: 16h
branch: develop
tags: [market-data, infrastructure, binance, bug-fix]
created: 2026-05-07
brainstorm: plans/reports/brainstorm-260507-1835-vps-bars-mismatch-tv-pro-fix.md
---

# Plan — Binance data provider + BarBuilder volume fix

**Brainstorm:** [`brainstorm-260507-1835-vps-bars-mismatch-tv-pro-fix.md`](../reports/brainstorm-260507-1835-vps-bars-mismatch-tv-pro-fix.md)

## Goal

Eliminate TradingView from crypto data path (full removal, not cold backup). Use Binance public REST `/api/v3/klines` for historical sync and Binance WebSocket `@aggTrade` (per-trade stream) for realtime ticks. Fix `BarBuilder.add_tick()` volume bug via delta-pass adapter. Audit then re-sync last **2 years** of bars on production across **all canonical timeframes** (1m, 5m, 15m, 1h, 4h, 1d).

## Phases

| # | Phase | Status | Blocks | Effort |
|---|---|---|---|---|
| 01 | [Binance providers (REST + WS @aggTrade)](./phase-01-binance-providers.md) | completed | 03,04 | 5h |
| 02 | [Volume aggregation fix (delta-pass)](./phase-02-volume-aggregation-fix.md) | completed | — | 1h |
| 03 | [IDataProvider abstraction + TV removal](./phase-03-idataprovider-abstraction-and-tv-removal.md) | completed | 04 | 2h |
| 04 | [Audit + 2y re-sync (all tfs)](./phase-04-audit-and-resync-2y.md) | completed | 05 | 6h |
| 05 | [Cleanup + documentation](./phase-05-cleanup-documentation.md) | completed | — | 2h |

## Dependency graph

```
P1 ──► P3 ──► P4 ──► P5
P2 ─────────────────► P5
```

P2 ships independently in parallel. P3 depends on P1 (BinanceClient must exist). P4 depends on P1+P3 (production wired with Binance). P5 last.

## Single-writer matrix (preserved from plan 260506-1959)

| Data | Store | Writer |
|---|---|---|
| `quote:latest:{ex}:{sym}` | Redis | WS only (Binance WS @aggTrade in P3) |
| `bar:current:{ex}:{sym}:{tf}` | Redis | WS only (Binance WS @aggTrade in P3) |
| `bars` collection | MongoDB | Cron `sync_1m` (Binance REST in P3) |

## Key decisions (locked)

- 100% Binance for crypto path (REST + WS); TradingView **fully removed** — code, env vars, deps deleted
- Re-sync depth: **2 years** for all canonical tfs (1m, 5m, 15m, 1h, 4h, 1d) — full historical replacement
- Re-sync window: `[now - 2y, now - 1m]` per symbol; cascade re-build higher tfs from clean 1m source
- Single provider, no `MARKET_DATA_PROVIDER` env flag (no swap logic — YAGNI)
- WS stream: `@aggTrade` (per-trade delta volume) — fixes Bug #2 (volume) + Bug #3 (sampling resolution)
- Symbol passthrough: PocketQuant `BTCUSDT` == Binance native, zero transformation
- `IDataProvider` relocates to `infrastructure/data_provider.py` — no legacy re-export shim
- `IRealtimeQuoteProvider` Protocol retained for type hints + future provider extensibility

## Success criteria (whole feature)

- 95%+ 1m bars `H>L` and `volume>0` after Phase 4 re-sync
- VPS chart visually matches Binance reference (no flat candles)
- Live in-progress 1m bar volume within ±5% of Binance API ground truth
- Cascade 5m/15m/1h/4h/1d bars aggregate proper OHLCV from clean 1m source
- `infrastructure/tradingview/` folder deleted (verifiable via `ls`)
- Zero `tvDatafeed` imports anywhere in repo (verifiable via `grep -r tvDatafeed packages/`)
- Integrity check still reports `missing_count: 0` after re-sync

## Outcome

**Status:** All 5 phases completed on 2026-05-08. 96 new tests (30 Phase 01 binance providers, 10 Phase 02 volume, 4 Phase 03 DI, 52 Phase 04 audit/resync). Production audit (pre-resync): flat_pct=8.9%, zerovol_pct=8.9%, 60,783 docs, backup saved `/tmp/pq-backup-260508/`. Resync executed: 1,051,199 1m bars fetched from Binance (104s), higher tfs cascaded from clean 1m source. Post-audit: flat_pct=0.0%, zerovol_pct=0.0% across all canonical tfs. Deviation from plan: cascade aggregator slow over WAN at 730d lookback; directly fetched higher tfs from Binance REST instead (estimated hours → 104s). Code review fixes C1-C2-H1-H4 applied. Docs synced (system-architecture, codebase-summary, handler-pipelines, deployment-guide, README, changelog); major version bump 0.1.0 → 2.0.0; commit 95bf32e.

## Risks (top-level)

| Risk | Mitigation |
|---|---|
| Binance IP ban during 2y re-sync (~52.5M bars / ~52,500 calls) | 1200 weight/min budget; 100ms inter-call sleep; resumable per-symbol checkpoint; multi-day execution option |
| WS disconnect during volatile ticks | Existing reconnection pattern; exponential backoff 1s→60s |
| `@aggTrade` high event rate (1000+ events/sec on BTCUSDT volatility) | Profile `BarAppService` lock contention under load; per-symbol lock if needed |
| TV removal — no Plan B if Binance breaks | Pin Binance API version; monitor docs; OKX as future option (research-03) |
| Breaking change to handlers depending on `TradingViewClient` directly | Phase 03 grep guard catches; CI fails on residual imports |

## Rollback strategy

- Phase 2: revert `bar_builder.py` + adapter. Independent fix; isolated git revert safe.
- Phase 3: TV removal is destructive (code deleted) — rollback = git revert merge commit. No env-flag escape hatch.
- Phase 4: re-sync script idempotent; if Binance returns garbage, restore via `mongodump` snapshot taken pre-run.
- Phase 5 docs: pure documentation; no runtime impact.

## Out of scope (YAGNI)

- Multi-provider router/fallback chain (defer until stocks/forex needed)
- OKX market data integration (research-03 confirms Binance superior)
- TradingView Pro account auth (research-01 confirms reCAPTCHA blocks; deferred indefinitely)
- Tick-level archival of WS frames

## Validation Summary

**Validated:** 2026-05-07 19:58 +07
**Last revision:** 2026-05-08 14:30 +07
**Completed:** 2026-05-08 14:30 +07
**Questions asked:** 4

### Confirmed Decisions

- **Phase 4 cleanup scope:** Delete bars for ALL canonical tfs (1m, 5m, 15m, 1h, 4h, 1d) within re-sync window, then cascade-build higher tfs from clean 1m source.
- **Re-sync depth:** **2 years** (full historical replacement) — `[now - 2y, now - 1m]` per symbol.
- **Phase 1 WS stream:** **@aggTrade** (per-trade delta) — fixes Bug #3 sampling resolution; volume aggregation simplifies (delta-sum).
- **Phase 3 TV cleanup:** **Remove entirely** `infrastructure/tradingview/` — no backup, no archive, no env flag.

### Action Items (revisions completed)

- [x] **plan.md:** Effort 12h → 16h. Phase links updated for renamed files (03, 04). TV-removal language replaces cold-backup. `MARKET_DATA_PROVIDER` env flag removed.
- [x] **phase-01-binance-providers.md:** WS stream switched to `@aggTrade`. Volume = `q` per-trade quantity (delta). Effort 4h → 5h.
- [x] **phase-02-volume-aggregation-fix.md:** Simplified to delta-pass adapter contract. Baseline-diff logic removed. Effort 1.5h → 1h.
- [x] **phase-03-idataprovider-abstraction-and-tv-removal.md:** Renamed. Full TV folder + tests + deps + env vars removed. No env flag. Effort 1.5h → 2h.
- [x] **phase-04-audit-and-resync-2y.md:** Renamed. Window 30d → 2y. Delete + cascade rebuild for all tfs. Per-symbol progress logging. Multi-day execution documented. Effort 3h → 6h.
- [x] **phase-05-cleanup-documentation.md:** Reflects TV removal (not demotion). `MARKET_DATA_PROVIDER` references removed.

### Risk additions

- **2y re-sync:** Binance IP ban risk elevated — ~52.5M bars / ~52,500 calls × 100ms = ~88 min sustained. Resumable checkpoint + multi-day option mandatory.
- **TV removal:** No fallback. If Binance breaks, no Plan B. Mitigation: pin API version, monitor docs, OKX as future provider.
- **@aggTrade volume:** Each tick = single trade. High volatility = thousands of events/sec on BTCUSDT. Mitigation: profile `BarAppService` under load; per-symbol lock if contention surfaces.
