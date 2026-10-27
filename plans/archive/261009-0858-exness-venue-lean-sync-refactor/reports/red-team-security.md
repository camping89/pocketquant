# Red team: Security Adversary (Fact Checker)

This review produced 8 findings: 3 Critical, 2 High and 3 Medium. The full reviewer text is in the controller transcript.

1. **Critical — Phase 07 T7.7, Phase 08 T8.7, Phase 06 T6.17.** Live-money trading can be reached from the anonymous public internet.
   - The subscription create, start, stop and delete routes have no auth (`app/routes/strategy.py:69,112,121,147`).
   - `verify_admin_token` is a no-op when the token is unset (`admin_auth_middleware.py:28-31`), and prod `.env` has no `ADMIN_TOKEN`.
   - `/api/` is proxied publicly (`web/nginx.conf:13-14`).
   - Fix: add auth on all mutation routes before T7.7, and add a U4 precondition that `ADMIN_TOKEN` is set. Fail closed in production, and restrict `broker=exness` to `:EXNESS` symbols.
2. **Critical — Phase 07 T7.3, Phase 06 T6.4, Phase 01 T1.6.** The daily loss cap reads `d["profit"]`, but the spec returns `items[].deal.profit`.
   - As written, the cap never fires.
   - The code also needs to follow pagination (`next_cursor`/`has_more`), and it currently counts deposit (`balance`) deals.
   - Fix: add a deals fixture to the spike and test against that recorded fixture.
3. **Critical — U2, Phase 01 T1.4.** A multi-line PEM in `.env` can leak into public GitHub Actions logs.
   - The masking step only handles single-line `k=v` values (`.github/actions/get-vps-config/action.yml`).
   - The deploy script runs `source .env` (`deploy/vps/10-deploy.sh:33`), and the repo is PUBLIC.
   - `EXNESS_PRIVATE_KEY_PATH` won't work because the `app` service has no volume (`deploy/compose.prod.yml:32-60`).
   - Fix: require a single-line base64url seed, drop `_PATH`, and add a pre-deploy guard.
4. **High — Phase 07 T7.3, T7.4.** Lost async fills create orphan live positions.
   - A timeout after Exness accepts the order goes through the reject path, and the later WS fill is dropped (`order_app_service.py` ~110-118, ~179-181).
   - Fix: retry with the same idempotency key, poll `GET /operations/{id}`, and reconcile against the snapshot. Refuse new orders while a position is unmapped.
5. **High — Phase 06 T6.4, T6.15, Phase 08 T8.4.** One token bucket is shared by unauthenticated bulk sync and live orders.
   - `/sync/bulk` has no auth and no cap on `symbols` (`market_data_sync.py:17,31,48`, `sync_dtos.py:44-48`).
   - The backfill script runs a separate bucket.
   - Fix: reserve budget for orders, retry 429s idempotently, cap bulk sync, and add auth.
6. **Medium — Phase 06 T6.10, T6.6.** An unknown instrument triggers a WS strike and 1008 close loop.
   - That loop drains the connection-rate budget the events stream also uses, so fills are lost.
   - Fix: validate subscriptions against `instruments()`.
7. **Medium — Phase 01 T1.6, T1.10, T1.12.** Spike fixtures commit live account state to a PUBLIC repo.
   - The secret scans only match the spec's example key prefix.
   - Fix: redact monetary and identity fields, and scan for the actual secret values without printing them.
8. **Medium — Phase 01 T1.3, Phase 06 T6.4.** `EXNESS_API_BASE_URL` is never validated.
   - `ws_url` is built with a plain string replace, so a bad value could send credentials in cleartext or off-box.
   - The `config.py:98` citation is wrong; `Settings` is at `:30`.
   - Fix: allowlist the https scheme and host.

Fact check: 13 claims verified. 3 failed: the `config.py:98` line, the deals shape, and the T6.17 admin-token claim.
