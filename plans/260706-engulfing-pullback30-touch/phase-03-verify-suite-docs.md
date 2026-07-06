---
phase: 3
title: "Verify suite + docs"
status: completed
priority: P2
dependencies: [2]
---

# Phase 3: Verify suite + docs

## Overview

Chạy full quality gate (test suite + ruff + pyright) và cập nhật docs nếu strategy list có liệt kê. Xác nhận bản gốc + golden fixture không đổi.

## Requirements

- Non-functional: toàn bộ test xanh, lint/type sạch, không regression bản gốc.
- Docs: cập nhật nơi liệt kê strategy có sẵn (nếu có) để nhắc `engulfing_pullback30_touch`.

## Architecture

Không có code mới — chỉ verify + docs. Golden fixture (`engulfing_golden_fixture.json` cả Python lẫn TS) KHÔNG đổi vì detection dùng lại nguyên `detect_engulfing`.

## Related Code Files

- Read/verify: `tests/core_test/unit/domain/strategy/patterns/engulfing_golden_fixture.json`, `web/src/lib/indicators/__fixtures__/engulfing_golden_fixture.json` (không đổi).
- Modify (nếu có liệt kê strategy): `docs/system-architecture.md` và/hoặc `docs/codebase-summary.md` — thêm 1 dòng mô tả variant. Grep trước; nếu docs không liệt kê strategy cụ thể thì bỏ qua (AS-IS, không thêm nhiễu).

## Implementation Steps

1. Grep docs cho `engulfing`/`hitnrun2` để tìm chỗ liệt kê strategy; nếu có bảng/danh sách → thêm dòng `engulfing_pullback30_touch` (mô tả: pullback 30% body, vào tại close bar kế tiếp khi chạm intrabar).
2. Chạy focused: `pytest tests/core_test/unit/domain/strategy/test_engulfing_pullback30_touch.py tests/backtest_test/engine/test_engulfing_pullback30_touch_backtest.py`.
3. Broaden: chạy `tests/core_test/unit/domain/strategy/` + `tests/backtest_test/engine/` (regression bản gốc engulfing).
4. `ruff check` + `ruff format --check` trên file mới; `pyright`/`basedpyright` (theo config repo) trên module + test mới.
5. Xác nhận `git status`: không có thay đổi ngoài file dự kiến (2 source/registry, 2 test, tối đa 1-2 docs).

## Success Criteria

- [ ] Focused + broadened strategy/backtest tests xanh.
- [ ] ruff + type-check sạch trên file mới.
- [ ] `engulfing_golden_fixture.json` (Python + TS) và `engulfing_strategy_service.py` không đổi (git diff rỗng).
- [ ] Docs cập nhật nếu có liệt kê strategy; ngược lại ghi rõ "không có chỗ liệt kê → bỏ qua".

## Risk Assessment

- **Type-check tool:** repo có thể dùng basedpyright/mypy — kiểm `pyproject.toml`/CI trước khi chạy lệnh đúng.
- **Docs over-reach:** không thêm changelog/banner; chỉ 1 dòng AS-IS nếu đã có danh sách strategy. Nếu không có → không tạo mục mới.
