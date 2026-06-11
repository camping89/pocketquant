# 2026-06-11 — Collapse 6 subpackages → 4, single backend process

## Việc đã làm

4 commits trên develop (chưa push tại thời điểm viết — atomic push 4 commit cùng 1 lần):

1. `23feaa2` — xóa `trading/webhooks/` dead code (~110 LOC, zero importers); khóa layout expectation 4 subpackages bằng test (`test_dissolved_subpackages_are_gone` xfail strict trong transition).
2. `df7f20a` — giải thể `trading/`: 3 services (`strategy_command_service`, `strategy_query_service`, `orders_positions_service`) → `engine/`; OKX broker → `core/infra/brokers/okx/` (cạnh `paper/`); tests phân bổ vào `engine_test/` + `core_test/infra/persistence/`.
3. `53da61f` — gộp `bff/` vào `app/`: 1 FastAPI app, 1 Dishka container, 1 lifespan (full runtime + toàn bộ routes + SPA), port `:41921`. Xóa console script `pocketquant-bff`. OpenAPI snapshot diff đúng 2 path: `info.title`, `info.description`.
4. `7fb6caf` — compose prod còn 1 backend service; nginx upstream `app:41921`; `10-deploy.sh`/`11-verify.sh` gọn 1 container; docs sync AS-IS.

## Quyết định kỹ thuật đáng nhớ

- **DI dedupe khi merge container**: dishka 1.9.1 cho phép duplicate provide — provider sau thắng *thầm lặng*. Khi union 2 container, 3 types trùng (`StrategyCommandService`, `StrategyQueryService`, `SyncService`) phải strip khỏi provider ex-bff, giữ bản app. Invariant: mỗi type đúng 1 registration.
- **REPLACE thay vì đắp `register_routes`**: cả 2 bản main_extensions đều đăng ký `/health` — cộng dồn sẽ duplicate route và lệch snapshot. Body bản bff (routes + SPA + /health) thay thế nguyên khối bản app.
- **OpenAPI title hardcode literal `"PocketQuant"`**: lấy từ `settings.app_name` sẽ làm snapshot phụ thuộc env (`APP_NAME=pocketquant-test` trong test fixtures).
- **Thứ tự snapshot bắt buộc**: repoint import `bff.main` → `app.main` TRƯỚC, diff với snapshot đã commit (chỉ cho phép info.title/description), RỒI mới regenerate + rename file. Regenerate trước = che giấu diff thật.
- **Bug 500 `/trading/orders|positions` tự hết**: single container resolve được `OrderPositionQueryService` (cần `OrderAppService`/`PositionAppService` in-RAM) — không cần code mới.
- **Single worker only**: scheduler/WS feed/broker là in-process singletons; `--workers N` sẽ nhân bản reconcile loop + live broker connection. Comment cảnh báo đặt ở 4 chỗ: Dockerfile, compose.prod.yml, justfile, CLAUDE.md.

## Bug bất ngờ gặp giữa chừng

- **structlog `cache_logger_on_first_use=True` + test order**: test assert log qua `capture_logs()` fail khi chạy sau integration tests (module logger đã cache processor chain trước khi capture config). Fix: autouse fixture trong `tests/app_test/unit/handlers/sync/conftest.py` rebind fresh lazy proxy cho 4 modules có log assertion. Bisect mất nhiều vòng vì cần ≥4 file combination mới reproduce.
- **PEP 420 namespace package ghost**: xóa `bff/` bằng `git rm` nhưng `__pycache__/` còn sót → `find_spec("pocketquant.bff")` vẫn resolve (namespace package không cần `__init__.py`). Layout contract test bắt được đúng như thiết kế — phải `rm -rf` cả pycache.

## Đánh đổi đã chấp nhận (user duyệt)

- Blast radius khi boot fail: trước đây app crash thì bff vẫn serve API; giờ crash-loop = API chết toàn bộ. Đổi lấy: 1 entrypoint, hết DI duplication (~160 LOC), bug 500 tự hết.
- `/api/v1/trading/orders|positions` trả live positions không auth (pre-existing posture, reachable chỉ qua nginx) — đã ghi nhận follow-up về auth coverage cho mutation routes.

## Deploy (chưa thực hiện tại thời điểm viết)

Push 4 commits cùng 1 lần `git push` — CI auto-deploy mỗi push develop; push lẻ commit 3 khi compose cũ còn gọi `uvicorn pocketquant.bff.main:app` = crash-loop + 502 toàn bộ API. Rollback sau deploy: `git revert` cả 2 commit cuối + full CI rebuild, KHÔNG rollback image lẻ (backend cũ trên port mới chỉ có /health; web cũ trỏ upstream bff không tồn tại). `11-verify.sh` giờ có probe `/api/v1/market-data/symbols` — backend mất routes sẽ hiện hình FAIL thay vì verify HEALTHY mù.
