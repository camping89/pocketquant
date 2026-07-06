# Brainstorm — Cloudflare → Origin TLS (Flexible → Full strict)

## TL;DR

Domain `pocketquant.xyz` đã live qua Cloudflare proxy, SSL mode = **Flexible**. Browser→Cloudflare đã mã hóa (TLS 1.3, Universal SSL cert OK), nhưng **Cloudflare→origin vẫn HTTP:80 trần**. Với app trading có auth + API credentials, đoạn này là lỗ hổng thật (man-in-the-middle giữa CF edge và VPS). Mục tiêu: nâng lên **Full (strict)** với Cloudflare Origin Certificate. Không gấp — làm sau.

## Hiện trạng (AS-IS)

```
Browser ──HTTPS(TLS1.3)──> Cloudflare ──HTTP:80 (trần)──> Origin nginx :80 ──> app:41921
         [✅ mã hóa]                    [❌ KHÔNG mã hóa]
```

| Thành phần | Giá trị |
|---|---|
| DNS | Cloudflare proxied (orange) — `A @ → 207.148.79.60`, `CNAME www → pocketquant.xyz` |
| SSL mode | Flexible |
| Origin | VPS `207.148.79.60`, container `pocketquant-web` (nginx) publish `WEB_PORT=80:80` |
| nginx | listen 80 only, reverse-proxy `/api/*` → `app:41921`, SPA fallback |
| Port 443 trên VPS | **chưa mở, chưa có cert** |

## Vấn đề cần giải

1. **Đoạn CF→origin không mã hóa** — traffic (kể cả login/trading payload) đi internet dạng plaintext giữa CF edge và VPS. Flexible cũng dễ dính redirect loop nếu app tự ép HTTPS.
2. **Origin IP có thể bị bypass** — ai biết `207.148.79.60` vẫn gọi thẳng HTTP:80, qua mặt Cloudflare (WAF, rate-limit, TLS).

## Hướng tiếp cận

### Option A — Cloudflare Origin Certificate + Full (strict) ✅ KHUYẾN NGHỊ

CF cấp free origin cert (hạn tối đa 15 năm), cài vào nginx, mở 443, đổi mode sang Full strict.

```
Browser ──HTTPS──> Cloudflare ──HTTPS:443 (CF Origin cert)──> Origin nginx :443 ──> app:41921
         [✅]                   [✅ mã hóa, verify cert]
```

- **Pros:** end-to-end TLS; cert 15 năm = zero renewal toil; strict verify chặn spoof; không phụ thuộc Let's Encrypt ACME / cron renew; cert do CF tin cậy (chỉ CF gọi origin được nếu kèm Authenticated Origin Pulls).
- **Cons:** cert chỉ hợp lệ khi đi QUA Cloudflare (gọi thẳng IP bằng browser sẽ báo cert lạ — đúng ý đồ); phải sửa nginx + compose + Dockerfile + .env.
- **Files chạm:**
  - `web/nginx.conf` — thêm `listen 443 ssl;` + `ssl_certificate` / `ssl_certificate_key`, redirect 80→443.
  - `web/Dockerfile` — `EXPOSE 443`, COPY cert vào image HOẶC mount runtime (xem rủi ro bên dưới).
  - `deploy/compose.prod.yml` — `web.ports` thêm `"443:443"` (hoặc đổi mapping theo `WEB_PORT`).
  - `pocketquant-config/vps/default/.env` — `WEB_PORT=443`.
  - Nơi chứa cert/key (xem "Quyết định mở" #1).

### Option B — Authenticated Origin Pulls (bổ sung cho A)

Sau khi A xong, bật mTLS: origin chỉ chấp nhận kết nối mang client cert của Cloudflare. Chặn hoàn toàn bypass IP.

- **Pros:** đóng nốt lỗ hổng "gọi thẳng IP"; phòng thủ tốt nhất cho origin.
- **Cons:** thêm 1 lớp config nginx (`ssl_client_certificate` + `ssl_verify_client on`); chỉ làm sau khi A chạy ổn.

### Option C — Let's Encrypt + certbot

Cert công khai thật (hợp lệ cả khi gọi thẳng IP).

- **Pros:** cert chuẩn public.
- **Cons:** cần ACME renewal (cron/sidecar), HTTP-01 challenge phải mở 80 public, thêm moving parts. **Thừa** so với nhu cầu — traffic luôn đi qua CF nên Origin Cert (A) đủ và đơn giản hơn. Vi phạm KISS.

→ **Chốt: A (chính) + B (sau, optional). Bỏ C.**

## Quyết định mở (cần chốt khi làm)

1. **Cert nằm đâu?** Bake vào Docker image (đơn giản, nhưng private key vào image — chỉ ổn nếu registry private) **HAY** lưu ở `pocketquant-config/vps/default/` rồi rsync + mount vào container (sạch hơn, key không vào image, khớp pattern config-repo hiện tại). → Nghiêng về **mount từ config-repo** (đồng nhất với "single source of truth" hiện có).
2. **80 redirect hay đóng?** Giữ 80 listen để redirect 301→443 (cho "Always Use HTTPS" của CF + user gõ http). Khuyến nghị giữ redirect.
3. **`11-verify.sh`** có cần thêm check 443/TLS không? (hiện chỉ check app health nội bộ.)
4. **Firewall ufw** — mở 443, cân nhắc đóng 80 public hoặc chỉ allow CF IP ranges.

## Việc nhỏ làm NGAY (không thuộc scope nâng cấp) — ✅ DONE

- ✅ **Always Use HTTPS** = On. Verified: `http://pocketquant.xyz/` và `http://www.pocketquant.xyz/` → `301 → https://…`.
- ✅ **Automatic HTTPS Rewrites** = On (tránh mixed-content).

Tất cả edge-cert toggles đã xong. Còn lại duy nhất là nâng cấp **Full (strict) + Origin Certificate** (Phased plan bên dưới) — để làm sau.

## Phased plan (khi triển khai)

1. **Phase 1** — Tạo Origin Cert trên CF dashboard, lưu vào `pocketquant-config/vps/default/` (vd `origin-cert.pem` + `origin-key.pem`), `git push` config-repo.
2. **Phase 2** — Sửa `nginx.conf` (443 ssl + redirect 80→443), `compose.prod.yml` (mount cert + publish 443), `.env` (`WEB_PORT=443`). Đảm bảo deploy rsync cert vào VPS.
3. **Phase 3** — Đổi CF SSL mode → **Full (strict)**. Verify `https://pocketquant.xyz/` + `/api/v1/docs` = 200, và `openssl s_client` tới origin:443 thấy CF origin cert.
4. **Phase 4 (optional)** — Bật Authenticated Origin Pulls (Option B) + ufw siết 80/443.

## Acceptance criteria

- `https://pocketquant.xyz/`, `/api/v1/docs`, `/api/v1/backtest/strategies` → 200 (qua CF).
- CF SSL mode = Full (strict), không 521/525/526.
- Origin `:443` handshake bằng CF Origin cert (xác minh qua `openssl s_client -connect 207.148.79.60:443`).
- SSE/streaming (`/api/*`, `proxy_buffering off`) vẫn hoạt động qua CF (chú ý CF free idle timeout ~100s — test live feed).
- CI/CD deploy không vỡ (cert có mặt trên VPS trước khi nginx start).

## Rủi ro

- **521/525 nếu đổi mode trước khi origin sẵn sàng 443** — luôn làm Phase 2 xong + verify origin:443 TRƯỚC khi đổi sang Full strict. Có thể tạm Full (không strict) để test rồi mới strict.
- **Private key lộ** — nếu bake vào image, registry phải private; nếu mount, key chỉ ở config-repo (đã là nơi chứa SSH key + .env, cùng mức bảo mật).
- **Deploy race** — `web` container start nhưng cert chưa rsync → nginx fail boot. Đảm bảo thứ tự rsync cert trước `docker compose up`.
- **SSE qua CF** — Cloudflare free có thể ngắt long-lived SSE; nếu live feed rớt, cách ly bằng cách tạm grey-cloud record để xác nhận là CF.

## Tham chiếu

- `docs/deployment.md` → mục "Custom Domain" (đã mô tả đúng hướng A) + "Port Map" + "Firewall".
- `web/nginx.conf`, `web/Dockerfile`, `deploy/compose.prod.yml`.
- `pocketquant-config/vps/default/.env` (`WEB_PORT`), `pocketquant-config/vps/default/` (nơi chứa cert đề xuất).
