---
title: Trades UI (notional + gross/net PnL + $ label) + commission 5bps + unify bps
status: completed
branch: develop
date: 2026-07-06
---

# Mục tiêu

5 thay đổi user yêu cầu trên trang backtest `/trades` + config phí:

1. Thêm cột **Notional (USD)** — cả entry & exit (`qty × price`).
2. PNL hiển thị rõ **USD** (thêm nhãn `$`; PnL vốn đã tính bằng quote USDT).
3. Cột PnL thành **2 cột: Gross + Net** (net = pnl − commission).
4. `commission_bps` default **4 → 5 bps**.
5. Fix lệch đơn vị: config live đổi **fraction → bps** (commission + slippage), thống nhất 1 đơn vị `bps`.

## Quyết định đã chốt (AskUserQuestion)
- Notional: **cả 2 cột** (entry notional + exit notional).
- PNL USD: **chỉ thêm nhãn `$`** (không thêm cột %).
- Unify: **sang bps** (rename key config).
- Slippage: **unify luôn** cùng commission.

# Nguyên tắc
- Notional & Net **derive ở FE** (đã có `quantity`, `entry_price`, `exit_price`, `pnl`, `commission`) → KHÔNG đổi DB/DTO/migration.
- Footer "Total Net" cần tổng commission → thêm 1 aggregate backend (`total_commission`).
- Unify chỉ ở tầng config/settings; `PaperBrokerAdapter` giữ nguyên tham số nội bộ (`slippage_percent` fraction, commission model bps) — conversion 1 lần ở `broker_factory`.

# Phases

## Phase 1 — Backend: commission 5bps + unify bps
| File | Thay đổi |
|---|---|
| `core/domain/backtest/config.py` | `commission_bps 4.0 → 5.0` + `slippage_bps 10.0 → 5.0`; docstring `(4=0.04%)→(5=0.05%)`, `(10=0.1%)→(5=0.05%)` |
| `engine/backtest/backtest_command_service.py:34-35` | slippage default `10.0 → 5.0`; commission default `4.0 → 5.0` |
| `engine/backtest/backtest_dispatch.py:50-51` | slippage fallback `10.0 → 5.0`; commission fallback `4.0 → 5.0` |
| `core/config.py:72-73` | `paper_slippage_percent=0.001 → paper_slippage_bps=5.0`; `paper_commission_percent=0.0004 → paper_commission_bps=5.0` |
| `app/di/execution.py:70-71` | keys → `slippage_bps`, `commission_bps` |
| `core/infra/brokers/broker_factory.py:34-41` | đọc `commission_bps`/`slippage_bps` trực tiếp; `slippage_percent=slippage_bps/10_000`; bỏ `*10_000`; sửa comment |
| `.env:40` | `PAPER_SLIPPAGE_PERCENT=0.001 → PAPER_SLIPPAGE_BPS=5` |

> **Slippage = 5 bps** (websearch: BTCUSDT perp taker realistic ~2–5 bps; 5 khớp commission, cân bằng realistic↔conservative).

## Phase 2 — Backend: total_commission cho footer net
| File | Thay đổi |
|---|---|
| `core/infra/persistence/repositories/backtest_trade_repository.py` | thêm `sum_commission_by_run(run_id, pnl_filter)` (mirror `sum_pnl_by_run`, `$sum $commission`) |
| `engine/backtest/backtest_stats_service.py` | `PagedTradesResponse` + `total_commission: float`; tính ở first page |

## Phase 3 — Frontend: notional + net + $ label
| File | Thay đổi |
|---|---|
| `web/src/lib/number-format.ts` | thêm `formatUsd(n)` → `+$0.08` / `-$0.13` |
| `web/src/api/backtest-api.ts` | `PagedTrades` + `total_commission: number` |
| `web/src/components/strategy/backtest-panel/positions-table.tsx` | support cột display-only (không sort); thêm **Entry $**, **Exit $** (sau Qty), **Net** (sau PnL); format `$` cho PnL/Net/Fee/Notional; màu net như pnl |
| `web/src/components/strategy/backtest-panel/positions-tab.tsx` | footer thêm **Net** = `total_pnl − total_commission`; đọc `total_commission`; nhãn `$` |

Column order: `Trade Id · Entry Time · Dir · Entry · Exit · Qty · Entry $ · Exit $ · Duration · PnL$ · Net$ · Fee$ · Status`

## Phase 4 — Tests + verify
- Fix `tests/core_test/infra/brokers/paper_broker_commission_test.py:184` (`commission_percent` → `commission_bps`).
- Thêm test `sum_commission_by_run` + `total_commission` trong stats.
- FE: thêm test `formatUsd` ở `number-format.test.ts`.
- Rà test đọc default cũ (r7 worked-example dùng bps=4 tường minh — không vỡ; kiểm tra không có test assert config default==4).
- `tester` + `code-reviewer` subagents.

# Acceptance
- Bảng trades có 2 cột notional (entry/exit) đúng `qty×price`, hiển thị `$`.
- Cột PnL(gross) + Net(=pnl−fee) tách bạch, có `$`; Fee có `$`.
- Footer: `Total PnL` (gross) + `Total Net`.
- Backtest run mới dùng 5 bps (UI form không gửi → ăn default backend).
- Config commission+slippage đều đơn vị `bps`; live paper tính phí = 5 bps (parity backtest).
- Toàn bộ test pass, không lỗi lint/type/build.

# Rủi ro
- Rename Settings key: `.env` cũ `PAPER_SLIPPAGE_PERCENT` bị `extra="ignore"` bỏ qua → fallback default 10bps (=cùng giá trị, không vỡ), vẫn update .env cho đúng.
- Run cũ trong DB (`019f141c…`) vẫn 10bps trong `config_snapshot` — không đổi lịch sử; chỉ ảnh hưởng run mới.
- Cột display-only phá cơ chế sort hiện tại nếu không tách flag → thêm `sortable` flag.
