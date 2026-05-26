# Feature: Add Symbol (Strategy Subscription)

**Last Updated:** 2026-05-05 | **Status:** Production | **Related:** `journals/strategy-subscriptions-cached-backtest-260505.md`

Documents the **Add Symbol** feature — a modal that lets a user register a symbol (trading pair) into a loaded strategy. Part of the **Strategy Subscription Management** flow, with cardinality 1 strategy : N subscriptions.

---

## 1. User POV

### Purpose

Register a `(symbol, exchange, interval)` combo for a running strategy so the strategy receives a market-data feed and emits trading signals.

### Happy path

1. Open the **Add Symbol** modal from the strategy page
2. Enter symbol (auto-uppercased) — e.g. `BTC-USDT`
3. Select exchange — `OKX` or `BINANCE`
4. Select interval — `1m` / `5m` / `15m` / `1h` / `4h` / `1d`
5. Click **Add**
6. Success → modal closes, subscriptions list auto-refreshes (TanStack Query invalidation)
7. Error → red banner inside the modal

### Error UX

| HTTP status | Displayed message | Cause |
|---|---|---|
| 404 | "Strategy not loaded. Load it first." | Strategy not yet loaded into memory via `LoadStrategyCommand` |
| 400 / 409 | "Subscription already exists for this symbol/exchange/interval." | Duplicate combo |
| Other | `API {status}: {statusText}` | Generic fallback (route miss, network, server error) |

> **Note:** `API 404: Not Found` also appears when `strategyId` is empty/null or the route isn't mounted — distinguish from the "strategy not loaded" 404 (which has a specific message body).

---

## 2. Dev POV

### Stack

| Layer | Tech |
|---|---|
| Frontend | React + TanStack Query (`pocketquant-web`) |
| Backend | FastAPI + Mediator (CQRS) + Dishka DI (`pocketquant-trading`) |
| Storage | MongoDB collection `subscriptions`, deterministic PK on `(strategy_code, symbol, interval)` |

### Frontend

| File | Role |
|---|---|
| `packages/pocketquant-web/src/components/strategy/add-symbol-dialog.tsx` | Modal component — local state for `symbol`, `interval`, `errorMsg` |
| `packages/pocketquant-web/src/hooks/use-subscriptions.ts` | `useAddSymbol(strategyCode)` — TanStack mutation + cache invalidation |
| `packages/pocketquant-web/src/api/strategy-api.ts` | `addSymbol()` — POST client wrapper |

**Constants:**
- `INTERVALS = ['1m', '5m', '15m', '1h', '4h', '1d']` (exchange is derived from symbol's composite format `CODE:EXCHANGE`)

**Cache invalidation:** On success, the hook runs `qc.invalidateQueries({ queryKey: ['subscriptions', strategyCode] })` → list re-fetches immediately.

### Backend (CQRS)

```
HTTP Route → Command → Handler → Domain → Repository → MongoDB
```

| File | Role |
|---|---|
| `packages/pocketquant-api/.../strategy/subscriptions/add_symbol/route.py` | `POST /api/v1/strategies/{strategy_code}/subscriptions`, builds `AddSymbolCommand`, dispatches via Mediator |
| `packages/pocketquant-api/.../strategy/subscriptions/add_symbol/handler.py` | Validates strategy is loaded → creates `Subscription` → persists |
| `packages/pocketquant-core/.../domain/subscription/entities.py` | `Subscription` aggregate with deterministic ID |
| `packages/pocketquant-core/.../persistence/subscription_repository.py` | Mongo persistence + duplicate detection via deterministic hash |

### Deterministic ID

```
subscription_id = sha256(f"{strategy_code}|{symbol.upper()}|{interval_val}")[:16]
```

**Where:**
- `strategy_code`: e.g. `hitnrun2`
- `symbol`: composite format `{CODE}:{EXCHANGE}` e.g. `BTC-USDT:OKX` (uppercased and colon-separated)
- `interval_val`: integer-valued interval e.g. `60` for `1m`

**Why:**
- Idempotency — calling twice with the same combo produces same ID
- No distributed lock needed; deterministic collision provides implicit uniqueness
- Back-compatible: hash input is the value of `strategy_code` (not changed by rename), verified at `test_subscription_deterministic_id.py:test_back_compat_known_id_hitnrun2_btc_1m`

### Error mapping

| Exception | HTTP | Trigger |
|---|---|---|
| `NotFoundError` | 404 | `StrategyAppService.get_strategy()` returns None |
| `DomainError` (duplicate) | 400 | MongoDB insert collision on deterministic ID (should be rare due to idempotency) |
| `AppError` (base) | 400 | Generic domain validation failure |

A global handler maps `AppError` → JSON `{error: {code, message}}`.

---

## 3. Data Flow

```
┌──────────────┐
│ User clicks  │
│   "Add"      │
└──────┬───────┘
       │ POST /api/v1/strategies/{strategy_code}/subscriptions
       │ body: {symbol, interval}  (e.g., symbol="BTC-USDT:OKX")
       ▼
┌──────────────────────┐
│ FastAPI route        │
│ (add_symbol/route.py)│
└──────┬───────────────┘
       │ AddSymbolCommand
       ▼
┌──────────────────────┐    ┌─────────────────────┐
│ AddSymbolHandler     │───▶│ StrategyAppService  │
│                      │    │ .get_strategy()     │
│                      │◀───│ → None? raise 404   │
└──────┬───────────────┘    └─────────────────────┘
       │ build Subscription
       │ id = sha256(strategy_code|symbol|interval)[:16]
       ▼
┌──────────────────────────┐    ┌─────────────────┐
│ SubscriptionRepository   │───▶│ MongoDB         │
│ .save()                  │    │ collision rare  │
│                          │◀───│ (idempotent)    │
└──────┬───────────────────┘    └─────────────────┘
       │ 201 + subscription
       ▼
┌──────────────────────┐
│ TanStack Query       │
│ invalidate           │
│ ['subscriptions',    │
│  strategy_code]      │
└──────────────────────┘
```

---

## 4. Known Issues & Trade-offs

### Validation gaps

- **Symbol validity is not checked against the exchange:** a user can submit `FAKE-COIN` and a subscription is created → fails at runtime when fetching market data.
- **Suggested fix:** validate against the exchange API (e.g. OKX `/public/instruments`) inside the handler before persisting.

### Error code ambiguity

- HTTP 404 carries two different meanings (route missing vs. strategy not loaded) — the frontend can't distinguish them.
- **Suggested fix:** the frontend should branch on `error.code` in the response body (`STRATEGY_NOT_LOADED`) instead of HTTP status.

### Status code inconsistency

- Duplicate subscription returns 400 (DomainError) instead of 409 (Conflict) per REST convention. Should we align?
- See journal: `strategy-subscriptions-cached-backtest-260505.md` § "Unresolved Questions"

### UX coupling

- `LoadStrategyCommand` must run before `AddSymbolCommand` — implicit two-step coupling.
- **Suggested fix:** auto-trigger strategy load if not loaded; transparent to the user.

---

## 5. Related Docs

- [Handler Pipelines](./handler-pipelines.md) — CQRS pipeline pattern details
- [System Architecture](./system-architecture.md) — backend/frontend overview, subscription entity
- [Debug Audit Order Execution](./debug-audit-order-execution.md) — live trading flow with subscription IDs
- [Code Standards](./code-standards.md) — CQRS naming conventions
- [Journal: Strategy Subscriptions Shipped](./journals/strategy-subscriptions-cached-backtest-260505.md) — implementation history & bug fixes

---

## Unresolved Questions

- Should we validate symbol-exchange compatibility at the API boundary? (e.g. reject invalid pairs before persisting)
- Should removing a subscription also clean up cached backtests for that subscription?
