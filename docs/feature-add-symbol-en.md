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
| Storage | MongoDB collection `strategy_subscriptions`, sparse unique index on `(strategy_id, symbol, exchange, interval)` |

### Frontend

| File | Role |
|---|---|
| `packages/pocketquant-web/src/components/strategy/add-symbol-dialog.tsx` | Modal component — local state for `symbol`, `exchange`, `interval`, `errorMsg` |
| `packages/pocketquant-web/src/hooks/use-subscriptions.ts` | `useAddSymbol(strategyId)` — TanStack mutation + cache invalidation |
| `packages/pocketquant-web/src/api/strategy-api.ts` | `addSymbol()` — POST client wrapper |

**Constants:**
- `EXCHANGES = ['OKX', 'BINANCE']`
- `INTERVALS = ['1m', '5m', '15m', '1h', '4h', '1d']`

**Cache invalidation:** On success, the hook runs `qc.invalidateQueries({ queryKey: ['subscriptions', strategyId] })` → list re-fetches immediately.

### Backend (CQRS)

```
HTTP Route → Command → Handler → Domain → Repository → MongoDB
```

| File | Role |
|---|---|
| `packages/pocketquant-trading/.../strategy/add_symbol/route.py` | `POST /api/v1/strategies/{strategy_id}/symbols`, builds `AddSymbolCommand`, dispatches via Mediator |
| `packages/pocketquant-trading/.../strategy/add_symbol/handler.py` | Validates strategy is loaded → creates `StrategySubscription` → persists |
| `packages/pocketquant-trading/.../domain/subscription.py` | `StrategySubscription` aggregate with deterministic ID |
| `packages/pocketquant-trading/.../persistence/strategy_subscription_repository.py` | Mongo upsert + duplicate detection |

### Deterministic ID

```
subscription_id = sha256(f"{strategy_id}|{symbol}|{exchange}|{interval}")[:16]
```

**Why:**
- Idempotency — calling twice with the same combo collides on the Mongo unique index
- No distributed lock needed; business logic doesn't need a pre-check
- DB constraint enforces duplicate detection

### Error mapping

| Exception | HTTP | Trigger |
|---|---|---|
| `NotFoundError` | 404 | `StrategyService.get_strategy()` returns None |
| `SubscriptionAlreadyExistsError` (extends `DomainError`) | 400 | `DuplicateKeyError` from Mongo unique index |
| `AppError` (base) | 400 | Generic domain validation failure |

A global handler maps `AppError` → JSON `{error: {code, message}}`.

---

## 3. Data Flow

```
┌──────────────┐
│ User clicks  │
│   "Add"      │
└──────┬───────┘
       │ POST /api/v1/strategies/{id}/symbols
       │ body: {symbol, exchange, interval}
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
       │ build StrategySubscription
       │ id = sha256(...)[:16]
       ▼
┌──────────────────────────┐    ┌─────────────────┐
│ SubscriptionRepository   │───▶│ MongoDB         │
│ .save()                  │    │ unique idx fail │
│                          │◀───│ → 400           │
└──────┬───────────────────┘    └─────────────────┘
       │ 201 + subscription
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
- [System Architecture](./system-architecture.md) — backend/frontend overview
- [Code Standards](./code-standards.md) — CQRS naming conventions
- [Journal: Strategy Subscriptions Shipped](./journals/strategy-subscriptions-cached-backtest-260505.md) — implementation history & bug fixes

---

## Unresolved Questions

- Should we validate symbol-exchange compatibility? (e.g. block `BTC-USDT` on exchanges that don't list that pair)
- Should removing a subscription also clean up the market-data feed?
- `400 vs 409` for duplicates — which approach do we pick? (see journal § Unresolved)
