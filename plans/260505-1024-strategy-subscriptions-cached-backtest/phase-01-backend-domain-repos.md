---
phase: 1
title: "Backend Domain & Repos"
status: pending
priority: P1
effort: "0.5d"
dependencies: []
---

# Phase 1: Backend Domain & Repos

## Overview
Thêm `StrategySubscription` entity + repo (collection `strategy_subscriptions`). Mở rộng `BacktestRepository` với keys & status fields. Đặt nền móng để P2 wire vào CQRS.

## Requirements

**Functional**
- Tạo/đọc/xóa subscription theo `(strategy_id, symbol, exchange, interval)`
- ID deterministic để dedup tự nhiên + ổn định trong URL
- BacktestRepository upsert + lookup theo `subscription_id`
- Cascade delete: theo `subscription_id` (single) và `strategy_id` (bulk)

**Non-functional**
- Indexes phù hợp cho query `by_strategy` + cascade
- Theo namespace conventions trong `CLAUDE.md` (file < 200 lines, kebab-case, no `I` prefix cho domain entity)

## Architecture

### Entity (concept-level domain object)

`packages/pocketquant-core/src/pocketquant/core/concepts/strategy/value_objects.py` đã có `StrategyConfig`. Subscription là **runtime mapping** không phải concept thuần — đặt vào `pocketquant-trading` (cùng tầng StrategyAppService) để tránh phá tầng dependency của core.

`packages/pocketquant-trading/src/pocketquant/trading/domain/subscription.py`:
```python
@dataclass(frozen=True)
class StrategySubscription:
    id: str            # = deterministic_id(strategy_id, symbol, exchange, interval)
    strategy_id: str
    symbol: str
    exchange: str
    interval: Interval
    created_at: datetime

    @staticmethod
    def deterministic_id(strategy_id, symbol, exchange, interval) -> str:
        # sha256 truncated 16 chars, lowercase
        ...

    def to_mongo(self) -> dict: ...
    @classmethod
    def from_mongo(cls, doc: dict) -> "StrategySubscription": ...
```

### Repository

`packages/pocketquant-trading/src/pocketquant/trading/persistence/strategy_subscription_repository.py`:
```python
class StrategySubscriptionRepository:
    COLLECTION = "strategy_subscriptions"

    async def add(sub: StrategySubscription) -> None  # insert, raise if exists
    async def get(sub_id: str) -> StrategySubscription | None
    async def list_by_strategy(strategy_id: str) -> list[StrategySubscription]
    async def delete(sub_id: str) -> int
    async def delete_by_strategy(strategy_id: str) -> int
    async def ensure_indexes() -> None  # _id default + index(strategy_id)
```

### BacktestRepository extensions

`packages/pocketquant-backtest/src/pocketquant/backtest/persistence/backtest_repository.py` (extend, NOT replace):

Thêm fields vào doc schema (no new collection):
- `subscription_id: str` (cache key, unique)
- `status: 'running' | 'done' | 'failed'`
- `last_run_at: datetime`
- `error_msg: str | None`
- `strategy_id: str` (đã có; xác nhận index)

Thêm methods:
```python
async def find_by_subscription(sub_id: str) -> BacktestResult | None
async def upsert_status(sub_id: str, *, strategy_id: str, status: str, error_msg: str | None = None) -> None
async def save_for_subscription(sub_id: str, result: BacktestResult) -> None  # upsert filter={subscription_id}
async def delete_by_subscription(sub_id: str) -> int
async def delete_by_strategy(strategy_id: str) -> int
async def ensure_indexes() -> None  # add unique(subscription_id), keep index(strategy_id)
```

`save()` cũ giữ lại cho ad-hoc runs (handlers/run còn dùng); methods mới chỉ touch khi có `subscription_id`.

## Related Code Files

**Create**
- `packages/pocketquant-trading/src/pocketquant/trading/domain/subscription.py`
- `packages/pocketquant-trading/src/pocketquant/trading/persistence/strategy_subscription_repository.py`
- `packages/pocketquant-trading/src/pocketquant/trading/persistence/__init__.py` (nếu chưa có)

**Modify**
- `packages/pocketquant-backtest/src/pocketquant/backtest/persistence/backtest_repository.py` (add 5 methods + index)
- `packages/pocketquant-backtest/src/pocketquant/backtest/domain/entities.py` (nếu BacktestResult cần expose `subscription_id` field — optional, có thể chỉ ở repo layer)

**Read for context**
- `packages/pocketquant-core/src/pocketquant/core/persistence/repositories/bar_repository.py` (pattern repo)
- `packages/pocketquant-trading/src/pocketquant/trading/app_services/strategy_app_service.py:24-183`
- `packages/pocketquant-core/src/pocketquant/core/domain/shared/enums.py` (Interval)

## Implementation Steps

1. Tạo `subscription.py`: dataclass + `deterministic_id()` (sha256 → 16-char hex), `to_mongo`/`from_mongo`. Validate `Interval` enum khi parse from_mongo.
2. Tạo `strategy_subscription_repository.py` theo pattern `BarRepository`. Inject Mongo `Database` qua DI sau (P2). `ensure_indexes`: index(`strategy_id`).
3. `add()`: dùng `insert_one`, catch `DuplicateKeyError` → raise `SubscriptionAlreadyExistsError` (domain error).
4. Mở rộng `backtest_repository.py`:
   - Thêm field schema vào upsert payload
   - Thêm 5 methods mới (signatures trên)
   - `ensure_indexes`: thêm unique index `subscription_id` (sparse=True để không phá run cũ không có sub_id)
5. Compile: `uv run python -c "from pocketquant.trading.domain.subscription import StrategySubscription; from pocketquant.trading.persistence.strategy_subscription_repository import StrategySubscriptionRepository; from pocketquant.backtest.persistence.backtest_repository import BacktestRepository; print('ok')"`

## Success Criteria

- [ ] `StrategySubscription` entity import được từ `pocketquant.trading.domain.subscription`
- [ ] `deterministic_id()` cùng input → cùng output (test simple: assert eq)
- [ ] `StrategySubscriptionRepository` có đủ 6 methods + `ensure_indexes`
- [ ] `BacktestRepository` thêm 5 methods, không break methods cũ (`save`, `list_by_strategy`, `delete`, `find_by_id`)
- [ ] `ensure_indexes` idempotent (chạy 2 lần OK)
- [ ] Sparse unique index trên `subscription_id` cho phép null cho legacy docs

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Conflict với BacktestResult schema cũ trong DB | `subscription_id` sparse index; methods mới chỉ filter docs có sub_id |
| Vi phạm dependency layering (trading dùng concept của core) | Subscription là runtime mapping, đặt trong trading; chỉ import Interval enum từ core |
| File > 200 LOC | Tách `to_mongo`/`from_mongo` ra utility nếu cần; subscription entity dự kiến < 80 LOC |
