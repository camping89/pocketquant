# Slice 2 — Orders per Subscription — Brainstorm Report

## Metadata

| | |
|---|---|
| Priority | 2/5 |
| Scope | FE + BE (slice BE nhỏ nhất trong 5 slices) |
| Depends on | Slice 1 (Forward tab shell — open-positions + equity/KPI đã dựng) |
| Unblocks | Slice 5 (explain trade — link order → trade khi hover) |
| Date | 2026-06-28 |

> Re-scout note (AS-IS hiện tại): `StrategyQueryService` đã được trim — chỉ còn inject `SubscriptionRepository` + `PositionRepository` (2 repo), backtest đã tách sang `backtest/backtest_query_service.py` + route `app/routes/backtest.py` riêng. FE `DashboardColumn` cũng đã đơn giản hóa: KHÔNG còn tab switcher / MetricsTab / EquitySparkline — chỉ `PnlBadge` + `RecentTradesTable` phẳng; backtest sống ở page `/backtest` tách rời. Các citation dưới đây phản ánh trạng thái này.

---

## 1. Problem Statement

Forward tab (shell do Slice 1 dựng) hiện chỉ có open-positions + equity/KPI. Người dùng chọn 1 subscription `(strategy_code, symbol, interval)` nhưng KHÔNG thấy được **order book** của nó — không biết lệnh nào pending/submitted/filled/cancelled, type gì (market/limit/SL/TP), price/qty/filled bao nhiêu, đặt lúc nào.

Order book là mảnh dữ liệu còn thiếu giữa "positions" (kết quả) và "trades" (đã đóng). Nó cho thấy **ý định thực thi** (order) tách khỏi **kết quả thực thi** (fill → position). Slice này thêm Orders panel vào Forward tab, scoped theo subscription đang chọn, đọc từ orders **đã persist** (sống sót qua restart), đúng pattern command/query service hiện hữu.

Đây là slice rẻ nhất: `OrderRepository.find_by_subscription()` đã tồn tại + đã có index. Backend chỉ thiếu 1 route + 1 service method + 1 DTO mapping. Frontend chỉ thiếu 1 api client + 1 hook + 1 table cắm vào shell.

---

## 2. Current State (evidence)

### Backend — repo đã có, chỉ thiếu route

- `OrderRepository.find_by_subscription(subscription_id, limit=1000)` ĐÃ TỒN TẠI — `core/infra/persistence/repositories/order_repository.py:24-29`, đọc `{"subscription_id": ...}` từ collection orders (`.limit(limit)`), trả `list[OrderAggregate]`.
- Index đã có: `ix_orders_subscription_id` — `order_repository.py:40` (trong `ensure_indexes`, cùng `ix_orders_status` `:41` + `ix_orders_symbol` `:42`). Query scoped sub không full-scan.
- `OrderRepository` đã được wire DI: `app/di/persistence.py:63` `order_repository = provide(OrderRepository, scope=Scope.APP)` (import `:28`).
- `OrderAggregate` (shape DTO) — `core/domain/order/entities.py:33-48`: `id` (UUID/uuid7), `subscription_id` (str), `symbol`, `side`, `order_type`, `quantity`, `price`, `stop_price`, `sl_price`, `tp_price`, `status`, `filled_quantity`, `filled_price`, `broker_order_id`, `created_at`, `updated_at`. Property `remaining_quantity` — `entities.py:215-217`. **XÁC NHẬN: KHÔNG có field `position_id`** (toàn bộ fields ở `:33-48`; `to_mongo` `:219-236` cũng không serialize `position_id`) → link order↔position là gián tiếp (xem §5 + §10).
- `id` sinh bằng `generate_id()` (uuid7) trong factory `create()` — `entities.py:82`; serialize Mongo dùng `str(self.id)` `:222`.
- Enums — `core/domain/order/enums.py`: `OrderType` = market/limit/stop_limit/stop_market (`:6-12`); `OrderSide` = buy/sell (`:15-19`); `OrderStatus` = pending/submitted/partially_filled/filled/cancelled/rejected/expired (`:22-38`), có `is_terminal` (`:40-47`) + `is_active` (`:49-52`).

### Route hiện tại đọc in-RAM, KHÔNG dùng repo persisted

- `GET /trading/orders` — `app/routes/trading_orders_positions.py:22-24` → `OrderPositionQueryService.list_orders()`.
- `OrderPositionQueryService` đọc **live in-RAM** từ `OrderAppService.get_pending_orders() + get_filled_orders()` — `engine/orders_positions_service.py:67-84`. Docstring tự khai: *"answers reflect the running engine, not persisted DB rows"* (`:36-39`). DTO in-RAM chỉ 10 field (`:70-83`) — thiếu `stop_price`/`sl_price`/`tp_price`/`created_at`/`updated_at`/`broker_order_id`.
- Hệ quả: KHÔNG filter theo sub (lấy toàn cục), **ephemeral** (mất khi restart, mất khi engine chưa chạy), chỉ work trong process chạy engine.

### Pattern đích đã có sẵn — sub-scoped query service đọc repo persisted

- `StrategyQueryService` (`engine/strategy_query_service.py`) hiện inject **2 repo** từ core: `SubscriptionRepository` + `PositionRepository` — constructor `:48-54` (import `:14-19`). (Backtest đã tách ra — `bt_repo` không còn ở đây.) Đây là **bằng chứng `engine → core.infra` hợp lệ** với import-linter (xem §5). Thêm `OrderRepository` là repo thứ 3 cùng kiểu.
- `get_positions()` (`:101-115`) và `get_trades()` (`:117-139`) đã đọc `PositionRepository` scoped theo `subscription_id`, map sang dict DTO. Orders đi đúng khuôn này.
- Route sub-scoped đã có: `GET /subscriptions/{sub_id}/positions` (`app/routes/strategy.py:130-135`), `.../trades` (`:138-144`, có `limit: int = Query(100, ge=1, le=500)`). Route cuối của `subscription_router` là `.../trades`, rồi `DELETE /{sub_id}` (`:147-153`). **Route `.../backtest` đã bị gỡ** khỏi file này — orders chèn vào ngay sau `.../trades`.
- `StrategyQueryService` provided tại `app/di/trading_services.py:16` (auto-wire constructor — Dishka tự resolve dependency mới).
- Router mount: `subscription_router` + `trading_router` include tại `app/main_extensions.py:401-403` (`backtest_router` `:404`).

### Order lifecycle: persisted vs in-RAM

```
                  OrderAggregate (state machine, entities.py:52-58)
                  PENDING → SUBMITTED → PARTIALLY_FILLED → FILLED
                                      → CANCELLED / REJECTED / EXPIRED

  ┌─────────────────────────────────────────────────────────────────────┐
  │ IN-RAM (ephemeral, toàn cục)          PERSISTED (Mongo, sub-scoped)   │
  │                                                                       │
  │ OrderAppService (engine)              OrderRepository.save()          │
  │   get_pending_orders()                  collection orders             │
  │   get_filled_orders()        ◁── mất    find_by_subscription(sub_id)  │
  │      │                          khi      ix_orders_subscription_id    │
  │      ▼                        restart        │                        │
  │ GET /trading/orders                          ▼                        │
  │ (KHÔNG sub-scope, KHÔNG bền)         GET /subscriptions/{id}/orders    │
  │  DTO 10 field, thiếu SL/TP/ts          DTO đầy đủ từ OrderAggregate   │
  │        ✗ loại                          ✓ Slice 2 dùng cái này         │
  └─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Requirements

- **Expected output**: `GET /api/v1/subscriptions/{sub_id}/orders?limit=N` trả list order DTO (newest-relevant) cho đúng subscription đó, đọc từ `OrderRepository` persisted.
- **Acceptance**: Chọn 1 sub đã chạy live → Forward tab → Orders panel hiển thị bảng order với status / type / side / price / qty / filled_qty / time; sub chưa chạy → empty-state, không lỗi.
- **Scope boundary IN**: 1 endpoint persisted sub-scoped, 1 method trong `StrategyQueryService`, 1 DTO mapping từ `OrderAggregate`, FE api client + hook + Orders table cắm vào Forward shell.
- **Scope boundary OUT**: KHÔNG sửa `/trading/orders` in-RAM (giữ nguyên), KHÔNG ghi/cancel order từ UI (read-only), KHÔNG hover-link order↔trade (để Slice 5), KHÔNG WebSocket realtime (poll `refetchInterval` như positions/trades).
- **Constraints**: import-linter 7 contracts phải pass (route ở app, query service ở engine import repo từ core); PK uuid7 (id order đã là uuid7, chỉ serialize `str(id)`); single uvicorn worker (read từ Mongo, không in-RAM singleton nên an toàn); không trộn tiếng Việt-Anh trong code/comment.
- **Touchpoints**: BE `strategy_query_service.py` + `strategy.py` (route); FE `strategy-api.ts` (hoặc file mới `orders-api.ts`) + hook mới + table mới + Forward shell (Slice 1).

---

## 4. Approaches Evaluated

### 4.1 Nguồn dữ liệu orders

| | (a) Endpoint mới persisted — `GET /subscriptions/{sub_id}/orders` đọc `find_by_subscription` | (b) Mở rộng `/trading/orders` filter sub (in-RAM) |
|---|---|---|
| Sub-scoped | ✓ native (query theo `subscription_id` + index) | ✗ phải filter list toàn cục in-RAM |
| Bền qua restart | ✓ Mongo persisted | ✗ mất sạch khi restart / khi engine chưa chạy |
| DTO đầy đủ | ✓ full `OrderAggregate` (SL/TP/timestamps) | ✗ in-RAM DTO chỉ 10 field (`orders_positions_service.py:70-83`) |
| Đúng pattern hiện hữu | ✓ giống `.../positions`, `.../trades` | ✗ in-RAM service khác trục |
| Single worker an toàn | ✓ stateless read | ✗ phụ thuộc in-RAM singleton của process engine |
| Effort | thấp (repo + index đã có) | trung bình (đụng service in-RAM, vẫn không bền) |
| **Verdict** | **CHỌN** | loại |

### 4.2 Service layer

| | (a) Mở rộng `StrategyQueryService` (thêm `get_orders`) | (b) Tạo query service riêng |
|---|---|---|
| Nhất quán | ✓ cùng nơi serve positions/trades cùng sub-scope | ✗ thêm service + DI provider mới |
| Inject `OrderRepository` | ✓ đã inject 2 repo core (sub + position) → thêm 1 hợp lệ | ✓ nhưng phải wire lại |
| import-linter | ✓ engine→core.infra đã được chứng minh hợp lệ | ✓ tương đương |
| DI churn | ✓ 0 (provider auto-wire constructor mới) | ✗ thêm `provide(...)` ở `trading_services.py` |
| Effort | thấp nhất | cao hơn, không lợi gì |
| **Verdict** | **CHỌN** | loại (YAGNI) |

---

## 5. Recommended Solution

**Persisted endpoint mới + mở rộng `StrategyQueryService`.** (Recommendation không đổi sau re-scout.)

- Route `GET /subscriptions/{sub_id}/orders?limit=N` trong `app/routes/strategy.py` (cạnh `.../trades` `:138-144`), `FromDishka[StrategyQueryService]` + `DishkaRoute` — không `Depends()`.
- Thêm method `get_orders(GetSubscriptionOrdersQuery)` vào `StrategyQueryService`; constructor (`:48-54`) nhận thêm `order_repository: OrderRepository`. Dishka auto-resolve vì `OrderRepository` đã `provide` ở `app/di/persistence.py:63` — KHÔNG cần sửa `trading_services.py`.
- Map `OrderAggregate` → dict DTO trong service (giống `get_trades` map Position → dict `:126-138`).

### import-linter — verify hợp lệ

- **Route ở app gọi query service ở engine**: app là top tier (`layers` contract `pyproject.toml:78-86`), app→engine cho phép. ✓
- **Query service ở engine import `OrderRepository` từ `core.infra`**: contract "Engine imports no sibling/upper package" (`pyproject.toml:104-111`) chỉ cấm `engine → {backtest, app}`, KHÔNG cấm `engine → core`. Bằng chứng sống: `strategy_query_service.py:14-19` đã import `PositionRepository` + `SubscriptionRepository` từ `core.infra.persistence.repositories` và đang chạy production. Thêm `OrderRepository` cùng package = cùng tính hợp lệ. ✓
- **fastapi only in app** (`pyproject.toml:119-130`): chỉ route mới (app) chạm fastapi; service/repo không. ✓
- **uuid7 / no bson** (`:132-136`): `OrderAggregate.id` đã là uuid7 (`generate_id()` trong `create()`, `entities.py:82`); DTO chỉ `str(order.id)`. Không hash/ObjectId/bson. ✓

### Order ↔ position/trade linking (note, không bắt buộc slice này)

`OrderAggregate` KHÔNG có `position_id` field (verified `entities.py:33-48`) — link order→trade hiện chỉ gián tiếp qua `subscription_id` + `symbol` + timeline. Slice 5 (explain) sẽ cần thiết kế cách correlate (vd theo thời gian fill vs entry/exit của closed position). Slice 2 chỉ trả flat order list; FE table giữ `id` để Slice 5 hook hover-highlight sau. Không chặn slice này.

---

## 6. Vertical Slice Breakdown

### 6.1 Backend

1. `strategy_query_service.py`:
   - Import `OrderRepository` từ `core.infra.persistence.repositories.order_repository` (cạnh import `PositionRepository`/`SubscriptionRepository` `:14-19`).
   - Thêm `order_repository: OrderRepository` vào `__init__` (`:48-54`), gán `self._order_repo`.
   - Thêm `class GetSubscriptionOrdersQuery(BaseModel)` với `subscription_id: str`, `limit: int = 200`.
   - Thêm `async def get_orders(self, query)` → `orders = await self._order_repo.find_by_subscription(query.subscription_id, limit=query.limit)`; map mỗi `OrderAggregate` → dict (xem §6.3). Cân nhắc sort newest-first theo `created_at` desc (repo `find_by_subscription` `:24-29` KHÔNG order — sort trong service hoặc note để FE sort).
2. `app/routes/strategy.py`:
   - Import `GetSubscriptionOrdersQuery` (block import `:22-29`).
   - Thêm route `@subscription_router.get("/{sub_id}/orders")` (cạnh `.../trades` `:138-144`), param `limit: int = Query(200, ge=1, le=1000)`, gọi `query_svc.get_orders(...)`.
3. KHÔNG đụng `trading_orders_positions.py` / `orders_positions_service.py` / DI providers / `main_extensions.py` (route mới nằm trong `subscription_router` đã mount sẵn `:402`).

### 6.2 Frontend

1. API client: thêm `getSubscriptionOrders(subId, limit?)` vào `strategy-api.ts`, interface `SubscriptionOrder`. Dùng `apiFetch` từ `api-client.ts` (lưu ý: `apiFetch`/`apiPost` giờ throw `ApiError` có `status`+`code`, `api-client.ts:35-55`).
2. Hook `use-subscription-orders.ts`: copy khuôn `use-strategy-trades.ts` — `useQuery`, `queryKey: ['subscription-orders', subId]`, `enabled: !!subId`, `refetchInterval: 15_000`, `staleTime: 10_000`.
3. Component `orders-table.tsx`: khuôn `recent-trades-table.tsx` — `thStyle`/`tdStyle` (`:28-48`), `useFmt()` (`:51`), empty-state `<div className="empty-state">…</div>` (`:60-63`); cột Status / Type / Side / Price / Qty / Filled / Time; badge status (active vs terminal màu khác).
4. Cắm vào Forward shell (Slice 1): **lưu ý drift** — `DashboardColumn` hiện tại (`dashboard-column.tsx:17-58`) đã bỏ tab switcher, chỉ còn `PnlBadge` + `RecentTradesTable` phẳng. Slice 1 dựng lại Forward shell với tab/section; Slice 2 thêm Orders như 1 tab/panel vào shell đó. Nếu Slice 1 chưa cung cấp tab container, FE chờ shell (BE ship trước).

### 6.3 API Contract — order DTO shape

`GET /api/v1/subscriptions/{sub_id}/orders?limit=200` → `200 OK`:

```jsonc
[
  {
    "id": "0190...uuid7",          // str(order.id)
    "symbol": "BTCUSDT:BINANCE",   // composite {code}:{exchange}
    "side": "buy",                 // buy | sell  (order.side.value)
    "order_type": "limit",         // market | limit | stop_limit | stop_market
    "status": "partially_filled",  // pending|submitted|partially_filled|filled|cancelled|rejected|expired
    "price": 64000.0,              // null cho market order
    "stop_price": null,
    "sl_price": null,
    "tp_price": null,
    "quantity": 0.5,
    "filled_quantity": 0.2,
    "remaining_quantity": 0.3,     // property entities.py:215-217
    "filled_price": 63950.0,       // null nếu chưa fill
    "broker_order_id": "abc123",   // null nếu chưa submit
    "created_at": "2026-06-28T...Z",  // .isoformat()
    "updated_at": "2026-06-28T...Z"
  }
]
```

FE interface tương ứng (`status`/`side`/`order_type` literal unions). Map `.value` cho enum khi serialize (giống `get_positions` dùng `p.side.value.upper()` `:106`).

---

## 7. Decomposition into Sub-tasks (ordered, shippable)

1. **BE**: thêm `OrderRepository` vào `StrategyQueryService.__init__` + `GetSubscriptionOrdersQuery` + `get_orders()` mapping. Test trực tiếp service.
2. **BE**: thêm route `GET /subscriptions/{sub_id}/orders` vào `strategy.py`. Smoke với 1 sub đã chạy live (hoặc seed orders) → verify shape + empty list khi chưa có.
3. **FE**: api client `getSubscriptionOrders` + interface `SubscriptionOrder`.
4. **FE**: hook `use-subscription-orders.ts`.
5. **FE**: `orders-table.tsx` + cắm tab/panel "Orders" vào Forward shell (Slice 1).
6. **Verify**: import-linter pass; `cd web && npm run lint && npm run build`.

(Slice nhỏ → 1–2 task BE + 3 task FE, ship được từng bước; BE ship trước, FE consume sau.)

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Orders persisted có khớp positions không (order là ý định, position là kết quả) — user nhầm "5 orders nhưng 1 position" | Đây là đúng bản chất; panel label rõ "Orders" tách "Positions"/"Trades". `filled` vs `quantity` cho thấy order chưa fill hết → chưa thành position. |
| `OrderStatus` 7 trạng thái — FE map thiếu (vd `expired`, `rejected`) | DTO trả raw `.value`; FE dùng literal union đủ 7 + badge mặc định cho status lạ. Group màu: active (`submitted`/`partially_filled`) vs terminal (`filled`/`cancelled`/`rejected`/`expired`) vs `pending`. |
| Empty state khi sub chưa chạy live (orders chỉ sinh từ reconcile loop + broker) | Endpoint trả `[]` (không 404); FE empty-state "No orders yet." Không lỗi. |
| `find_by_subscription` không đảm bảo sort order (cursor `.limit` không order — `order_repository.py:28`) | Service sort `created_at` desc (newest-first) trước khi trả, hoặc note FE sort; limit mặc định 200 đủ cho UI panel. |
| Order không có `position_id` (verified) → Slice 5 link khó | Note ở §5; Slice 2 không phụ thuộc. Giữ `id` + `symbol` + timestamps trong DTO để Slice 5 correlate. |
| Backtest cũng sinh orders (`BacktestOrderRepository` riêng — `persistence.py:66`) lẫn vào? | KHÔNG: forward orders ở collection `orders` (COLLECTION_ORDERS), backtest orders ở repo/collection tách biệt. `find_by_subscription` chỉ chạm orders forward. |
| FE `apiFetch` đổi error type (`ApiError` thay `Error`, `api-client.ts:35-55`) | Hook orders dùng `fetch` trực tiếp như `use-strategy-trades.ts` HOẶC `apiFetch` — nếu dùng `apiFetch`, catch `ApiError` cho empty-state vs lỗi thật. |

---

## 9. Success Metrics & Validation

- `lint-imports` (import-linter) pass — 7 contracts xanh, đặc biệt "Engine imports no sibling/upper package" + "fastapi only in app".
- BE: unit test `StrategyQueryService.get_orders` map đúng shape; route trả `[]` khi sub không có order, trả list khi có (seed `OrderRepository.save`).
- FE: `cd web && npm run lint && npm run build` pass; type-check interface `SubscriptionOrder` khớp DTO.
- Manual: chọn sub đã chạy live → Forward tab → tab/panel Orders hiện bảng; sub chưa chạy → empty-state.

---

## 10. Dependencies & Open Questions

**Dependencies:**
- **Slice 1** (`slice-1-*-forward-shell-report.md` / Forward tab shell): cung cấp tab container + open-positions + equity/KPI. Slice 2 chèn Orders như 1 tab/panel mới vào shell này. **Drift cảnh báo**: `DashboardColumn` AS-IS đã bị trim còn `PnlBadge` + `RecentTradesTable` (`dashboard-column.tsx:17-58`), backtest dời sang page `/backtest`. Slice 1 phải dựng lại tab container; nếu chưa có, BE ship trước, FE chờ shell.

**Unblocks:**
- **Slice 5** (`slice-5-*-explain-trade-report.md` / explain trade): dùng order list (id, symbol, timestamps) để hover-highlight order liên quan 1 trade. Slice 5 sẽ quyết định cách correlate order↔position vì `OrderAggregate` thiếu `position_id` (verified).

**Open Questions:**
1. Order ↔ position correlation: thêm `position_id` vào `OrderAggregate` (cần migration + sửa nơi tạo order) hay correlate runtime theo time/symbol? — đẩy sang Slice 5, KHÔNG quyết ở đây.
2. Sort + limit: newest-first 200 có đủ cho panel, hay cần phân trang? (giả định panel forward đủ với 200, như `.../trades` cap 500).
3. Forward shell (Slice 1) đặt Orders là tab riêng hay sub-section trong 1 tab? — phụ thuộc layout cuối của Slice 1 (đang phải dựng lại do `DashboardColumn` đã trim).
4. Có hiển thị order `expired`/`rejected`/`cancelled` mặc định hay filter chỉ active+filled? (đề xuất: hiện hết, badge phân biệt — order book đầy đủ giá trị hơn cho debug).

---

Status: DONE_WITH_CONCERNS
Summary: Re-scout phát hiện drift đáng kể so với report cũ nhưng recommendation KHÔNG đổi — persisted endpoint `GET /subscriptions/{sub_id}/orders` + mở rộng `StrategyQueryService` vẫn là đường nhỏ nhất, đúng pattern, hợp import-linter. Mọi citation `file:line` đã verify lại và sửa drift.
Changes:
- BE `strategy_query_service.py`: constructor giờ chỉ 2 repo (sub + position), KHÔNG còn `BacktestRepository`/`bt_repo`/`get_subscription_backtest` — sửa cite "3 repo `:56-64`" → "2 repo `:48-54`", imports `:14-19`, `get_positions :101-115`, `get_trades :117-139`.
- BE `strategy.py`: route `GET /subscriptions/{sub_id}/backtest` đã bị gỡ; cite mới `.../positions :130-135`, `.../trades :138-144`, DELETE `:147-153`, import block `:22-29` (bỏ `GetSubscriptionBacktestQuery`).
- BE `app/di/persistence.py`: `order_repository = provide(...)` sửa `:69` → `:63` (file đã thêm `TrackedSymbolRepository`, bỏ vài repo cũ như optimization/backtest_request).
- BE backtest đã tách sang `backtest/backtest_query_service.py` + `app/routes/backtest.py` (bổ sung mới — không còn ở `StrategyQueryService`).
- BE router mount xác nhận tại `app/main_extensions.py:401-404` (bổ sung mới — KHÔNG phải `main.py`).
- FE `dashboard-column.tsx`: đã trim bỏ tab switcher/MetricsTab/PositionsTab/EquitySparkline/useSubscriptionBacktest → chỉ `PnlBadge`+`RecentTradesTable` (`:17-58`); cập nhật §6.2 + §10.
- FE `strategy-api.ts`: refactor — thêm `desired_state`/`actual_state`, bỏ `backtest`/`SubscriptionBacktest`/`getSubscriptionBacktest`/`runAllBacktests`.
- FE `api-client.ts`: `apiFetch`/`apiPost` giờ throw `ApiError`(status+code) (`:35-55`) thay `Error` — thêm risk row §8.
- Verified KHÔNG đổi: `OrderRepository.find_by_subscription :24-29`, index `:40`, `OrderAggregate` fields `:33-48` (CONFIRMED không có `position_id`), enums, import-linter contracts `:78-136`.
Concerns: Slice 1 dependency rủi ro hơn dự kiến — `DashboardColumn` đã bị trim còn flat layout (không tab), nên Slice 1 phải dựng lại tab container trước khi Slice 2 FE cắm Orders panel; BE Slice 2 vẫn ship độc lập được. `OrderAggregate` thiếu `position_id` → Slice 5 link order↔trade cần thiết kế correlation riêng.
