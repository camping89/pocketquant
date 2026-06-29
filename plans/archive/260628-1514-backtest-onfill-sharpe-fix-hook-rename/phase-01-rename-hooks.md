---
phase: 1
title: "Rename Hooks"
status: done
priority: P2
dependencies: []
---

# Phase 1: Rename Hooks (mirror-event naming)

## Overview

Đổi tên 3 hook trong `IStrategy` contract theo triết lý B (mirror tên event sinh ra chúng), để tên hook truy ngược thẳng về event/callback. Chạy TRƯỚC Phase 2 để wiring fill dùng tên mới ngay, tránh rename 2 lần.

## Requirements

- Functional: rename không đổi hành vi — chỉ đổi tên method + mọi call-site + tests.
- Non-functional: giữ `on_start`/`on_stop` nguyên (lifecycle, không có event tương ứng). Không đổi trigger string `"bar"/"tick"` trong config (độc lập với tên method, chỉ là nhãn `_find_strategies` lọc).

## Rename map (verified)

| Cũ | Mới | Trigger thật |
|---|---|---|
| `on_bar(bar)` | `on_bar_completed(bar)` | `BarCompletedEvent` |
| `on_tick(tick)` | `on_quote_received(tick)` | `QuoteReceivedEvent` |
| `on_fill(order, fill_price)` | `on_order_filled(order, fill_price)` | broker `OrderResult` callback (≈`OrderFilledEvent`) |
| `on_start` | `on_start` (giữ) | — lifecycle |
| `on_stop` | `on_stop` (giữ) | — lifecycle |

## Architecture

`IStrategy` là public contract (ABC). Rename phải đồng bộ 3 nơi: (1) abstract/định nghĩa, (2) implementation `hitnrun2`, (3) call-site trong orchestrator. Tests gọi trực tiếp method cũng phải đổi.

**⚠ Collision phải tránh:** KHÔNG đụng `BacktestResultCollector.on_fill(result)` — đó là method KHÁC (consumer callback của broker, nhận `OrderResult`, không thuộc `IStrategy`). Chỉ rename `on_fill` thuộc `IStrategy`/`hitnrun2`.

## Related Code Files

- Modify: `src/pocketquant/core/domain/strategy/interfaces.py` — 3 abstract `def` + docstring (`on_bar:37`, `on_tick:48`, `on_fill:62`) + lifecycle list dòng 17.
- Modify: `src/pocketquant/core/domain/strategy/services/hitnrun2.py` — `on_bar`→`on_bar_completed` (dòng 71), `on_fill`→`on_order_filled` (dòng 114) + docstring module dòng 15.
- **Modify (RED-TEAM CRIT): `src/pocketquant/engine/app_services/strategy_app_service.py`** — HAI việc:
  - `class _DefaultStrategy(IStrategy)` định nghĩa `async def on_bar` tại **dòng 383** → rename `on_bar_completed`. Đây là abstract override; nếu sót → `TypeError: Can't instantiate abstract class` khi `_DefaultStrategy(config)` ở `load_strategy:102` (live default path, không test nào cover).
  - Call-site: `strategy.on_bar(bar)` (dòng 230) → `on_bar_completed`; `strategy.on_tick(tick)` (dòng 255) → `on_quote_received`. Handler `_on_bar_completed`/`_on_quote_received` GIỮ NGUYÊN tên (đúng quy ước event-handler).
- **Modify (RED-TEAM): `tests/engine_test/strategy_injection_roundtrip_characterization_test.py:65`** — `class _CountingStrategy(IStrategy)` có `async def on_bar` (abstract override) → rename.
- Modify: `tests/core_test/unit/domain/strategy/test_hitnrun2.py` — nhiều `s.on_bar(...)`/`s.on_fill(...)` (dòng 83-222) → rename gọi.
- Do NOT touch: `tests/backtest_test/engine/test_result_collector_fifo.py:81` (`collector.on_fill(fill)` — là collector).
- Do NOT list (RED-TEAM: phantom): `tests/engine_test/test_strategy_handlers_declarative.py` — KHÔNG có hook reference nào (chỉ test subscription CRUD). Bỏ khỏi scope Phase 1.

## Implementation Steps

1. Grep **cả `def` lẫn call** (red-team: grep `.on_bar(` bỏ sót abstract override `def on_bar`):
   `grep -rn "def on_bar\b\|def on_tick\b\|def on_fill\b\|\.on_bar(\|\.on_tick(\|\.on_fill(\|(IStrategy)" src/ tests/` → phân loại: IStrategy subclass def / call-site / collector-callback (giữ).
2. Đổi `interfaces.py`: 3 abstract def + docstring + lifecycle comment dòng 17.
3. Đổi `hitnrun2.py`: 2 method def + module docstring.
4. Đổi `strategy_app_service.py`: `_DefaultStrategy.on_bar:383` (def) + 2 call-site (bar:230, tick:255).
5. Đổi `_CountingStrategy.on_bar:65` (test) + `test_hitnrun2.py` gọi hook.
6. `just types` để bắt sót (mypy báo abstract-not-implemented + method-not-found).

## Success Criteria

- [ ] `grep -rn "def on_bar\b\|\.on_bar(\|def on_fill\b" src/` chỉ còn handler `_on_*` và `collector.on_fill`; không còn hook cũ.
- [ ] `IStrategy.on_order_filled` tồn tại; `on_fill` không còn trong `IStrategy`/`hitnrun2`/`_DefaultStrategy`.
- [ ] `_DefaultStrategy` + `_CountingStrategy` instantiate được (không abstract error).
- [ ] `BacktestResultCollector.on_fill` vẫn nguyên.
- [ ] `just types` xanh; tests collect/pass.

## Risk Assessment

- **Risk (RED-TEAM CRIT):** sót `_DefaultStrategy.on_bar:383` → `TypeError` runtime ở live default path (no test cover). Mitigation: step 4 explicit + `just types` bắt abstract-not-implemented.
- **Risk:** grep `.on_bar(` bỏ sót `def` override. Mitigation: step 1 grep cả `def` + `(IStrategy)`.
- **Risk:** nhầm rename `collector.on_fill`. Mitigation: step 1 phân loại trước.
- **Verified an toàn:** trigger string `"bar"/"tick"` độc lập tên method (chỉ là nhãn `_find_strategies:284` lọc) — KHÔNG migrate subscription doc. OpenAPI snapshot không đổi (hook là internal).
- **Rollback:** rename thuần, revert commit.
