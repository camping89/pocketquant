---
phase: 4
title: "Docs accounting model"
status: done
priority: P3
dependencies: [2]
---

# Phase 4: Docs accounting model

## Overview

Tài liệu hoá futures/margin accounting model của PaperBroker và lý do chọn nó thay vì spot, trong `docs/system-architecture.md`. AS-IS, bullet/bảng, không changelog.

## Requirements

- Functional: docs mô tả model hiện tại (sau Phase 2) đủ để maintainer hiểu vì sao `total_equity = balance + unrealized` và `_balance` chỉ đổi theo realized.
- Non-functional: tuân `docs/code-standards.md` comment/prose policy + CLAUDE.md (prose tiếng Việt, thuật ngữ tiếng Anh nguyên cụm, AS-IS, no banner).

## Architecture

Thêm sub-section vào `docs/system-architecture.md` gần bảng broker hiện có (`:304`, `:444`, `:526`). Nội dung:

- **Bảng so sánh** spot vs futures/margin accounting:

| | Spot | Futures/margin (PaperBroker dùng) |
|---|---|---|
| Open | cash −= notional | balance không đổi |
| Close | cash += proceeds | balance += realized pnl (delta) |
| total_equity | cash + Σ market_value | balance + Σ unrealized (mark per-bar) |
| available_balance | cash | = balance |

- **Vì sao futures:** domain là OKX perpetual SWAP (`okx_broker.py` instType SWAP); tránh điểm `total_equity ≈ 0` khi all-in; công thức `balance + unrealized` đúng cho cả long lẫn short không cần signed market value.
- **Leverage:** 1× cố định (không margin call).
- **`available_balance = balance`** (giữ nguyên field). Ghi rõ semantics: dưới futures, mở vị thế không tiêu cash → `available_balance` khi đang positioned cao hơn mô hình spot cũ. Strategy round-trip 1 vị thế (đóng trước khi mở mới) sizing không đổi; pyramiding/multi-symbol sẽ size theo full balance (đúng cho futures). Ghi như known semantics (validate-chốt: chấp nhận, không thêm guard).
- **OKX parity (red-team C6):** OKX trả `availBal`/`eq` riêng từ sàn — KHÔNG khẳng định PaperBroker `available_balance` khớp `availBal` (định nghĩa `availBal` cho SWAP account là external/unverified). Chỉ mô tả PaperBroker model; ghi rõ live balance lấy thẳng từ sàn, không qua `_execute_fill`.
- KHÔNG thêm diagram (bảng đã đủ — red-team C12; CLAUDE.md: diagram chỉ khi 2+ interacting parts).

## Related Code Files

- Modify: `docs/system-architecture.md` (sub-section accounting model)
- Read: `docs/code-standards.md` (prose/comment policy)

## Implementation Steps

1. Đọc `docs/system-architecture.md` quanh các dòng broker (`:304`, `:444`, `:526`) chọn vị trí chèn hợp lý.
2. Viết sub-section "PaperBroker accounting model" với bảng so sánh + rationale + leverage note + `available_balance = balance` note.
3. Verify prose tuân CLAUDE.md (tiếng Việt, thuật ngữ Anh nguyên cụm, no banner, AS-IS); KHÔNG claim OKX availBal parity.

## Success Criteria

- [ ] `docs/system-architecture.md` có sub-section accounting model với bảng spot vs futures
- [ ] Giải thích rationale (OKX SWAP domain, tránh điểm 0, long+short uniform); `available_balance = balance`
- [ ] KHÔNG khẳng định PaperBroker khớp OKX `availBal` (external/unverified)
- [ ] Prose tuân policy; không changelog/banner; không diagram

## Risk Assessment

- **Risk thấp:** docs-only. Đảm bảo mô tả khớp code sau Phase 2 (đọc lại `get_balance` final + `available_balance = _balance` trước khi viết).
