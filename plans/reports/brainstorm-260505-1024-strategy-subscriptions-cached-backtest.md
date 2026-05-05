---
type: brainstorm
date: 2026-05-05
slug: strategy-subscriptions-cached-backtest
status: agreed
---

# Brainstorm — Strategy Subscriptions + Cached Backtest

## Problem
Hiện tại chọn strategy trong dropdown → trigger `POST /backtest/run` → recalc đồng bộ → UX chậm. Mỗi strategy chỉ gắn 1 symbol qua YAML, không scale.

## Goals
- Chọn strategy/subscription → chart paint < 200ms (đọc cache, không recalc)
- 1 strategy ↔ N symbols (mapping persistent)
- Run backtest = manual, async, fan-out cho tất cả subscriptions
- Cascade delete: xóa strategy/subscription → xóa backtest cache liên quan
- Stale data: hiển thị `last_run_at`, user tự refresh

## Decisions (locked)

| # | Quyết định | Lý do |
|---|------------|-------|
| 1 | Manual trigger qua nút "Run All Backtests" | Strategy cần tweak nhiều trước khi publish, user biết khi nào sẵn sàng |
| 2 | Async via `JobScheduler` (`MongoDBJobStore`) | Không block UI, tận dụng infra sẵn có |
| 3 | Backtest range = full data có sẵn (BarRepository.get_range) | Full picture, không cần user chọn |
| 4 | 1 backtest per subscription, upsert | Chart load nhanh, query đơn giản |
| 5 | Re-run = overwrite không hỏi | Giảm friction, user chịu trách nhiệm |
| 6 | Delete strategy/subscription → cascade backtest | "no worries" theo lời user |
| 7 | Stale = hiển thị `last_run_at`, manual refresh | KISS, tránh CPU lãng phí |
| 8 | Mapping (strategy ↔ symbols) trong mongo, quản lý qua API | Single source of truth runtime |
| 9 | "Run All" fan-out, không có per-row Run | Đơn giản UI, ít button |
| 10 | Mapping chứa (symbol, exchange, interval) | Linh hoạt đa interval/exchange cho cùng logic |
| 11 | Auth/authz: skip | User confirm |

## Architecture

```
Strategy (YAML, in-memory via StrategyAppService)
    └── 1..N StrategySubscription (mongo: strategy_subscriptions)
            └── 0..1 BacktestResult (mongo: backtest_runs)
                keyed by subscription_id (upsert)
```

### Collections

**`strategy_subscriptions`** (new)
```
_id: deterministic hash(strategy_id, symbol, exchange, interval)
strategy_id: str
symbol: str
exchange: str
interval: str (Interval enum value)
created_at: datetime
indexes: (strategy_id), unique on _id
```

**`backtest_runs`** (extend existing)
```
+ subscription_id: str        (cache key)
+ status: 'running'|'done'|'failed'
+ last_run_at: datetime
+ error_msg: str?
upsert filter: { subscription_id }
indexes: (subscription_id) unique, (strategy_id) for cascade
```

### Routes (new)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/strategies/{id}/symbols` | Body `{symbol, exchange, interval}` → tạo subscription |
| GET | `/strategies/{id}/symbols` | List subscriptions + status backtest |
| DELETE | `/strategies/{id}/symbols/{sub_id}` | Cascade delete subscription + backtest |
| POST | `/strategies/{id}/backtest/run-all` | Fan-out 1 job/subscription, returns `[job_ids]` |
| GET | `/strategies/{id}/symbols/{sub_id}/backtest` | Cached BacktestResult cho chart |
| DELETE | `/strategies/{id}` | Cascade unload + xóa subscriptions + backtests |

### Job Worker

```python
# pocketquant-trading/jobs/backtest_jobs.py
async def run_subscription_backtest(subscription_id: str):
    sub = subscription_repo.get(subscription_id)
    config = build_backtest_config(sub, full_range=BarRepository.get_range(sub.symbol, sub.interval))
    backtest_repo.upsert_status(subscription_id, status='running')
    try:
        result = await BacktestAppService.run(config)
        backtest_repo.save(result, subscription_id, status='done')
    except Exception as e:
        backtest_repo.upsert_status(subscription_id, status='failed', error_msg=str(e))
```

Concurrency: `scheduler.add_job(id=f"bt:{sub_id}", replace_existing=True)` → 1 sub = 1 job slot.

## Frontend

- **Subscription panel** trong strategy section:
  ```
  [Strategy: macd-cross ▾]   [+ Add Symbol]   [Run All Backtests]
  ┌─ BTC-USDT • okx • 1h • last_run: 5m ago • [● done]   [×] ─┐
  ┌─ ETH-USDT • okx • 1h • last_run: 1h ago • [● done]   [×] ─┐
  ┌─ SOL-USDT • okx • 4h • —                  • [○ none]  [×] ─┐
  ```
- Click row → `GET /strategies/{id}/symbols/{sub_id}/backtest` → chart render positions ngay
- Run All → POST → polling 2s/sub đến khi tất cả `done|failed`
- Delete strategy/subscription → confirm dialog → cascade

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| 2 lần Run đồng thời cùng sub | `replace_existing=True` với deterministic job_id |
| Job crash mid-run, status stuck `running` | App startup hook: `running` quá N phút → `failed` |
| Symbol chưa có bars | Job fail sớm với error_msg rõ ràng |
| Backtest doc > 16MB | Chấp nhận; nếu cần → tách positions ra collection riêng (P3+) |
| Orphan backtest khi YAML xóa thủ công | Chấp nhận; cleanup script sau nếu cần |
| Strategy YAML id đổi | User confirm stable; orphan acceptable |

## Success Criteria

1. Switch subscription trong dropdown → chart paint < 200ms (no recalc, đo qua DevTools)
2. POST `/run-all` → trả về < 100ms với danh sách job_ids
3. Run-all với N subs → N jobs chạy song song, UI cập nhật từng cái khi xong
4. DELETE `/strategies/{id}` → 0 docs còn lại trong cả `strategy_subscriptions` + `backtest_runs` với strategy_id đó
5. Concurrent POST `/run-all` x2 → chỉ 1 job thực sự chạy per subscription

## Out of Scope

- Auth/authz
- Backtest history (chỉ giữ snapshot mới nhất)
- Auto-refresh khi có bars mới
- Per-symbol Run button (chỉ Run All)
- Chỉnh range backtest qua UI

## Unresolved Questions

(none — đã chốt)
