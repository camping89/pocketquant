# R3: Commission Abstraction — Brainstorm + Plan

**Date**: 2026-07-05 21:19
**Severity**: Low
**Component**: Commission model, PaperBrokerAdapter, OKX mapper, core.domain.trading
**Status**: Planned (chưa implement)

---

## What Happened

Brainstorm R3 (logic track của initiative trading-calculation-fix) — grounding bằng đọc code thật (`paper_broker_adapter.py`, `value_objects.py`, `okx_order_mapper.py`, `backtest_result_app_service.py`, `config.py`, `broker_factory.py`, `execution.py`), không chỉ design doc. Chốt 4 quyết định mở → ghi design report + plan 5 phase.

## Phát hiện grounding

- Xác nhận **2 ledger song song**: broker `_balance` (futures, **không commission**) vs collector `_current_equity` (có commission, formula post-hoc `fill_price*qty*config.commission_percent`). `OrderResult` chưa có field commission. `OkxOrderMapper` bỏ lỡ `fee` (data có sẵn trong payload).
- PaperBroker có **4 fill path** tạo `OrderResult(FILLED)` riêng biệt: market, limit-immediate, limit-cross (`_fill_pending_on_bar`), synthetic SL/TP exit (`_fire_synthetic_exit`) → rủi ro #1: sót path = mất commission path đó.

## 4 quyết định chốt (với user)

1. **Funding fee SWAP**: KHÔNG sim — YAGNI (chưa có historical funding data), gap bounded + document. Không stub interface (speculative generality).
2. **CommissionModel placement**: `core.domain.trading` (không `brokers`) — tầng neutral để R6 `PositionCalculator` (position domain) dùng chung, tránh coupling position→brokers.
3. **Ranh giới R3 vs R5**: collector đọc `result.commission` (single-source ngay, số không đổi vì cùng giá trị) — dọn sẵn cho R5 xoá collector.
4. **Settings field**: thêm `paper_commission_percent=0.0004` ở R3 (match sibling `paper_slippage_percent`), wire qua `execution.py`→`broker_factory` để live-paper có commission ngay. R7 tune value + currency.

## Kiến trúc

`CommissionModel` (Protocol) + `PercentageCommissionModel(bps)` → `OrderResult.commission`. PaperBroker giữ 1 model, wrapper `_execute_fill_with_commission` gom điểm trừ `_balance` cho cả 4 path (chống sót). `_can_afford` gồm commission. OKX map `abs(float(fee))` (dấu âm=phí → cost dương). import-linter giữ **8/8** (không contract mới).

## Không làm (YAGNI)

Funding sim, SlippageModel, est_entry_commission (→R6), maker/taker/tiered.

## Artifacts

- Design: `plans/trading-calulation-fix/r3-commission-abstraction.md`
- Plan: `plans/260705-2119-r3-commission-abstraction/` (5 phase)
- Roadmap R3 → 📋 Planned; 2 unresolved (funding, Settings field) → GIẢI.
- Cross-plan: MAE/MFE plan `blockedBy` R3 (soft — đụng broker SL/TP path + LotTrackingHelper mà R3→R5 sửa).

## Unresolved (chuyển impl/R sau)

- `feeCcy != quote` (OKB/cross-margin) — R3 giả định quote, gap FX chưa xử.
- OKX `fee` per-fill vs accumulated — chọn accumulated (khớp `accFillSz`), verify payload demo khi impl.
- Funding fee perpetual parity gap — mở tới khi có funding data.
