# Phase 4 — Infra: Market Data Context (Port + Adapter)

**Priority:** P2 · **Risk:** med (DI-bound, split file) · **Status:** completed

## Overview
Bounded context `market_data`: đổi port `I*` → `I*Port` (tách file), adapter → `*Adapter`. Làm port + adapter cùng phase để chỉ đụng DI provider 1 lần.

## Rename mapping
| Current class | New class | Current file | New file | refs |
|---|---|---|---|---|
| `IDataProvider` | `IDataProviderPort` | `core/domain/market_data/interfaces.py` | `data_provider_port.py` | 10 |
| `IRealtimeQuoteProvider` | `IRealtimeQuoteProviderPort` | `core/domain/market_data/interfaces.py` | `realtime_quote_provider_port.py` | 6 |
| `BinanceClient` | `BinanceAdapter` | `core/infra/binance/binance_client.py` | `binance_adapter.py` | 5 |

`BinanceAdapter` (bỏ `DataProvider` — đa mục đích tương lai, không single-purpose).

## Implementation steps
1. **Split** `market_data/interfaces.py` → 2 file: `data_provider_port.py` (`IDataProviderPort`) + `realtime_quote_provider_port.py` (`IRealtimeQuoteProviderPort`). Xoá `interfaces.py` sau khi chuyển hết (kiểm tra không còn class khác trong đó).
2. Rename `BinanceClient(IDataProvider)` → `BinanceAdapter(IDataProviderPort)` + `git mv` file.
3. Cập nhật DI: `app/di/market_data.py` + `app/di/infrastructure.py` — provide return-hint `IDataProviderPort`, bind impl `BinanceAdapter`; `FromDishka[IDataProviderPort]` tại consumers.
4. Cập nhật mọi type-hint `IDataProvider`/`IRealtimeQuoteProvider` (10+6 file: bar_app_service, quote_app_service, sync_service, quotes_service, tests…).
5. `__init__.py` re-export (`market_data/__init__.py`).

## Gotchas
- `interfaces.py` chứa 2 port → phải tách đúng, cập nhật **tất cả** import điểm (import từ `...market_data.interfaces` → 2 module mới).
- Dishka bind theo type: đổi type-hint mà quên provider → runtime resolve fail (pyright bắt phần lớn, nhưng test integration mới chắc).
- `IRealtimeQuoteProvider` là `Protocol` (structural) — impl không khai báo kế thừa; đổi tên chỉ ở điểm type-hint + định nghĩa.

## Verify
- `just test` · `import-linter` · `pyright` → xanh.
- Commit: `refactor(naming): market_data ports → I*Port, BinanceClient → BinanceAdapter`

## Todo
- [x] Split interfaces.py → data_provider_port.py + realtime_quote_provider_port.py
- [x] IDataProvider → IDataProviderPort (10 refs)
- [x] IRealtimeQuoteProvider → IRealtimeQuoteProviderPort (6 refs, Protocol)
- [x] BinanceClient → BinanceAdapter + git mv
- [x] DI: market_data.py + infrastructure.py return-hint + bind
- [x] __init__ re-export
- [x] pytest + import-linter + pyright xanh

## Success criteria
Test/lint/type xanh; DI resolve `IDataProviderPort` → `BinanceAdapter`; market data sync/quote hoạt động; refs tên cũ = 0.
