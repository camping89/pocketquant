# Feature: Add Symbol (Strategy Subscription)

**Last Updated:** 2026-05-05 | **Status:** Production | **Related:** `journals/strategy-subscriptions-cached-backtest-260505.md`

Tài liệu mô tả feature **Add Symbol** — modal cho phép user đăng ký một symbol (cặp giao dịch) vào một strategy đã load. Feature thuộc luồng **Strategy Subscription Management** với cardinality 1 strategy : N subscriptions.

---

## 1. User POV

### Mục đích

Đăng ký combo `(symbol, exchange, interval)` cho một strategy đang chạy, để strategy nhận market data feed và sinh tín hiệu giao dịch.

### Flow chuẩn

1. Mở modal **Add Symbol** từ trang strategy
2. Nhập symbol (auto-uppercase) — ví dụ `BTC-USDT`
3. Chọn exchange — `OKX` hoặc `BINANCE`
4. Chọn interval — `1m` / `5m` / `15m` / `1h` / `4h` / `1d`
5. Nhấn **Add**
6. Thành công → modal đóng, danh sách subscriptions refresh tự động (TanStack Query invalidation)
7. Lỗi → banner đỏ trong modal

### Error UX

| HTTP Status | Message hiển thị | Nguyên nhân |
|-------------|------------------|-------------|
| 404 | "Strategy not loaded. Load it first." | Strategy chưa được `LoadStrategyCommand` load vào memory |
| 400 / 409 | "Subscription already exists for this symbol/exchange/interval." | Trùng combo đã đăng ký |
| Khác | `API {status}: {statusText}` | Generic fallback (route không match, network, server error) |

> **Lưu ý:** `API 404: Not Found` hiện khi `strategyId` rỗng/null hoặc route chưa mount — phân biệt với 404 "strategy not loaded" (có message cụ thể).

---

## 2. Dev POV

### Stack

| Layer | Tech |
|-------|------|
| Frontend | React + TanStack Query (`pocketquant-web`) |
| Backend | FastAPI + Mediator (CQRS) + Dishka DI (`pocketquant-trading`) |
| Storage | MongoDB collection `strategy_subscriptions`, sparse unique index `(strategy_id, symbol, exchange, interval)` |

### Frontend

| File | Vai trò |
|------|---------|
| `packages/pocketquant-web/src/components/strategy/add-symbol-dialog.tsx` | Modal component — local state `symbol`, `exchange`, `interval`, `errorMsg` |
| `packages/pocketquant-web/src/hooks/use-subscriptions.ts` | `useAddSymbol(strategyId)` — TanStack mutation + cache invalidation |
| `packages/pocketquant-web/src/api/strategy-api.ts` | `addSymbol()` — POST client wrapper |

**Constants:**
- `EXCHANGES = ['OKX', 'BINANCE']`
- `INTERVALS = ['1m', '5m', '15m', '1h', '4h', '1d']`

**Cache invalidation:** Sau success, hook `qc.invalidateQueries({ queryKey: ['subscriptions', strategyId] })` → list re-fetch tức thì.

### Backend (CQRS)

```
HTTP Route → Command → Handler → Domain → Repository → MongoDB
```

| File | Vai trò |
|------|---------|
| `packages/pocketquant-trading/.../strategy/add_symbol/route.py` | `POST /api/v1/strategies/{strategy_code}/subscriptions`, build `AddSymbolCommand`, gửi qua Mediator |
| `packages/pocketquant-trading/.../strategy/add_symbol/handler.py` | Validate strategy loaded → tạo `Subscription` → persist |
| `packages/pocketquant-trading/.../domain/subscription.py` | Aggregate `Subscription` với deterministic ID |
| `packages/pocketquant-trading/.../persistence/subscription_repository.py` | Mongo upsert + duplicate detection (collection: `subscriptions`, renamed from `strategy_subscriptions` in 2026-05-26) |

### Deterministic ID

```
subscription_id = sha256(f"{strategy_code}|{symbol}|{interval}")[:16]
```

**Lý do:**
- Idempotency — gọi 2 lần cùng combo collide ở Mongo unique index
- Không cần distributed lock, business logic không cần check trước
- DB constraint enforce duplicate detection

**Lưu ý:** (2026-05-26) Thay đổi parameter name `strategy_id` → `strategy_code` nhưng hash input vẫn là value, vì vậy existing subscription IDs không đổi.

### Error mapping

| Exception | HTTP | Trigger |
|-----------|------|---------|
| `NotFoundError` | 404 | `StrategyService.get_strategy()` returns None |
| `SubscriptionAlreadyExistsError` (extends `DomainError`) | 400 | `DuplicateKeyError` từ Mongo unique index |
| `AppError` (base) | 400 | Generic domain validation failures |

Global handler map `AppError` → JSON `{error: {code, message}}`.

---

## 3. Data Flow

```
┌──────────────┐
│ User clicks  │
│   "Add"      │
└──────┬───────┘
       │ POST /api/v1/strategies/{strategy_code}/subscriptions
       │ body: {symbol, interval}
       ▼
┌──────────────────────┐
│ FastAPI route        │
│ (add_symbol/route.py)│
└──────┬───────────────┘
       │ AddSymbolCommand
       ▼
┌──────────────────────┐    ┌─────────────────────┐
│ AddSymbolHandler     │───▶│ StrategyService     │
│                      │    │ .get_strategy()     │
│                      │◀───│ → None? raise 404   │
└──────┬───────────────┘    └─────────────────────┘
       │ build Subscription
       │ id = sha256(...)[:16]
       ▼
┌──────────────────────────┐    ┌─────────────────┐
│ SubscriptionRepository   │───▶│ MongoDB         │
│ .save()                  │    │ unique idx fail │
│                          │◀───│ → 400           │
└──────┬───────────────────┘    └─────────────────┘
       │ 201 + subscription (includes is_running)
       ▼
┌──────────────────────┐
│ TanStack Query       │
│ invalidate           │
│ ['subscriptions',id] │
└──────────────────────┘
```

---

## 4. Known Issues & Trade-offs

### Validation gaps

- **Symbol validity không kiểm với exchange:** User nhập `FAKE-COIN` vẫn được tạo subscription → fail tại runtime khi fetch market data.
- **Suggested fix:** Validate qua exchange API (e.g. OKX `/public/instruments`) trong handler trước khi persist.

### Error code ambiguity

- HTTP 404 mang 2 nghĩa khác nhau (route missing vs strategy not loaded) — frontend không phân biệt được.
- **Suggested fix:** Frontend dựa vào `error.code` trong response body (`STRATEGY_NOT_LOADED`) thay vì HTTP status.

### Status code inconsistency

- Duplicate subscription trả 400 (DomainError) thay vì 409 (Conflict) per REST convention. Có nên align?
- Liên quan journal: `strategy-subscriptions-cached-backtest-260505.md` § "Unresolved Questions"

### UX coupling

- `LoadStrategyCommand` phải chạy trước `AddSymbolCommand` — coupling ngầm 2 bước.
- **Suggested fix:** Auto-trigger load strategy nếu chưa load, transparent với user.

---

## 5. Related Docs

- [Handler Pipelines](./handler-pipelines.md) — chi tiết CQRS pipeline pattern
- [System Architecture](./system-architecture.md) — overview backend/frontend
- [Code Standards](./code-standards.md) — naming conventions cho CQRS
- [Journal: Strategy Subscriptions Shipped](./journals/strategy-subscriptions-cached-backtest-260505.md) — implementation history & bug fixes

---

## Unresolved Questions

- Có cần validate symbol-exchange compatibility không? (ví dụ chặn `BTC-USDT` trên exchange không list cặp đó)
- Remove subscription có cleanup market data feed không?
- `400 vs 409` cho duplicate — chọn approach nào? (xem journal § Unresolved)
