---
title: Exness credentials and access point plan update
date: 2026-10-11
summary: "Lưu EXNESS_SECRET_KEY dạng 128-hex, spike và Phase 06 xử lý access point theo từng account"
---

# Exness credentials and access point plan update

## What happened
- Credentials Exness đã nằm trong `pocketquant-config/vps/default/.env` và đã push: `EXNESS_API_BASE_URL=https://api.exness.com` (host "Main" trong Key Management), `EXNESS_ACCOUNT_ID`, `EXNESS_API_KEY` và `EXNESS_SECRET_KEY`.
- Secret Exness cấp là 128 hex: 32 byte seed Ed25519 rồi 32 byte public key. Lưu nguyên văn để thêm account mới chỉ cần copy-paste; `load_secret_key` kiểm tra nửa public có khớp không.
- Key không giới hạn IP (quyết định của user).
- Docs Exness: host giao dịch là riêng cho từng account, lấy qua `GET /v1/trading/access-point`, không có TTL.

## Decision
- Phase 01 T1.4: spike gọi access-point trước và ghi `access_point_resolved` cùng `ws_host`.
- Phase 06: cache host trong Redis `exness:access_point:<account_id>`, preload lúc khởi động. Job `exness_access_point_refresh` chạy mỗi giờ và log `exness.access_point_changed` khi host đổi. Khi lỗi kết nối hoặc 421 thì re-resolve một lần rồi thử lại.
- Configuration, market data và history vẫn gọi base URL cho tới khi spike chứng minh điều ngược lại.

## Next steps
- Build Phase 01 (spike script, tests, `.env` guard, `cryptography`). Deploy cần user duyệt. Chạy spike trong giờ thị trường FX (từ thứ Hai 01:00 UTC).

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
