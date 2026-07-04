# Unresolved questions — test suite trim (max-lean)

Bối cảnh: trim test suite cho lean/pragmatic. Kết quả `pytest`: **551 passed, 1 skipped**; `ruff check` sạch trên file đã đổi; `lint-imports` 7/7 kept. Before/after: **95 → 70 test file** (excl conftest), **~14.8k → ~12.6k LOC** trong `tests/`, và bỏ ~3.1k dòng snapshot JSON (`openapi_app_snapshot.json`, `route_inventory_app_snapshot.json`).

## Cần xác nhận / quyết định

1. **`test_domain_purity.py` — giữ hay swap sang import-linter?**
   Plan max-lean liệt kê xóa file này (dup import-linter), nhưng đã **khôi phục** vì: (a) docs hiện hành tham chiếu nó như guard được enforce (`docs/system-architecture.md:116,494`, `docs/code-standards.md:20`); (b) nó có coverage **duy nhất** — chặn `core.domain` import trực tiếp `pymongo/redis/httpx/fastapi`, mà 7 import-linter contract hiện tại **không** phủ.
   → Có muốn swap: thêm 1 import-linter `forbidden` contract cho external I/O libs trong `core.domain`, rồi xóa AST test + cập nhật 3 docs ref? (canonical hơn, nhanh hơn, nhưng đụng `pyproject.toml` + docs).

2. **Baseline snapshots đã xóa (OpenAPI + route inventory).**
   Workflow `BASELINE_UPDATE=1 uv run pytest tests/baseline` (thấy trong journals) không còn → mất phát hiện API-drift tự động. Xác nhận không còn dựa vào nó? (Đã chọn max-lean nên coi như OK, chỉ flag lại.)

3. **Guard bị bỏ theo max-lean — chấp nhận?**
   - `test_lifespan_boot.py`: bỏ luôn assertion idempotent boot-migration (chặn boot migration phá seeded data).
   - `test_quotes_service.py`: bỏ guard uppercase cache-key (footgun cache-miss do case-mismatch).

4. **`scripts/audit_bar_quality.py` giờ không có test** (đã xóa `tests/scripts/test_audit_bar_quality.py`).
   Nếu bar-quality monitoring dùng trong vận hành, có muốn giữ lại 2–3 test math (flat%/zero-volume%) thay vì xóa cả file?

5. **4 lỗi `ruff check` có sẵn ở HEAD trong `tests/`** (không do trim):
   `test_quote_app_service.py:8`, `test_lot_tracker.py:3`, `test_event_bus.py:3`, `sync_progress_tracker_test.py:7` (import-sort, auto-fixable).
   Cố ý **không** đụng để giữ commit focused. Muốn dọn trong 1 commit riêng?
