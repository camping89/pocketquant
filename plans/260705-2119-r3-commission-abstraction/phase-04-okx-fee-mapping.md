# Phase 04 — OKX map abs(fee) → OrderResult.commission

**Priority:** P2 · **Status:** completed · **Depends:** P01 · **Blocks:** P05

Song song được với P02/P03 (chỉ cần P01: `OrderResult.commission`).

## Overview

OKX là **thick broker** — trả `fee` sẵn trong payload orders channel nhưng `OkxOrderMapper.to_order_result` đang **bỏ lỡ**. R3 map `commission = abs(float(fee))`. Paper **tính**, OKX **đọc** → `IBrokerPort` cân xứng (xem `okx-broker-verification.md`).

## Key insight — dấu + đơn vị

- OKX `fee` thường **âm** (phí trừ), maker có thể **dương** (rebate) → `commission` là **cost dương** → `abs()`.
- `feeCcy`: giả định `== quote` cho R3 (USDT-margined perp trả phí USDT). Nếu khác (OKB/cross-margin) → gap FX, KHÔNG xử R3 (document).
- `fee` trong orders channel là **accumulated** (khớp `accFillSz`/`avgPx` accumulated mà mapper dùng) → map thẳng. `fillFee` = per-fill (không dùng ở đây).
- **side vẫn KHÔNG map** ở R3 (Trade cần side → R4). Chỉ thêm commission.

## Requirements

- `to_order_result`: đọc `data.get("fee")`, set `commission = abs(float(fee))` nếu có, else `0.0`.

## Related code files

- **MODIFY** `src/pocketquant/core/infra/brokers/okx/websocket/okx_order_mapper.py`

## Implementation steps

1. Trong `to_order_result` (sau block filled_price ~dòng 48):
   ```python
   fee_raw = data.get("fee", "")
   commission = abs(float(fee_raw)) if fee_raw else 0.0
   ```
2. Thêm `commission=commission` vào `OrderResult(...)` return.
3. Comment 1 dòng: OKX `fee` âm=phí / dương=rebate → `abs`; feeCcy giả định quote (gap FX chưa xử — R3).

## Todo

- [x] Đọc + `abs(float(fee))` guard rỗng
- [x] `commission=` vào OrderResult
- [x] Comment dấu + feeCcy assumption
- [x] compile + `pyright`

## Success criteria

- `to_order_result({"fee": "-0.42", ...}).commission == 0.42` (phí âm → cost dương).
- `to_order_result({"fee": "0.05", ...}).commission == 0.05` (rebate → vẫn abs; chấp nhận đơn giản hoá R3).
- `to_order_result({...})` (không `fee`) → `commission == 0.0`.
- `fee == ""` (rỗng) không raise.

## Risks

- `fee` per-fill vs accumulated: chọn accumulated (khớp mapper). Verify payload thật (demo mode) khi impl — docs có thể lệch version (unresolved, chuyển verify runtime).
- Rebate maker map thành cost dương = sai dấu kinh tế nhỏ; YAGNI cho R3 (paper không có rebate), ghi nhận.
