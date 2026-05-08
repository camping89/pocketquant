---
title: "Binance per-minute sync: fix in-progress bar capture + regression backfill"
description: "Fix BinanceClient.fetch_ohlcv fetching in-progress bars; backfill regression window since 2026-05-08 07:30 UTC; harden verify cron"
status: completed
priority: P1
effort: 6h
branch: develop
tags: [market-data, binance, bug-fix, regression]
blockedBy: []
blocks: []
created: 2026-05-08
createdBy: ck:plan
source: skill
related:
  - plans/260507-1835-vps-bars-mismatch-tv-pro-fix/  # immediate predecessor (Binance migration)
  - plans/reports/debugger-260508-2116-binance-bar-mismatch.md  # debug evidence
---

# Plan — Binance per-minute sync regression fix

**Debug report:** [`debugger-260508-2116-binance-bar-mismatch.md`](../reports/debugger-260508-2116-binance-bar-mismatch.md)

## Goal

Loại bỏ regression làm corrupt OHLCV bars sau migration Binance (plan `260507-1835-vps-bars-mismatch-tv-pro-fix`). Cụ thể: `BinanceClient.fetch_ohlcv` fetch cả bar đang chạy → cron `sync_1m` ghi snapshot 2 giây đầu vào Mongo → `filter_new_bars` khóa cứng partial data. Sửa root cause, backfill window từ 2026-05-08 07:30 UTC (lúc 2y resync hoàn thành) đến hiện tại, và harden verify cron để catch regression tương tự trong tương lai.

## Phases

| # | Phase | Status | Blocks | Effort |
|---|---|---|---|---|
| 01 | [Fix endpoint at source](./phase-01-fix-endpoint-at-source.md) | completed | 02 | 1.5h |
| 02 | [Backfill regression window](./phase-02-backfill-regression-window.md) | completed | 03 | 2h |
| 03 | [Harden verify cron](./phase-03-harden-verify-cron.md) | completed | 04 | 1.5h |
| 04 | [Docs sync and journal](./phase-04-docs-sync-and-journal.md) | completed | — | 1h |

## Dependency graph

```
P1 ──► P2 ──► P3 ──► P4
```

P1 phải xong trước P2 (nếu không backfill cũng dính bug). P3 độc lập về code nhưng nên sau P2 để không alert nhiễu trong lúc backfill. P4 cuối.

## Single-writer matrix (preserved from migration plan)

| Data | Store | Writer |
|---|---|---|
| `quote:latest:{ex}:{sym}` | Redis | WS only (Binance @aggTrade) |
| `bar:current:{ex}:{sym}:{tf}` | Redis | WS only (Binance @aggTrade) |
| `bars` collection (1m) | MongoDB | Cron `sync_1m` (Binance REST) **— bug fix here** |
| `bars` collection (5m–1d) | MongoDB | Cron cascade aggregator from 1m |

## Key decisions

- **Fix at source** (Option A in debug report) — cap `endTime` ở biên closed bar gần nhất trong `BinanceClient.fetch_ohlcv`. KISS, single point fix.
- **Backfill scope** — chỉ regression window từ 2026-05-08 07:30 UTC (lúc 2y resync hoàn thành) đến lúc deploy fix. Không cần lại 2y; data cũ đã clean.
- **Backfill method** — delete bị ảnh hưởng + re-sync via fixed code path; cascade tự rebuild từ 1m. **Pause cron `sync_1m` trong lúc backfill** qua `JobScheduler.pause_job`; fallback `ENABLE_JOBS=false` + restart container.
- **Verify cron strengthen** — compare full OHLCV (O+H+L+C+V) thay vì chỉ close; threshold **0.01% relative cho price (O/H/L/C), 5% relative cho volume**, alert khi > 5% bars divergent; coverage = all tracked symbols (drop round-robin). Thay thế threshold absolute hiện tại (`abs(close - close) > $0.01`) vì không scale theo asset.
- **Observability** — chỉ thêm `logger.debug("binance.in_progress_bar_filtered", count=N)`. **KHÔNG add Prometheus** — codebase chưa có infra, vi phạm YAGNI.
- **Redis cache** — KHÔNG invalidate `bar:current:*` sau backfill. Namespace độc lập với `bars` Mongo; WS @aggTrade tự overwrite trong vài giây.
- **No env flag** — fix là backwards-compat (chỉ thay đổi behavior endpoint), không cần feature flag.
- **WebSocket path** — KHÔNG đụng. WS @aggTrade build in-memory, không write Mongo.

## Success criteria

- 1m bars mới sau deploy match Binance REST tuyệt đối (O/H/L/C, volume sai số < 0.001 BTC)
- Cascade 5m/15m/1h/4h/1d aggregate đúng từ 1m clean source
- Regression window đã backfill: 0 bar có `tick_count < 50` (BTCUSDT/ETHUSDT spot)
- Verify cron compare full OHLCV; alert trong 1 phút nếu detect mismatch
- Unit test cover: `BinanceClient.fetch_ohlcv` không bao giờ trả bar có `openTime >= floor(now/duration)*duration`
- Docs: `system-architecture.md`, `codebase-summary.md` cập nhật; journal entry written

## Risks (top-level)

| Risk | Mitigation |
|---|---|
| Backfill chạy song song với cron `sync_1m` đang chạy → race | Pause `sync_1m` job trong lúc backfill; dùng `JobScheduler.pause_job` hoặc set `ENABLE_JOBS=false` trên VPS tạm |
| Binance rate limit khi backfill ~7h × 60 phút × 6 tf = ~2520 bars | Trong budget (2 weight/call × 2520 = 5040 weight tổng, 1200/min limit → < 5 phút) |
| Delete sai range / quá rộng | Backup `bars` collection trước (mongodump); range guard chặt theo datetime |
| Verify cron alert spam ngay sau deploy fix | Deploy P3 SAU P2; window quan sát 24h trước khi tighten threshold |
| Sửa sai `endTime` logic, broke existing tests | Phase 01 thêm unit test mock `now`; CI gate |

## Rollback strategy

- **P1 (code fix):** git revert single commit; cron tiếp tục fetch in-progress bar (status quo regression).
- **P2 (backfill):** restore `bars` collection từ mongodump backup taken pre-backfill.
- **P3 (verify cron):** revert verify_cascade changes; threshold cũ vẫn hoạt động (chỉ kém nhạy).
- **P4 (docs):** pure docs revert.

## Out of scope (YAGNI)

- Đổi sang upsert thay vì insert_many (Option C debug report) — không cần nếu fix at source đúng
- 2y full re-sync lại — data cũ đã clean (post-migration audit confirmed flat_pct=0%)
- Multi-provider router — đã out-of-scope từ migration plan
- Strict mode trong cron để fail-fast nếu Binance trả bar in-progress — Phase 03 covers via verify

## Validation Summary

**Created:** 2026-05-08 21:48 +07
**Validated:** pending (sẽ chạy `/ck:plan validate` sau khi user review)

### Resolved decisions (2026-05-08)

| # | Question | Decision | Rationale |
|---|---|---|---|
| 1 | Pause cron khi backfill? | **Có**, qua `JobScheduler.pause_job`; fallback `ENABLE_JOBS=false` + restart | Cron mới không tự fix bars cũ vì `filter_new_bars` drop existing; race nguy hiểm khi delete + insert song song |
| 2 | Prometheus metric? | **Skip**, dùng `logger.debug("binance.in_progress_bar_filtered", count=N)` | Codebase chưa có Prometheus infra; add 1 metric vi phạm YAGNI |
| 3 | Verify threshold? | **Price 0.01% relative, Volume 5% relative, alert khi > 5% bars divergent** | Hiện tại absolute $0.01 close-only không scale; 0.01% trên BTC $80k = $8 đủ tight, scale theo asset; volume 5% catch major drift |
| 4 | Invalidate Redis post-backfill? | **Skip** | `bar:current:*` namespace độc lập với `bars` Mongo; WS tự overwrite trong vài giây |

### Remaining open questions

(none — all 4 questions resolved before implementation)
