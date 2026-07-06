# Backtest run name

**Status:** DRAFT — chờ duyệt

## Mục tiêu

Thêm `name` (optional) cho một backtest run: nhập lúc tạo từ UI, sửa được sau đó (như `verdict`), hiển thị ở list + RunHeader (vùng overview). Không có field `desc`.

## Quyết định đã chốt (user)

- **Vị trí overview:** `RunHeader` (identity, luôn hiển thị trên mọi tab) — inline-editable.
- **Editable:** cho sửa sau khi tạo → thêm `PATCH /backtest/{run_id}/name` (mirror `verdict`).
- **Empty name:** fallback `strategy_code` (name khi có thành tiêu đề nổi bật).

## Ràng buộc

- `name` phải sống sót qua **cả 2 lần ghi doc**: started (`BacktestResult.started`) và finished (engine rebuild `config_snapshot` từ `BacktestConfig` trong `finalize()`, ghi đè cùng `run_id`). ⇒ phải thêm vào `BacktestConfig`.
- Mirror y pattern `verdict`: top-level field trên `BacktestResult`, `to_mongo`/`from_mongo`, repo `set_verdict` → `set_name`, route PATCH, FE `setVerdict`/`useSetVerdict`/`VerdictPanel`.
- `max_length = 200` cho name (verdict dùng 2000; name ngắn).
- Import-linter: không đổi ranh giới layer. Không thêm import fastapi ngoài app.

## Edge case

- Sửa name khi run còn `started`: lần finish sẽ ghi đè bằng `config.name` (giá trị lúc tạo). Sửa sau khi `finished` sẽ giữ. Chấp nhận — trùng ngữ nghĩa verdict (chỉ sửa post-run). Ghi chú, không guard.

## Phases

- `phase-01-backend-name-field.md` — domain + command/query + repo + route + engine snapshot.
- `phase-02-frontend-name-ui.md` — api types + hook + form input + list item + RunHeader inline edit.

## Acceptance criteria

1. Tạo run **không** name → chạy bình thường, list/header hiện `strategy_code` như cũ.
2. Tạo run **có** name → name lưu ở started doc, **vẫn còn** sau khi finished.
3. Name hiển thị ở `RunListItem` (list) và `RunHeader` (overview).
4. Sửa name sau khi finished qua PATCH → persist + optimistic update; list refresh.
5. `GET /backtest/{id}` trả `name`; `GET /backtest/strategy/{id}` mỗi row có `name`.
6. Không lỗi mới: `ruff`, `pyright`, `lint-imports`, `pytest` (backend); build FE.
7. Public contract khác giữ nguyên (verdict, metrics, symbol/interval…).

## Dependencies

phase-02 phụ thuộc phase-01 (FE cần shape API + PATCH endpoint).
