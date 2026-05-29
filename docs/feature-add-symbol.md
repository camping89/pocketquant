# Feature: Add Symbol (Strategy Subscription)

**Last Updated:** 2026-05-26 | **Status:** Production | **Related:** `archive/journals/strategy-subscriptions-cached-backtest-260505.md`

Tài liệu mô tả feature **Add Symbol** — modal cho phép user đăng ký một symbol (cặp giao dịch) vào một strategy template. Feature thuộc luồng **Strategy Subscription Management** với cardinality 1 strategy template : N subscriptions.

---

## 1. User POV

### Mục đích

Đăng ký combo `(symbol, interval)` cho một strategy template, để strategy nhận market data feed và sinh tín hiệu giao dịch. `symbol` là composite `{CODE}:{EXCHANGE}` (ví dụ `BTCUSDT:BINANCE`).

### Flow chuẩn

1. Mở modal **Add Symbol** từ trang strategy
2. Nhập symbol (auto-uppercase, composite format) — ví dụ `BTC-USDT:OKX`
3. Chọn interval — `1m` / `5m` / `15m` / `1h` / `4h` / `1d`
4. Nhấn **Add**
5. Thành công → modal đóng, danh sách subscriptions refresh tự động (TanStack Query invalidation)
6. Lỗi → banner đỏ trong modal

### Error UX

| HTTP Status | Message hiển thị | Nguyên nhân |
|-------------|------------------|-------------|
| 404 | "Symbol not tracked." | Symbol chưa được admin thêm vào `tracked_symbols` |
| 404 | "Strategy template not found." | `strategy_code` không có trong `STRATEGY_REGISTRY` |
| 400 / 409 | "Subscription already exists." | Trùng combo `(strategy_code, symbol, interval)` đã đăng ký |
| Khác | `API {status}: {statusText}` | Generic fallback (route không match, network, server error) |

> **Lưu ý:** `API 404: Not Found` hiện khi `strategy_code` rỗng/null hoặc route chưa mount — phân biệt với 404 có message cụ thể (symbol/template missing).

---

## 2. Dev POV

### Stack

| Layer | Tech |
|-------|------|
| Frontend | React + TanStack Query (`pocketquant-web`) |
| Backend | FastAPI + Mediator (CQRS) + Dishka DI (`pocketquant-trading`) |
| Storage | MongoDB collection `subscriptions`, deterministic PK trên `(strategy_code, symbol, interval)` |

### Frontend

| File | Vai trò |
|------|---------|
| `packages/pocketquant-web/src/components/strategy/add-symbol-dialog.tsx` | Modal component — local state `symbol`, `interval`, `errorMsg` |
| `packages/pocketquant-web/src/hooks/use-subscriptions.ts` | `useAddSymbol(strategyCode)` — TanStack mutation + cache invalidation |
| `packages/pocketquant-web/src/api/strategy-api.ts` | `addSymbol(strategyCode, body)` — POST client wrapper |

**Constants:**
- `INTERVALS = ['1m', '5m', '15m', '1h', '4h', '1d']` (exchange được derive từ composite symbol `{CODE}:{EXCHANGE}`)

**Cache invalidation:** Sau success, hook `qc.invalidateQueries({ queryKey: ['subscriptions', strategyCode] })` → list re-fetch tức thì.

### Backend (CQRS)

```
HTTP Route → Command → Handler → Domain → Repository → MongoDB
```

| File | Vai trò |
|------|---------|
| `packages/pocketquant-trading/.../handlers/strategy/add_symbol/route.py` | `POST /api/v1/strategies/{strategy_code}/subscriptions`, build `AddSymbolCommand`, gửi qua Mediator |
| `packages/pocketquant-trading/.../handlers/strategy/add_symbol/handler.py` | Auto-load strategy template nếu cần → tạo `Subscription` → persist |
| `packages/pocketquant-trading/.../domain/subscription.py` | Aggregate `Subscription` với deterministic ID |
| `packages/pocketquant-trading/.../persistence/subscription_repository.py` | Mongo persistence trên collection `subscriptions` (renamed từ `strategy_subscriptions` tại 2026-05-26 boot migration) |

### Deterministic ID

```
subscription_id = sha256(f"{strategy_code}|{symbol.upper()}|{interval_val}")[:16]
```

**Trong đó:**
- `strategy_code`: tên template, ví dụ `hitnrun2`
- `symbol`: composite `{CODE}:{EXCHANGE}`, ví dụ `BTC-USDT:OKX` (uppercased, có dấu hai chấm)
- `interval_val`: string value của Interval enum, ví dụ `1m`

**Lý do:**
- Idempotency — gọi 2 lần cùng combo collide ở Mongo unique index → cùng `_id`
- Không cần distributed lock; deterministic collision đảm bảo uniqueness implicit
- Back-compatible: hash input là **value** của `strategy_code` (không đổi khi rename parameter), verified tại `test_subscription_deterministic_id.py:test_back_compat_known_id_hitnrun2_btc_1m`

### Error mapping

| Exception | HTTP | Trigger |
|-----------|------|---------|
| `NotFoundError` (`SYMBOL_NOT_TRACKED`) | 404 | `TrackedSymbolRepository.exists()` returns False |
| `NotFoundError` (template) | 404 | `STRATEGY_REGISTRY.get(strategy_code)` returns None |
| `SubscriptionAlreadyExistsError` (extends `DomainError`) | 400 | `DuplicateKeyError` từ Mongo unique index trên `_id` |
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
       │ body: {symbol, interval}  (symbol="BTC-USDT:OKX")
       ▼
┌──────────────────────┐
│ FastAPI route        │
│ (add_symbol/route.py)│
└──────┬───────────────┘
       │ AddSymbolCommand
       ▼
┌──────────────────────┐    ┌─────────────────────┐
│ AddSymbolHandler     │───▶│ TrackedSymbolRepo   │
│                      │    │ .exists()           │
│                      │◀───│ → False? raise 404  │
└──────┬───────────────┘    └─────────────────────┘
       │ STRATEGY_REGISTRY.get(strategy_code)
       │   → None? raise 404
       │ build Subscription
       │ id = sha256(strategy_code|symbol|interval)[:16]
       ▼
┌──────────────────────────┐    ┌─────────────────┐
│ SubscriptionRepository   │───▶│ MongoDB         │
│ .add()                   │    │ collision rare  │
│                          │◀───│ (idempotent)    │
└──────┬───────────────────┘    └─────────────────┘
       │ 201 + subscription (includes is_running)
       ▼
┌──────────────────────┐
│ TanStack Query       │
│ invalidate           │
│ ['subscriptions',    │
│  strategyCode]       │
└──────────────────────┘
```

---

## 4. Known Issues & Trade-offs

### Validation gaps

- **Symbol validity không kiểm với exchange:** User nhập `FAKE-COIN:OKX` vẫn được tạo subscription (nếu đã trong `tracked_symbols`) → fail tại runtime khi fetch market data.
- **Suggested fix:** Validate qua exchange API (e.g. OKX `/public/instruments`) trong `tracked_symbol` seeding thay vì runtime.

### Error code ambiguity

- HTTP 404 mang 2 nghĩa khác nhau (symbol not tracked vs template not in registry) — frontend cần check `error.code` để phân biệt.
- **Suggested fix:** Frontend dựa vào `error.code` trong response body (`SYMBOL_NOT_TRACKED` vs generic) thay vì chỉ HTTP status.

### Status code inconsistency

- Duplicate subscription trả 400 (DomainError) thay vì 409 (Conflict) per REST convention. Có nên align?
- Liên quan journal: `strategy-subscriptions-cached-backtest-260505.md` § "Unresolved Questions"

### Auto-load coupling

- `AddSymbolHandler` tự động `StrategyAppService.load_strategy(...)` nếu instance cho `sub_id` chưa tồn tại. User không cần load thủ công.

---

## 5. Related Docs

- [Handler Pipelines](./handler-pipelines.md) — chi tiết CQRS pipeline pattern
- [System Architecture](./system-architecture.md) — overview backend/frontend, subscription entity
- [Debug Audit Order Execution](./archive/debug-audit-order-execution.md) — live trading flow với subscription IDs
- [Code Standards](./code-standards.md) — CQRS naming conventions + Strategy ID Disambiguation
- [Strategy Lifecycle](./strategy-lifecycle.md) — bảng routes đầy đủ, mongo collection map
- [Journal: Strategy Subscriptions Shipped](./archive/journals/strategy-subscriptions-cached-backtest-260505.md) — implementation history & bug fixes

---

## Unresolved Questions

- Có cần validate symbol-exchange compatibility ở API boundary không? (ví dụ chặn cặp invalid trước khi persist)
- Remove subscription có cleanup cached backtests không? (Trả lời: có, `RemoveSymbolHandler` cascade `BacktestRepository.delete_by_subscription(sub_id)`.)
- `400 vs 409` cho duplicate — chọn approach nào? (xem journal § Unresolved)
