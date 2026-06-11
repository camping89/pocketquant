---
phase: 1
title: "Lock baseline net and delete dead webhooks"
status: completed
priority: P1
effort: "2h"
dependencies: []
---

# Phase 1: Lock baseline net and delete dead webhooks

## Overview

TDD bước khóa: xác nhận regression net SP3 còn xanh trên develop hiện tại, viết TRƯỚC các expectation mới cho end-state 4 subpackages (đỏ tại thời điểm này — đó là chủ đích), rồi xóa `trading/webhooks/` dead code. Phase này không move code nào khác.

## Context Links

- Brainstorm: [report](../reports/brainstorm-260611-1651-collapse-six-subpackages-to-four-single-process-report.md)
- Regression net hiện tại: `tests/baseline/` (openapi snapshot, route inventory, boot smoke, layout contract)

## Key Insights

- `trading/webhooks/` (~110 LOC: `config.py`, `dispatcher.py`, `__init__.py`): zero importers ngoài chính nó, không có trong DI container nào, không có test nào reference — verified bằng grep toàn src + tests.
- `tests/baseline/test_package_layout_contract.py` hiện assert đủ 6 subpackages `("core", "engine", "backtest", "trading", "app", "bff")` — phải sửa expectation thành 4 và assert `trading`/`bff` KHÔNG còn importable. Test này sẽ đỏ cho tới hết Phase 3 → đánh dấu `xfail` có lý do, gỡ xfail ở Phase 3.
- `tests/baseline/test_app_boot_smoke.py` có test import `pocketquant.bff.main` — giữ nguyên trong Phase 1-2 (bff vẫn tồn tại), Phase 3 sẽ gộp thành 1 test.
- OpenAPI snapshot (`openapi_bff_snapshot.json`) không đổi trong toàn bộ plan trừ `info.title`/`info.description` ở Phase 3.

## Requirements

- Functional: develop hiện tại xanh toàn bộ gates; webhooks bị xóa không gây import error.
- Non-functional: expectation cho end-state được khóa dưới dạng test trước khi move code (TDD).

## Related Code Files

- Delete: `src/pocketquant/trading/webhooks/` (toàn bộ — `__init__.py`, `config.py`, `dispatcher.py`)
- Modify: `tests/baseline/test_package_layout_contract.py` — target layout 4 subpackages, xfail tạm với lý do "transition until phase 3"
- Verify-only: `tests/baseline/test_openapi_snapshot.py`, `test_route_inventory.py`, `test_app_boot_smoke.py`

## Implementation Steps

1. Chạy full gates trên develop sạch: `just test && just lint-imports && just types && just lint`. Tất cả phải xanh trước khi đụng bất kỳ file nào — đây là baseline.
2. Sửa `test_package_layout_contract.py`:
   - `test_all_subpackages_importable_from_single_src_tree`: đổi tuple thành `("core", "engine", "backtest", "app")` — KHÔNG đánh marker. Test này xanh ngay bây giờ (cả 4 đã importable) và xanh luôn ở end-state. <!-- red-team: xfail strict trên test đang pass sẽ XPASS→FAIL ngay -->
   - Thêm test mới `test_dissolved_subpackages_are_gone`: assert `find_spec("pocketquant.trading") is None` và `find_spec("pocketquant.bff") is None`. CHỈ test này đánh `pytest.mark.xfail(reason="4-subpackage end-state lands at phase 3", strict=True)`. `strict=True` để khi Phase 3 xong, xfail-pass sẽ FAIL nhắc gỡ marker.
   - Sửa vòng lặp trong `test_no_dishka_fastapi_integration_outside_app_bff`: bỏ `"trading"` khỏi tuple ngay (sau phase này trading vẫn tồn tại nhưng vòng lặp `(core, engine, backtest)` vẫn đúng và sẽ đúng luôn ở end-state — không cần xfail).
3. Xóa `src/pocketquant/trading/webhooks/` toàn bộ.
4. Grep xác nhận không còn reference: `grep -rn "webhooks" src/ tests/ --include='*.py'` → rỗng.
5. Chạy lại full gates → xanh (trừ đúng 1 xfail có chủ đích).
6. Commit: `chore: delete dead webhook dispatcher and lock 4-subpackage layout expectations`.

## Todo List

- [x] Baseline gates xanh trên develop sạch
- [x] Layout contract test sửa sang end-state 4 subpackages; chỉ test dissolved-gone đánh xfail strict
- [x] Xóa trading/webhooks/
- [x] Grep webhooks rỗng
- [x] Full gates xanh
- [x] Commit

## Success Criteria

- [x] `just test` xanh, đúng 1 xfail (`test_dissolved_subpackages_are_gone`) không hơn không kém
- [x] `src/pocketquant/trading/webhooks/` không tồn tại
- [x] `just lint-imports`, `just types`, `just lint` xanh

## Risk Assessment

- Rủi ro thấp. Webhooks không importer. Nếu grep bước 4 phát hiện reference ẩn (string-based import) → dừng, báo lại, không xóa.

## Security Considerations

- Không có. Xóa code không wire.

## Next Steps

- Phase 2: dissolve `trading` vào `engine` + `core`.
