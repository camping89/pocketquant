# Phase 5 — Infra: Brokers Context (Port + Adapter)

**Priority:** P2 · **Risk:** HIGH (`PaperBroker` 25 refs, DI + factory) · **Status:** completed

## Overview
Bounded context `brokers`: port `I*` → `I*Port` (tách file) + 3 adapter → `*Adapter`. Phase cuối, blast radius lớn nhất. Làm cẩn thận, verify kỹ.

## Rename mapping
| Current class | New class | Current file | New file | refs |
|---|---|---|---|---|
| `IBroker` | `IBrokerPort` | `core/domain/brokers/interfaces.py` | `broker_port.py` | 13 |
| `IBrokerFactory` | `IBrokerFactoryPort` | `core/domain/brokers/interfaces.py` | `broker_factory_port.py` | 4 |
| `PaperBroker` | `PaperBrokerAdapter` | `core/infra/brokers/paper/paper_broker.py` | `paper_broker_adapter.py` | **25** (15 src + 10 test) |
| `OKXBroker` | `OKXBrokerAdapter` | `core/infra/brokers/okx/okx_broker.py` | `okx_broker_adapter.py` | 6 |
| `OkxWebSocketClient` | `OKXWebSocketAdapter` | `core/infra/brokers/okx/websocket/okx_websocket_client.py` | `okx_websocket_adapter.py` | 4 |

**KHÔNG đổi** (exempt, sub-component OKX): `OkxMessageParser`, `OkxOrderMapper`, `OkxPositionMapper`, `OkxReconnectionHandler`, `OkxStateReconciler`. `BrokerFactory` (`app/di/broker_factory.py`) là `*Factory` → exempt.

## Implementation steps
1. **Split** `brokers/interfaces.py` → `broker_port.py` (`IBrokerPort`) + `broker_factory_port.py` (`IBrokerFactoryPort`). Kiểm tra không còn class khác; xoá interfaces.py.
2. Rename `PaperBroker(IBroker)` → `PaperBrokerAdapter(IBrokerPort)` + `git mv`. **25 refs** — grep kỹ src + test.
3. Rename `OKXBroker` → `OKXBrokerAdapter`, `OkxWebSocketClient` → `OKXWebSocketAdapter` + `git mv`.
4. Cập nhật DI: `app/di/broker_factory.py`, `app/di/execution.py` — provide return-hint `IBrokerPort`/`IBrokerFactoryPort`, bind impl adapter mới; `FromDishka[IBrokerPort]` tại order/position/strategy app services.
5. `BrokerFactory.create()` return-hint `IBrokerPort`; map broker type→adapter class.
6. Cập nhật `backtest/engine/backtest_engine_sandbox.py` (`_SingleBrokerFactory`) + `backtest_app_service.py` (khởi tạo `PaperBroker`).
7. Cập nhật toàn bộ test refs `PaperBroker` (10 file test).

## Gotchas
- `PaperBroker` 25 refs — cao nhất; test fixtures dùng nhiều. Đổi sót → test đỏ (đó là mục đích: pytest bắt).
- Dishka bind `IBrokerPort` → factory chọn `PaperBrokerAdapter`/`OKXBrokerAdapter` theo config. Sai type-hint → resolve fail.
- `paper_broker.py` docstring đề cập "PaperBroker", "collectors" — cập nhật name-echo nếu có.
- import-linter: `core/infra` không được import `fastapi` — rename không đổi layer, an toàn; vẫn chạy `lint-imports` xác nhận 7 contracts pass.
- Overlap MAE/MFE plan: `paper_broker.py` (broker SL/TP path). Rename trước.

## Verify
- `just test` (FULL suite — phase nhạy nhất) · `import-linter` (7 contracts) · `pyright`.
- Chạy thử 1 backtest end-to-end + kiểm tra live broker wiring (nếu có môi trường) để chắc DI resolve.
- Commit: `refactor(naming): broker ports → I*Port, brokers → *Adapter`

## Todo
- [x] Split interfaces.py → broker_port.py + broker_factory_port.py
- [x] IBroker → IBrokerPort (13) · IBrokerFactory → IBrokerFactoryPort (4)
- [x] PaperBroker → PaperBrokerAdapter (25 — grep kỹ src+test)
- [x] OKXBroker → OKXBrokerAdapter · OkxWebSocketClient → OKXWebSocketAdapter
- [x] DI: broker_factory.py + execution.py return-hint + bind
- [x] BrokerFactory.create() return-hint + sandbox factory
- [x] pytest FULL + import-linter + pyright xanh
- [x] Backtest end-to-end smoke

## Success criteria
Full pytest xanh; import-linter 7 contracts pass; pyright sạch; DI resolve `IBrokerPort` → adapter đúng; backtest chạy; refs tên cũ = 0.
