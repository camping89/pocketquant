---
phase: 4
title: "Deploy runtime and docs sync"
status: pending
priority: P2
effort: "3h"
dependencies: [3]
---

# Phase 4: Deploy runtime and docs sync

## Overview

Đồng bộ hạ tầng chạy với end-state 1 process: compose (local + prod) còn 1 backend service, nginx upstream đổi `bff` → `app`, deploy/verify scripts trên VPS gọn lại, docs/README/CLAUDE.md mô tả AS-IS 4 subpackages.

## Context Links

- Brainstorm: [report](../reports/brainstorm-260611-1651-collapse-six-subpackages-to-four-single-process-report.md)
- Files đã scout: `deploy/compose.prod.yml` (services: web, app:41920, bff:41921, mongodb, redis, portainer), `deploy/compose.local.yml`, `web/nginx.conf:14` (`proxy_pass http://bff:41921`), `deploy/vps/10-deploy.sh:74-75`, `deploy/vps/11-verify.sh:66-108`.

## Key Insights

- **Deployment atomicity (CRITICAL):** CI auto-deploy mỗi push lên develop (`.github/workflows/cicd.yml:165-215` chạy `10-deploy.sh`). Phase 3 (code) và Phase 4 (compose/nginx) PHẢI lên develop trong CÙNG 1 push — push lẻ Phase 3 = compose cũ chạy `uvicorn pocketquant.bff.main:app` trên image không còn module bff → crash-loop + web 502 toàn bộ API trên hệ thống live-trading. nginx.conf nằm TRONG web image (CI build context `./web`) nên swap chỉ atomic khi backend image + web image cùng sha deploy cùng nhau — cùng 1 push là đủ.
- Web nginx + Vite proxy đều đã trỏ `:41921` → app mới listen 41921 nghĩa là FE-side chỉ cần đổi service name trong nginx (`bff` → `app`), Vite config không đổi.
- Prod compose: xóa service `bff`; service `app` đổi command sang port 41921, healthcheck 41921; `web.depends_on` chuyển từ `bff` sang `app`. `--remove-orphans` ĐÃ CÓ sẵn trong `10-deploy.sh:50` — container bff cũ tự bị dọn.
- **`compose.local.yml` chỉ có mongodb + redis** — không có web/app/bff service. `just up` không smoke được full stack; smoke full stack phải qua prod compose hoặc dev flow (`just be` + `npm run dev`). Bước smoke viết theo thực tế này.
- `11-verify.sh` hiện KHÔNG probe route `/api/v1/*` nào (chỉ /health, SPA, mongo/redis) — backend mất hết routes vẫn verify HEALTHY. Thêm 1 curl `/api/v1/...` để đóng lỗ này (cũng là guard cho rollback mù).
- `BFF_PORT` env: chỉ dùng trong justfile recipe bff cũ (đã xóa ở Phase 3) — sweep nốt nếu còn nơi nào reference. Không tìm thấy trong `pocketquant-config/` lúc scout.
- Docs phải AS-IS (rule CLAUDE.md): không viết "previously 6 packages", chỉ mô tả trạng thái 4 subpackages hiện hành.

## Requirements

- Functional: dev flow (`just be` + Vite) hoạt động end-to-end; compose prod config hợp lệ; deploy VPS scripts pass với 1 backend container.
- Non-functional: docs/CLAUDE.md/README phản ánh đúng cấu trúc mới, không sót reference `bff`/`trading`.

## Related Code Files

- Modify: `deploy/compose.prod.yml` — xóa service `bff`; `app`: command port 41921, healthcheck 41921, giữ depends_on mongo/redis; `web.depends_on` → `app` healthy. Cập nhật comment SP3 (không còn đúng). Thêm comment trên `command:`: "single worker only — scheduler/WS/broker là in-process singletons; `--workers N` sẽ nhân bản reconcile loop + live broker connection".
- (compose.local.yml: chỉ mongodb+redis, không có backend service — KHÔNG cần sửa.)
- Modify: `web/nginx.conf:14` — `proxy_pass http://app:41921;` + comment.
- Modify: `deploy/vps/10-deploy.sh` — `wait_health pocketquant-app 41921 60`, xóa dòng bff; sửa comment.
- Modify: `deploy/vps/11-verify.sh` — CONTAINERS/HEALTH_CONTAINERS bỏ `pocketquant-bff`; health curl app → 41921; xóa block 3a (bff healthcheck); THÊM 1 probe `/api/v1/*` (vd `curl -sf http://localhost:41921/api/v1/symbols` qua docker exec) — verify hiện chỉ check /health nên backend mất routes vẫn báo HEALTHY.
- Modify: `justfile` — comment recipe `be`: "single worker only" (cùng lý do compose).
- Modify (docs): `README.md` (Repo Layout tree, dependency direction, Quick Start bỏ `just bff`, URLs), `CLAUDE.md` (layout 6→4, dependency graph, rules nhắc app/bff), `docs/system-architecture.md` (diagram + SP3 section viết lại AS-IS), `docs/architecture-visual-map.md`, `docs/system-relationship-map.md`, `docs/code-standards.md` (nếu nhắc bff/trading), `docs/deployment.md`.

## Implementation Steps

1. **TDD-lock:** viết check nhỏ vào `tests/baseline/` hoặc dùng layout contract sẵn có — grep guard: `grep -rln "pocketquant.bff\|pocketquant.trading\|41920" docs README.md CLAUDE.md deploy web/nginx.conf justfile` dùng làm acceptance thủ công cuối phase (docs không testable bằng pytest, dùng checklist; pattern PHẢI gồm `41920` — Dockerfile/main.py từng lọt guard chỉ grep tên module).
2. Compose prod: áp thay đổi như Related Code Files (compose.local không cần sửa — chỉ mongo+redis). Chú ý comment cũ nhắc SP3/bff — viết lại AS-IS. Thêm comment single-worker.
3. `web/nginx.conf`: upstream `app:41921`.
4. VPS scripts: 10-deploy.sh + 11-verify.sh gọn còn 1 backend container; 11-verify.sh thêm probe `/api/v1/*`.
5. Smoke local (compose.local không có web/app service — KHÔNG dùng `just up` smoke full stack): chạy `just be` (app đầy đủ trên :41921) + `cd web && npm run build && npm run preview` hoặc dev flow `npm run dev` (Vite proxy /api → 41921) → SPA load, gọi API, refresh client-route OK. Smoke nginx-level (upstream rename) xác nhận ở bước deploy thật qua 11-verify.sh probe mới — hoặc nếu muốn pre-verify local: `docker compose -f deploy/compose.prod.yml config` để check cú pháp + service refs.
6. Docs sync (AS-IS, prose tiếng Việt cho phần mô tả, giữ thuật ngữ tiếng Anh):
   - `CLAUDE.md`: layout `core, engine, backtest, app`; dependency graph `core ◁ engine ◁ backtest ◁ app`, `web → app`; xóa câu "app and bff are independent siblings".
   - `README.md`: tree mới, bỏ `just bff`, URLs chỉ còn `:41921`.
   - `docs/system-architecture.md`: diagram 1 backend container; section SP3 control-plane giữ (reconcile loop vẫn tồn tại) nhưng bỏ ngôn ngữ 2-process.
   - Visual maps + deployment.md: đồng bộ.
7. Grep guard cuối: `grep -rn "bff\|pocketquant.trading\|41920" README.md CLAUDE.md docs/ deploy/ web/nginx.conf justfile pyproject.toml` → chỉ còn match hợp lệ (nếu có tên lịch sử trong plans/ thì ngoài scope — plans không sửa).
8. Full gates + smoke. Commit: `chore(deploy): single backend service on 41921, docs sync to 4-subpackage layout`.
9. **Push atomic:** push commit Phase 3 + Phase 4 lên develop trong CÙNG 1 lần `git push` (CI auto-deploy mỗi push — xem Key Insights). Theo dõi CI deploy job + `11-verify.sh` output; sẵn sàng rollback theo quy trình trong plan.md.

## Todo List

- [ ] compose prod 1 backend service + comment single-worker (compose.local không cần sửa)
- [ ] nginx upstream app:41921
- [ ] VPS deploy/verify scripts cập nhật + 11-verify.sh probe /api/v1/*
- [ ] Smoke dev flow: `just be` + Vite → SPA + API OK; `docker compose -f deploy/compose.prod.yml config` pass
- [ ] CLAUDE.md / README / docs sync AS-IS
- [ ] Grep guard sạch (gồm pattern 41920)
- [ ] Full gates xanh, commit
- [ ] Push atomic Phase 3+4 cùng 1 lần, theo dõi CI deploy + verify

## Success Criteria

- [ ] compose prod chỉ còn 1 backend service (`app`), command/healthcheck 41921, comment single-worker
- [ ] `11-verify.sh` có probe `/api/v1/*`
- [ ] Không còn reference `bff` / `pocketquant.trading` / `41920` trong README, CLAUDE.md, docs/, deploy/, web/nginx.conf, justfile, pyproject.toml
- [ ] Full gates xanh
- [ ] Sau deploy thật: web:80 serve SPA, proxy `/api` tới app:41921, tất cả containers healthy, verify probe API pass

## Risk Assessment

| Risk | Mitigation |
|---|---|
| Push lẻ Phase 3 không kèm Phase 4 → CI deploy image thiếu bff trên compose cũ → outage | Quy tắc atomic push (bước 9 + plan.md "Deployment atomicity"); Phase 3 commit-không-push |
| nginx upstream rename sót → web 502 sau deploy | nginx.conf + compose đổi cùng đợt push; `compose config` check trước; 11-verify.sh probe API bắt ngay sau deploy |
| Rollback image-only sau merge → backend cũ chạy port mới chỉ có /health (API 404) hoặc web cũ trỏ upstream bff không tồn tại (502), mà verify cũ vẫn báo HEALTHY | Rollback section trong plan.md: rollback = `git revert` cả 2 phase + full CI rebuild, KHÔNG rollback image lẻ; probe API mới trong 11-verify.sh biến rollback hỏng thành verify FAIL nhìn thấy được |
| VPS còn orphan container bff từ deploy trước | `--remove-orphans` đã có sẵn trong 10-deploy.sh:50 — confirmed, không cần thêm |
| Docs sót reference cũ | grep guard bước 7 là acceptance bắt buộc |

## Security Considerations

- App container giờ là upstream public duy nhất (qua nginx) — không expose port app ra host trong prod compose (chỉ internal network), giữ pattern hiện tại của bff.

## Next Steps

- Plan hoàn tất → `/ck:journal`; cân nhắc theo dõi API latency khi backtest nặng (đã ghi nhận out-of-scope).
