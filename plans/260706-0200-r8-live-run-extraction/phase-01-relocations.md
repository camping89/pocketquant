# Phase 1 — Relocations (BrokerFactory + Quote/WsSubscription)

**Context:** [plan.md](./plan.md) · brainstorm `../reports/brainstorm-260706-0200-r8-live-run-extraction.md`
**Priority:** P2 · **Status:** Done · **Track:** structure (move thuần, test xanh liên tục)

## Overview

3 pure move đưa mảnh framework-free về đúng tầng. Không đổi logic — chỉ đổi vị trí file + rewire import. Verify (`lint-imports`+`pytest`) NGAY sau mỗi move để bắt import app-only bị kéo theo.

## Key insights (đã verify)

- `QuoteAppService` imports: chỉ `asyncio/datetime/core.*/engine.market_data` — **zero app import** → move an toàn.
- `WsSubscriptionAppService`: `asyncio/core.domain port/core.infra repo` + forward-ref string tới `QuoteAppService` — an toàn.
- `BrokerFactory` imports: `core.common.messaging`, `core.domain.brokers/trading`, `core.infra.brokers.{okx,paper}` — hợp lệ cho `core.infra`.
- Rewire tối thiểu: BrokerFactory → 2 file; Quote/Ws → 2 file. `_SingleBrokerFactory` (engine/backtest) + `IBrokerFactoryPort` (core.domain) KHÔNG đụng.

## Related code files

**Move:**
- `src/pocketquant/app/di/broker_factory.py` → `src/pocketquant/core/infra/brokers/broker_factory.py`
- `src/pocketquant/app/market_data/app_services/quote_app_service.py` → `src/pocketquant/engine/market_data/app_services/quote_app_service.py`
- `src/pocketquant/app/market_data/app_services/ws_subscription_app_service.py` → `src/pocketquant/engine/market_data/app_services/ws_subscription_app_service.py`

**Rewire imports:**
- `src/pocketquant/app/di/infrastructure.py:5,33` (BrokerFactory import + provide)
- `src/pocketquant/app/di/execution.py:11,53` (BrokerFactory type hint)
- `src/pocketquant/app/di/market_data.py:3-5` (Quote/Ws imports)
- `src/pocketquant/app/main_extensions.py:19-21` (Quote/Ws imports)

## Implementation steps

1. **Move BrokerFactory** → `core/infra/brokers/broker_factory.py` (nội dung không đổi). Rewire `di/infrastructure.py` + `di/execution.py` import path. Provider `provide(BrokerFactory, scope=Scope.APP)` giữ ở `infrastructure.py` (chỉ đổi import).
2. `lint-imports` + `pytest` + `ruff` + `pyright` → xanh. (Kỳ vọng: `core.infra` importing `core.*` hợp lệ; app import `core.infra.brokers.broker_factory` hợp lệ.)
3. **Move QuoteAppService** → `engine/market_data/app_services/quote_app_service.py`. Rewire `di/market_data.py` + `main_extensions.py` import. Giữ nguyên forward-ref trong `ws_subscription`.
4. `lint-imports` + `pytest` → xanh.
5. **Move WsSubscriptionAppService** → `engine/market_data/app_services/ws_subscription_app_service.py`. Rewire `di/market_data.py` + `main_extensions.py`. Cập nhật forward-ref comment nếu path đổi (vẫn string `QuoteAppService`).
6. `lint-imports` + `pytest` + `ruff` + `pyright` → xanh.
7. Xoá thư mục `app/market_data/app_services/` nếu rỗng (còn `tracked_symbol_seeder.py`, `__init__.py` → GIỮ; `tracked_symbol_seeder` ngoài scope R8).

## Todo

- [x] Move BrokerFactory + rewire 2 file → gate xanh
- [x] Move QuoteAppService + rewire 2 file → gate xanh
- [x] Move WsSubscriptionAppService + rewire 2 file → gate xanh
- [x] `__init__.py` engine/market_data/app_services vẫn discover được (grimp contract)

## Success criteria

- 3 file ở tầng mới; `grep -rn "app.di.broker_factory\|app.market_data.app_services.quote\|app.market_data.app_services.ws_subscription"` = 0 (trừ comment).
- 8 import-linter contract + 560 test + ruff + pyright xanh.

## Risk assessment

- **Circular import Quote↔Ws:** `ws` ref `Quote` qua string forward-ref (`# type: ignore[name-defined]`) → move không phá. Nếu pyright than → giữ nguyên pattern string.
- **grimp discover:** engine feature-area cần `__init__.py` (đã có). Thêm file vào `engine/market_data/app_services/` không đổi contract graph.
- **DI scope:** BrokerFactory provider vẫn APP scope ở app/di — chỉ import path đổi, không đổi wiring.

## Next steps

→ Phase 2 (fold rehydrate). Độc lập với Phase 1 nhưng chạy sau để giữ diff nhỏ.
