---
phase: 1
title: "Engulfing detector + golden fixture"
status: completed
priority: P2
dependencies: []
---

# Phase 1: Engulfing detector + golden fixture

## Overview

Pure detection function (Python) + golden fixture JSON dùng chung cho cả Python và TS. Đây là nền: Phase 2 (strategy) và Phase 3 (chart) import detector này / fixture này. Khóa định nghĩa engulfing không lệch giữa 2 runtime.

## Requirements

- Functional: hàm thuần nhận 2 bar liên tiếp (prev, curr) → trả `EngulfingResult{is_bullish, is_bearish, rejection_wick_pct}`. Không state, không I/O.
- Functional: golden fixture = mảng case `{prev, curr} → expected{is_bullish, is_bearish, rejection_wick_pct}`, đủ phủ: bullish strong, bullish weak (upper wick dài), bearish strong, bearish weak (lower wick dài), không engulfing (body không bao), doji/range-0 edge, equal-body boundary.
- Non-functional: detector trong `core/domain` (zero deps ngoài stdlib); fixture ngôn ngữ-trung lập (JSON), không nhúng kỳ vọng riêng cho 1 runtime.

## Architecture

**Định nghĩa (strict body, 2 chiều):**
```
bullish = prev_close < prev_open  AND  close > open
          AND open <= prev_close  AND  close >= prev_open
bearish = prev_close > prev_open  AND  close < open
          AND open >= prev_close  AND  close <= prev_open
```

**rejection_wick_pct (close-location, hướng phụ thuộc chiều) — LUÔN float (red-team Finding 5):**
```
range = high - low
range == 0 → rejection_wick_pct = 1.0 (luôn fail filter, tránh chia 0)
bullish → (high - close) / range     # upper wick ngược chiều LONG
bearish → (close - low)  / range     # lower wick ngược chiều SHORT
không engulfing → rejection_wick_pct = 1.0 (sentinel "fail", KHÔNG None)
```

> **KHÔNG dùng `None` (red-team Finding 5):** JSON không có `None` canonical; `pytest.approx(None)` crash; TS `null` vs Python `None` lệch parity ở đúng edge case (no-engulf, range-0) — chính nơi fixture cần khóa. → `rejection_wick_pct: float` luôn (sentinel `1.0` khi không engulf/range-0). So sánh fixture 1 path numeric cả 2 runtime. `EngulfingResult.rejection_wick_pct: float` (không `| None`).

Consumer áp ngưỡng riêng: strategy `<= max_rejection_wick_pct` mới entry; chart dùng để chọn màu đậm/nhạt.

**Vì sao có hướng (không dùng body/range ratio):** body-dominance phạt oan lower wick tốt của nến LONG (người mua đỡ đáy = bullish). Chỉ wick **ngược chiều lệnh** mới là rejection. Xem brainstorm-report §3.

## Related Code Files

- Create: `src/pocketquant/core/domain/strategy/patterns/__init__.py`
- Create: `src/pocketquant/core/domain/strategy/patterns/engulfing_detector.py` — `detect_engulfing(prev: dict, curr: dict) -> EngulfingResult` + `EngulfingResult` dataclass (frozen).
- Create: `tests/core_test/unit/domain/strategy/patterns/engulfing_golden_fixture.json` — shared fixture (source of truth).
- Create: `tests/core_test/unit/domain/strategy/patterns/test_engulfing_detector.py` — load fixture, assert mỗi case.
- Reference: Phase 3 COPY fixture này vào `web/src/lib/indicators/__fixtures__/` (import-as-JSON, KHÔNG cross-root `node:fs` — red-team Finding 3). Phase 5 verify `diff` 2 file chống drift.

## Implementation Steps

1. Tạo `patterns/` package + `EngulfingResult` frozen dataclass: `is_bullish: bool`, `is_bearish: bool`, `rejection_wick_pct: float` (LUÔN float, sentinel 1.0 — không `| None`).
2. Implement `detect_engulfing(prev, curr)`: bar dict keys `open/high/low/close` (float). Tính bullish/bearish theo công thức; tính `rejection_wick_pct` theo hướng; guard `range == 0`.
3. Viết golden fixture JSON với ≥8 case phủ branch (liệt kê ở Requirements). Mỗi case ghi rõ `prev`, `curr`, `expected`.
4. Viết test load fixture, loop assert. So `rejection_wick_pct` với `pytest.approx` (sai số float).
5. `uv run pytest tests/core_test/unit/domain/strategy/patterns/ -q` cho file này. (KHÔNG có mypy — bỏ type-check BE.)

## Success Criteria

- [ ] `detect_engulfing` trả đúng `is_bullish`/`is_bearish` cho mọi case fixture.
- [ ] `rejection_wick_pct` khớp expected (approx) cho case engulfing; `range==0` → 1.0; no-engulf → 1.0 (float, không None).
- [ ] Fixture phủ: bullish strong/weak, bearish strong/weak, no-engulf, range-0, boundary body bằng nhau.
- [ ] Detector zero deps ngoài stdlib (import-linter core contract giữ nguyên).
- [ ] `uv run lint-imports` 7 contracts pass; `uv run ruff check` xanh.

<!-- Updated: Validation Session 1 + Red Team Session 1 - fixture canonical ở tests/; Phase 3 COPY vào web/ (không cross-root); rejection_wick_pct luôn float -->
> Fixture JSON này là **canonical source** ở `tests/core_test/...`. Phase 3 vitest dùng 1 **bản copy** trong `web/src/lib/indicators/__fixtures__/` (import-as-JSON, KHÔNG cross-root `node:fs` — tránh vỡ `tsc -b`). Phase 5 `diff` 2 file chống drift. Parity TS↔Python **máy enforce** qua test 2 bên cùng dữ liệu.

## Risk Assessment

- **Risk:** boundary `<=`/`<` của body-bao sai lệch giữa định nghĩa và test. Mitigation: fixture có case body-bằng-nhau (open == prev_close) chốt rõ inclusive/exclusive.
- **Risk:** fixture chỉ dùng được Python, TS không tái sử dụng. Mitigation: JSON thuần, không field Python-specific; Phase 3 load cùng file.
- **Risk:** chia 0 khi nến doji range 0. Mitigation: guard explicit → 1.0, có case fixture.
