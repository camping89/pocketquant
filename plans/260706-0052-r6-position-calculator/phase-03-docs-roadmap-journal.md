# Phase 03 — Docs sync + roadmap R6 done + journal

**Priority:** P2 · **Status:** done · **Depends:** 02

Đồng bộ docs AS-IS (đổi tên service + method + VO mới), đánh dấu R6 done trong roadmap, viết journal.

## Related files

**Modify**
- `docs/code-standards.md` — line ~368 (bảng example Domain Services), ~391 (ví dụ đọc tên)
- `docs/system-architecture.md` — line ~155, ~178, ~222, ~622 (signal flow step 4)
- `plans/trading-calulation-fix/roadmap.md` — hàng R6 → **Done** + resolve unresolved-question R6

**Create**
- `docs/journals/2026-07-06-r6-position-calculator.md` (qua `/ck:journal`)

**KHÔNG đụng**: `docs/journals/*` cũ (lịch sử AS-IS, git giữ).

## Implementation steps

### 1. `code-standards.md`

- Bảng ~368: `PositionSizerDomainService` → `PositionCalculatorDomainService` trong cột example.
- ~391: ví dụ `PositionSizerDomainService` → `PositionCalculatorDomainService`.

### 2. `system-architecture.md`

- ~155: `services/position_sizer_domain_service.py  # PositionSizerDomainService (pure calc)` → tên mới + file mới.
- ~178: `BarBuilderDomainService and PositionSizerDomainService …` → `PositionCalculatorDomainService`.
- ~222: `position_sizer_domain_service.py  # PositionSizerDomainService (risk calculations)` → file + class mới.
- ~622 signal flow: `PositionSizerDomainService.calculate_size()` → `PositionCalculatorDomainService.calculate()`.
- (tuỳ chọn) 1 dòng: `calculate()` trả `PositionCalculation{size,notional,risk_amount,est_entry_commission}`; risk defaults = class consts. Giữ AS-IS, bullet, không changelog.

### 3. `roadmap.md`

- Bảng Decomposition hàng **R6**: prepend `✅`, cột Scope thêm `**Done** — …` (tóm tắt: rename + `PositionCalculation` VO + consts 1-source + xoá KELLY/FIXED/validate_size + RiskCheckHandler consts + giữ RiskConfig override; `just test` pass parity, 4 gate xanh).
- Unresolved questions: gạch bỏ dòng **R6** override-question, note **GIẢI (R6)**: *4 runtime site dùng default; chỉ tests override `max_exposure_percent` → GIỮ optional `RiskConfig`; consts = nguồn default (RiskConfig defaults tham chiếu). `from_dict` dead giữ nguyên.*
- (Design doc §10 cùng question — tuỳ chọn note ngắn, không bắt buộc.)

### 4. Journal

`/ck:journal` → `docs/journals/2026-07-06-r6-position-calculator.md`: concise, handoff cho R7 (defaults USD 10k/4bps + currency; R6 đã lo sizing/consts, R7 chỉ tune value).

## Todo

- [x] code-standards.md 2 vị trí
- [x] system-architecture.md 4 vị trí (+ signal flow)
- [x] roadmap.md R6 → Done + resolve unresolved
- [x] journal 2026-07-06-r6

## Success criteria

- `git grep 'PositionSizer\|calculate_size' -- docs` chỉ còn trong `docs/journals/*` lịch sử.
- roadmap R6 = ✅ Done; unresolved R6 resolved.
- Journal tồn tại, có handoff R7.

## Next

→ R7 (config defaults USD 10k / 4bps / currency) — session riêng.
