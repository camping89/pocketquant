---
title: "R7 — Config defaults (balance 10k / currency USD / commission 4bps)"
description: "Tune defaults cuối initiative: paper initial_balance 100k→10k (code + .env), currency USD cho paper/backtest (OKX giữ USDT venue), commission default 4 bps (backtest commission_bps 10→4; paper-live đã 4 từ R3). Verify worked-example (USD 10000, 4bps, slip 10bps) design §6 trên 1 run thật của broker sim. Kế thừa Model E §3(#11)/§6."
status: done
priority: P3
branch: develop
tags: [trading-calc, config, defaults, currency, commission, paper-broker]
blockedBy: []
blocks: []
created: "2026-07-06T01:31:00+07:00"
createdBy: "ck:plan"
source: "plans/trading-calulation-fix/roadmap.md (R7) + design-execution-metrics-separation.md §3(#11) + §6"
---

# R7 — Config defaults + worked-example verify

## Overview

- **Priority:** P3 (config-only, cơ học). **Depends:** R3 ✅ + R5 ✅ (đã done).
- **Scope:** chỉ tune giá trị default + 1 test verify. KHÔNG đổi logic khớp lệnh, KHÔNG đổi contract.
- **Bất biến giữ:** parity backtest↔paper, import-linter 8 contract xanh, characterization số KHÔNG đổi.

R7 là hàng cuối track logic/config của initiative (chi tiết: `plans/trading-calulation-fix/roadmap.md`). Ba nhóm thay đổi + verify.

## Key insights (từ research)

- **`.env` đè code default:** `.env` có `PAPER_INITIAL_BALANCE=100000` → phải sửa cả `.env`, không thì local run vẫn 100k dù code đổi.
- **Commission backtest vẫn 10 bps** ở 3 nơi (`config.py`, `command_service.py`, `dispatch.py`); paper-live đã 4 bps (`paper_commission_percent=0.0004`, R3). Web backtest-form KHÔNG gửi `commission_bps`/`slippage_bps` → UI backtest ăn default backend ⇒ đổi 10→4 áp cho cả UI.
- **Characterization tests** (engulfing/hitnrun2, `test_backtest_single_run_direct_task`, `test_result_collector_mark_to_market`) pin **explicit** `commission_bps`/`initial_capital`/`currency` ⇒ đổi default KHÔNG phá test hiện có.
- **Currency = label thuần** (không phép tính phụ thuộc); duy nhất `test_result_collector_mark_to_market.py:56` dùng currency và đã là `"USD"`. OKX pin explicit `"USDT"` tại mọi call site → an toàn tách paper=USD / OKX=USDT.
- **Web frontend** không surface currency/initial_balance default (chỉ dùng `BTCUSDT` như ví dụ symbol) → KHÔNG đụng `web/`.
- **Futures balance model xác nhận** (`paper_broker_adapter.py:595` `self._balance -= commission`; balance đổi theo realized-pnl delta khi reduce): entry chỉ trừ commission (không trừ notional) → tái hiện chính xác worked-example §6.

## Changes — Group A: initial_balance 100k → 10k

| File:line | Hiện tại | Đổi |
|---|---|---|
| `src/pocketquant/core/config.py:71` | `paper_initial_balance: float = 100_000.0` | `10_000.0` |
| `.env:51` | `PAPER_INITIAL_BALANCE=100000` | `PAPER_INITIAL_BALANCE=10000` |
| `src/pocketquant/app/di/broker_factory.py:36` | `initial_balance=config.get("initial_balance", 100_000.0)` | `..., 10_000.0)` |
| `src/pocketquant/core/infra/brokers/paper/paper_broker_adapter.py:110` | `initial_balance: float = 100_000.0` | `10_000.0` |

> Backtest path đã `10_000.0` sẵn (`backtest/config.py:30`, `backtest_command_service.py:33`, `backtest_dispatch.py:49`, `backtest_strategy_loader.py:60,72`) → không đụng.

## Changes — Group B: currency USD (paper/backtest); OKX giữ USDT

| File:line | Hiện tại | Đổi |
|---|---|---|
| `src/pocketquant/core/infra/brokers/paper/paper_broker_adapter.py:113` | `currency: str = "USDT"` | `"USD"` |
| `src/pocketquant/app/di/broker_factory.py:39` (nhánh paper) | `currency=config.get("currency", "USDT")` | `..., "USD")` |
| `src/pocketquant/engine/backtest/backtest_sandbox_app_service.py:116` | `currency: str = "USDT"` | `"USD"` |

**KHÔNG đụng (OKX venue = USDT):** `broker_factory.py:58` (`inst_suffix`), `okx_mapper.py:32,84,120,127`, `okx_broker_adapter.py:46,253,263,272`.

**KHÔNG đụng (no-op, giữ minimal churn):** `core/domain/brokers/value_objects.py:40` `AccountBalance.currency: str = "USDT"` — VO default không bao giờ bị hit (paper truyền `self._currency`, OKX truyền explicit `"USDT"`). Đổi = churn vô nghĩa. → verify không có call site nào construct `AccountBalance()` thiếu `currency`.

## Changes — Group C: commission default 4 bps

| File:line | Hiện tại | Đổi |
|---|---|---|
| `src/pocketquant/core/domain/backtest/config.py:32` | `commission_bps: float = 10.0` | `4.0` |
| `src/pocketquant/engine/backtest/backtest_command_service.py:35` | `Field(default=10.0, ge=0, ...)` | `default=4.0` |
| `src/pocketquant/engine/backtest/backtest_dispatch.py:51` | `payload.get("commission_bps", 10.0)` | `..., 4.0)` |

> Sửa cả comment `# 0.1% default (validated requirement)` ở `config.py:32` → phản ánh 4 bps.
> **Paper-live đã 4 bps** (`paper_commission_percent=0.0004`, R3) → không đụng `config.py:73`.
> **`slippage_bps` GIỮ 10** (worked-example dùng slip 10 bps); `paper_slippage_percent=0.001` giữ nguyên.

## Verify — worked-example design §6 (1 run thật)

**Artifact:** `tests/backtest_test/engine/test_r7_worked_example_defaults.py` — drive **PaperBrokerAdapter thật** (shared sim engine, cùng path backtest+paper) với đúng default R7.

**Scenario (design §6):** LONG qty=10, initial=10000, slippage=0.001 (10bps), commission bps=4.
1. BUY 10 @ market, ref price 100 → fill `100×1.001 = 100.10`, entry commission `100.10×10×0.0004 = 0.4004`.
2. SELL 10 @ market, ref price 104 → fill `104×0.999 = 103.896`, exit commission `103.896×10×0.0004 = 0.415584`.

**Assert (abs tol < 1e-2):**
| Đại lượng | Kỳ vọng |
|---|---|
| entry fill price | 100.10 |
| entry commission | 0.4004 |
| exit fill price | 103.896 |
| exit commission | 0.415584 |
| gross PnL | 37.96 |
| net PnL (gross − 2 fee) | 37.144 |
| **final balance** | **10037.144** |
| `get_balance().currency` | `"USD"` |

Cơ chế balance (đã verify): `10000 − 0.4004` (entry fee) `+ 37.96` (realized delta khi reduce) `− 0.415584` (exit fee) `= 10037.1440`.

**Cross-check dùng lại `_run_engulfing` harness (optional, cùng file test):** chạy full engulfing replay với `initial_capital=10000, slippage_bps=10, commission_bps=4`, rồi assert *invariant* trên output broker thật (không cần khớp số §6 tuyệt đối):
- mỗi fill: `commission == price*qty*0.0004`
- `net_pnl == gross_pnl − Σ commission`
- `final_balance == 10000 + Σ net_pnl`, `currency == "USD"`

> Chọn Tier-2 (direct broker drive) làm verify chính vì deterministic + khớp §6 tuyệt đối, không phụ thuộc nội tại TP/SL của engulfing. Cross-check invariant là guard phụ.

## Non-changes / rationale

- `web/` — currency/initial_balance không surface ở UI → 0 đổi.
- `test_paper_broker_order_events.py:31,95` `initial_balance=100_000` — pin explicit, test tự chọn, không phải default ⇒ giữ.
- `AccountBalance` VO default — xem Group B (no-op).
- `slippage_bps` / `paper_slippage_percent` — giữ 10 bps (worked-example dùng).

## Success criteria

- 4 default balance = 10k (code) + `.env` = 10000; live-paper + backtest mặc định khởi tạo 10k.
- Paper/backtest broker báo `currency="USD"`; OKX vẫn `"USDT"` (unit + grep verify).
- Backtest commission default = 4 bps (3 nơi); UI backtest không truyền commission ⇒ ăn 4 bps.
- Test worked-example xanh: final balance = 10037.144 ± 1e-2, currency USD.
- **Gates:** `just test` (đủ 560 pass + test mới) · `ruff` · `pyright` (baseline) · `lint-imports` (8 contract) — tất cả xanh.

## Todo

- [x] Group A — sửa 4 site balance 100k→10k (gồm `.env`)
- [x] Group B — sửa 3 site currency USD; xác nhận OKX USDT nguyên; verify AccountBalance VO no-op
- [x] Group C — sửa 3 site backtest commission_bps 10→4 + comment
- [x] Viết `test_r7_worked_example_defaults.py` (Tier-2 + cross-check invariant)
- [x] Chạy 4 gate (`just test`/`ruff`/`pyright`/`lint-imports`) — xanh hết
- [x] Cập nhật bảng roadmap R7 `pending`→`Done` + `docs/` nếu chạm (dự kiến minor: nêu default mới trong system-architecture/code-standards nếu có liệt kê)

## Risks

- **Thấp toàn phần** (config values). Rủi ro duy nhất: `.env` chưa sửa → local backtest/paper vẫn 100k (mismatch code) → checklist ép sửa `.env`.
- Commission 10→4 đổi net PnL của UI backtest runs tương lai (mong muốn, không phá test pin explicit). Persisted runs cũ giữ commission_bps đã lưu (đọc từ doc, không từ default).

## Unresolved questions (resolved)

- `docs/` impact: Grep found no AS-IS doc in `docs/` hardcoding 100k/USDT/10bps defaults. Historical journals mention old values but journals are immutable AS-IS records. **Resolution:** Docs impact = NONE.
- `PAPER_COMMISSION_PERCENT` vào `.env`: Code default already 0.0004; left for user to decide if adding to .env for explicitness. **Resolution:** NOT added (not required; user can override at runtime if needed).
