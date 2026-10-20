---
phase: 1
title: "Exness read-only spike"
status: completed
priority: P1
effort: 2d
dependencies: []
---

# Phase 01: Exness read-only spike

<!-- Updated: 2026-10-13 develop re-base - T1.1-T1.7 done on develop; resume at T1.8 -->
## Develop status
- The base branch is `develop` (worktree `D:/w/_me/algotrading/pocketquant`, local branch `develop-sync` tracking `origin/develop`). Every `master` in this file means `develop`; push with `git push origin develop-sync:develop`. Deploys to the VPS are approved.
- T1.1 is done: `reports/user-preconditions.md` holds U1 and U2 confirmed and host `api.exness.com`.
- T1.2–T1.5 and T1.7 are done: the spike script, its tests, `cryptography>=46` and the `.env` guard reached develop and prod in CI run 38362717425 (verdict HEALTHY). Evidence: `reports/integrate-develop-step1-ports.md`. On develop the spike checks candle alignment with `is_bar_aligned(..., Continuous24x7Calendar())` from `bar_builder_domain_service`.
- Start at T1.8. T1.6 is the gate for the T1.12 commit only.
- 2026-10-13: T1.9 failed on the access-point host check because the API returns `access_point` as a full https URL, not a bare host. `allowed_access_point` now accepts a bare host or a plain https URL and returns the host; the fix ships in a second deploy, then resume at T1.8.
- 2026-10-13: the second T1.9 run exited 3 with `HTTP_404` on `getLimits`. A read-only probe showed `api.exness.com` returns a bare 404 for every account route and the access point answers all of them, and that a deals window of exactly `history_age_days` (30) returns 400 `REQUEST_INVALID_TIME_RANGE` while 29 days returns 200. The spike now sends every call after discovery to the access point, spaces requests by the strictest published rate limit with 20% headroom, and reads the deals window from `limits`; the fix ships in a third deploy, then resume at T1.8.
- 2026-10-13: the third T1.9 run exited 3 with `REQUEST_RATE_LIMIT` on the second M1 candles request, at 0.6 s spacing under the published 2 per second. Three read-only replays of the same sequence returned 200 throughout and no response carried a rate-limit or `Retry-After` header, so the cause is unverified; the spec lists `REQUEST_RATE_LIMIT` on every operation and reports REST limits for the whole access-point cluster. The spike now retries a 429 at most 3 times with backoff and records `rate_limited_retries`; the fix ships in a fourth deploy, then resume at T1.8.
- 2026-10-13: phase complete. The fourth run exited 0 with one absorbed 429 (`rate_limited_retries: 1`). T1.8–T1.12 passed; the fixtures and the journal `docs/journals/2026-10-13-exness-api-spike.md` (`A-v feasible: yes`) are on develop as commit 20baa15, and CI run 38378550812 deployed HEALTHY. The phase took four deploys (spike fixes: access-point URL form, access-point routing, deals window, 429 retry) instead of one. The T1.12 file-scope Verify used `git show --stat`, which shortens long paths to `.../`; it now uses `--name-only`, which prints `0` for 20baa15.

## Context Links
- Advice: `D:/w/_me/algotrading/plans/reports/advise-261008-1148-exness-api-replacement.md` §2.1, §8, §9
- Interview state (A-i..A-v, API facts): `D:/w/_me/algotrading/plans/reports/advise-261008-1148-exness-api-replacement-state.md`
- Exness OpenAPI 1.0.2: `https://www.exness-api.com/exness_api.yaml`. Operation ids used here: `getLimits`, `getAccountDetails`, `getAvailableInstrumentList`, `getInstrumentCondition`, `getCandleHistory`, `getTradingStateSnapshot`, `getDealsHistory`. Deals come back as `{items: [{event_time, deal: {type, profit: {amount, currency}, ...}}], next_cursor, has_more}`. Sessions are `trade_sessions: [{trade_mode, week_start_time: "Mon, 00:00:00", week_end_time: "Fri, 23:59:59"}]` in UTC.
- CI secret path: `.github/actions/get-vps-config/action.yml:73-84` masks only single-line `k=v` values; `deploy/vps/10-deploy.sh:33` runs `source .env`; the `app` service in `deploy/compose.prod.yml:32-60` has no volume, so a key file path cannot work.
- Prod container: user `appuser` (`deploy/Dockerfile`), scripts ship in `/app/scripts` (`COPY scripts/ scripts/`), env from `deploy/.env` via `env_file`.
- Sizer: `src/pocketquant/core/domain/risk/services/position_sizer.py:58` caps size at `balance * max_exposure_percent / price`; the default is `0.10` (`src/pocketquant/core/domain/risk/value_objects.py:11`).

<!-- Updated: Validation Session 1 - spike stays in scripts/, no src/ change, one deploy only -->
## Goal
Settle assumptions A-i..A-v with real numbers and record redacted fixtures for the adapter tests. The spike lives entirely in `scripts/` until feasibility is known; nothing in `src/` changes and runtime behaviour is untouched. The signer is promoted into `src/` in Phase 06. The phase deploys exactly once (the spike runs in the prod container and the image needs `cryptography`); the fixtures and journal are committed and pushed to develop in T1.12.

## Files to Create or Modify
- Create: `scripts/exness_spike.py`, `tests/scripts/test_exness_spike.py`
- Create: `tests/core_test/infra/exness/fixtures/*.json` (no `__init__.py` needed for a data folder)
- Create: `docs/journals/<YYYY-MM-DD>-exness-api-spike.md`, using the execution date from `date -u +%Y-%m-%d`
- Create: `plans/261009-0858-exness-venue-lean-sync-refactor/reports/user-preconditions.md`
- Modify: `pyproject.toml` and `uv.lock` (add `cryptography`), `.github/actions/get-vps-config/action.yml` (pre-deploy `.env` guard)

## Tasks

<!-- Updated: Validation Session 1 - U2 rewritten: single-line seed, pushed to config master, API host recorded -->
<!-- Updated: Validation Session 3 - no IP allowlist in U2; skip the questions when the file is already complete -->
### T1.1 Record user preconditions U1 and U2
- **Goal:** The phase starts only after the user confirms the portal domain, the key format and where the key lives.
- **Target files and symbols:** `plans/261009-0858-exness-venue-lean-sync-refactor/reports/user-preconditions.md`
- **Steps:**
  0. If `plans/261009-0858-exness-venue-lean-sync-refactor/reports/user-preconditions.md` already holds `U1: confirmed`, `U2: confirmed` and a `U2 api host:` line, skip steps 1–3; the Verify still applies.
  1. Ask the user these questions verbatim.
     - (U1) "Does the Developer Portal link inside your Exness Personal Area open a page on exness-api.com?"
     - (U2) "Are EXNESS_API_BASE_URL, EXNESS_ACCOUNT_ID, EXNESS_API_KEY and EXNESS_SECRET_KEY stored in pocketquant-config/vps/default/.env, for a key scoped to one account, with EXNESS_SECRET_KEY written as the 128-hex secret exactly as Key Management shows it (no PEM block), and is that change committed and pushed to pocketquant-config master? Please also tell me the host name inside EXNESS_API_BASE_URL (host only, it is not secret)."
  2. Write the file with three lines: `U1: confirmed` or `U1: failed`; `U2: confirmed` or `U2: missing`; `U2 api host: <host>`. Never write any key, key id or account id.
  3. If U1 is `failed`, STOP and ask the user how to proceed. If U2 is `missing`, STOP and wait for the user.
- **Success criteria:** Both preconditions are confirmed and the API host is recorded.
- **Verify:** `grep -c "confirmed" plans/261009-0858-exness-venue-lean-sync-refactor/reports/user-preconditions.md` prints `2`. `grep -cE "^U2 api host: [A-Za-z0-9.-]+$" plans/261009-0858-exness-venue-lean-sync-refactor/reports/user-preconditions.md` prints `1`.

### T1.2 Branch and dependency
- **Goal:** Work happens on a branch, and `cryptography` is a direct dependency so the prod image can sign requests.
- **Target files and symbols:** `pyproject.toml` `[project].dependencies`, `uv.lock`
- **Steps:**
  1. `git switch master && git pull --ff-only && git switch -c feat/exness-spike`
  2. `uv add "cryptography>=46"`
- **Success criteria:** `cryptography>=46` is listed in `pyproject.toml` dependencies.
- **Verify:** `uv run python -c "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey; print('ok')"` exits 0 and prints `ok`.

<!-- Updated: Validation Session 1 - pre-deploy .env guard against multi-line secrets -->
### T1.3 Pre-deploy `.env` guard
- **Goal:** A deploy fails before any secret is masked or written when the config `.env` holds a PEM block or a line without `=`.
- **Target files and symbols:** `.github/actions/get-vps-config/action.yml`, step `Read + mask + emit outputs`
- **Steps:**
  1. Directly after the line `ENV_CONTENT=$(normalize "$VPS_DIR/.env")` and before the `while IFS='=' read -r k v; do` loop, insert (same 8-space indentation as the surrounding lines):
     ```bash
     if grep -q 'BEGIN' <<< "$ENV_CONTENT" || grep -vE '^[[:space:]]*(#|$)' <<< "$ENV_CONTENT" | grep -qv '='; then
       echo "::error::.env must contain only single-line KEY=VALUE entries"
       exit 1
     fi
     ```
  2. The error line never prints any part of the file.
- **Success criteria:** The guard trips on a PEM line or a bare continuation line and passes a normal `.env`.
- **Verify:**
  - `grep -c "single-line KEY=VALUE entries" .github/actions/get-vps-config/action.yml` prints `1`.
  - `ENV_CONTENT=$'A=1\n-----BEGIN PRIVATE KEY-----' bash -c 'grep -q BEGIN <<< "$ENV_CONTENT" || grep -vE "^[[:space:]]*(#|\$)" <<< "$ENV_CONTENT" | grep -qv "="; echo $?'` prints `0` (guard trips).
  - `ENV_CONTENT=$'A=1\nMIIEvQIBADAN' bash -c 'grep -q BEGIN <<< "$ENV_CONTENT" || grep -vE "^[[:space:]]*(#|\$)" <<< "$ENV_CONTENT" | grep -qv "="; echo $?'` prints `0` (guard trips).
  - `ENV_CONTENT=$'A=1\n# c\n\nB=x=y' bash -c 'grep -q BEGIN <<< "$ENV_CONTENT" || grep -vE "^[[:space:]]*(#|\$)" <<< "$ENV_CONTENT" | grep -qv "="; echo $?'` prints `1` (guard passes).

<!-- Updated: Validation Session 1 - self-contained spike: raw-seed only, URL allowlist, redaction, deals, sessions, subscribe mode, sizer line -->
### T1.4 Read-only spike script
- **Goal:** One self-contained script signs requests, measures limits, instruments, sessions, candles, deals and ticks, and writes redacted fixtures. It never mutates the account.
- **Target files and symbols:** `scripts/exness_spike.py` with `load_secret_key(material: str) -> Ed25519PrivateKey`, `body_hash(body: bytes) -> str`, `sign_headers(*, api_key, private_key, method, path_with_query, body, idempotency_key, timestamp_ms) -> dict[str, str]`, `class ServerClock` (`update_from_date_header(value)`, `now_ms()`), `validate_base_url(url: str, api_host: str) -> str`, `allowed_access_point(host: str) -> str`, `ws_url(base_url: str, path: str) -> str`, `redact(obj)`, `parse_args(argv)`, `async run(cfg) -> int`, `main(argv) -> int`.
- **Steps:**
  1. CLI: `--api-host HOST` (required), `--out PATH` (required unless `--check-config`), `--tick-seconds INT` (default 600), `--instruments` (default `XAUUSD,EURUSD,BTCUSD`), `--check-config`.
  2. Read `EXNESS_API_BASE_URL`, `EXNESS_ACCOUNT_ID`, `EXNESS_API_KEY` and `EXNESS_SECRET_KEY` from `os.environ`. Never print their values.
  3. `load_secret_key`: strip whitespace. If the text contains `BEGIN`, raise `ValueError("EXNESS_SECRET_KEY must be the 128-hex secret from Key Management, not PEM")`. Require `re.fullmatch(r"[0-9a-fA-F]{128}", text)`; `raw = bytes.fromhex(text)` is the 32-byte Ed25519 seed followed by its 32-byte public key. Build `key = Ed25519PrivateKey.from_private_bytes(raw[:32])` and require `key.public_key().public_bytes_raw() == raw[32:]`, then return `key`. Any other case raises `ValueError("unsupported Ed25519 key format")`. Messages never include the input.
  4. `body_hash`: `base64.urlsafe_b64encode(hashlib.sha256(body).digest()).rstrip(b"=").decode()`.
  5. `sign_headers`: build `payload = {"api_key", "idempotency_key", "timestamp", "sign_version": 1, "method": method.upper(), "path": path_with_query, "body_hash": body_hash(body)}`, serialize with `json.dumps(payload, separators=(",", ":")).encode()` as `data_bytes`, and return `EXN-API-KEY`, `EXN-IDEMPOTENCY-KEY` (empty string for GET), `EXN-TIMESTAMP` (str), `EXN-SIGN-VERSION="1"`, `EXN-DATA = b64url_nopad(data_bytes)` and `EXN-SIGN = b64url_nopad(private_key.sign(data_bytes))`.
  6. `ServerClock`: `offset_ms: int = 0`; `update_from_date_header` parses an RFC 7231 date with `email.utils.parsedate_to_datetime` and sets `offset_ms = server_ms - local_ms`; `now_ms()` returns `int(time.time()*1000) + offset_ms`.
  7. `validate_base_url`: `parts = urllib.parse.urlsplit(url)`. Require `parts.scheme == "https"`, `parts.hostname == api_host`, and no `username`, `password`, `query` or `fragment`; otherwise raise `ValueError("EXNESS_API_BASE_URL must be https on the confirmed host")`. Return `url.rstrip("/")`. `ws_url` returns `urlunsplit(("wss", parts.netloc, parts.path.rstrip("/") + path, "", ""))` from the validated URL. `allowed_access_point(value)` accepts a bare host or a plain `https://host[/]` URL (no port, userinfo, path, query or fragment; the live API returns the URL form), lowercases the host and requires `re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)*\.(exness\.com|exness-api\.com)", host)`, else raises `ValueError("access point host is not an Exness host")`; it is applied only to the discovered host, never to `EXNESS_API_BASE_URL`.
  8. `--check-config`: print exactly one line `base_url_valid=<bool> account_id_set=<bool> api_key_set=<bool> secret_key_valid=<bool> configured=<bool>` (each value `True` or `False`, computed with try/except around steps 3 and 7) and exit 0 when `configured=True`, else 4. Nothing else is printed.
  9. `redact(obj)`: walk dicts and lists recursively. For a key in `{"account_id","account_name","login","position_id","order_id","deal_id","operation_id","client_request_id"}` whose value is a scalar, write `"REDACTED"`. For a key in `{"balance","equity","used_margin","free_margin","margin_level","credit","amount","commission","swap"}` whose value is a scalar, write `"0.00"`. Every response is passed through `redact` before it is written, and the account id string is then replaced by `"0"` in the serialized text.
  10. Requests: signed GETs only, with `httpx.AsyncClient(base_url=<validated url>, timeout=15)`. Build the query with `urllib.parse.urlencode(params)`, request the literal `f"{path}?{query}"`, and sign the same string. Update the `ServerClock` from each `Date` header. Save:
      - `access_point.json` (`GET /v1/trading/access-point?account_id={id}` on the base URL, sent first). On 200, set `ap_base = "https://" + allowed_access_point(body["access_point"])` (the field is a full https URL; `allowed_access_point` strips the scheme); on 404 or any other non-auth error, set `ap_base = None` and continue (401/403 still exits 2). The access point is per account and resolved at runtime from `EXNESS_ACCOUNT_ID`; it is never stored in `.env`.
      - Every call below goes to `ap_base or base` (the base host answers only discovery; it returns a bare 404 for every account route). Requests are spaced by the strictest `rate_limit` in `limits` (global and per method) with 20% headroom. A 429 is retried at most 3 times with backoff (1, 2, 4 s), honouring a numeric `Retry-After`.
      - `limits.json` (`GET /v1/configuration/accounts/{id}/limits`)
      - `account.json` (`GET /v1/configuration/accounts/{id}/account`)
      - `instruments.json` (`GET /v1/configuration/accounts/{id}/instruments`)
      - For each requested code `I`: resolve `name = ` the first entry of `instruments` whose `upper()` equals `I` or starts with `I` (case-preserving), recorded as `instrument_names[I]` (null when none). Use `name` in every later call for `I`.
      - `conditions_<I>.json` (`GET .../instruments/<name>/conditions`)
      - `candles_<I>_M1.json` (`GET /v1/market-data/accounts/{id}/candles` with `instrument=<name>`, `timeframe=M1`, `price_type=bid`, `from=<now UTC ISO, seconds, +00:00>`, `count=-min(1000, max_candles_per_request)`)
      - `candles_XAUUSD_<TF>.json` for TF in M5, M15, H1, H4, D1 with `count=-10`
      - `snapshot.json` (`GET /v1/trading/accounts/{id}/snapshot`)
      - `deals.json` (`GET /v1/history/accounts/{id}/deals` with `from=<now minus (history_age_days - 1) days, ISO>` where `history_age_days` comes from `limits.rest.methods[api_operation_id=="getDealsHistory"].limits` (default 30; a window of exactly `history_age_days` is rejected), `limit=200`); follow `next_cursor` while `has_more` is true for at most 5 pages, save the first page, and collect `deal_types_seen` from every page.
  11. WS host: open each WS on `ap_base or base`; if the handshake fails there and `ap_base` is set, retry once on `base`, and record `ws_host` as `access_point` or `base`. TLS verification stays on.
      Ticks WS: open `ws_url(<ws host>, "/v1/server-events/accounts/{id}/ws/ticks")`, signing `sign_headers(method="GET", path_with_query=<that path>, body=b"", idempotency_key="")` as `additional_headers` with `subprotocols=["exness-ws-protocol"]`; if the handshake fails, retry once without subprotocols and record which attempt worked as `ws_subprotocol`.
      - Subscribe-mode probe: send `{"id":"spike-ticks-1","subscribe":{"event":"ticks","instruments":[<name of first code>]}}`, collect 20 s; send `{"id":"spike-ticks-2","subscribe":{"event":"ticks","instruments":[<name of second code>]}}`, collect 30 s. `ticks_subscribe_mode` is `add` if frames for the first instrument still arrive after the second message, else `replace`.
      - Send `{"id":"spike-ticks-all","subscribe":{"event":"ticks","instruments":[all names]}}`, collect for `--tick-seconds`, save the first 50 frames as `ticks_sample.json`, record any error frames as `ticks_errors`, then close.
  12. Events WS: open `/v1/server-events/accounts/{id}/ws/events` the same way, send `{"id":"spike-tx","subscribe":{"event":"transactions"}}`, save the first frame redacted as `events_snapshot.json`, close after 15 s.
  13. Write `summary.json` with: `fetched_at` (the UTC time in ISO seconds with `+00:00`, taken just before the first candles request); `access_point_resolved` (bool); `rest_host` (`access_point` or `base`); `history_age_days`; `ws_host`; `ws_subprotocol`; `ticks_subscribe_mode`; `max_candles_per_request` (from `limits.rest.methods[api_operation_id=="getCandleHistory"].limits.max_candles_per_request`); `rate_limits` (the `rate_limit` of every method in `limits.rest.methods`, keyed by `api_operation_id`, plus `global_account_rate` and `websocket`); `instrument_names`; `conditions` (`{I: {contract_size, volume_min, volume_step, volume_max, point_digits, trade_mode, trade_sessions}}`); `candles` (`{"<I>_<TF>": {count, first_time, last_time, all_aligned, last_in_progress}}`, `all_aligned` via `pocketquant.core.domain.bar.services.bar_builder.is_bar_aligned` with M1→1m, M5→5m, M15→15m, H1→1h, H4→4h, D1→1d); `ticks` (`{I: {count, median_spread, max_gap_seconds, first, last}}`); `ticks_errors`; `deal_types_seen`; `rate_limited_retries` (count of 429 retries); `account_currency` (`account.json` → `settings.currency`); `sizer_min_balance` (`{I: volume_min * contract_size * last M1 close / 0.10}`) and `sizer_reaches_min_lot` (`{I: snapshot account_state.balance >= sizer_min_balance[I]}`). The live balance itself is never written.
  14. Print `summary.json` only. Exit 0 on success, 2 on any 401/403, 3 on any other HTTP error (print the `error_message` field only, never request headers), 4 on missing or invalid settings.
  15. Keep every function ≤ 60 lines.
- **Success criteria:** The script is read-only, rejects PEM keys and foreign hosts, and writes only redacted data.
- **Verify:** no verification needed; T1.5 covers this module.

<!-- Updated: Validation Session 1 - spike tests cover raw-seed, PEM rejection, URL allowlist, redaction -->
### T1.5 Spike unit tests
- **Goal:** Pin the signer, key loading, URL validation and redaction with known answers.
- **Target files and symbols:** `tests/scripts/test_exness_spike.py` (imports `from scripts.exness_spike import ...`; `tests/scripts/conftest.py` already puts the repo root on `sys.path`)
- **Steps:**
  1. `body_hash(b"") == "47DEQpj8HBSa-_TImW-5JCeuQeRkm5NMpJWZG3hSuFU"` (the spec example).
  2. Generate a key with `Ed25519PrivateKey.generate()`, call `sign_headers(method="GET", path_with_query="/v1/configuration/accounts/1/account", body=b"", idempotency_key="", timestamp_ms=1773656070123, api_key="k")`. Assert `"="` is in neither `EXN-DATA` nor `EXN-SIGN`, decoded `EXN-DATA` equals the expected dict with `sign_version == 1` and `idempotency_key == ""`, and `public_key.verify(sig, decoded_data)` does not raise.
  3. With `seed = key.private_bytes_raw()` and `pub = key.public_key().public_bytes_raw()`, `load_secret_key((seed + pub).hex())` returns a key with the same public bytes. `load_secret_key((seed + bytes(32)).hex())` raises `ValueError` (public half does not match). `load_secret_key(<PEM PKCS8 text>)` raises `ValueError` whose message contains `not PEM` and does not contain `BEGIN`. `load_secret_key("not-a-key-SECRET")` raises `ValueError` and `"SECRET" not in str(exc)`.
  4. `validate_base_url("https://api.example.test", "api.example.test")` returns the URL; `http://api.example.test`, `https://evil.test`, `https://u:p@api.example.test` and `https://api.example.test/?x=1` each raise `ValueError`. `ws_url("https://api.example.test", "/v1/x")` returns `wss://api.example.test/v1/x`. `allowed_access_point("ap-x.trading.exness.com")` returns the host; `allowed_access_point("exness.com.evil.test")` and `allowed_access_point("evil.test")` each raise `ValueError`.
  5. `redact({"account_id": "9", "items": [{"deal": {"profit": {"amount": "-12.5", "currency": "USD"}, "deal_id": "7"}}]})` returns `account_id == "REDACTED"`, `amount == "0.00"`, `currency == "USD"`, `deal_id == "REDACTED"`.
  6. A `ServerClock` fed a Date header 5 s ahead of now has `offset_ms` between 4000 and 6000.
- **Success criteria:** All tests pass.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/scripts/test_exness_spike.py -q` exits 0 and the last line contains `passed` and no `failed`.

### T1.6 Phase gate
- **Goal:** The full quality gate is green before shipping.
- **Target files and symbols:** whole repo
- **Steps:**
  1. `docker info > /dev/null && echo docker-ok`
  2. `just test 2>&1 | tail -n 3`
  3. `uv run ruff check`
  4. `uv run pyright`
  5. `uv run lint-imports`
- **Success criteria:** All four tools are green.
- **Verify:**
  - Step 1 prints `docker-ok`.
  - Step 2 exits 0, and the output contains `passed` but not `failed` or ` error`.
  - Step 3 exits 0 and prints `All checks passed!`.
  - Step 4 exits 0, and the output contains `0 errors`.
  - Step 5 exits 0 and contains `Contracts: 8 kept, 0 broken.`.
  - On develop, steps 3 and 4 need 0 errors only in `src/` and in touched files; pre-existing test lint and type debt is accepted. Step 2 may show only the 4 known Windows `time.tzset` failures. `uv run python scripts/code_metrics.py --ratchet` exits 0.

<!-- Updated: Validation Session 1 - the only deploy of this phase; no src/ files staged -->
### T1.7 Ship the spike build
- **Goal:** The spike script, the `cryptography` dependency and the `.env` guard reach prod in one deploy.
- **Target files and symbols:** git `master`, CI `.github/workflows/cicd.yml`
- **Steps:**
  1. `git add pyproject.toml uv.lock scripts/exness_spike.py tests/scripts/test_exness_spike.py .github/actions/get-vps-config/action.yml`
  2. `git diff --cached | grep -ciE "BEGIN [A-Z ]*PRIVATE KEY|EXN-SIGN: [A-Za-z0-9_-]{20}"` must print `0`.
  3. `git commit -m "feat(exness): add read-only api spike script and single-line env guard"`
  4. Ask the user: "Approve merging feat/exness-spike into master and pushing? This deploys to production." Wait for a yes. If the user says no, STOP and report.
  5. `git switch master && git merge --ff-only feat/exness-spike && git push origin master`
  6. Repeat `gh run list --branch master --limit 1 --json databaseId,headSha -q '.[0]'` until `headSha` equals `git rev-parse HEAD` (at most 10 tries). Then run `gh run watch <databaseId> --exit-status`.
- **Success criteria:** The CI run for HEAD is green, including the guard, deploy and `11-verify.sh`.
- **Verify:** `gh run watch <databaseId> --exit-status` exits 0. `gh run view <databaseId> --log | grep "=== Verdict:" | grep -c ", 0 failures)"` prints a number ≥ 1.

<!-- Updated: Validation Session 1 - boolean-only config check after deploy -->
### T1.8 Boolean-only configuration check on the VPS
- **Goal:** Prove the deployed container sees a valid key and URL without printing any value.
- **Target files and symbols:** VPS container `pocketquant-app`, `scripts/exness_spike.py --check-config`
- **Steps:**
  1. From the repo root, set `KEY=../pocketquant-config/vps/default/id_rsa`, `HOST="$(cat ../pocketquant-config/vps/default/host)"` and `API_HOST=<the U2 api host from user-preconditions.md>`.
  2. `ssh -i "$KEY" "$HOST" "docker exec pocketquant-app python scripts/exness_spike.py --check-config --api-host $API_HOST" > .cache/exness-check.txt; echo $?` (create `.cache/` with `mkdir -p .cache` first; `.cache` is gitignored).
- **Success criteria:** The container reports `configured=True` and prints nothing but booleans.
- **Verify:** Step 2 ends with `0`. `grep -c "configured=True" .cache/exness-check.txt` prints `1`. `tr ' ' '\n' < .cache/exness-check.txt | grep -cvE '^[a-z_]+=(True|False)$'` prints `0`.

<!-- Updated: Validation Session 1 - repo-relative local paths, in-container secret scan with real values -->
### T1.9 Run the spike on the VPS and fetch outputs
- **Goal:** Real numbers and redacted fixtures, captured during FX market hours (Mon 01:00 to Fri 19:00 UTC).
- **Target files and symbols:** VPS container `pocketquant-app`, container dir `/home/appuser/exness-spike`, local dir `.cache/exness-spike`
- **Steps:**
  1. Reuse `KEY`, `HOST` and `API_HOST` from T1.8.
  2. Start the spike detached:
     ```bash
     ssh -i "$KEY" "$HOST" "docker exec -d pocketquant-app sh -c 'mkdir -p /home/appuser/exness-spike && python scripts/exness_spike.py --api-host $API_HOST --out /home/appuser/exness-spike --tick-seconds 600 > /home/appuser/exness-spike/stdout.txt 2>&1; echo \$? > /home/appuser/exness-spike/exit_code'"
     ```
  3. Every 2 minutes, at most 15 times, run `ssh -i "$KEY" "$HOST" "docker exec pocketquant-app cat /home/appuser/exness-spike/exit_code"` until it prints a number.
  4. Secret scan inside the container against the real values, printing only a count:
     ```bash
     ssh -i "$KEY" "$HOST" "docker exec pocketquant-app python -c \"import os,pathlib;v=[os.environ[k] for k in ('EXNESS_API_KEY','EXNESS_SECRET_KEY','EXNESS_ACCOUNT_ID') if os.environ.get(k)];print(sum(s in p.read_text(errors='ignore') for p in pathlib.Path('/home/appuser/exness-spike').iterdir() for s in v))\""
     ```
  5. `ssh -i "$KEY" "$HOST" "rm -rf ~/exness-spike && docker cp pocketquant-app:/home/appuser/exness-spike ~/exness-spike"`
  6. `rm -rf .cache/exness-spike && mkdir -p .cache && scp -r -i "$KEY" "$HOST:~/exness-spike" .cache/exness-spike`
  7. `ssh -i "$KEY" "$HOST" "rm -rf ~/exness-spike && docker exec pocketquant-app rm -rf /home/appuser/exness-spike"`
- **Success criteria:** `exit_code` is `0`, `summary.json` exists locally, and no secret value appears in the outputs.
- **Verify:**
  - `cat .cache/exness-spike/exit_code` prints `0`.
  - `test -f .cache/exness-spike/summary.json && echo ok` prints `ok`.
  - Step 4 prints `0`.
  - `grep -rlE "PRIVATE KEY|EXN-SIGN|BEGIN" .cache/exness-spike | wc -l` prints `0`.

<!-- Updated: Validation Session 1 - deals fixture added, monetary/identity redaction checked -->
### T1.10 Copy redacted fixtures
- **Goal:** Adapter tests in Phases 06 and 07 get recorded API shapes, including the deals envelope.
- **Target files and symbols:** `tests/core_test/infra/exness/fixtures/`
- **Steps:**
  1. `mkdir -p tests/core_test/infra/exness/fixtures`
  2. Copy from `.cache/exness-spike/`: `limits.json`, `account.json`, `instruments.json`, `conditions_*.json`, `candles_*.json`, `snapshot.json`, `deals.json`, `ticks_sample.json`, `events_snapshot.json`, `summary.json`.
- **Success criteria:** The fixtures exist and contain no account id, identity field, monetary value or secret.
- **Verify:**
  - `ls tests/core_test/infra/exness/fixtures/*.json | wc -l` prints a number ≥ 19.
  - `grep -rlE "PRIVATE KEY|EXN-SIGN" tests/core_test/infra/exness/fixtures | wc -l` prints `0`.
  - `grep -rhoE '"(account_id|position_id|deal_id|order_id|account_name)": *"[^"]*"' tests/core_test/infra/exness/fixtures | grep -vc '"REDACTED"'` prints `0`.
  - `grep -rhoE '"(balance|equity|used_margin|free_margin|amount)": *"[^"]*"' tests/core_test/infra/exness/fixtures | grep -vc '"0.00"'` prints `0`.

<!-- Updated: Validation Session 1 - instrument map recorded instead of stopping; sessions stop condition; sizer and subscribe-mode lines -->
<!-- Updated: Validation Session 3 - condition (f): empty or stale XAUUSD candles stop the spike -->
### T1.11 Spike journal and feasibility decision
- **Goal:** A-i..A-v are settled in writing, with stop-and-ask on infeasibility.
- **Target files and symbols:** `docs/journals/<YYYY-MM-DD>-exness-api-spike.md`
- **Steps:**
  1. Write the journal in English, matching develop's docs. Cover:
     - the WS subprotocol and `ticks_subscribe_mode` (add or replace);
     - `max_candles_per_request` and the rate limits per `api_operation_id`;
     - per instrument: the Exness instrument name, `contract_size`, `volume_min`, `volume_step`, `point_digits` and `trade_sessions` (including any daily break);
     - candle alignment per TF and whether the last candle is in progress;
     - tick count, median spread and max gap per instrument;
     - the deal types seen;
     - `rate_limited_retries` and whether the real limiter is tighter than the published limits;
     - the sizer feasibility per instrument (`sizer_min_balance`, `sizer_reaches_min_lot`). Live trading is off in this plan, so this line informs tests and docs only.
  2. Add one line per assumption, `A-i: confirmed|changed: <detail>`, for A-i through A-v.
  3. Evaluate these stop conditions in order. If any is true, write `A-v feasible: no`, STOP and ask the user, quoting the condition:
     - (a) any of XAUUSD, EURUSD or BTCUSD has `instrument_names[I] == null` (no instrument even with a case-preserving suffix such as `XAUUSDm`);
     - (b) any `candles.XAUUSD_<TF>.all_aligned=false`;
     - (c) the `getCandleHistory` rate limit, normalised to per minute, is below 30;
     - (d) `ticks.XAUUSD.count == 0`;
     - (e) `conditions.XAUUSD.trade_sessions` or `conditions.EURUSD.trade_sessions` is empty, or an entry lacks `week_start_time` or `week_end_time`, so a market calendar cannot be built;
     - (f) any `candles.XAUUSD_<TF>.count == 0`, or `candles.XAUUSD_M1.last_time` is not within the 24 hours up to `fetched_at` (a negative `count` read forward or returned stale data). Evaluate it with the command below; it prints `True` when (f) is clear and `False` when (f) is true:
       ```bash
       uv run python -c "import json,datetime as d;s=json.load(open('tests/core_test/infra/exness/fixtures/summary.json'));c=s['candles'];f=d.datetime.fromisoformat(s['fetched_at']);l=d.datetime.fromisoformat(c['XAUUSD_M1']['last_time']);print(all(v['count']>0 for k,v in c.items() if k.startswith('XAUUSD_')) and f-d.timedelta(hours=24)<=l<=f)"
       ```
  4. Otherwise write `A-v feasible: yes`, followed by exactly these lines: `access_point: resolved|unavailable`, `rest_host: access_point|base`, `ws_subprotocol: <value>`, `ticks_subscribe_mode: add|replace`, `instrument_names: XAUUSD=<name>, EURUSD=<name>, BTCUSD=<name>`, `sizer_feasibility: XAUUSD=<yes|no>, EURUSD=<yes|no>, BTCUSD=<yes|no>`.
- **Success criteria:** The journal makes an explicit feasibility decision and records the inputs Phase 06 needs.
- **Verify:** `grep -c "A-v feasible: yes" docs/journals/*-exness-api-spike.md` prints `1`. `grep -cE "^- ?A-(i|ii|iii|iv|v):" docs/journals/*-exness-api-spike.md` prints `5`. `grep -cE "^(access_point|rest_host|ws_subprotocol|ticks_subscribe_mode|instrument_names|sizer_feasibility): " docs/journals/*-exness-api-spike.md` prints `6`. The step 3 (f) command prints `True`.

<!-- Updated: 2026-10-13 develop re-base - commit on develop-sync and push to develop -->
### T1.12 Commit fixtures and journal and push to develop
- **Goal:** The evidence is versioned on develop. Phase 02 is already integrated, so this commit is pushed on its own.
- **Target files and symbols:** git `develop-sync` → `origin/develop`, CI `.github/workflows/cicd.yml`
- **Steps:**
  1. `git pull --ff-only`, then run the T1.6 gate.
  2. `git add tests/core_test/infra/exness/fixtures docs/journals`
  3. `git diff --cached | grep -ciE "BEGIN [A-Z ]*PRIVATE KEY|EXN-SIGN: [A-Za-z0-9_-]{20}"` must print `0`.
  4. `git commit -m "test(exness): record redacted read-only api fixtures and spike findings"`
  5. `git push origin develop-sync:develop`, then wait for the CI run whose `headSha` equals `git rev-parse HEAD` and run `gh run watch <databaseId> --exit-status`.
- **Success criteria:** The commit holds only fixtures and the journal, and its CI run is green with a HEALTHY deploy.
- **Verify:** `git show --name-only --format= HEAD | grep -vcE "^(tests/core_test/infra/exness/fixtures/|docs/journals/)"` prints `0`. `gh run watch <databaseId> --exit-status` exits 0. `gh run view <databaseId> --log | grep "=== Verdict:" | grep -c ", 0 failures)"` prints a number ≥ 1.

## Verification
T1.3 (guard), T1.5 (spike tests), T1.6 (gate), T1.8 (boolean config check), T1.9 (no secret values), T1.10 (redacted fixtures) and T1.11 (feasibility lines).

<!-- Updated: Validation Session 1 - stop-and-ask list for this phase -->
## Stop-and-ask
- U1 fails, or U2 is missing.
- Any T1.11 stop condition (a)–(e) is true (Exness limits or data make policy A-v infeasible).
- A test failure stays unexplained.
- Any step would place, modify or close an order, or would set `EXNESS_LIVE_TRADING=true`.

## Risks
- The key has no IP allowlist (user decision), so it works from any host and a leak is not contained by IP. Mitigation: the spike runs inside the prod container after one deploy, the key never leaves `pocketquant-config`, and nothing is printed or committed.
- A negative candles `count` may not read backward (the spec only says "bidirectional"). Mitigation: T1.11 condition (f) stops the spike when the XAUUSD candles are empty or not recent relative to `fetched_at`.
- Account endpoints answer only on the per-account access point (confirmed 2026-10-13: the base host returns a bare 404 for every account route). Mitigation: the spike resolves `/v1/trading/access-point` first, sends every later call there, and records `access_point_resolved`, `rest_host` and `ws_host` for Phase 06.
- The spike runs during FX closure and records zero ticks. Mitigation: run it Mon–Fri; the zero-tick case is stop condition (d).
- A multi-line key leaks into Actions logs (H impact). Mitigation: U2 requires a single-line 128-hex secret key, `load_secret_key` rejects PEM, and the T1.3 guard fails the deploy before masking.
- The account is new and `deals.json` holds no `close` deal. Mitigation: Phase 07 tests reuse the recorded envelope (`items`, `next_cursor`, `has_more`) and fill `deal` objects from the spec schema.

## Security
Key material is read only from the container env, which comes from `pocketquant-config`. It is never printed, logged or committed. `EXNESS_API_BASE_URL` must be https on the user-confirmed host. Every response is redacted before it is written, and the in-container scan checks the real secret values while printing only a count. The spike sends only GETs and WS subscriptions, never mutations.

## Rollback
`git revert` the spike merge commit and push. That redeploys without the spike; the `.env` guard can stay or be reverted with it. The unpushed fixture commit is dropped with `git reset --hard origin/master` on local `master` if the user abandons the plan. No data is written.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same
failure evidence to the user. Never continue by self-reasoning.
