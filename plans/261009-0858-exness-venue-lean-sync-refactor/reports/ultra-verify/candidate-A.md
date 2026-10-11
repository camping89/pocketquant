<!-- FILE: plan.md -->
---
title: "Exness venue behind existing ports + lean sync refactor"
description: "Refactor market-data sync into one SyncPolicy per provider plus one shared runner (Binance first, pinned by characterization tests), rewrite the coding standard, then add Exness data, quotes and broker and validate both strategies on it."
status: pending
priority: P1
effort: 6.5w
branch: master
tags: [exness, market-data, sync-policy, refactor, broker, standards]
blockedBy: []
blocks: []
created: 2026-10-09
---

# Exness venue + lean sync refactor

## Overview
The ports `IDataProvider`, `IRealtimeQuoteProvider`, `IBroker` and `IStrategy` stay the seams. The work runs in this order. First a read-only Exness spike runs. Then the sync pipeline is refactored with Binance as the proving provider and pinned by characterization tests, giving one `SyncPolicy` per provider and one shared runner. DI, routes and scalar Query/Command wrappers are collapsed, and `docs/code-standards.md` is rewritten. After that Exness becomes policy #2 and a third live venue (data, quotes, broker). Validation uses a PaperBroker `spread` parameter, backtests and a minimum-lot live round trip, and docs come last. Binance, OKX, PaperBroker, `hitnrun2` and `engulfing` all stay. MT5 is only documented. Nothing is built for MCP, and the deployment topology does not change.

## Goals
- G1: Exness is a live venue next to Binance/OKX. It uses the same strategies, risk checks and position tracking, and the SPA needs no change.
- G2: Adding a provider means one adapter package plus one `SyncPolicy`. Every sync flow can be read in ≤3 files.
- G3: The team follows a lean standard. Ruff, 3 import-linter contracts and a soft metric gate enforce it.

## Phases
| # | Phase | Effort | Status |
|---|-------|--------|--------|
| 01 | [Exness read-only spike and request signer](./phase-01-exness-read-only-spike.md) | 2d | Pending |
| 02 | [Characterization tests and metric baseline](./phase-02-characterization-and-metric-baseline.md) | 2d | Pending |
| 03 | [Sync policy and shared runner (Binance)](./phase-03-sync-policy-shared-runner.md) | 4d | Pending |
| 04 | [Collapse DI, routes and scalar wrappers](./phase-04-collapse-di-routes-wrappers.md) | 3d | Pending |
| 05 | [Lean coding standard and metric gate](./phase-05-lean-standard-and-metric-gate.md) | 2d | Pending |
| 06 | [Exness market data, quotes and policy](./phase-06-exness-market-data-and-policy.md) | 6d | Pending |
| 07 | [Exness broker and live order wiring](./phase-07-exness-broker-and-live-wiring.md) | 5d | Pending |
| 08 | [Validation: spread, backtests, live round trip](./phase-08-validation-spread-backtests-live.md) | 7d + weekend | Pending |
| 09 | [Architecture, deployment and MT5 docs](./phase-09-docs-architecture-deployment-mt5.md) | 1d | Pending |

## Dependencies
- The phases run strictly in order, 01 → 09. No two phases run in parallel, so no file has two concurrent owners.
- Phase 01 waits on U1 and U2. Phase 07 needs U3 config. The live step in Phase 08 needs U3 plus the user's explicit go-ahead.
- Each phase works on its own branch. A push to `master` deploys to prod through `.github/workflows/cicd.yml`, so every merge-and-push needs the user's approval.

## Success criteria (D1–D7)
- D1: `POST /api/v1/market-data/sync` with `{"symbol":"XAUUSD:EXNESS","interval":"1m","n_bars":1000,"source":"rest_backfill"}` returns `total_bars >= 1000`. The SSE bars stream for `XAUUSD%3AEXNESS` emits `"is_in_progress": true` within 60 s during market hours, and the quote stream emits `"bid"`.
- D2: One minimum-lot live Exness order per strategy, with SL attached, logs `exness.order_filled` with `ack_to_fill_ms <= 10000`. The position appears in `GET /api/v1/trading/positions` and in the SPA.
- D3: `hitnrun2` and `engulfing` backtests on Exness bars reach `finished` in `backtest_runs`, with a non-empty trades list. `PaperBroker` has a `spread` parameter.
- D4: `engine/market_data/sync_internals/` is gone. `app/di` has 3 provider modules, and market-data routes live in 2 files. `scripts/code_metrics.py` reports tiny share ≤ 0.30 and delegations ≤ 20, or whatever values the user decides at the Phase 05 gate.
- D5: `docs/code-standards.md` is rewritten with no stale status claims, and `uv run lint-imports` prints `Contracts: 3 kept, 0 broken.`.
- D6: Binance, OKX and PaperBroker tests keep the same pass count as the Phase 02 baseline. `just test`, ruff, pyright and lint-imports are green, and the CI deploy is green (`11-verify.sh` 19 checks).
- D7: `docs/system-architecture.md` shows the Exness adapters, the sync-policy pattern and MT5 as a future provider.
- After one live week: no circuit-breaker trips (`exness_ws.circuit_breaker_open` count 0), and no `integrity.issues_found` for FX Exness symbols across the weekend close.

## Test matrix
| Level | Covers | Where |
|---|---|---|
| Unit | signer, mappers, lot math, calendar, policy, router, metric script, broker state machine | `tests/core_test/infra/exness/`, `tests/engine_test/market_data/`, `tests/scripts/` |
| Characterization | sync jobs, cascade, DI graph, OKX WS mapping, OpenAPI + route snapshots | `tests/app_test/integration/`, `tests/core_test/infra/brokers/`, `tests/baseline/` |
| Integration | runner on real Mongo/Redis (testcontainers), async fill wiring | `tests/app_test/integration/`, `tests/engine_test/` |
| End-to-end | prod sync/SSE, backtests, min-lot live round trip, weekend watch | Phases 06 and 08 (VPS) |

## User preconditions (the plan gates on these and never performs them)
- U1: The Developer Portal link inside the Exness Personal Area resolves to `exness-api.com`.
- U2: A scoped API key exists (one account, VPS IP allowlist). `EXNESS_API_BASE_URL`, `EXNESS_ACCOUNT_ID`, `EXNESS_API_KEY` and `EXNESS_PRIVATE_KEY` (or `EXNESS_PRIVATE_KEY_PATH`) are stored in `pocketquant-config/vps/default/.env`.
- U3: The user sets the live risk cap. `EXNESS_DAILY_LOSS_CAP` goes in `pocketquant-config`. `EXNESS_MAX_LOTS` stays unset, which means the instrument minimum lot. SL is always attached and is enforced in code.
- Stop and ask the user if any of these happens: a live order would exceed the minimum lot or run without SL; a change would delete Binance or OKX code; the deployment topology would change; Exness limits make the A-v policy infeasible; a test failure stays unexplained; U1 fails.

<!-- FILE: phase-01-exness-read-only-spike.md -->
---
phase: 1
title: "Exness read-only spike and request signer"
status: pending
priority: P1
effort: 2d
dependencies: []
---

# Phase 01: Exness read-only spike and request signer

## Context Links
- Advice: `D:/w/_me/algotrading/plans/reports/advise-261008-1148-exness-api-replacement.md` §2.1, §8, §9
- Interview state (A-i..A-v, API facts): `D:/w/_me/algotrading/plans/reports/advise-261008-1148-exness-api-replacement-state.md`
- Exness OpenAPI 1.0.2: `https://www.exness-api.com/exness_api.yaml`. Paths verified: `/v1/configuration/accounts/{account_id}/limits|account|instruments|instruments/{instrument}/conditions`, `/v1/market-data/accounts/{account_id}/candles`, `/v1/trading/accounts/{account_id}/snapshot`, `/v1/server-events/accounts/{account_id}/ws/ticks|ws/events`
- Settings class: `src/pocketquant/core/config.py:98` (`Settings`)
- Prod run pattern for scripts: `docs/deployment.md` → "2-Year Bar Re-Sync" (scripts ship in image `/app/scripts`, `deploy/Dockerfile` `COPY scripts/ scripts/`)

## Goal
Settle assumptions A-i..A-v with real numbers and record fixtures for adapter tests. The phase makes no change to existing runtime behaviour. The Ed25519 signer is written once, here, and reused by every later Exness module (DRY).

## Files to Create or Modify
- Create: `src/pocketquant/core/infra/exness/__init__.py`, `src/pocketquant/core/infra/exness/signer.py`
- Create: `scripts/exness_spike.py`
- Create: `tests/core_test/infra/exness/__init__.py`, `tests/core_test/infra/exness/test_signer.py`, `tests/core_test/infra/exness/fixtures/*.json`
- Create: `docs/journals/<YYYY-MM-DD>-exness-api-spike.md`, using the execution date from `date -u +%Y-%m-%d`
- Create: `plans/261009-0858-exness-venue-lean-sync-refactor/reports/user-preconditions.md`
- Modify: `pyproject.toml` and `uv.lock` (add `cryptography`), `src/pocketquant/core/config.py` (Exness settings)

## Tasks

### T1.1 Record user preconditions U1 and U2
- **Goal:** The phase starts only after the user confirms the portal domain and the key storage.
- **Target files and symbols:** `plans/261009-0858-exness-venue-lean-sync-refactor/reports/user-preconditions.md`
- **Steps:**
  1. Ask the user these two questions verbatim. (U1) "Does the Developer Portal link inside your Exness Personal Area open a page on exness-api.com?" (U2) "Are EXNESS_API_BASE_URL, EXNESS_ACCOUNT_ID, EXNESS_API_KEY and EXNESS_PRIVATE_KEY (or EXNESS_PRIVATE_KEY_PATH) stored in pocketquant-config/vps/default/.env, for a key scoped to one account with the VPS IP allowlisted?"
  2. Write the file with two lines, `U1: confirmed` or `U1: failed`, and `U2: confirmed` or `U2: missing`. Never write any key value.
  3. If U1 is `failed`, STOP and ask the user how to proceed (stop-and-ask condition). If U2 is `missing`, STOP and wait for the user.
- **Success criteria:** The file shows both preconditions confirmed.
- **Verify:** `grep -c "confirmed" plans/261009-0858-exness-venue-lean-sync-refactor/reports/user-preconditions.md` prints `2`.

### T1.2 Branch and dependency
- **Goal:** Work happens on a branch, and `cryptography` is a direct dependency.
- **Target files and symbols:** `pyproject.toml` `[project].dependencies`, `uv.lock`
- **Steps:**
  1. `git switch master && git pull --ff-only && git switch -c feat/exness-spike`
  2. `uv add "cryptography>=46"`
- **Success criteria:** `cryptography>=46` is listed in `pyproject.toml` dependencies.
- **Verify:** `uv run python -c "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey; print('ok')"` exits 0 and prints `ok`.

### T1.3 Exness settings fields
- **Goal:** The Settings class can carry Exness configuration. Every field is optional, so existing environments keep booting.
- **Target files and symbols:** `src/pocketquant/core/config.py` → `Settings`
- **Steps:**
  1. Below the OKX block (`okx_demo_mode`), add `exness_api_base_url: str | None = None`, `exness_account_id: str | None = None`, `exness_api_key: SecretStr | None = None`, `exness_private_key: SecretStr | None = None`, `exness_private_key_path: str | None = None`.
- **Success criteria:** The Settings class loads unchanged when no `EXNESS_*` variable is set.
- **Verify:** `uv run python -c "from pocketquant.core.config import Settings; s=Settings(_env_file=None, app_name='a', app_version='1', environment='development', mongodb_url='mongodb://localhost:27017', mongodb_database='x', mongodb_min_pool_size=1, mongodb_max_pool_size=2, redis_url='redis://localhost:6379/0', redis_cache_ttl=1, log_level='INFO', log_format='json'); print(s.exness_api_key is None)"` prints `True`.

### T1.4 Ed25519 request signer
- **Goal:** One module produces the `EXN-*` headers exactly as the spec describes.
- **Target files and symbols:** `src/pocketquant/core/infra/exness/signer.py`. It holds `load_private_key(material: str) -> Ed25519PrivateKey`, `body_hash(body: bytes) -> str`, `sign_headers(*, api_key: str, private_key: Ed25519PrivateKey, method: str, path_with_query: str, body: bytes, idempotency_key: str, timestamp_ms: int) -> dict[str, str]`, and `class ServerClock` with `update_from_date_header(value: str) -> None` and `now_ms() -> int`.
- **Steps:**
  1. Create an empty `src/pocketquant/core/infra/exness/__init__.py`.
  2. `load_private_key`: if `material.strip()` starts with `-----BEGIN`, use `serialization.load_pem_private_key(material.encode(), password=None)` and require the result to be an `Ed25519PrivateKey`. Otherwise strip whitespace, add `=` padding to a multiple of 4, and decode with `base64.urlsafe_b64decode`. If the result is not 32 bytes, decode the original with `base64.b64decode` instead. Accept the result only when it is exactly 32 bytes, then call `Ed25519PrivateKey.from_private_bytes`. In every other case raise `ValueError("unsupported Ed25519 key format")`. The message must never include the input.
  3. `body_hash`: return `base64.urlsafe_b64encode(hashlib.sha256(body).digest()).rstrip(b"=").decode()`.
  4. `sign_headers`: build `payload = {"api_key", "idempotency_key", "timestamp", "sign_version": 1, "method": method.upper(), "path": path_with_query, "body_hash": body_hash(body)}`. Serialize it with `json.dumps(payload, separators=(",", ":")).encode()`, which gives `data_bytes`. Compute `EXN-DATA = b64url_nopad(data_bytes)` and `EXN-SIGN = b64url_nopad(private_key.sign(data_bytes))`. Return the headers `EXN-API-KEY`, `EXN-IDEMPOTENCY-KEY` (an empty string for GET), `EXN-TIMESTAMP` (as a str), `EXN-SIGN-VERSION="1"`, `EXN-DATA` and `EXN-SIGN`.
  5. `ServerClock`: store `offset_ms: int = 0`. `update_from_date_header` parses an RFC 7231 date with `email.utils.parsedate_to_datetime` and sets `offset_ms = server_ms - local_ms`. `now_ms()` returns `int(time.time()*1000) + offset_ms`.
- **Success criteria:** The headers match the spec's signed GET and POST examples in structure.
- **Verify:** no verification needed; T1.5 covers this module.

### T1.5 Signer tests
- **Goal:** Pin signer behaviour with known answers.
- **Target files and symbols:** `tests/core_test/infra/exness/__init__.py` (empty), `tests/core_test/infra/exness/test_signer.py`
- **Steps:**
  1. Test `body_hash(b"") == "47DEQpj8HBSa-_TImW-5JCeuQeRkm5NMpJWZG3hSuFU"`. This is the spec's example value.
  2. Generate a key with `Ed25519PrivateKey.generate()` and call `sign_headers(method="GET", path_with_query="/v1/configuration/accounts/1/account", body=b"", idempotency_key="", timestamp_ms=1773656070123, api_key="k")`. Assert that `"=" not in` `EXN-DATA` or `EXN-SIGN`, and that decoding `EXN-DATA` yields JSON equal to the expected dict with `sign_version == 1` and `idempotency_key == ""`. Assert that `public_key.verify(sig, decoded_data)` does not raise.
  3. Assert that `load_private_key` accepts a PEM string (from `private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())`) and the base64url raw 32-byte seed, and returns keys with equal public bytes. Assert that `load_private_key("not-a-key-SECRET")` raises `ValueError` and that `"SECRET" not in str(exc)`.
  4. Assert that `ServerClock.update_from_date_header` with a Date header 5 s ahead of now sets `offset_ms` between 4000 and 6000.
- **Success criteria:** All tests pass.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_signer.py -q` exits 0 and the last line contains `passed` and no `failed`.

### T1.6 Read-only spike script
- **Goal:** One script measures limits, instruments, candles and ticks, and saves scrubbed fixtures. It never mutates the account.
- **Target files and symbols:** `scripts/exness_spike.py` with `parse_args(argv)`, `async run(cfg) -> int`, `main(argv) -> int`
- **Steps:**
  1. CLI: `--out PATH` (required), `--tick-seconds INT` (default 600), `--instruments` (default `XAUUSD,EURUSD,BTCUSD`).
  2. Load `get_settings()`. If `exness_api_base_url`, `exness_account_id` or `exness_api_key` is missing, or both `exness_private_key` and `exness_private_key_path` are missing, print `missing setting: <field name>` and return 4. Load the key material from the SecretStr or from the file path and pass it to `load_private_key`. Never print it.
  3. Send only signed GETs, with `httpx.AsyncClient(base_url=settings.exness_api_base_url, timeout=15)`. Build the query with `urllib.parse.urlencode(params)`, request the literal `f"{path}?{query}"`, and sign the exact same string. Update the `ServerClock` from each response's `Date` header. Save each body to `--out`, after replacing the account id string everywhere in the text with `"0"`:
     - `limits.json` from `GET /v1/configuration/accounts/{id}/limits`
     - `account.json` from `GET /v1/configuration/accounts/{id}/account`
     - `instruments.json` from `GET /v1/configuration/accounts/{id}/instruments`
     - `conditions_<I>.json` for each instrument from `GET /v1/configuration/accounts/{id}/instruments/<I>/conditions`
     - `candles_<I>_M1.json` for each instrument from `GET /v1/market-data/accounts/{id}/candles` with `instrument=<I>`, `timeframe=M1`, `price_type=bid`, `from=<now UTC ISO, seconds precision, +00:00>`, `count=-min(1000, max_candles_per_request)`
     - `candles_XAUUSD_<TF>.json` for TF in M5, M15, H1, H4, D1 with `count=-10`
     - `snapshot.json` from `GET /v1/trading/accounts/{id}/snapshot`
  4. Ticks WS: open `wss://<host of base_url>/v1/server-events/accounts/{id}/ws/ticks`, using `sign_headers(method="GET", path_with_query=<that path>, body=b"", idempotency_key="")` as `additional_headers` and `subprotocols=["exness-ws-protocol"]`. If the handshake fails, retry once without subprotocols and record which attempt worked. Send `{"id":"spike-ticks","subscribe":{"event":"ticks","instruments":[...]}}`. Collect frames for `--tick-seconds`, save the first 50 as `ticks_sample.json`, then close.
  5. Events WS: open `/v1/server-events/accounts/{id}/ws/events` the same way and send `{"id":"spike-tx","subscribe":{"event":"transactions"}}`. Save the first frame as `events_snapshot.json`, then close after 15 s.
  6. Write `summary.json` with these keys:
     - `key_format`: `pem` or `raw`
     - `ws_subprotocol`: `exness-ws-protocol` or `none`
     - `max_candles_per_request`: from `limits.rest.methods[api_operation_id=="getCandleHistory"].limits.max_candles_per_request`
     - `rate_limits`: the `rate_limit` of `getCandleHistory`, `openPosition`, `closePosition`, `getTradingStateSnapshot` and `getDealsHistory`, plus `global_account_rate` and `websocket`
     - `instruments_found`: `{I: bool}`
     - `conditions`: `{I: {contract_size, volume_min, volume_step, volume_max, point_digits, trade_mode, trade_sessions}}`
     - `candles`: `{"<I>_<TF>": {count, first_time, last_time, all_aligned, last_in_progress}}`. Compute `all_aligned` with `pocketquant.core.domain.bar.services.bar_builder.is_bar_aligned`, mapping M1→1m, M5→5m, M15→15m, H1→1h, H4→4h, D1→1d. `last_in_progress` is true when the last open time plus the timeframe is later than now.
     - `ticks`: `{I: {count, median_spread, max_gap_seconds, first, last}}`
     - `account_currency`
  7. Print `summary.json` only. Exit 0 on success, 2 on any 401/403, 3 on any other HTTP error, after printing the error `code` but never the request headers.
  8. Keep every function ≤ 60 lines.
- **Success criteria:** The script runs read-only and its output contains no secrets.
- **Verify:** `uv run python scripts/exness_spike.py --help` exits 0. `uv run ruff check scripts/exness_spike.py` exits 0 and prints `All checks passed!`.

### T1.7 Phase gate
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
  - Step 5 exits 0 and contains `Contracts: 7 kept, 0 broken.`.

### T1.8 Ship the spike build
- **Goal:** The signer and the spike script reach the prod image, because the key is IP-allowlisted to the VPS.
- **Target files and symbols:** git `master`, CI `cicd.yml`
- **Steps:**
  1. Stage the files with `git add pyproject.toml uv.lock src/pocketquant/core/config.py src/pocketquant/core/infra/exness scripts/exness_spike.py tests/core_test/infra/exness`.
  2. `git diff --cached | grep -ciE "exnsk-|BEGIN [A-Z ]*PRIVATE KEY"` must print `0`.
  3. Commit with `git commit -m "feat(exness): add ed25519 request signer and read-only api spike script"`.
  4. Ask the user: "Approve merging feat/exness-spike into master and pushing? This deploys to production." Wait for a yes. If the user says no, STOP and report.
  5. `git switch master && git merge --ff-only feat/exness-spike && git push origin master`
  6. Repeat `gh run list --branch master --limit 1 --json databaseId,headSha -q '.[0]'` until `headSha` equals `git rev-parse HEAD` (at most 10 tries). Then run `gh run watch <databaseId> --exit-status`.
- **Success criteria:** The CI run for HEAD is green, which includes deploy and `11-verify.sh`.
- **Verify:** `gh run watch <databaseId> --exit-status` exits 0.

### T1.9 Run the spike on the VPS and fetch outputs
- **Goal:** Real numbers and fixtures, captured during FX market hours (Mon 01:00 to Fri 19:00 UTC).
- **Target files and symbols:** VPS container `pocketquant-app`, `/tmp/exness-spike`
- **Steps:**
  1. From the repo root, set `KEY=../pocketquant-config/vps/default/id_rsa` and `HOST="$(cat ../pocketquant-config/vps/default/host)"`.
  2. Start the spike detached:
     ```bash
     ssh -i "$KEY" "$HOST" "docker exec -d pocketquant-app sh -c 'mkdir -p /tmp/exness-spike && python scripts/exness_spike.py --out /tmp/exness-spike --tick-seconds 600 > /tmp/exness-spike/stdout.txt 2>&1; echo \$? > /tmp/exness-spike/exit_code'"
     ```
  3. Every 2 minutes, at most 15 times, run `ssh -i "$KEY" "$HOST" "docker exec pocketquant-app cat /tmp/exness-spike/exit_code"` until it prints a number.
  4. `ssh -i "$KEY" "$HOST" "rm -rf /tmp/exness-spike && docker cp pocketquant-app:/tmp/exness-spike /tmp/exness-spike"`
  5. `rm -rf /tmp/exness-spike && scp -r -i "$KEY" "$HOST:/tmp/exness-spike" /tmp/exness-spike`
  6. `ssh -i "$KEY" "$HOST" "rm -rf /tmp/exness-spike && docker exec pocketquant-app rm -rf /tmp/exness-spike"`
- **Success criteria:** `exit_code` is `0`, `summary.json` exists locally, and nothing secret appears in the outputs.
- **Verify:**
  - `cat /tmp/exness-spike/exit_code` prints `0`.
  - `test -f /tmp/exness-spike/summary.json && echo ok` prints `ok`.
  - `grep -rciE "exnsk-|PRIVATE KEY|EXN-SIGN" /tmp/exness-spike | grep -v ":0$" | wc -l` prints `0`.

### T1.10 Commit scrubbed fixtures
- **Goal:** Adapter tests in Phases 06 and 07 get recorded API shapes to test against.
- **Target files and symbols:** `tests/core_test/infra/exness/fixtures/`
- **Steps:**
  1. `mkdir -p tests/core_test/infra/exness/fixtures`
  2. Copy these files from `/tmp/exness-spike/`: `limits.json`, `account.json`, `instruments.json`, `conditions_*.json`, `candles_*.json`, `snapshot.json`, `ticks_sample.json`, `events_snapshot.json`, `summary.json`.
- **Success criteria:** The fixtures exist and contain no account id or secrets.
- **Verify:**
  - `ls tests/core_test/infra/exness/fixtures/*.json | wc -l` prints a number ≥ 12.
  - `grep -rlE "exnsk-|PRIVATE KEY" tests/core_test/infra/exness/fixtures | wc -l` prints `0`.
  - `grep -rhoE '"account_id": *"[1-9][0-9]*"' tests/core_test/infra/exness/fixtures | wc -l` prints `0`.

### T1.11 Spike journal and feasibility decision
- **Goal:** A-i..A-v are settled in writing, with stop-and-ask on infeasibility.
- **Target files and symbols:** `docs/journals/<YYYY-MM-DD>-exness-api-spike.md`
- **Steps:**
  1. Write the journal in Vietnamese prose, keeping English technical terms. Cover:
     - the key format and the WS subprotocol;
     - `max_candles_per_request` and the rate limits for the listed operations;
     - per instrument: `contract_size`, `volume_min`, `volume_step`, `point_digits` and `trade_sessions`;
     - candle alignment per TF;
     - whether the last candle is in progress;
     - tick count, median spread and max gap per instrument;
     - whether `BTCUSD` trade_sessions include Saturday and Sunday.
  2. Add one line per assumption, in the form `A-i: confirmed|changed: <detail>`, for A-i through A-v.
  3. Evaluate these stop conditions in order. If any is true, write `A-v feasible: no`, STOP and ask the user, quoting the condition:
     - (a) any of XAUUSD, EURUSD or BTCUSD has `instruments_found=false`;
     - (b) any `candles.XAUUSD_<TF>.all_aligned=false`;
     - (c) the `getCandleHistory` rate limit, normalised to per minute, is below 30;
     - (d) `ticks.XAUUSD.count == 0`.
  4. Otherwise write `A-v feasible: yes`, followed by `rate_budget_per_minute: <getCandleHistory per-minute limit>`, `BTCUSD calendar: always_open|fx_weekend` (fx_weekend when the sessions lack Saturday or Sunday) and `ws_subprotocol: <value>`.
- **Success criteria:** The journal makes an explicit feasibility decision.
- **Verify:** `grep -c "A-v feasible: yes" docs/journals/*-exness-api-spike.md` prints `1`. `grep -cE "^- ?A-(i|ii|iii|iv|v):" docs/journals/*-exness-api-spike.md` prints `5`.

### T1.12 Ship fixtures and journal
- **Goal:** The evidence is versioned.
- **Target files and symbols:** git
- **Steps:**
  1. `git switch -c test/exness-fixtures`
  2. `git add tests/core_test/infra/exness/fixtures docs/journals`
  3. `git commit -m "test(exness): record read-only api fixtures and spike findings"`
  4. Ask the user for approval, then `git switch master && git merge --ff-only test/exness-fixtures && git push origin master`.
  5. Watch the CI as in T1.8 step 6.
- **Success criteria:** The fixtures are on `master` and CI is green.
- **Verify:** `gh run watch <databaseId> --exit-status` exits 0.

## Verification
T1.5 (signer tests), T1.7 (gate), T1.9 (no secrets), T1.10 (scrubbed fixtures) and T1.11 (feasibility line).

## Risks
- The key is IP-allowlisted to the VPS, so a local spike would fail. Mitigation: the spike runs inside the prod container.
- The spike runs during FX closure and records zero ticks. Mitigation: run it Mon–Fri, and the zero-tick case is stop condition (d).
- The access point differs from `EXNESS_API_BASE_URL` [UNVERIFIED: spec v1.0.2 declares only `servers: url: /`]. Mitigation: a failing `/limits` call exits 3 and triggers the Failure Protocol.

## Security
Key material is read only from Settings, which comes from `pocketquant-config`. It is never printed, logged or committed. Fixtures are scrubbed of the account id. The spike sends only GETs and WS subscriptions, never mutations.

## Rollback
Run `git revert` on the two merge commits and push. That redeploys without the spike, and the new Settings fields are optional. No data is written.

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

<!-- FILE: phase-02-characterization-and-metric-baseline.md -->
---
phase: 2
title: "Characterization tests and metric baseline"
status: pending
priority: P1
effort: 2d
dependencies: [1]
---

# Phase 02: Characterization tests and metric baseline

## Context Links
- Sync jobs: `src/pocketquant/engine/market_data/app_services/sync_jobs.py`. Symbols: `SYNC_INTERVALS` (:54), `CATCHUP_TARGETS` (:72), `_sync_by_intervals` (:130), `sync_1m` (:382), `sync_verify_cascade` (:511), `sync_backfill` (:609), `register_sync_jobs` (:663).
- Integrity: `src/pocketquant/engine/market_data/app_services/integrity_jobs.py` (`check_integrity` :33, `repair_integrity` :76). Cascade: `src/pocketquant/engine/market_data/app_services/cascade_aggregator.py` (`cascade_for_symbol` :140).
- DI: `src/pocketquant/app/di/*.py` (11 files). Test container builder: `tests/app_test/integration/app_factory.py` (`TestCoreProvider` :46, `make_test_app` :66).
- OKX WS handling: `src/pocketquant/core/infra/brokers/okx/okx_broker.py` (`_handle_ws_message` :335, `_handle_order_update` :349). Mapper: `.../okx/websocket/okx_order_mapper.py:25`.
- Existing snapshots: `tests/baseline/test_openapi_snapshot.py` and `tests/baseline/test_route_inventory.py`.

## Goal
Pin today's observable behaviour before any refactor: the sync jobs, the cascade output, the DI graph, OKX WS order mapping and the API surface (snapshots). Record the baseline gate and the metric numbers. No production code changes in this phase.

## Files to Create or Modify
- Create: `scripts/code_metrics.py`, `tests/scripts/test_code_metrics.py`
- Create: `tests/app_test/integration/test_sync_pipeline_characterization.py`, `tests/app_test/integration/test_di_resolution_characterization.py`, `tests/core_test/infra/brokers/test_okx_ws_order_flow_characterization.py`
- Modify: `tests/app_test/integration/app_factory.py` (add `build_test_container`)
- Create: `plans/261009-0858-exness-venue-lean-sync-refactor/reports/baseline-gate.txt`, `.../reports/metrics-baseline.json`

## Tasks

### T2.1 Branch and baseline gate record
- **Goal:** A recorded green baseline, so any later failure can be attributed.
- **Target files and symbols:** `plans/261009-0858-exness-venue-lean-sync-refactor/reports/baseline-gate.txt`
- **Steps:**
  1. `git switch master && git pull --ff-only && git switch -c test/sync-characterization`
  2. `docker info > /dev/null && echo docker-ok`
  3. `just test 2>&1 | tail -n 1`. Write it to the file as `full: <line>`.
  4. `uv run ruff check | tail -n 1`, `uv run pyright | tail -n 1` and `uv run lint-imports | grep Contracts`. Write each line as `ruff: `, `pyright: ` and `lint-imports: `.
- **Success criteria:** The baseline is green. If it is not, this is an unexplained failure, so STOP.
- **Verify:** `grep -c "passed" .../reports/baseline-gate.txt` ≥ 1. `grep -c "failed" .../reports/baseline-gate.txt` prints `0`. `grep -c "Contracts: 7 kept, 0 broken." .../reports/baseline-gate.txt` prints `1`.

### T2.2 Metric script with a pinned definition
- **Goal:** A reproducible measure of tiny methods and pure delegations that matches the advisor's baseline.
- **Target files and symbols:** `scripts/code_metrics.py` → `measure(path: Path) -> dict`, `main(argv: list[str] | None = None) -> int`
- **Steps:**
  1. Population: every `ast.FunctionDef` and `ast.AsyncFunctionDef` in `*.py` under `--path` (default `src/pocketquant`), including methods and nested functions. Read files as UTF-8.
  2. Define `body` as the function body without a leading docstring (`Expr` holding a `str` `Constant`).
  3. **Measured set** for the tiny share excludes functions with any of these properties:
     - `body` is empty, or consists only of `...` or `pass`;
     - a decorator named `property`, `setter`, `cached_property` or `abstractmethod`, matched on the `Name.id` or `Attribute.attr` (for `Call` decorators, use the callee);
     - a name of the form `__x__`.
  4. `tiny` counts measured functions with `len(body) <= 2`. `tiny_share = tiny / functions_measured`, rounded to 4 decimals.
  5. `delegations` counts population functions, with no exclusions, whose `body` is exactly one `Return` or `Expr` statement. After unwrapping one `Await`, its value must be an `ast.Call` whose `func` is an `ast.Attribute`.
  6. `functions_over_60` lists `"<relative path>:<lineno> <name> <length>"` for functions where `end_lineno - lineno + 1 > 60`.
  7. CLI flags: `--path`, `--json` (prints the dict), `--max-tiny-share FLOAT`, `--max-delegations INT` and `--soft`. When a threshold is exceeded, print `::warning title=code-metrics::<metric> <value> > <threshold>` and exit 1, or exit 0 with `--soft`. Exit 0 otherwise.
  8. Write `tests/scripts/test_code_metrics.py`, importing `from scripts.code_metrics import measure`. Write synthetic files into `tmp_path` and assert each rule:
     - a docstring is not counted;
     - a stub, a property or a dunder is excluded;
     - `return self.a.b(x)`, `await self.a.b()` and a bare `self.x.append(y)` each count as a delegation;
     - `return f(x)` does not count, and neither do two statements;
     - a 61-line function is listed in `functions_over_60`.
- **Success criteria:** The script works and the unit tests pass.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/scripts/test_code_metrics.py -q` exits 0 with `passed`.

### T2.3 Metric baseline at the pre-plan commit
- **Goal:** Prove the script reproduces the confirmed baseline (48% tiny, 63 delegations).
- **Target files and symbols:** `.../reports/metrics-baseline.json`
- **Steps:**
  1. `git worktree add ../pq-metric-baseline 29f2f67`
  2. `uv run python scripts/code_metrics.py --path ../pq-metric-baseline/src/pocketquant --json > plans/261009-0858-exness-venue-lean-sync-refactor/reports/metrics-baseline.json`
  3. `git worktree remove ../pq-metric-baseline`
  4. `uv run python scripts/code_metrics.py --json > plans/261009-0858-exness-venue-lean-sync-refactor/reports/metrics-current.json`
- **Success criteria:** The baseline at `29f2f67` is functions 794, measured 661, tiny 315 (0.4766) and delegations 63.
- **Verify:** `uv run python -c "import json;d=json.load(open('plans/261009-0858-exness-venue-lean-sync-refactor/reports/metrics-baseline.json'));print(d['functions_total'],d['functions_measured'],d['tiny'],d['delegations'])"` prints `794 661 315 63`.

### T2.4 Sync pipeline characterization test (real Mongo/Redis)
- **Goal:** Pin what the five scheduled jobs write and record, independent of module paths.
- **Target files and symbols:** `tests/app_test/integration/test_sync_pipeline_characterization.py`
- **Steps:**
  1. Async fixture `deps(settings)`:
     - Connect `Database()` and `Cache()` with `settings`.
     - Build `BarRepository`, `SymbolRepository`, `SyncStatusRepository`, `JobHistoryRepository` and `TrackedSymbolRepository` with the db, and call `ensure_indexes()` on each.
     - Run `delete_many({})` on the collections `bars`, `sync_status`, `symbols`, `job_history` and `tracked_symbols` (constants in `src/pocketquant/core/common/constants.py`), before and after the test.
     - Seed `TrackedSymbol(symbol="BTCUSDT:BINANCE")` with `TrackedSymbolRepository.upsert`.
  2. `FakeProvider(IDataProvider)`: `fetch_ohlcv(symbol, interval, n_bars)` appends `(symbol, interval, n_bars)` to `self.calls` and returns `n_bars` closed, aligned bars that end at `get_bar_start(now, interval) - step`. Price is deterministic, `open = 100 + i`, `high = open + 2`, `low = open - 1`, `close = open + 1`, `volume = 1 + i % 3`, `tick_count = 1`. Cap the return at 100 bars per call to keep the test fast.
  3. Build a real `SyncService(provider=fake, cache=cache, bar_repository=..., symbol_repository=..., sync_status_repository=...)` and a `FakeContainer` whose `async get(cls)` maps `SyncService`, `JobHistoryRepository`, `TrackedSymbolRepository`, `BarRepository` and `IDataProvider` to these objects.
  4. A `RecordingScheduler` with `add_cron_job(func, *, job_id, **kw)` and `add_one_off_job(func, *, job_id, **kw)` stores the calls. Call `await register_sync_jobs(container, recording_scheduler)`, imported from `pocketquant.engine.market_data.app_services.sync_jobs`. That import is the only line later phases may edit. Resolve each stored `func` text `module:name` with `importlib.import_module(module)` and `getattr`.
  5. Assertions:
     - (a) **Registrations:** the cron jobs equal exactly this list, compared as `(job_id, kwargs)`. No catch-ups are enqueued on an empty history.
       - `("sync_1m", {"cron_expression": "*/1 * * * *", "second": 2, "misfire_grace_time": 120})`
       - `("sync_verify_cascade", {"cron_expression": "0 * * * *", "misfire_grace_time": 600})`
       - `("sync_backfill", {"hour": 3, "minute": 0, "misfire_grace_time": 3600})`
       - `("sync_integrity", {"hour": 4, "minute": 0, "misfire_grace_time": 3600})`
       - `("sync_repair", {"cron_expression": "0 */12 * * *", "misfire_grace_time": 1800})`
     - (b) **sync_1m:** after running it, `fake.calls == [("BTCUSDT:BINANCE", Interval.MINUTE_1, 100)]`, and the `bars` collection has 100 docs with `interval "1m"` and `source "rest_sync_1m"`. For every 5m, 15m, 1h, 4h and 1d doc with `source "cascade"`, O/H/L/C/V equal the aggregation of the stored 1m docs in its bucket: first open, max high, min low, last close and summed volume, computed in the test. The latest `job_history` doc for `sync_1m` has `status "completed"`, `total_inserted 100`, `total_fetched 100` and one `details` entry.
     - (c) **sync_1m again:** the latest `sync_1m` doc has `total_inserted 0`. `SyncStatusRepository.find_one("BTCUSDT:BINANCE", Interval.MINUTE_1).consecutive_empty_fetches == 1`.
     - (d) **sync_backfill:** clear `fake.calls` and run it. Then `fake.calls` equals `[("BTCUSDT:BINANCE", iv, 5000) for iv in (1m, 5m, 15m, 1h, 4h, 1d, 1w)]` in that order, and the latest `sync_backfill` doc is `completed`.
     - (e) **sync_repair:** delete one 1m bar inside the last hour with `BarRepository.delete_many_by_ids`, clear `fake.calls` and run it. `fake.calls` contains `("BTCUSDT:BINANCE", Interval.MINUTE_1, 5000)`, the deleted datetime exists again, and the latest `sync_repair` doc is `completed`.
     - (f) **sync_integrity:** the latest `sync_integrity` doc is `completed`.
     - (g) **sync_verify_cascade:** clear `fake.calls` and run it. `fake.calls == [("BTCUSDT:BINANCE", Interval.MINUTE_5, 12)]`, and the latest doc is `completed`.
     - (h) **sync_one response shape:** `SyncService.sync_one(SyncSymbolCommand(symbol="btcusdt:binance", interval=Interval.MINUTE_1, n_bars=10, source="rest_backfill")).model_dump().keys()` equals `{"symbol","interval","status","bars_synced","bars_fetched","filtered_existing","filtered_misaligned","total_bars","last_bar_at","message"}`, with `symbol == "BTCUSDT:BINANCE"` and `status == "completed"`.
- **Success criteria:** The current behaviour is pinned.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/app_test/integration/test_sync_pipeline_characterization.py -q` exits 0 with `passed` and no `failed`.

### T2.5 DI resolution characterization
- **Goal:** Pin which concrete classes the container returns, so the DI merge in Phase 04 is checked.
- **Target files and symbols:** `tests/app_test/integration/app_factory.py` → new `build_test_container(settings) -> AsyncContainer`, which wraps today's provider list with `TestCoreProvider(settings)`. Also `tests/app_test/integration/test_di_resolution_characterization.py`.
- **Steps:**
  1. Add `build_test_container`, returning `make_async_container(TestCoreProvider(settings), PersistenceProvider(), InfrastructureProvider(), ExecutionProvider(), MarketDataProvider(), AppTradingServiceProvider(), BacktestWorkerProvider(), ServicesProvider())`.
  2. In the test, build the container and assert `isinstance` on these resolved types:
     - `IDataProvider` → `BinanceClient`
     - `IRealtimeQuoteProvider` → `BinanceWebSocketClient`
     - `BrokerFactory` → `BrokerFactory`; `get_available_types() == ["paper","okx"]`, `create("paper", {})` is a `PaperBroker`, `create("okx", {"api_key":"k","api_secret":"s","passphrase":"p"})` is an `OKXBroker`, and `create("x", {})` raises `ValueError`
     - each of `SyncService`, `BarAppService`, `QuoteAppService`, `WsSubscriptionManager`, `OrderAppService`, `PositionAppService`, `StrategyAppService`, `StrategyReconcileService`, `BacktestExecutionService`, `TrackedSymbolService`, `StrategyCommandService`, `StrategyQueryService`, `OrderPositionQueryService` and `JobScheduler` resolves to its own class.
  3. Call `await container.close()` in teardown.
- **Success criteria:** The graph is pinned.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/app_test/integration/test_di_resolution_characterization.py -q` exits 0 with `passed`.

### T2.6 OKX WS order-flow characterization
- **Goal:** Pin OKX order mapping and dedupe before shared code moves. The OKX source itself is not edited.
- **Target files and symbols:** `tests/core_test/infra/brokers/test_okx_ws_order_flow_characterization.py`
- **Steps:**
  1. Create `broker = OKXBroker(api_key="k", api_secret="s", passphrase="p")`. Register a callback with `await broker.subscribe_order_updates(results.append)` (sync list append).
  2. Feed `await broker._handle_ws_message(msg)` with:
     - (a) `{"event":"subscribe","arg":{"channel":"orders"}}` should produce no result.
     - (b) `{"arg":{"channel":"orders"},"data":[{"ordId":"111","clOrdId":"abc","state":"filled","accFillSz":"0.5","avgPx":"100.5","sCode":"0"}]}` should produce one result with `order_id=="abc"`, `broker_order_id=="111"`, `status==OrderStatus.FILLED`, `filled_quantity==0.5`, `filled_price==100.5` and `error_message is None`.
     - (c) The same message again should add no result, and `broker.seen_terminal_orders == {"111"}`.
     - (d) `{"arg":{"channel":"orders"},"data":[{"ordId":"222","clOrdId":"def","state":"live","accFillSz":"0","avgPx":"","sCode":"0"}]}` sent twice should add 2 results, with `status==OrderStatus.SUBMITTED`, `filled_quantity==0.0` and `filled_price is None`.
     - (e) `{"arg":{"channel":"positions"},"data":[]}` should add no result.
- **Success criteria:** OKX behaviour is pinned.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/brokers/test_okx_ws_order_flow_characterization.py -q` exits 0 with `passed`.

### T2.7 Venue regression baseline
- **Goal:** One command whose pass count must stay constant through Phase 08.
- **Target files and symbols:** `.../reports/baseline-gate.txt`
- **Steps:**
  1. `.venv/Scripts/python.exe -m pytest tests/core_test/infra/binance tests/core_test/infra/brokers tests/backtest_test/engine/test_paper_broker_limit_orders.py tests/backtest_test/engine/test_paper_broker_order_events.py -q 2>&1 | tail -n 1`
  2. Append the output line to `baseline-gate.txt` as `venue: <line>`.
- **Success criteria:** The venue pass count is recorded.
- **Verify:** `grep -c "^venue: .* passed" .../reports/baseline-gate.txt` prints `1`.

### T2.8 Phase gate and ship
- **Goal:** Tests and scripts are merged with a green gate.
- **Target files and symbols:** git
- **Steps:**
  1. Run the gate: `just test`, `uv run ruff check`, `uv run pyright` and `uv run lint-imports`.
  2. Stage the files with `git add scripts/code_metrics.py tests/scripts/test_code_metrics.py tests/app_test/integration tests/core_test/infra/brokers/test_okx_ws_order_flow_characterization.py`.
  3. Commit with `git commit -m "test: pin sync jobs, di graph and okx ws mapping before refactor"`.
  4. Ask the user for approval, then `git switch master && git merge --ff-only test/sync-characterization && git push origin master`.
  5. Watch CI as in Phase 01 T1.8 step 6.
- **Success criteria:** Green.
- **Verify:**
  - `just test` exits 0 with `passed` and no `failed`.
  - `uv run ruff check` prints `All checks passed!`.
  - `uv run pyright` reports `0 errors`.
  - `uv run lint-imports` contains `Contracts: 7 kept, 0 broken.`.
  - `gh run watch <databaseId> --exit-status` exits 0.

## Verification
T2.3 (baseline numbers 794/661/315/63), T2.4–T2.6 (new characterization tests green on current code) and T2.8 (gate).

## Risks
- Time-dependent flakiness in T2.4. Mitigation: expected cascade values are computed from the stored 1m docs, not from hard-coded clock values.
- Testcontainers need Docker. Mitigation: `docker info` runs first in the gate.

## Rollback
This phase is test-only. `git revert` the merge commit.

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

<!-- FILE: phase-03-sync-policy-shared-runner.md -->
---
phase: 3
title: "Sync policy and shared runner (Binance)"
status: pending
priority: P1
effort: 4d
dependencies: [2]
---

# Phase 03: Sync policy and shared runner (Binance as proving provider)

## Context Links
- Advice §2.2, §2.3 (fold `sync_internals`) and §3 (keep the Binance cascade as a policy flag).
- Current code: `engine/market_data/app_services/sync_jobs.py` (729 LOC), `engine/market_data/app_services/integrity_jobs.py` (137), `engine/market_data/sync_service.py` (181; `sync_one` :48, `sync_bulk` :130), `engine/market_data/sync_internals/{anomaly_log,bar_alignment,bar_filters,provider_fetch,responses}.py` and `engine/market_data/sync_dtos.py`.
- Wiring: `src/pocketquant/app/main.py:31-33,51` (`set_sync_container`), `src/pocketquant/app/main_extensions.py:178` (`register_sync_jobs` import), `src/pocketquant/app/routes/integrity.py:9` and `src/pocketquant/core/infra/scheduling/scheduler.py` (`add_cron_job` uses `replace_existing=True`).
- Test patch targets that must keep working: `pocketquant.engine.market_data.sync_service.fetch_with_retry|filter_new_bars|drop_misaligned_bars`, `sync_service.asyncio` (previously `provider_fetch.asyncio`), and the module attributes `_container` and `cascade_for_symbol` on the runner module.

## Goal
One declarative `SyncPolicy` per provider and one shared runner that executes `fetch → align → persist → cascade? → integrity → repair`. The Binance policy reproduces today's behaviour exactly, which the Phase 02 characterization test proves. The job modules and `sync_internals/` are deleted.

## Files to Create or Modify
- Create: `src/pocketquant/engine/market_data/sync_policy.py`, `src/pocketquant/engine/market_data/sync_runner.py`, `src/pocketquant/engine/market_data/bar_integrity.py` and `tests/engine_test/market_data/test_sync_policy.py`
- Modify: `src/pocketquant/engine/market_data/sync_service.py`, `src/pocketquant/app/main.py`, `src/pocketquant/app/main_extensions.py`, `src/pocketquant/app/routes/integrity.py`, `src/pocketquant/engine/market_data/app_services/cascade_aggregator.py` (the docstring line that names `sync_jobs.sync_1m`) and `src/pocketquant/core/infra/persistence/repositories/job_history_repository.py` (the module docstring line that names `sync_jobs._run_sync`)
- Delete: `src/pocketquant/engine/market_data/app_services/sync_jobs.py`, `.../app_services/integrity_jobs.py`, `src/pocketquant/engine/market_data/sync_dtos.py` and `src/pocketquant/engine/market_data/sync_internals/` (all 6 files)
- Modify tests (imports and patch targets only, no assertion changes):
  - `tests/app_test/integration/app_factory.py`
  - `tests/app_test/integration/test_sync_backfill_gap_fill.py`
  - `tests/app_test/integration/test_sync_pipeline_characterization.py` (the single import line)
  - `tests/app_test/market_data/test_integrity_jobs_repair_source.py`
  - `tests/app_test/market_data/test_sync_jobs_source_labels.py`
  - `tests/app_test/test_sync_jobs_phase.py`
  - `tests/app_test/unit/handlers/sync/conftest.py`
  - `tests/app_test/unit/handlers/sync/test_bar_filters.py`
  - `tests/app_test/unit/handlers/sync/test_provider_fetch.py`
  - `tests/app_test/unit/market_data/test_sync_jobs_catchup.py`
  - `tests/app_test/unit/market_data/test_sync_verify_cascade.py`

## Tasks

### T3.1 Branch
- **Goal:** Isolate the refactor.
- **Target files and symbols:** git
- **Steps:**
  1. `git switch master && git pull --ff-only && git switch -c refactor/sync-policy-runner`
- **Success criteria:** The branch is checked out.
- **Verify:** `git branch --show-current` prints `refactor/sync-policy-runner`.

### T3.2 `sync_policy.py`
- **Goal:** A declarative policy type, a market calendar and the Binance policy.
- **Target files and symbols:** `src/pocketquant/engine/market_data/sync_policy.py`
- **Steps:**
  1. Write this module (the code is load-bearing):
     ```python
     @dataclass(frozen=True)
     class MarketCalendar:
         weekend_close: tuple[int, int] | None = None  # (weekday Mon=0, hour) UTC
         weekend_open: tuple[int, int] | None = None

         def is_open(self, ts: datetime) -> bool:
             if self.weekend_close is None or self.weekend_open is None:
                 return True
             utc = ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts.astimezone(UTC)
             week_hours = utc.weekday() * 24 + utc.hour + utc.minute / 60
             close = self.weekend_close[0] * 24 + self.weekend_close[1]
             reopen = self.weekend_open[0] * 24 + self.weekend_open[1]
             return not (close <= week_hours < reopen)

     ALWAYS_OPEN = MarketCalendar()
     FX_WEEKEND = MarketCalendar(weekend_close=(4, 20), weekend_open=(6, 23))

     @dataclass(frozen=True)
     class SyncPolicy:
         exchange: str
         live_source: str
         poll_intervals: tuple[Interval, ...]
         poll_n_bars: int
         cascade: bool
         cascade_lookback_minutes: int
         integrity_intervals: tuple[Interval, ...]
         backfill_n_bars: int
         rate_budget_per_minute: int
         history_days: Mapping[Interval, int | None] = field(default_factory=dict)
         calendars: Mapping[str, MarketCalendar] = field(default_factory=dict)

         def calendar_for(self, symbol: str) -> MarketCalendar:
             return self.calendars.get(symbol.split(":")[0].upper(), ALWAYS_OPEN)
     ```
  2. Add `BINANCE_POLICY = SyncPolicy(exchange="BINANCE", live_source="ws_aggtrade", poll_intervals=(Interval.MINUTE_1,), poll_n_bars=100, cascade=True, cascade_lookback_minutes=100, integrity_intervals=(Interval.MINUTE_1, Interval.MINUTE_5, Interval.MINUTE_15, Interval.HOUR_1, Interval.HOUR_4, Interval.DAY_1, Interval.WEEK_1), backfill_n_bars=5000, rate_budget_per_minute=1000)`.
  3. Add `POLICIES: dict[str, SyncPolicy] = {"BINANCE": BINANCE_POLICY}`.
  4. Add `def policy_for(symbol: str) -> SyncPolicy | None`, which returns `POLICIES.get(symbol.rsplit(":", 1)[-1].upper())` when `":" in symbol`, and `None` otherwise.
  5. Add `def market_calendar(symbol: str) -> MarketCalendar`, which returns the policy calendar or `ALWAYS_OPEN`.
  6. FX_WEEKEND closes Friday 20:00 UTC and reopens Sunday 23:00 UTC. The margin covers both US DST states. Write one short comment saying so, because the margin is a magic-number rationale.
- **Success criteria:** The module imports only stdlib, `pocketquant.core.domain.shared.enums` and nothing from infra.
- **Verify:** no verification needed; T3.3 covers this module.

### T3.3 Policy tests
- **Goal:** Pin the policy values and the calendar maths.
- **Target files and symbols:** `tests/engine_test/market_data/test_sync_policy.py`
- **Steps:**
  1. Assert `policy_for("btcusdt:binance") is BINANCE_POLICY`, `policy_for("X:UNKNOWN") is None` and `policy_for("nocolon") is None`.
  2. Assert that the `BINANCE_POLICY` fields equal the values in T3.2 step 2.
  3. For `FX_WEEKEND`: Fri 19:59 UTC is open, Fri 20:00 is closed, Sat 12:00 is closed, Sun 22:59 is closed, Sun 23:00 is open, and Wed 03:00 is open. A naive datetime (Sat 12:00) is treated as UTC and is closed.
  4. `ALWAYS_OPEN.is_open` returns True for a Saturday.
- **Success criteria:** The tests pass.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/engine_test/market_data/test_sync_policy.py -q` exits 0 with `passed`.

### T3.4 Fold `sync_internals` and `sync_dtos` into `sync_service.py`
- **Goal:** A manual sync is readable in one file, and the existing test patch targets keep working.
- **Target files and symbols:** `src/pocketquant/engine/market_data/sync_service.py`. It holds `SyncSymbolCommand`, `BulkSyncCommand`, `SyncResponse`, module functions `fetch_with_retry`, `filter_new_bars`, `drop_misaligned_bars` and `emit_no_progress`, constants `_BACKOFF_SECONDS`, `_TIME_BUDGET_SECONDS` and `_STUCK_STREAK_THRESHOLD`, and `class SyncService`.
- **Steps:**
  1. Move the three Pydantic models from `sync_dtos.py` into `sync_service.py` verbatim, with fields and descriptions unchanged, because the OpenAPI snapshot depends on them. Remove the re-export `__all__` comment.
  2. Move `fetch_with_retry` (from `provider_fetch.py`), `filter_new_bars` and `drop_misaligned_bars` (from `bar_filters.py`), and `emit_no_progress` with `_STUCK_STREAK_THRESHOLD` (from `anomaly_log.py`) into `sync_service.py` as module-level functions with the same names and bodies. Import `asyncio` and `time` at module level.
  3. Inline `has_aligned_bar` (from `bar_alignment.py`) into `fetch_with_retry` as `any(b.datetime is not None and is_bar_aligned(b.datetime, interval) for b in records)`.
  4. Inline `build_success` (from `responses.py`) into the success return of `SyncService.sync_one`. Fold the private one-call helpers `_persist_bars`, `_get_bar_stats`, `_mark_completed` and `_invalidate_cache` into their single call sites. Keep `_fail`, which has two callers.
  5. If `sync_one` exceeds 60 lines, move the progress-bookkeeping branch (the `SyncProgressTracker.decide` through `emit_no_progress` block) into `async def _record_progress(self, symbol, interval, *, inserted, bars_fetched, filtered_misaligned, filtered_existing, attempts, latest_bar) -> None`.
  6. Keep `sync_bulk` as is.
  7. Delete `src/pocketquant/engine/market_data/sync_internals/` and `src/pocketquant/engine/market_data/sync_dtos.py`.
  8. In the test files listed under "Files to Create or Modify", replace imports from `...sync_internals.bar_filters`, `...sync_internals.provider_fetch` and `...sync_internals` with `pocketquant.engine.market_data.sync_service` (or `import ... sync_service as provider_fetch` where a module object is patched). In `tests/app_test/unit/handlers/sync/conftest.py`, rebind the logger only on `sync_service`.
- **Success criteria:** No reference to `sync_internals` or `sync_dtos` remains.
- **Verify:** `grep -rn "sync_internals\|sync_dtos" src tests scripts | wc -l` prints `0`. `.venv/Scripts/python.exe -m pytest tests/app_test/unit/handlers tests/engine_test/market_data/test_sync_service.py tests/app_test/integration/test_sync_backfill_gap_fill.py -q` exits 0 with `passed`.

### T3.5 `bar_integrity.py`
- **Goal:** Integrity checks, repair and cascade verification are calendar-aware and live in one module.
- **Target files and symbols:** `src/pocketquant/engine/market_data/bar_integrity.py`. Symbols: `_group_gaps`, `check_integrity(symbol, interval, bar_repo, days_back=7, calendar=ALWAYS_OPEN)`, `repair_integrity(symbol, interval, bar_repo, sync_service, *, source, days_back=7, calendar=ALWAYS_OPEN)`, `PRICE_THRESHOLD_PCT`, `VOLUME_THRESHOLD_PCT`, `DIVERGENCE_ALERT_FRACTION`, `_diff_pct`, `compare_bar_fields` and `_verify_one_symbol`.
- **Steps:**
  1. Move `_group_gaps`, `check_integrity` and `repair_integrity` from `integrity_jobs.py` verbatim.
  2. In `check_integrity`, change only the expected-grid line to `expected = {t for t in (start + i * step for i in range(int((end - start) / step))) if calendar.is_open(t)}`. `repair_integrity` passes `calendar` through to both `check_integrity` calls.
  3. Move `PRICE_THRESHOLD_PCT`, `VOLUME_THRESHOLD_PCT`, `DIVERGENCE_ALERT_FRACTION`, `_diff_pct`, `compare_bar_fields` and `_verify_one_symbol` from `sync_jobs.py` verbatim.
  4. In `src/pocketquant/app/routes/integrity.py`, import from `bar_integrity`, and pass `calendar=market_calendar(symbol)` (from `sync_policy`) to both calls.
  5. In `test_integrity_jobs_repair_source.py` and `test_sync_verify_cascade.py`, change the imports to `pocketquant.engine.market_data.bar_integrity`.
- **Success criteria:** For `ALWAYS_OPEN` the behaviour is identical.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/app_test/market_data/test_integrity_jobs_repair_source.py tests/app_test/unit/market_data/test_sync_verify_cascade.py -q` exits 0 with `passed`.

### T3.6 `sync_runner.py`, the shared runner
- **Goal:** One module schedules and executes every provider's sync through its policy, keeping job ids, triggers, sources, history records and log event names.
- **Target files and symbols:** `src/pocketquant/engine/market_data/sync_runner.py`. Symbols: `_MODULE = "pocketquant.engine.market_data.sync_runner"`, `CATCHUP_TARGETS`, `_container`, `set_container`, `_get_container`, `_ms_since`, `_tracked_policies`, `_run_recorded`, `_record_detail`, `_sync_symbols`, `sync_1m`, `sync_verify_cascade`, `sync_backfill`, `sync_integrity`, `sync_repair`, `enqueue_missed_catchups` and `register_sync_jobs`. Import `cascade_for_symbol` by name at module level, because tests monkeypatch it.
- **Steps:**
  1. `CATCHUP_TARGETS`, `set_container`, `_get_container`, `_ms_since`, `enqueue_missed_catchups` and `register_sync_jobs` are copied from `sync_jobs.py` with `_MODULE` updated. Keep the same 5 `add_cron_job` calls with identical kwargs, and the log `market_data.registered_sync_jobs` with `job_count=5`.
  2. `async def _tracked_policies(repo) -> list[tuple[str, SyncPolicy]]` returns `(ts.symbol, policy)` for each tracked symbol where `policy_for(ts.symbol)` is not None. Otherwise it logs a warning `market_data.sync.no_policy` with `symbol=` and skips the symbol.
  3. `async def _run_recorded(name, history_repo, body) -> None` is the single owner of the copied `record_start`, `record_finish` and failure blocks. `body` is a zero-arg coroutine function that returns `tuple[int, int] | None`. With totals, call `record_finish(status="completed", duration_ms, total_inserted, total_fetched)`. Without totals, call `record_finish(status="completed", duration_ms)`. On an exception, record `failed` with `error=str(exc)` and re-raise. Keep the same warning log names.
  4. `async def _record_detail(history_repo, doc_id, job_name, symbol, interval, *, result=None, error=None)` records one detail row. It covers both existing call shapes: success from `result`, error with zeros. Any exception is swallowed with the warning `job_history.record_detail_failed`.
  5. `async def _sync_symbols(job_name, targets, source, sync_service, history_repo, doc_id) -> tuple[int, int]` ports `_sync_by_intervals`. `targets` is `list[tuple[str, tuple[Interval, ...], int]]`, meaning (symbol, intervals, n_bars). Keep the same `started`, `skipped` (no tracked symbols), `symbol_failed` and `completed` logs, the iteration order (symbol, then interval), and the "raise first error at end" rule.
  6. `sync_1m()` resolves exactly `JobHistoryRepository`, `SyncService`, `TrackedSymbolRepository` and `BarRepository`.
     - Inside `_run_recorded("sync_1m", ...)`: build `targets = [(s, p.poll_intervals, p.poll_n_bars) for s, p in tracked if p.calendar_for(s).is_open(now)]` and run `_sync_symbols` with `SOURCE_REST_SYNC_1M`.
     - Then, for each `(s, p)` with `p.cascade`, call `cascade_for_symbol(s, lookback_minutes=p.cascade_lookback_minutes, bar_repo=bar_repo)` with the same `sync_1m.cascade_failed` and `sync_1m.cascade_summary` logs.
     - If a policy's planned requests (`len(targets for that policy) * len(p.poll_intervals)`) exceed `p.rate_budget_per_minute`, log a warning `market_data.sync.rate_budget_exceeded` with `exchange`, `planned` and `budget`.
     - Return the totals.
  7. `sync_backfill()`: targets are `(s, p.integrity_intervals, p.backfill_n_bars)` with source `SOURCE_REST_BACKFILL`, and no calendar filter.
  8. `sync_integrity()` resolves `JobHistoryRepository`, `TrackedSymbolRepository` and `BarRepository`. For each `(s, p)` and each `p.integrity_intervals`, it calls `check_integrity(s, interval, bar_repo, calendar=p.calendar_for(s))` and emits the same `integrity.issues_found` warning.
  9. `sync_repair()` resolves those three plus `SyncService` and calls `repair_integrity(..., source=SOURCE_REST_REPAIR, calendar=p.calendar_for(s))` with the same `integrity.repaired` log.
  10. `sync_verify_cascade()` resolves `JobHistoryRepository`, `TrackedSymbolRepository`, `BarRepository` and `IDataProvider`. It iterates only over symbols whose policy has `cascade=True`, using `symbol = s.upper()`. The skip, ok, `rest_empty`, `cascade_empty` and `divergence_alert` logs stay identical.
  11. Every function stays ≤ 60 lines.
- **Success criteria:** The Binance behaviour is unchanged.
- **Verify:** no verification needed; T3.7 covers this module.

### T3.7 Rewire callers, delete job modules, migrate tests
- **Goal:** Nothing imports the old modules, and the characterization test passes with only its import line edited.
- **Target files and symbols:** `app/main.py`, `app/main_extensions.py`, the test files listed above, and the deleted `sync_jobs.py` and `integrity_jobs.py`.
- **Steps:**
  1. `app/main.py`: `from pocketquant.engine.market_data.sync_runner import set_container as set_sync_container`.
  2. `app/main_extensions.py` `start_background_jobs`: `from pocketquant.engine.market_data.sync_runner import register_sync_jobs`. Update the docstring word `sync_jobs` to `sync_runner`.
  3. Test imports:
     - `test_sync_pipeline_characterization.py`: change only the `register_sync_jobs` import line to `sync_runner`.
     - `test_sync_jobs_source_labels.py`: use `from pocketquant.engine.market_data import sync_runner as sync_jobs`, which keeps the monkeypatch lines identical.
     - `test_sync_jobs_phase.py` and `test_sync_jobs_catchup.py`: import from `sync_runner`.
     - `app_factory.py`: change the `set_sync_container` import to `sync_runner`.
  4. Docstrings: in `cascade_aggregator.py` replace `sync_jobs.sync_1m` with `sync_runner.sync_1m`, and in `job_history_repository.py` replace `sync_jobs._run_sync` with `sync_runner._run_recorded`.
  5. Delete `src/pocketquant/engine/market_data/app_services/sync_jobs.py` and `.../app_services/integrity_jobs.py`.
- **Success criteria:** The old modules are gone and every test passes.
- **Verify:**
  - `grep -rn "app_services.sync_jobs\|app_services.integrity_jobs\|app_services import sync_jobs" src tests scripts | wc -l` prints `0`.
  - `test ! -e src/pocketquant/engine/market_data/sync_internals && test ! -e src/pocketquant/engine/market_data/app_services/sync_jobs.py && echo gone` prints `gone`.
  - `.venv/Scripts/python.exe -m pytest tests/app_test/integration/test_sync_pipeline_characterization.py tests/app_test/market_data tests/app_test/unit tests/app_test/test_sync_jobs_phase.py -q` exits 0 with `passed`.

### T3.8 Size check of the refactored modules
- **Goal:** No god-functions in the new code.
- **Target files and symbols:** `scripts/code_metrics.py` output
- **Steps:**
  1. Run `uv run python scripts/code_metrics.py --json > /tmp/m.json`.
- **Success criteria:** No function over 60 lines in `sync_service.py`, `sync_runner.py`, `bar_integrity.py` or `sync_policy.py`.
- **Verify:** `uv run python -c "import json;d=json.load(open('/tmp/m.json'));bad=[f for f in d['functions_over_60'] if any(k in f for k in ('sync_service.py','sync_runner.py','bar_integrity.py','sync_policy.py'))];print(bad)"` prints `[]`.

### T3.9 Phase gate
- **Goal:** Full green, and the venue pass count is unchanged.
- **Target files and symbols:** whole repo
- **Steps:**
  1. `just test 2>&1 | tail -n 3`
  2. `uv run ruff check`
  3. `uv run pyright`
  4. `uv run lint-imports`
  5. Run the venue command from Phase 02 T2.7, `... -q 2>&1 | tail -n 1`.
  6. `.venv/Scripts/python.exe -m pytest tests/baseline -q` (OpenAPI and route snapshots, with no regeneration).
- **Success criteria:** Everything is green and identical.
- **Verify:**
  - Step 1 exits 0 with `passed` and no `failed`.
  - Step 2 prints `All checks passed!`.
  - Step 3 reports `0 errors`.
  - Step 4 shows `Contracts: 7 kept, 0 broken.`.
  - Step 5's `passed` count equals the number on the `venue:` line of `reports/baseline-gate.txt`.
  - Step 6 exits 0.

### T3.10 Ship and verify jobs in prod
- **Goal:** The runner is live, and the persisted APScheduler jobs point at the new module.
- **Target files and symbols:** git, VPS `/api/v1/system/jobs`
- **Steps:**
  1. Stage with `git add -A src tests` and check `git status --short` shows only files listed in this phase.
  2. `git commit -m "refactor(market-data): drive sync jobs from per-provider SyncPolicy and one shared runner"`
  3. Ask the user for approval, then merge, push and watch CI as in Phase 01 T1.8 steps 4-6.
  4. Wait about 3 minutes after the deploy turns green, then run:
     ```bash
     ssh -i "$KEY" "$HOST" 'docker exec -i pocketquant-app sh -s' <<'EOF'
     curl -s "http://localhost:41921/api/v1/system/jobs/sync_1m/runs?limit=1"
     EOF
     ```
  5. Run the same pattern with `curl -s http://localhost:41921/api/v1/system/jobs`.
- **Success criteria:** `sync_1m` completes in prod and all 5 job ids are registered. A one-time APScheduler log `Unable to restore job` for the old func refs is expected and harmless, because `replace_existing=True` re-registers each id.
- **Verify:**
  - `gh run watch` exits 0.
  - The step 4 output contains `"status":"completed"`.
  - The step 5 output contains each of `"sync_1m"`, `"sync_verify_cascade"`, `"sync_backfill"`, `"sync_integrity"` and `"sync_repair"`, which `grep -o` counts as 5 distinct ids.

## Verification
T3.4–T3.7 (migrated and characterization tests), T3.8 (function size), T3.9 (gate plus unchanged snapshots and venue count) and T3.10 (prod).

## Risks
- **Silent behaviour drift**, such as a changed iteration order, source label or n_bars (likelihood M, impact H). Mitigation: T2.4 asserts the exact provider calls, sources and history fields. The characterization test may change only its import line.
- **Stale persisted func refs in `apscheduler_jobs`** (L/M). Mitigation: APScheduler drops unrestorable jobs on load, and registration re-adds the same ids. `_catchup` one-offs with old refs are dropped too, and the next boot's catch-up sweep re-enqueues them if a run was missed.
- **Calendar logic leaks into Binance** (L/H). Mitigation: `BINANCE_POLICY.calendars` is empty, so `ALWAYS_OPEN` applies.

## Rollback
`git revert` the merge commit and push. On the next boot the old module re-registers the same job ids with `replace_existing=True`. No data migration is involved.

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

<!-- FILE: phase-04-collapse-di-routes-wrappers.md -->
---
phase: 4
title: "Collapse DI, routes and scalar wrappers"
status: pending
priority: P1
effort: 3d
dependencies: [3]
---

# Phase 04: Collapse DI, routes and scalar wrappers

## Context Links
- Advice §2.3. Keep the ports, aggregates, PaperBroker/live symmetry and 3 import-linter contracts.
- DI today is 11 files and 493 LOC: `src/pocketquant/app/di/{__init__,backtest_worker,broker_factory,container,core,execution,infrastructure,market_data,persistence,services,trading_services}.py`. `services.py:6-9` warns that the last duplicate registration silently wins.
- Market-data routes today: `src/pocketquant/app/routes/{market_data,market_data_ohlcv,market_data_status,market_data_sync,integrity,list_symbols,tracked_symbols}.py` plus `market_data_quotes.py`. They are mounted in `src/pocketquant/app/main_extensions.py:366-406` (`register_routes`).
- Scalar wrapper services:
  - `backtest/backtest_query_service.py:51`, `backtest/backtest_command_service.py:74`
  - `engine/market_data/quotes_service.py:54`, `symbols_service.py:14`, `sync_status_service.py:96,135`, `tracked_symbols_service.py:78,91,102`
  - `engine/orders_positions_service.py:50,67,86,92`
  - `engine/strategy_command_service.py:73,83,131,140`
  - `engine/strategy_query_service.py:56,59,71,101,117`
- import-linter contracts: `pyproject.toml` `[[tool.importlinter.contracts]]` (7 entries). bson is also banned by ruff `[tool.ruff.lint.flake8-tidy-imports.banned-api]`.

## Goal
`app/di` holds 3 provider modules, with strict validation and no silent duplicates. Market-data routes live in 2 files. Query/Command classes that wrap 0–2 scalars are gone, while Pydantic models stay for real request bodies. import-linter has 3 contracts. The HTTP surface is byte-identical, which the snapshots prove.

## Files to Create or Modify
- Create: `src/pocketquant/app/di/adapters.py`
- Rewrite: `src/pocketquant/app/di/__init__.py`, `src/pocketquant/app/di/infrastructure.py`, `src/pocketquant/app/di/services.py`
- Delete: `src/pocketquant/app/di/{backtest_worker,broker_factory,container,core,execution,market_data,persistence,trading_services}.py`
- Rewrite: `src/pocketquant/app/routes/market_data.py`. Delete `src/pocketquant/app/routes/{market_data_ohlcv,market_data_status,market_data_sync,integrity,list_symbols,tracked_symbols}.py`.
- Modify:
  - `src/pocketquant/app/main.py`, `src/pocketquant/app/main_extensions.py`
  - `src/pocketquant/app/routes/{backtest,strategy,trading_orders_positions,market_data_quotes}.py`
  - the wrapper-owning services listed in Context Links
  - `pyproject.toml`
- Modify tests:
  - `tests/app_test/integration/app_factory.py`, `test_app_standalone_runtime.py`, `test_reconcile_di_resolution.py`, `test_di_resolution_characterization.py`
  - `tests/app_test/unit/di/test_di_data_provider.py`
  - `tests/engine_test/test_reconcile_restart_resume_integration.py`
  - `tests/engine_test/market_data/test_quotes_service.py`, `tests/engine_test/market_data/test_tracked_symbols_service.py`
  - `tests/engine_test/test_strategy_handlers_declarative.py`, `tests/engine_test/test_strategy_service.py`, `tests/engine_test/test_orders_positions_service.py`, `tests/engine_test/test_strategy_position_and_trade_handlers.py`
  - `tests/app_test/unit/handlers/status/test_get_sync_status.py`, `tests/app_test/unit/handlers/status/test_get_symbol_sync_status.py`

## Tasks

### T4.1 Branch
- **Goal:** Isolate the work.
- **Target files and symbols:** git
- **Steps:**
  1. `git switch master && git pull --ff-only && git switch -c refactor/lean-wiring`
- **Success criteria:** On the branch.
- **Verify:** `git branch --show-current` prints `refactor/lean-wiring`.

### T4.2 DI collapsed to three provider modules
- **Goal:** Three providers (infrastructure, adapters, services), with `Settings` from context and strict validation.
- **Target files and symbols:** `app/di/infrastructure.py` → `InfrastructureProvider`, `app/di/adapters.py` → `BrokerFactory` and `AdaptersProvider`, `app/di/services.py` → `ServicesProvider`, and `app/di/__init__.py` → `create_container(settings: Settings | None = None) -> AsyncContainer`.
- **Steps:**
  1. Check that dishka supports strict validation: `uv run python -c "from dishka import STRICT_VALIDATION, from_context; print('ok')"` must print `ok`.
  2. `infrastructure.py`, `InfrastructureProvider(Provider)`:
     - `settings = from_context(provides=Settings, scope=Scope.APP)`
     - `get_event_bus` returning `EventBus(max_history=100)`
     - the `get_database` and `get_cache` generator factories, the 11 repository `provide(...)` lines, the `get_job_scheduler` generator and `get_health_coordinator`, all copied verbatim from `persistence.py`, `infrastructure.py` and `core.py`
  3. `adapters.py`: move `class BrokerFactory` verbatim from `broker_factory.py`. Then define `AdaptersProvider(Provider)` with `broker_factory = provide(BrokerFactory, scope=Scope.APP)`, plus `get_data_provider(self, settings) -> IDataProvider` returning `BinanceClient(settings=settings)` and `get_realtime_quote_provider(self) -> IRealtimeQuoteProvider` returning `BinanceWebSocketClient()`, both verbatim.
  4. `services.py`, `ServicesProvider(Provider)`: copy every remaining factory and `provide(...)` line verbatim from `market_data.py`, `execution.py`, `trading_services.py`, `backtest_worker.py` and the current `services.py`. Do not change any factory body. Remove the duplicate-registration comment.
  5. `__init__.py`: export the three providers and `BrokerFactory`, and define `create_container(settings=None)` returning `make_async_container(InfrastructureProvider(), AdaptersProvider(), ServicesProvider(), context={Settings: settings or get_settings()}, validation_settings=STRICT_VALIDATION)`.
  6. Delete `backtest_worker.py`, `broker_factory.py`, `container.py`, `core.py`, `execution.py`, `market_data.py`, `persistence.py` and `trading_services.py`.
  7. `app/main.py`: `from pocketquant.app.di import create_container`.
  8. Tests:
     - In `app_factory.py`, delete `TestCoreProvider`. `make_test_app` and `build_test_container` use `create_container(settings)`.
     - `test_app_standalone_runtime.py` and `test_reconcile_di_resolution.py` build their containers with `create_container(settings)`.
     - `test_di_data_provider.py` uses `AdaptersProvider().get_data_provider(mock_settings)` and `AdaptersProvider().get_realtime_quote_provider()`.
     - `test_reconcile_restart_resume_integration.py` imports `BrokerFactory` from `pocketquant.app.di.adapters`.
- **Success criteria:** Exactly 3 provider modules exist, and the DI characterization test passes unchanged except for the container builder.
- **Verify:**
  - `ls src/pocketquant/app/di/*.py | xargs -n1 basename | sort | tr '\n' ' '` prints `__init__.py adapters.py infrastructure.py services.py `.
  - `.venv/Scripts/python.exe -m pytest tests/app_test/integration tests/app_test/unit/di tests/engine_test/test_reconcile_restart_resume_integration.py tests/baseline/test_app_boot_smoke.py -q` exits 0 with `passed`.

### T4.3 Market-data routes in two files
- **Goal:** Every `/market-data/*` endpoint lives in `routes/market_data.py`. `routes/market_data_quotes.py` keeps `/quotes/*`.
- **Target files and symbols:** `src/pocketquant/app/routes/market_data.py` → `router` (`APIRouter(prefix="/market-data", tags=["Market Data"], route_class=DishkaRoute)`) and `tracked_symbols_router` (`APIRouter(tags=["Tracked Symbols"], route_class=DishkaRoute)`).
- **Steps:**
  1. Move these route functions verbatim, keeping decorator paths, `response_model`, `status_code`, `dependencies`, signatures and docstrings: `sync_symbol`, `sync_symbol_background`, `sync_bulk`, `get_sync_statuses`, `get_symbol_sync_status`, `integrity_check`, `integrity_repair`, `list_symbols`, `get_ohlcv`, `stream_bars` and their module helpers. Attach them to `router`. Move `IntegrityRequest` verbatim.
  2. Move `list_tracked_symbols`, `add_tracked_symbol`, `update_tracked_symbol`, `remove_tracked_symbol` and `backfill_tracked_symbol` verbatim onto `tracked_symbols_router`.
  3. In `sync_symbol_background`, replace the nested `run_sync` closure with `background_tasks.add_task(sync_service.sync_one, cmd)`.
  4. In `main_extensions.register_routes`, import `router as market_data_router, tracked_symbols_router` from `pocketquant.app.routes.market_data`, delete the `tracked_symbols` import, and keep `api.include_router(tracked_symbols_router, prefix="/market-data")`.
  5. Delete `market_data_ohlcv.py`, `market_data_status.py`, `market_data_sync.py`, `integrity.py`, `list_symbols.py` and `tracked_symbols.py`.
- **Success criteria:** The OpenAPI and route inventory snapshots are unchanged.
- **Verify:**
  - `ls src/pocketquant/app/routes/market_data*.py | wc -l` prints `2`.
  - `ls src/pocketquant/app/routes/ | grep -cE "^(integrity|list_symbols|tracked_symbols)\.py$"` prints `0`.
  - `.venv/Scripts/python.exe -m pytest tests/baseline -q` exits 0. Never set `BASELINE_UPDATE` in this phase.

### T4.4 Drop scalar Query/Command wrappers
- **Goal:** Routes pass scalars straight to services. The 22 wrapper classes are gone, and the request-body models stay.
- **Target files and symbols:** these new signatures. In each body, replace `query.x`, `cmd.x` and `request.x` with the parameter.
  - `BacktestQueryService.get_result(run_id: str)` and `BacktestCommandService.set_verdict(run_id: str, verdict: str | None)`
  - `QuoteQueryService.get_latest(symbol: str)` and `SymbolQueryService.list_symbols()`
  - `SyncStatusQueryService.get_sync_status()` and `get_symbol_sync_status(symbol: str, interval: str = "1d")`
  - `TrackedSymbolService.update(symbol: str)`, `remove(symbol: str)` and `list_all()`
  - `OrderPositionQueryService.get_order(order_id: str)`, `list_orders()`, `get_position(strategy_id: str)` and `list_positions()`
  - `StrategyCommandService.start(subscription_id: str)`, `stop(subscription_id: str)`, `remove_symbol(sub_id: str)` and `delete_strategy(strategy_id: str)`
  - `StrategyQueryService.get_all()`, `get_one(strategy_code: str)`, `list_symbols(strategy_code: str | None = None)`, `get_positions(subscription_id: str)` and `get_trades(subscription_id: str, limit: int = 100)`
- **Steps:**
  1. Delete these classes:
     - `GetBacktestQuery`, `SetVerdictCommand`, `GetLatestQuoteQuery`
     - `ListSymbolsQuery` (in both `symbols_service.py` and `strategy_query_service.py`)
     - `GetSyncStatusQuery`, `GetSymbolSyncStatusQuery`
     - `UpdateTrackedSymbolCommand`, `RemoveTrackedSymbolCommand`, `ListTrackedSymbolsQuery`
     - `GetOrderQuery`, `ListOrdersQuery`, `GetPositionQuery`, `ListPositionsQuery`
     - `StartStrategyCommand`, `StopStrategyCommand`, `RemoveSymbolCommand`, `DeleteStrategyCommand`
     - `GetStrategiesQuery`, `GetStrategyQuery`, `GetStrategyPositionsQuery`, `GetStrategyTradesQuery`
  2. Keep `RunBacktestCommand`, `ListBacktestsQuery`, `ListTradesQuery`, `GetOHLCVQuery`, `SyncSymbolCommand`, `BulkSyncCommand`, `BackfillTrackedSymbolCommand`, `AddTrackedSymbolCommand`, `AddSymbolCommand`, `CreateSubscriptionBody`, `SetVerdictBody` and `IntegrityRequest`.
  3. Update every route call site in `routes/backtest.py`, `routes/strategy.py`, `routes/trading_orders_positions.py`, `routes/market_data.py` and `routes/market_data_quotes.py`.
  4. Update the test call sites in the test files listed under "Files to Create or Modify". Change only the call shape; assertions stay unchanged.
- **Success criteria:** No wrapper class remains, pyright is clean, and the snapshots are unchanged.
- **Verify:**
  - `grep -rnwE "GetBacktestQuery|SetVerdictCommand|GetLatestQuoteQuery|ListSymbolsQuery|GetSyncStatusQuery|GetSymbolSyncStatusQuery|UpdateTrackedSymbolCommand|RemoveTrackedSymbolCommand|ListTrackedSymbolsQuery|GetOrderQuery|ListOrdersQuery|GetPositionQuery|ListPositionsQuery|StartStrategyCommand|StopStrategyCommand|RemoveSymbolCommand|DeleteStrategyCommand|GetStrategiesQuery|GetStrategyQuery|GetStrategyPositionsQuery|GetStrategyTradesQuery" src tests | wc -l` prints `0`.
  - `uv run pyright` reports `0 errors`.
  - `.venv/Scripts/python.exe -m pytest tests/baseline tests/engine_test tests/app_test -q` exits 0.

### T4.5 import-linter reduced to 3 contracts
- **Goal:** Keep only the contracts that matter: layers, core domain free of infra, and fastapi only in app.
- **Target files and symbols:** `pyproject.toml` `[[tool.importlinter.contracts]]`
- **Steps:**
  1. Keep "Layered architecture — app top tier", "Core domain stays free of infra adapters" and "fastapi only in app", with its comment.
  2. Delete "Core imports no inner package", "Engine imports no sibling/upper package" and "Backtest imports no upper package", which the layers contract already implies. Delete "No bson/ObjectId usage — UUID7 only", since ruff `banned-api` enforces it.
- **Success criteria:** 3 contracts, all kept, and the bson ban is still enforced.
- **Verify:** `uv run lint-imports` exits 0 and contains `Contracts: 3 kept, 0 broken.`. `grep -c '"bson"' pyproject.toml` prints a number ≥ 1 (the ruff banned-api entry).

### T4.6 Phase gate
- **Goal:** Full green.
- **Target files and symbols:** whole repo
- **Steps:**
  1. `just test 2>&1 | tail -n 3`
  2. `uv run ruff check`
  3. `uv run pyright`
  4. `uv run lint-imports`
  5. The venue command from T2.7.
- **Success criteria:** Green, with an unchanged venue count.
- **Verify:**
  - Step 1 exits 0 with `passed` and no `failed`.
  - Step 2 prints `All checks passed!`.
  - Step 3 reports `0 errors`.
  - Step 4 shows `Contracts: 3 kept, 0 broken.`.
  - Step 5's `passed` count equals the baseline `venue:` count.

### T4.7 Ship
- **Goal:** Deployed.
- **Target files and symbols:** git
- **Steps:**
  1. `git add -A src tests pyproject.toml`
  2. `git commit -m "refactor(app): collapse di to three providers, merge market-data routes, drop scalar query wrappers"`
  3. Ask the user for approval, then merge, push and watch CI as in Phase 01 T1.8.
  4. Smoke test, expecting HTTP 200:
     ```bash
     ssh -i "$KEY" "$HOST" 'docker exec -i pocketquant-app sh -s' <<'EOF'
     curl -s -o /dev/null -w "%{http_code}" http://localhost:41921/api/v1/market-data/tracked-symbols
     EOF
     ```
- **Success criteria:** Prod is green.
- **Verify:** `gh run watch` exits 0. The step 4 command prints `200`.

## Verification
T4.2 (DI: 3 modules plus characterization), T4.3 and T4.4 (snapshots unchanged) and T4.5 (3 contracts).

## Risks
- **STRICT_VALIDATION flags a latent duplicate or an unused provide** (M/M). That is the hazard being removed. Any error message goes to the Failure Protocol. Do not disable validation.
- **A route docstring change alters OpenAPI** (M/L). Mitigation: move function bodies verbatim, and the snapshot test blocks drift.
- **Moving the OKX construction code inside `BrokerFactory`** is a move, not a deletion. If a step would delete any Binance or OKX code, STOP and ask the user.

## Rollback
`git revert` the merge commit and push. There is no data impact.

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

<!-- FILE: phase-05-lean-standard-and-metric-gate.md -->
---
phase: 5
title: "Lean coding standard and metric gate"
status: pending
priority: P1
effort: 2d
dependencies: [4]
---

# Phase 05: Lean coding standard and metric gate

## Context Links
- Advice §2.4, §3 (soft gate, not tight) and §9 (success metrics).
- The current `docs/code-standards.md` is 799 lines. Stale claims: "Service Extract-Method Pattern" (§9), the 200-LOC module size rule ("Module Size") and the 20+ suffix roles ("Class Naming by Layer").
- `CLAUDE.md` lines 3 ("7 contracts") and 12 (the "Service methods take Pydantic command/query models" rule).
- CI: `.github/workflows/cicd.yml` job `tests` (step "Check import contracts").
- Metric baseline: `plans/261009-0858-exness-venue-lean-sync-refactor/reports/metrics-baseline.json` (794 / 661 / 315 = 0.4766 / 63).

## Goal
A standard that matches the code (D5). A soft CI gate shows the numbers. An explicit user decision is recorded if the confirmed thresholds (tiny share ≤ 0.30, delegations ≤ 20) are not met by the in-scope refactor.

## Files to Create or Modify
- Rewrite: `docs/code-standards.md`
- Modify: `CLAUDE.md`, `.github/workflows/cicd.yml`
- Create: `plans/261009-0858-exness-venue-lean-sync-refactor/reports/metrics-after-refactor.json`, `.../reports/metric-decision.md`

## Tasks

### T5.1 Branch
- **Goal:** Isolate the work.
- **Target files and symbols:** git
- **Steps:**
  1. `git switch master && git pull --ff-only && git switch -c docs/lean-standard`
- **Success criteria:** On the branch.
- **Verify:** `git branch --show-current` prints `docs/lean-standard`.

### T5.2 Rewrite `docs/code-standards.md`
- **Goal:** Rules of thumb instead of mandates, written AS-IS in Vietnamese prose with English technical terms, as `CLAUDE.md` requires.
- **Target files and symbols:** `docs/code-standards.md`
- **Steps:**
  1. Read the current file in full.
  2. Write the new file with exactly these H2 sections, in order. Keep the content of sections 10 and 11 from the current file, trimmed of history.
     1. `## Nguyên tắc`: KISS, DRY and balance (no god-functions and no micro-helpers).
     2. `## Khi nào extract helper`: extract only when the name adds meaning or the code is reused. A flow should be readable in one file where possible and in 3 at most.
     3. `## Kích thước file và hàm`: about 400 LOC per file is soft guidance, not a split trigger. Functions stay ≲ 60 lines.
     4. `## Đặt tên`: the suffix table is trimmed to `Repository`, `Service`, `Event`, `Error` and `Provider` (Dishka). Existing `AppService`, `CommandService` and `QueryService` names stay, but they are no longer distinct roles. Include the existing file-naming rules.
     5. `## Routes và services`: `FromDishka[...]` with `DishkaRoute`, never `Depends()` for services. Pydantic models only for real request bodies; scalars are passed directly.
     6. `## Dependency Injection`: 3 provider modules (`infrastructure`, `adapters`, `services`), `Settings` via `from_context`, `STRICT_VALIDATION`, and one provider per type.
     7. `## Repositories`: all in `core.infra.persistence.repositories`. UUIDv7 primary keys only (keep the existing code example).
     8. `## Sync policy pattern`: `SyncPolicy` fields, `sync_runner.py` jobs, `bar_integrity.py`, the calendar, and a checklist for adding a provider (one adapter package, one `SyncPolicy` in `POLICIES`, one DI router entry).
     9. `## Composite symbol`: keep the existing content.
     10. `## Async: await là preemption point`: keep the existing section, trimmed.
     11. `## Comment Policy`: keep the existing content verbatim. `CLAUDE.md` links this heading.
     12. `## Testing`: characterization tests before a refactor, the snapshot baselines with the `BASELINE_UPDATE=1` regeneration rule, and testcontainers.
     13. `## Quality gate`: `just test`, ruff, pyright, 3 import-linter contracts and the soft gate `scripts/code_metrics.py`, with the metric definition from `scripts/code_metrics.py`.
     14. `## Configuration & Secrets`: keep the existing content and add the `EXNESS_*` keys rule (only in `pocketquant-config`, never logged).
  3. Do not include any of these strings: `Current Status`, `Last Updated`, `Version:`, `200 LOC`, `Extract-Method`.
- **Success criteria:** The standard matches the code and contains no stale claims.
- **Verify:**
  - `grep -cE "Current Status|Last Updated|Version:|200 LOC|Extract-Method" docs/code-standards.md` prints `0`.
  - `grep -c "^## " docs/code-standards.md` prints `14`.
  - `grep -c "SyncPolicy" docs/code-standards.md` is ≥ 1.
  - `grep -c "## Comment Policy" docs/code-standards.md` prints `1`.

### T5.3 `CLAUDE.md` rules aligned
- **Goal:** The binding rule file stops contradicting the standard.
- **Target files and symbols:** `CLAUDE.md`, lines 3 and 12
- **Steps:**
  1. Line 3: replace `(7 contracts)` with `(3 contracts)`.
  2. Line 12: replace the sentence "Service methods take Pydantic command/query models and return DTOs." with "Service methods take Pydantic models only for real request bodies; scalar parameters are passed directly."
- **Success criteria:** Both lines are updated and nothing else changes.
- **Verify:** `grep -c "3 contracts" CLAUDE.md` prints `1`. `grep -c "Pydantic command/query models" CLAUDE.md` prints `0`. `git diff --stat CLAUDE.md` shows `2 insertions(+), 2 deletions(-)`.

### T5.4 Soft metric gate in CI
- **Goal:** The numbers are visible on every push and never block a deploy.
- **Target files and symbols:** `.github/workflows/cicd.yml`, job `tests`
- **Steps:**
  1. After the step `Check import contracts (layered architecture)`, insert:
     ```yaml
           - name: Code metrics (soft gate)
             run: uv run python scripts/code_metrics.py --max-tiny-share 0.30 --max-delegations 20 --soft
     ```
- **Success criteria:** The YAML is valid and the soft mode exits 0.
- **Verify:** `uv run python -c "import yaml;yaml.safe_load(open('.github/workflows/cicd.yml'))"` exits 0. `uv run python scripts/code_metrics.py --max-tiny-share 0.30 --max-delegations 20 --soft; echo $?` ends with `0`.

### T5.5 Measure and decide (stop-and-ask gate)
- **Goal:** D4 is met, or the user explicitly decides the thresholds.
- **Target files and symbols:** `.../reports/metrics-after-refactor.json`, `.../reports/metric-decision.md`
- **Steps:**
  1. `uv run python scripts/code_metrics.py --json > plans/261009-0858-exness-venue-lean-sync-refactor/reports/metrics-after-refactor.json`
  2. If `tiny_share <= 0.30` and `delegations <= 20`, write `metric-decision.md` with the line `decision: thresholds met`.
  3. Otherwise STOP. This is a stop-and-ask, not a self-fix. Send the user the JSON numbers, the baseline numbers and the top 15 files by tiny count, and offer these options verbatim:
     - (A) "Accept the measured values as the soft-gate thresholds."
     - (B) "Approve a further reduction pass. Candidates: dead functions with zero references (they include 3 unused OKX websocket getters, which would delete OKX code), passing services through to engine app-services, and property-like helpers. Each candidate list will be presented for approval."
     - (C) "Change the metric definition (state the change)."
  4. Write the user's choice to `metric-decision.md` as `decision: A|B|C` plus their words. For A, set `--max-tiny-share` and `--max-delegations` in `cicd.yml` to the measured values rounded up (tiny share to 2 decimals, delegations to an integer). For B or C, STOP and request a plan amendment before continuing.
- **Success criteria:** The decision is recorded, and CI thresholds match it.
- **Verify:** `grep -cE "^decision: (thresholds met|A|B|C)" .../reports/metric-decision.md` prints `1`.

### T5.6 Gate and ship
- **Goal:** Deployed with green CI, which now shows the metric step.
- **Target files and symbols:** git
- **Steps:**
  1. Run the full gate (`just test`, `uv run ruff check`, `uv run pyright`, `uv run lint-imports`).
  2. `git add docs/code-standards.md CLAUDE.md .github/workflows/cicd.yml`
  3. `git commit -m "docs(standards): rewrite code standard as lean rules of thumb and add soft metric gate"`
  4. Ask the user for approval, then merge, push and watch CI.
- **Success criteria:** Green.
- **Verify:** The gate passes with the same pass conditions as T4.6, `Contracts: 3 kept, 0 broken.` included. `gh run watch` exits 0. `gh run view <databaseId> --log | grep -c "Code metrics (soft gate)"` ≥ 1.

## Verification
T5.2 (greps), T5.3, T5.4 and T5.5 (recorded decision).

## Risks
- **The confirmed thresholds are not reachable without gaming** (likelihood H, impact M). Under the pinned definition the measured baseline is 0.4766 tiny share and 63 delegations. The in-scope reductions (deleted job modules and `sync_internals`, a smaller DI, merged routes) are projected to land around 0.40–0.44 and 50–58. Route handlers, port implementations and PaperBroker callbacks stay legitimately tiny. Mitigation: the T5.5 stop-and-ask. Never inline code only to move a number.

## Rollback
`git revert` the merge commit. These are docs and CI only.

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

<!-- FILE: phase-06-exness-market-data-and-policy.md -->
---
phase: 6
title: "Exness market data, quotes and policy"
status: pending
priority: P1
effort: 6d
dependencies: [5]
---

# Phase 06: Exness market data, quotes and policy

## Context Links
- Advice §2.5 (the files in `core/infra/exness/`), §2.7 and §3 (do not generate a client from the YAML).
- Spike journal: `docs/journals/*-exness-api-spike.md`. Its `rate_budget_per_minute`, `BTCUSD calendar` and `ws_subprotocol` lines are inputs here. Fixtures are in `tests/core_test/infra/exness/fixtures/`.
- Ports: `src/pocketquant/core/domain/market_data/interfaces.py` (`IDataProvider` :18, `IRealtimeQuoteProvider` :39). The quote callback contract is `src/pocketquant/app/market_data/app_services/quote_app_service.py:35`, which reads the keys `symbol`, `last_price`, `timestamp`, `bid`, `ask` and `volume`.
- Shapes to mirror: Binance REST `src/pocketquant/core/infra/binance/binance_client.py:50` (excludes the in-progress bar) and Binance WS `binance_websocket_client.py:97` (`run_forever`, watchdog and backoff).
- Spec facts: candles take `from` + `count` (negative count goes backward), `price_type=bid` is the default, the response is `candles[{time, open, high, low, close, volume}]` in ascending order, ticks are `{instrument, bid, ask, timestamp}` throttled to at most 1 per 500 ms, WS handshakes are signed as GET with path equality, and subscribe messages are `{"id", "subscribe": {"event": "ticks", "instruments": [...]}}`.

## Goal
`XAUUSD:EXNESS`, `EURUSD:EXNESS` and `BTCUSD:EXNESS` sync through the shared runner with `EXNESS_POLICY`: native M1–D1 polled every minute, no cascade, an FX calendar, and live ticks over WS. Binance keeps working through a venue router. The phase ends when D1 holds in prod.

## Files to Create or Modify
- Create in `src/pocketquant/core/infra/exness/`: `mappers.py`, `client.py`, `websocket.py`, `data_provider.py` and `quote_provider.py`.
- Create: `src/pocketquant/core/infra/venue_router.py` and `scripts/backfill/exness_bars.py`.
- Create tests: `tests/core_test/infra/exness/{test_mappers,test_client,test_websocket,test_data_provider,test_quote_provider}.py` and `tests/core_test/infra/test_venue_router.py`.
- Modify:
  - `src/pocketquant/engine/market_data/sync_policy.py` (add `EXNESS_POLICY`)
  - `src/pocketquant/app/di/adapters.py`
  - `tests/engine_test/market_data/test_sync_policy.py`
  - `tests/app_test/unit/di/test_di_data_provider.py`
  - `tests/app_test/integration/test_di_resolution_characterization.py`

## Tasks

### T6.1 Branch
- **Goal:** Isolate the work.
- **Target files and symbols:** git
- **Steps:**
  1. `git switch master && git pull --ff-only && git switch -c feat/exness-market-data`
- **Success criteria:** On the branch.
- **Verify:** `git branch --show-current` prints `feat/exness-market-data`.

### T6.2 `mappers.py`
- **Goal:** Pure conversions live in one place, and the adapter owns all CFD semantics.
- **Target files and symbols:** `src/pocketquant/core/infra/exness/mappers.py`. Symbols:
  - `INTERVAL_TO_EXNESS: dict[Interval, str] = {1m:"M1", 5m:"M5", 15m:"M15", 1h:"H1", 4h:"H4", 1d:"D1", 1w:"W1"}`
  - `instrument_code(symbol) -> str`
  - `candle_to_bar(candle: dict, symbol: str, interval: Interval) -> Bar`
  - `tick_to_quote_dict(tick: dict, symbol: str) -> dict`
  - `units_to_lots(quantity: Decimal, *, contract_size, volume_min, volume_step, volume_max, max_lots: Decimal | None) -> Decimal | None`
  - `lots_to_units(lots: Decimal, contract_size: Decimal) -> float`
  - `format_price(price: float, point_digits: int) -> str`
- **Steps:**
  1. `candle_to_bar` maps `datetime` (from `datetime.fromisoformat(candle["time"])` converted to UTC), the OHLC floats, `volume=float(candle["volume"])` and `tick_count=int(candle["volume"])`, with `symbol=symbol.upper()`.
  2. `tick_to_quote_dict` returns the key set of `aggtrade_to_quote_dict`: `symbol`, `timestamp`, `last_price=float(bid)`, `volume=None`, `bid`, `ask`, and `None` for `change`, `change_percent`, `open_price`, `high_price`, `low_price` and `prev_close`.
  3. `units_to_lots`:
     - compute `raw = quantity / contract_size`;
     - set `cap = min(volume_max, max_lots if max_lots is not None else volume_min)`;
     - set `steps = floor((min(raw, cap) - volume_min) / volume_step)`;
     - return `None` when `raw < volume_min`, otherwise `volume_min + steps * volume_step`.
     Use `Decimal` throughout.
  4. `format_price` returns `f"{price:.{point_digits}f}"`.
- **Success criteria:** No float rounding errors in the lot maths.
- **Verify:** no verification needed; T6.3 covers this module.

### T6.3 Mapper tests
- **Goal:** Pin the conversions against the fixtures.
- **Target files and symbols:** `tests/core_test/infra/exness/test_mappers.py`
- **Steps:**
  1. `candle_to_bar` on the first candle of `fixtures/candles_XAUUSD_M1.json` gives `symbol "XAUUSD:EXNESS"`, a UTC-aware datetime, and `tick_count == int(volume)`.
  2. `tick_to_quote_dict` on the first data frame of `fixtures/ticks_sample.json` gives `last_price == bid`.
  3. `units_to_lots`, with `contract_size` 100, `volume_min` 0.01, `step` 0.01, `volume_max` 200 and `max_lots` None:
     - quantity 0.5 → `None`
     - quantity 1 → `Decimal("0.01")`
     - quantity 7.9 → `Decimal("0.01")`, clamped to the minimum lot
  4. With `max_lots=Decimal("0.05")`, quantity 7.9 → `Decimal("0.05")`.
  5. `format_price(2345.678912, 2) == "2345.68"`.
- **Success criteria:** All tests pass.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_mappers.py -q` exits 0 with `passed`.

### T6.4 `client.py`
- **Goal:** One signed REST client with server clock sync and a self-managed rate budget. The API does not report remaining quota.
- **Target files and symbols:** `src/pocketquant/core/infra/exness/client.py`. Symbols:
  - `class ExnessApiError(Exception)` with `status`, `code` and `message`
  - `class ExnessClient`, built as `ExnessClient(settings: Settings)`, with:
    - property `is_configured`
    - `async request(method, path, *, params=None, json_body=None, idempotency_key="") -> dict`
    - `account_path(suffix) -> str`
    - `async limits()`, `async conditions(instrument) -> dict` (cached 1 h), `async candles(instrument, timeframe, from_iso, count) -> list[dict]`, `async snapshot()`
    - `async open_position(body: dict, idempotency_key: str)`, `async close_position(position_id: str, idempotency_key: str)`
    - `async deals_since(from_iso: str) -> list[dict]`
    - `sign_ws_headers(path: str) -> dict[str, str]`
    - `ws_url(path) -> str`
    - `async close()`
- **Steps:**
  1. `is_configured` is true when base URL, account id, API key and either private key or key path are all set. If it is false, every request raises `ExnessApiError(0, "NOT_CONFIGURED", "exness settings missing")`.
  2. In `request`, build the query with `urlencode(params)` and request the literal `f"{path}?{query}"` (or `path` alone). Serialize the JSON body with `json.dumps(body, separators=(",", ":")).encode()` and send it as `content=` with `Content-Type: application/json`. Headers come from `sign_headers(..., timestamp_ms=self._clock.now_ms())`. Call `self._clock.update_from_date_header(resp.headers["date"])` when the header is present.
  3. Rate budget: on the first call, read `limits()` once, bypassing the bucket, to get `global_account_rate.limit` and `window_seconds`. A token bucket with `asyncio.Lock` then sleeps until a token is available. On HTTP 429, log a warning `exness.rate_limited` and raise `ExnessApiError`.
  4. Errors: for a non-2xx response, parse `{"error": {"code"}, "error_message"}` and raise `ExnessApiError(status, code, message)`. Never log headers, the key or the body of signed requests.
  5. `ws_url` replaces `https://` with `wss://` on the base URL and appends the path.
- **Success criteria:** Requests are signed exactly as sent.
- **Verify:** no verification needed; T6.5 covers this module.

### T6.5 Client tests
- **Goal:** Pin signing equality, error mapping and secret hygiene.
- **Target files and symbols:** `tests/core_test/infra/exness/test_client.py`
- **Steps:**
  1. Use `httpx.MockTransport`. Inject it by monkeypatching `ExnessClient._http` with `httpx.AsyncClient(transport=..., base_url="https://api.test")`. Use a Settings stub (`MagicMock(spec=Settings)`) with a generated PEM key.
  2. Assert that the decoded `EXN-DATA.path` equals `request.url.raw_path` for a GET with params `{"instrument":"XAUUSD","from":"2026-01-01T00:00:00+00:00","count":-5}`, that `EXN-IDEMPOTENCY-KEY == ""` on GET, and that a POST carries a non-empty idempotency key and a `body_hash` equal to `body_hash(request.content)`.
  3. A 400 response with body `{"error":{"code":"REQUEST_INVALID_COUNT"},"error_message":"x"}` raises `ExnessApiError` with `code == "REQUEST_INVALID_COUNT"`.
  4. Under `structlog.testing.capture_logs()`, no captured event contains the API key string.
  5. `is_configured` is False when `exness_api_key` is None, and `request` then raises `NOT_CONFIGURED`.
- **Success criteria:** All tests pass.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_client.py -q` exits 0 with `passed`.

### T6.6 `websocket.py`
- **Goal:** One reconnecting signed WS stream, shaped like the OKX and Binance clients: backoff 1 s → 30 s and a circuit breaker after 10 consecutive failures that pauses for 300 s.
- **Target files and symbols:** `src/pocketquant/core/infra/exness/websocket.py` → `class ExnessStream` with `__init__(client: ExnessClient, path: str, on_message: Callable[[dict], Awaitable[None]], on_connect: Callable[[], Awaitable[None]], stale_after_s: float | None)`, `async run_forever()`, `async send(message: dict)`, `is_connected() -> bool`, `async close()` and attribute `last_frame_at`.
- **Steps:**
  1. Connect with `websockets.connect(client.ws_url(path), additional_headers=client.sign_ws_headers(path), subprotocols=[...] or None, ping_interval=20, ping_timeout=10, close_timeout=5)`. The subprotocol value comes from the journal line `ws_subprotocol` and is a module constant `_SUBPROTOCOL` (`"exness-ws-protocol"` or `None`).
  2. After connecting, reset the backoff and failure count and `await on_connect()`. For each frame, `json.loads`, update `last_frame_at` and `await on_message(frame)`. An invalid JSON frame is logged as a warning `exness_ws.invalid_json` and skipped.
  3. On any disconnect or exception: log `exness_ws.reconnecting` with `delay`, sleep the backoff, and double it up to a 30 s cap. After 10 consecutive failures, log an error `exness_ws.circuit_breaker_open` and sleep 300 s before the next attempt.
  4. When `stale_after_s` is set, a sibling watchdog task closes the socket if `last_frame_at` is older than `stale_after_s` (copy the Binance watchdog shape).
- **Success criteria:** Reconnect and backoff are deterministic and testable.
- **Verify:** no verification needed; T6.7 covers this module.

### T6.7 WS stream tests
- **Goal:** Pin the reconnect behaviour.
- **Target files and symbols:** `tests/core_test/infra/exness/test_websocket.py`
- **Steps:**
  1. Monkeypatch `websockets.connect` in the module to a fake that fails N times, then yields scripted frames and closes. Patch `asyncio.sleep` in the module with an `AsyncMock` that records delays.
  2. Assert that after 3 failures the recorded delays are `[1, 2, 4]` and that `on_connect` runs after the first success.
  3. Assert that 10 consecutive failures record one sleep of `300`.
  4. Assert that the handshake headers include `EXN-SIGN` and that the signed path equals the stream path.
- **Success criteria:** All tests pass.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_websocket.py -q` exits 0 with `passed`.

### T6.8 `data_provider.py`
- **Goal:** `IDataProvider` over native candles, paginated by `max_candles_per_request`, with the in-progress candle dropped.
- **Target files and symbols:** `src/pocketquant/core/infra/exness/data_provider.py` → `class ExnessDataProvider(IDataProvider)` with `fetch_ohlcv(symbol, interval, n_bars=1000)`, `search_symbols(query) -> []` and `close()`.
- **Steps:**
  1. `page` comes from `limits()` as the `max_candles_per_request` of method `getCandleHistory`, cached.
  2. Loop while `remaining > 0`:
     - fetch `candles(code, INTERVAL_TO_EXNESS[interval], from_iso=cursor, count=-min(remaining, page))`, where `cursor` starts at the current UTC time in ISO seconds precision;
     - map each candle with `candle_to_bar`;
     - drop bars whose `datetime + INTERVAL_SECONDS[interval] > now`;
     - drop bars whose datetime is already collected;
     - prepend the rest;
     - stop when the page returned fewer candles than requested;
     - otherwise move `cursor` to the oldest returned candle time.
  3. Log `exness.fetch_completed` with `symbol` and `bars_fetched`. Return the bars ascending, trimmed to the last `n_bars`.
- **Success criteria:** Same contract as `BinanceClient.fetch_ohlcv`.
- **Verify:** no verification needed; T6.9 covers this module.

### T6.9 Data provider tests
- **Goal:** Pin pagination and in-progress filtering.
- **Target files and symbols:** `tests/core_test/infra/exness/test_data_provider.py`
- **Steps:**
  1. Use a fake client (`AsyncMock`) with `limits()` returning `fixtures/limits.json` with `max_candles_per_request` patched to 100. `candles()` returns slices derived from `fixtures/candles_XAUUSD_M1.json`.
  2. Assert `fetch_ohlcv("XAUUSD:EXNESS", Interval.MINUTE_1, 250)` makes 3 `candles` calls with counts `-100`, `-100` and `-50`, and returns ascending, unique datetimes.
  3. Assert that a candle whose open time is `now - 30s` is excluded.
- **Success criteria:** All tests pass.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_data_provider.py -q` exits 0 with `passed`.

### T6.10 `quote_provider.py`
- **Goal:** `IRealtimeQuoteProvider` over WS ticks, using the same callback dict as Binance.
- **Target files and symbols:** `src/pocketquant/core/infra/exness/quote_provider.py` → `class ExnessQuoteProvider`. Attributes and members: `last_tick_at`, `connect()`, `disconnect()`, `subscribe(symbol, callback) -> str`, `unsubscribe(symbol)`, `run_forever()`, `is_connected()`, `subscription_count` and `subscriptions`.
- **Steps:**
  1. `self._subscriptions: dict[str, tuple[str, Callable]]` maps the composite symbol to `(code, callback)`. `subscribe` stores the entry. If the stream is connected, it also sends `{"id": f"sub-{code}", "subscribe": {"event": "ticks", "instruments": [code]}}`.
  2. `unsubscribe` removes the entry locally, and frames for unknown instruments are ignored.
  3. `run_forever` runs `ExnessStream(client, f"/v1/server-events/accounts/{account}/ws/ticks", on_message=self._on_frame, on_connect=self._resubscribe_all, stale_after_s=None)`. Ticks pause in closed markets, so there is no stale watchdog.
  4. `_on_frame`: when the frame has `instrument`, `bid` and `ask`, find the composite symbol by code, build `tick_to_quote_dict`, set `last_tick_at`, and call the callback (awaiting it if it is a coroutine). When the frame carries an error code `MARKET_TRADE_DISABLED` or a `trading_disabled` text, log a warning `exness_ws.trading_disabled` and continue.
  5. `connect()` is a no-op, because the connection happens inside `run_forever`. `disconnect()` closes the stream.
- **Success criteria:** It satisfies the Protocol structurally.
- **Verify:** no verification needed; T6.11 covers this module.

### T6.11 Quote provider tests
- **Goal:** Pin the callback contract.
- **Target files and symbols:** `tests/core_test/infra/exness/test_quote_provider.py`
- **Steps:**
  1. `isinstance(ExnessQuoteProvider(client_stub), IRealtimeQuoteProvider)` is True.
  2. After `subscribe("XAUUSD:EXNESS", cb)`, feeding `_on_frame` the first fixture tick for XAUUSD calls `cb` once with `symbol == "XAUUSD:EXNESS"` and `last_price == bid`.
  3. A frame for an unsubscribed instrument does not call `cb`.
  4. An error frame logs `exness_ws.trading_disabled` and does not raise.
- **Success criteria:** All tests pass.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_quote_provider.py -q` exits 0 with `passed`.

### T6.12 `venue_router.py`
- **Goal:** Consumers (`SyncService`, `QuoteAppService`, `WsSubscriptionManager`, backfill) stay unchanged while the providers become per-exchange.
- **Target files and symbols:** `src/pocketquant/core/infra/venue_router.py` → `class DataProviderRouter(IDataProvider)` and `class QuoteProviderRouter`.
- **Steps:**
  1. `_exchange(symbol) = symbol.rsplit(":", 1)[-1].upper()`.
  2. `DataProviderRouter(providers: dict[str, IDataProvider])`. `fetch_ohlcv` dispatches by exchange, and an unknown exchange raises `ValueError(f"no data provider for exchange {ex}")`. `search_symbols` returns `[]`. `close` closes all providers.
  3. `QuoteProviderRouter(providers: dict[str, IRealtimeQuoteProvider])`:
     - `subscribe` and `unsubscribe` dispatch by exchange, and an unknown exchange raises `ValueError`;
     - `run_forever` is `await asyncio.gather(*(p.run_forever() for p in providers.values()))`;
     - `connect` and `disconnect` apply to all providers;
     - `is_connected` is `all(...)`;
     - `subscriptions` merges the dicts, and `subscription_count` is its length;
     - `last_tick_at` is a property returning the max of the non-None values.
  4. Tests in `tests/core_test/infra/test_venue_router.py`: dispatch to the right fake by suffix (case-insensitive), the unknown exchange `ValueError`, merged `subscriptions`, and `last_tick_at` max.
- **Success criteria:** The routers are thin and fully covered.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/test_venue_router.py -q` exits 0 with `passed`.

### T6.13 `EXNESS_POLICY`
- **Goal:** Exness is policy #2 with no new job code (A-v).
- **Target files and symbols:** `src/pocketquant/engine/market_data/sync_policy.py` → `EXNESS_POLICY` and `POLICIES["EXNESS"]`
- **Steps:**
  1. Add `EXNESS_POLICY = SyncPolicy(exchange="EXNESS", live_source="ws_ticks", poll_intervals=(Interval.MINUTE_1, Interval.MINUTE_5, Interval.MINUTE_15, Interval.HOUR_1, Interval.HOUR_4, Interval.DAY_1), poll_n_bars=100, cascade=False, cascade_lookback_minutes=0, integrity_intervals=<same 6>, backfill_n_bars=5000, rate_budget_per_minute=<the journal's rate_budget_per_minute>, history_days={Interval.MINUTE_1: 365, Interval.MINUTE_5: 730, Interval.MINUTE_15: 1095, Interval.HOUR_1: None, Interval.HOUR_4: None, Interval.DAY_1: None}, calendars={"XAUUSD": FX_WEEKEND, "EURUSD": FX_WEEKEND, "BTCUSD": <ALWAYS_OPEN if the journal says "BTCUSD calendar: always_open" else FX_WEEKEND>})`.
  2. Register it with `POLICIES["EXNESS"] = EXNESS_POLICY`.
  3. Extend `test_sync_policy.py`: assert `policy_for("XAUUSD:EXNESS") is EXNESS_POLICY`, `cascade is False`, `calendar_for("XAUUSD:EXNESS") is FX_WEEKEND`, and that the `BTCUSD` calendar matches the journal.
- **Success criteria:** The policy is declarative only.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/engine_test/market_data/test_sync_policy.py -q` exits 0 with `passed`.

### T6.14 DI wiring through the routers
- **Goal:** Binance stays the default. Exness is added only when configured.
- **Target files and symbols:** `src/pocketquant/app/di/adapters.py` → `AdaptersProvider.get_exness_client` (async generator: yields `ExnessClient(settings)`, then awaits `close()`), `get_data_provider(self, settings, exness_client) -> IDataProvider` and `get_realtime_quote_provider(self, exness_client) -> IRealtimeQuoteProvider`.
- **Steps:**
  1. `get_data_provider` returns `DataProviderRouter({"BINANCE": BinanceClient(settings=settings), **({"EXNESS": ExnessDataProvider(exness_client)} if exness_client.is_configured else {})})`.
  2. `get_realtime_quote_provider` returns `QuoteProviderRouter({"BINANCE": BinanceWebSocketClient(), **({"EXNESS": ExnessQuoteProvider(exness_client)} if exness_client.is_configured else {})})`.
  3. Update `test_di_data_provider.py`. With unset Exness settings (`MagicMock(spec=Settings)` with the Exness attributes `None`), the result is a `DataProviderRouter` whose `providers` has keys `{"BINANCE"}` and whose `providers["BINANCE"]` is a `BinanceClient`. The same holds for the quote router with a `BinanceWebSocketClient`.
  4. Update `test_di_resolution_characterization.py`: `IDataProvider` is a `DataProviderRouter`, and `IRealtimeQuoteProvider` is a `QuoteProviderRouter`.
- **Success criteria:** With no Exness env the behaviour is identical for Binance.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/app_test/unit/di tests/app_test/integration/test_di_resolution_characterization.py tests/app_test/integration/test_sync_pipeline_characterization.py -q` exits 0 with `passed`.

### T6.15 Exness backfill script
- **Goal:** Deep history beyond the 5000-bar DTO cap, for Phase 08.
- **Target files and symbols:** `scripts/backfill/exness_bars.py` → `parse_args`, `async run(cfg) -> int`, `main`
- **Steps:**
  1. CLI: `--symbol` (must end in `:EXNESS`), `--interval` (one of `1m 5m 15m 1h 4h 1d`), `--days INT` and `--dry-run`.
  2. Reject `days` greater than `EXNESS_POLICY.history_days[interval]` when that is not None, with exit 2.
  3. `n_bars = days * 86400 // INTERVAL_SECONDS[interval]`. Fetch with `ExnessDataProvider(ExnessClient(get_settings())).fetch_ohlcv(symbol, interval, n_bars)`. Unless `--dry-run`, call `BarRepository(db).insert_many(chunk, source=SOURCE_REST_BACKFILL)` in chunks of 5000.
  4. Print exactly one line, `fetched=<n> inserted=<n> total_bars=<BarRepository.count(symbol, interval)>`. Exit 0, or 1 when fetched is 0.
- **Success criteria:** The script is safe to run in prod.
- **Verify:** `uv run python scripts/backfill/exness_bars.py --help` exits 0. `uv run python scripts/backfill/exness_bars.py --symbol XAUUSD:EXNESS --interval 1m --days 400 --dry-run; echo $?` ends with `2`.

### T6.16 Phase gate
- **Goal:** Full green.
- **Target files and symbols:** whole repo
- **Steps:**
  1. `just test 2>&1 | tail -n 3`
  2. `uv run ruff check`
  3. `uv run pyright`
  4. `uv run lint-imports`
  5. The venue command.
  6. `.venv/Scripts/python.exe -m pytest tests/baseline -q`
  7. `uv run python scripts/code_metrics.py --json > /tmp/m.json`
- **Success criteria:** Green, with no function over 60 lines in `core/infra/exness/` or `venue_router.py`.
- **Verify:**
  - Steps 1–4 meet the same pass conditions as T4.6.
  - Step 5's count equals the baseline.
  - Step 6 exits 0.
  - `uv run python -c "import json;d=json.load(open('/tmp/m.json'));print([f for f in d['functions_over_60'] if 'exness' in f or 'venue_router' in f])"` prints `[]`.

### T6.17 Ship, track symbols and verify D1 in prod
- **Goal:** Exness bars and quotes flow in prod. Run this during FX market hours.
- **Target files and symbols:** git, VPS API
- **Steps:**
  1. `git add -A src tests scripts`
  2. `git commit -m "feat(exness): add candle data provider, tick quote provider and exness sync policy"`
  3. Ask the user for approval, then merge, push and watch CI.
  4. Add the tracked symbols. The admin token stays in the container env.
     ```bash
     ssh -i "$KEY" "$HOST" 'docker exec -i pocketquant-app sh -s' <<'EOF'
     for s in XAUUSD EURUSD BTCUSD; do curl -s -X POST http://localhost:41921/api/v1/market-data/tracked-symbols -H "Content-Type: application/json" -H "X-Admin-Token: $ADMIN_TOKEN" -d "{\"symbol\":\"$s:EXNESS\"}"; echo; done
     EOF
     ```
  5. Run the manual sync with the same pattern:
     ```bash
     curl -s -X POST http://localhost:41921/api/v1/market-data/sync -H "Content-Type: application/json" -d '{"symbol":"XAUUSD:EXNESS","interval":"1m","n_bars":1000,"source":"rest_backfill"}'
     ```
  6. Check the bar stream with the same pattern: `timeout 70 curl -sN "http://localhost:41921/api/v1/market-data/bars/stream/XAUUSD%3AEXNESS?interval=1m" | grep -m1 -c '"is_in_progress": true'`.
  7. Check the quote stream with the same pattern: `timeout 30 curl -sN "http://localhost:41921/api/v1/quotes/stream/XAUUSD%3AEXNESS" | grep -m1 -c '"bid":'`.
  8. Wait 3 minutes, then check sync status with the same pattern: `curl -s "http://localhost:41921/api/v1/market-data/sync-status/XAUUSD%3AEXNESS?interval=1h"`.
- **Success criteria:** D1 holds. Binance keeps syncing.
- **Verify:**
  - `gh run watch` exits 0.
  - Step 5's JSON has `"status":"completed"` and `total_bars >= 1000`, checked by piping it to `python -c "import json,sys;d=json.load(sys.stdin);print(d['status']=='completed' and d['total_bars']>=1000)"`, which prints `True`.
  - Step 6 prints `1`.
  - Step 7 prints `1`.
  - Step 8 contains `"status":"completed"`.
  - The same step 8 command for `BTCUSDT%3ABINANCE?interval=1m` also contains `"status":"completed"`.

## Verification
T6.3–T6.12 (unit), T6.14 (DI and characterization), T6.16 (gate) and T6.17 (D1 in prod).

## Risks
- **Tracking an EXNESS symbol without the router** sends `xauusd@aggTrade` to Binance. Mitigation: symbols are added only after this phase deploys (T6.17).
- **Rate limits**: 3 instruments × 6 TF = 18 requests a minute, plus backfill and repair. Mitigation: the token bucket from `/limits`, plus the `rate_budget_exceeded` warning. If the limits make A-v infeasible, STOP and ask the user.
- **Closed-market noise**: the runner skips polling, and integrity skips the grid, inside `FX_WEEKEND`. `sync-status.is_stuck` may show true over the weekend. That flag is display-only and acceptable.
- **No topology change**: the Exness WS runs inside the existing single process. If anything would need a new container or worker, STOP and ask the user.

## Security
The key is read from Settings only. The client never logs headers, keys or signed bodies, which T6.5 asserts. The admin token is expanded inside the container and never echoed.

## Rollback
First remove the Exness tracked symbols (`DELETE /api/v1/market-data/tracked-symbols/XAUUSD%3AEXNESS`, and the same for EURUSD and BTCUSD, with `X-Admin-Token`). Then `git revert` the merge commit and push. Exness bars left in `bars` are harmless.

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

<!-- FILE: phase-07-exness-broker-and-live-wiring.md -->
---
phase: 7
title: "Exness broker and live order wiring"
status: pending
priority: P1
effort: 5d
dependencies: [6]
---

# Phase 07: Exness broker and live order wiring

## Context Links
- Advice §2.6 (CFD impedance in the adapter, async fills, the OKX dedupe pattern, `trading_disabled` and HMR) and §3 (do not fork the domain).
- `IBroker`: `src/pocketquant/core/domain/brokers/interfaces.py:13`. `OrderResult` and `AccountBalance`: `.../brokers/value_objects.py`.
- Engine: `src/pocketquant/engine/app_services/strategy_app_service.py` (`load_strategy` :96, `_get_or_create_broker` :409, `_process_signal`) and `src/pocketquant/engine/app_services/order_app_service.py` (`submit` :34, `on_order_update` :174; it is currently never subscribed, so async fills from a live broker never reach it).
- Order state machine: `src/pocketquant/core/domain/order/entities.py:52`. `SUBMITTED→REJECTED` is not allowed, so an async rejection maps to `CANCELLED`.
- PaperBroker synthetic exit pattern (publish `OrderFilledEvent` for broker-side exits): `src/pocketquant/core/infra/brokers/paper/paper_broker.py:671`.
- Subscription: `src/pocketquant/core/domain/subscription/entities.py:32`. Config build sites: `src/pocketquant/app/main_extensions.py:152` and `src/pocketquant/engine/app_services/strategy_reconcile_service.py:141`. Body: `src/pocketquant/app/routes/strategy.py` (`CreateSubscriptionBody`). Service: `src/pocketquant/engine/strategy_command_service.py` (`AddSymbolCommand`, `add_symbol`).
- Spec: `POST /v1/trading/accounts/{id}/positions` takes `instrument`, `side`, `volume`, `stop_loss_price` and `take_profit_price` and returns `202 {operation_id, client_request_id, status}`. `DELETE .../positions/{position_id}` closes a position. The events WS sends `transaction_event` with `client_request_id`, `status` (success/rejected/failed), `error_code` and `payload.{orders, positions, deals}`, where a deal has `type` open/close, `direction`, `volume`, `price`, `position_id` and `profit.amount`. `trading_state_snapshot` arrives on subscribe. `GET /v1/history/accounts/{id}/deals`.

## Goal
A broker type `exness` that converts quantity to lots inside the adapter. It always attaches SL, never exceeds the minimum lot unless the user raises `EXNESS_MAX_LOTS`, enforces a daily loss cap, and maps async fills and broker-side closes into the existing engine flow. Subscriptions can opt into a broker explicitly, with `paper` as the default.

## Files to Create or Modify
- Create: `src/pocketquant/core/infra/exness/broker.py`, `tests/core_test/infra/exness/test_broker.py` and `tests/engine_test/test_async_broker_fill_wiring.py`.
- Modify:
  - `src/pocketquant/core/config.py`
  - `src/pocketquant/core/domain/brokers/interfaces.py`
  - `src/pocketquant/engine/app_services/strategy_app_service.py`
  - `src/pocketquant/app/di/adapters.py` (`BrokerFactory`)
  - `src/pocketquant/app/di/services.py` (`default_broker_config`)
  - `src/pocketquant/core/domain/subscription/entities.py`
  - `src/pocketquant/engine/strategy_command_service.py`, `src/pocketquant/engine/strategy_query_service.py`
  - `src/pocketquant/app/routes/strategy.py`
  - `src/pocketquant/app/main_extensions.py`
  - `src/pocketquant/engine/app_services/strategy_reconcile_service.py`
  - `tests/baseline/openapi_app_snapshot.json`
  - `tests/engine_test/test_reconcile_restart_resume_integration.py`
  - `tests/app_test/integration/test_di_resolution_characterization.py`

## Tasks

### T7.1 Branch and settings
- **Goal:** Risk-cap configuration keys exist.
- **Target files and symbols:** `src/pocketquant/core/config.py` → `Settings.exness_daily_loss_cap: float | None = None` and `Settings.exness_max_lots: float | None = None`
- **Steps:**
  1. `git switch master && git pull --ff-only && git switch -c feat/exness-broker`
  2. Add the two fields after `exness_private_key_path`.
- **Success criteria:** Both fields are optional.
- **Verify:** `uv run pyright src/pocketquant/core/config.py` reports `0 errors`.

### T7.2 `IBroker.fills_async` and engine wiring
- **Goal:** Async-fill brokers deliver fills into `OrderAppService.on_order_update`. Paper and OKX stay unchanged.
- **Target files and symbols:** `interfaces.py` → `IBroker.fills_async: bool = False` (a class attribute, not abstract). `strategy_app_service.py` → `_get_or_create_broker`.
- **Steps:**
  1. Add `fills_async: bool = False` to `IBroker`.
  2. In `_get_or_create_broker`, after `broker = self._broker_factory.create(broker_type, config)`, add `if broker.fills_async: await broker.subscribe_order_updates(self._order_app_service.on_order_update)`. A reused broker found by name is returned before this line, so it is subscribed exactly once.
  3. Write `tests/engine_test/test_async_broker_fill_wiring.py` with a fake `IBroker` subclass that sets `fills_async=True`.
     - Its `submit_order` returns `OrderResult(status=SUBMITTED, broker_order_id="op1")`.
     - Load a strategy through a stub factory returning it, then submit an order through `OrderAppService.submit`.
     - Invoke the stored callback with `OrderResult(order_id=<id>, broker_order_id="op1", status=FILLED, filled_quantity=1, filled_price=10)`.
     - Assert one `OrderFilledEvent` was published (capture with an `EventBus` subscriber) and that `PositionAppService.get(sub_id)` is not None.
     - A second test: a `PaperBroker` from the factory is not subscribed, so `len(broker._order_callbacks) == 0` after `load_strategy`.
- **Success criteria:** The wiring is generic, with no venue name in the engine.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/engine_test/test_async_broker_fill_wiring.py -q` exits 0 with `passed`. `grep -c '"exness"' src/pocketquant/engine/app_services/strategy_app_service.py` prints `0`.

### T7.3 `broker.py`, the order path
- **Goal:** Submission enforces every live-safety rule before any HTTP call.
- **Target files and symbols:** `src/pocketquant/core/infra/exness/broker.py` → `class ExnessBroker(IBroker)`. Constructor: `(client: ExnessClient, event_bus: EventBus, position_repository: PositionRepository, daily_loss_cap: float | None, max_lots: float | None)`. Also `name -> "exness"`, `fills_async = True`, `is_connected` and `submit_order`.
- **Steps:**
  1. `submit_order(order)` returns `OrderResult(status=REJECTED, error_message=...)`, without any HTTP call, in this order:
     - (a) `order.order_type != OrderType.MARKET` → `"exness adapter supports market orders only"`
     - (b) `order.sl_price is None` → `"stop loss required"`
     - (c) `daily_loss_cap is None` → `"EXNESS_DAILY_LOSS_CAP not set"`
  2. Next check the daily loss with `deals = await client.deals_since(<UTC midnight ISO>)`. If `sum(float(d["profit"]["amount"]) for d in deals if d.get("profit")) <= -daily_loss_cap`, reject with `"daily loss cap reached"`.
  3. Next check open positions held by this broker for `order.subscription_id`, using the in-memory map `self._positions: dict[str, _Held]` (position_id → subscription_id, symbol, PositionSide, units, lots):
     - same direction → REJECTED `"position already open for subscription"`;
     - opposite direction → close it by calling `client.close_position(position_id, idempotency_key=str(order.id))` and return SUBMITTED with `broker_order_id=operation_id`.
  4. Otherwise convert the quantity:
     - `cond = await client.conditions(code)`;
     - `lots = units_to_lots(Decimal(str(order.quantity)), contract_size=Decimal(cond["contract_size"]), volume_min=..., volume_step=..., volume_max=..., max_lots=Decimal(str(max_lots)) if max_lots else None)`;
     - `None` → REJECTED `"quantity below minimum lot"`;
     - if the raw lots exceed `lots`, log a warning `exness.lots_clamped` with `requested` and `sent`.
  5. Register the in-flight order with `self._pending_ack.add(str(order.id))`. Send `client.open_position({"instrument": code, "side": "buy"|"sell", "volume": str(lots), "stop_loss_price": format_price(order.sl_price, cond["point_digits"]), **({"take_profit_price": ...} if order.tp_price else {})}, idempotency_key=str(order.id))`, and record `self._acked_at[str(order.id)] = time.monotonic()`.
  6. Log info `exness.order_submitted` with `order_id`, `operation_id`, `instrument`, `side`, `volume` and `volume_min`. An `ExnessApiError` becomes REJECTED with `error_message=f"{e.code}: {e.message}"`.
  7. In `finally`, run `self._pending_ack.discard(id)`. If `id in self._early`, schedule `asyncio.create_task(self._notify(self._early.pop(id)))`. That ordering lets `OrderAppService.submit` finish `order.submit(...)` under its lock first.
  8. Return `OrderResult(order_id, broker_order_id=operation_id, status=SUBMITTED, submitted_at, sl_price, tp_price, side)`.
- **Success criteria:** No live order can bypass the cap, the SL rule or the minimum lot.
- **Verify:** no verification needed; T7.5 covers this module.

### T7.4 `broker.py`, the events path and account state
- **Goal:** Fills, async rejections and broker-side closes reach the engine exactly once.
- **Target files and symbols:** `ExnessBroker.connect`, `disconnect`, `_on_event`, `_on_snapshot`, `_on_transaction`, `_notify`, `get_positions`, `get_balance`, `cancel_order`, `subscribe_order_updates` and `unsubscribe_order_updates`.
- **Steps:**
  1. `connect()` starts `ExnessStream(client, f"/v1/server-events/accounts/{account}/ws/events", on_message=self._on_event, on_connect=<send {"id":"tx","subscribe":{"event":"transactions"}}>, stale_after_s=None)` as a task and sets `_connected`. `disconnect()` closes the stream and cancels the task.
  2. For `event_type == "trading_state_snapshot"`, `_on_snapshot` rebuilds `self._positions` from `payload.positions` matched against `await position_repository.find_open()` by `pos.symbol == f"{instrument}:EXNESS"` and side. If more than one repository position matches, log an error `exness.position_map_ambiguous` and leave it unmapped.
  3. For `event_type == "transaction_event"`, `_on_transaction` works like this:
     - Let `rid = event.get("client_request_id")`. When `rid` is set and `rid in self._seen_terminal`, return (dedupe).
     - When `rid` is set and `status == "success"`, find the deal for `rid`'s operation. On an open deal, map its position into `self._positions`. On a close deal, remove the position from the map. Build `OrderResult(order_id=rid, broker_order_id=event["operation_id"], status=FILLED, filled_quantity=lots_to_units(Decimal(deal["volume"]), contract_size), filled_price=float(deal["price"]), side=...)` and log `exness.order_filled` with `order_id` and `ack_to_fill_ms=int((time.monotonic()-self._acked_at.pop(rid, now))*1000)`.
     - When `rid` is set and `status` is `rejected` or `failed`, build `OrderResult(status=CANCELLED, error_message=f"{error_code}: {error_message}")` and log a warning `exness.order_rejected_async`.
     - In both `rid` cases, add `rid` to `_seen_terminal`. If `rid in self._pending_ack`, store the result in `self._early[rid]`; otherwise `await self._notify(result)`.
     - When there is no `rid` and the payload has a deal with `type == "close"` whose `position_id` is in `self._positions`, publish `OrderFilledEvent(order_id=generate_id_str(), subscription_id=held.subscription_id, symbol=held.symbol, side=<opposite of held side>, filled_quantity=held.units, filled_price=float(deal["price"]))` on `event_bus`. Remove the position and log info `exness.position_closed_by_broker` with `reason` taken from the matching order's `reason` when present.
  4. For `event_type` `hmr_snapshot` or `hmr_update`, log info `exness.hmr_event`. Ignore `account_state_event`.
  5. `get_balance()` reads `snapshot()["account_state"]` and returns `AccountBalance(total_equity=float(equity), available_balance=float(equity)-float(used_margin), currency=<account currency from client.account() cached, default "USD">, margin_used=float(used_margin), unrealized_pnl=float(equity)-float(balance))`.
  6. `get_positions()` maps the snapshot positions to `PositionAggregate.open(subscription_id=<mapped or "">, symbol=f"{instrument}:EXNESS", side=..., entry_price=float(open_price), quantity=lots_to_units(...))`.
  7. `cancel_order(broker_order_id)` logs a warning `exness.cancel_unsupported` and returns False, because this adapter places market orders only.
- **Success criteria:** Every path is mapped, and nothing raises out of the WS listener.
- **Verify:** no verification needed; T7.5 covers this module.

### T7.5 Broker tests
- **Goal:** Pin every safety rule and the event mapping.
- **Target files and symbols:** `tests/core_test/infra/exness/test_broker.py`
- **Steps:**
  1. Fake client: `AsyncMock` with `conditions` returning `{"contract_size":"100","volume_min":"0.01","volume_step":"0.01","volume_max":"200","point_digits":2}`, `deals_since` returning `[]`, and `open_position` returning `{"operation_id":"op1","client_request_id":"<id>","status":"accepted"}`.
  2. Rejections with no HTTP call (assert `open_position.await_count == 0`):
     - a LIMIT order;
     - `sl_price=None`;
     - `daily_loss_cap=None`;
     - deals summing to `-60` with cap `50`;
     - quantity `0.5` (below the minimum lot).
  3. Quantity `7.9` with `max_lots=None` sends `volume == "0.01"` and logs `exness.lots_clamped`.
  4. An entry `transaction_event` (success, with a deal `{type:"open", volume:"0.01", price:"2345.10", position_id:"p1", direction:"buy"}`) calls the callback once with `FILLED`, `filled_quantity == 1.0` and `filled_price == 2345.10`. A duplicate event does not call it again.
  5. An event that arrives while the id is in `_pending_ack` is delivered exactly once, after `submit_order` returns. Simulate this by making `open_position` invoke `_on_event` before returning.
  6. A `rejected` event with `error_code "TRADING_RULE_INSUFFICIENT_MARGIN"` produces status `CANCELLED`, with the code in `error_message`.
  7. After the entry fill, an event with no `client_request_id` and a `close` deal for `p1` publishes one `OrderFilledEvent` with side `SELL` and the mapped `subscription_id`.
  8. With the position already held, an opposite-direction order calls `close_position("p1", idempotency_key=<order id>)` and does not call `open_position`.
  9. A same-direction order is REJECTED.
  10. Under `capture_logs()`, no captured event contains the API key string.
- **Success criteria:** All tests pass.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_broker.py -q` exits 0 with `passed`.

### T7.6 Broker factory entry `exness`
- **Goal:** Strategies can select `exness`.
- **Target files and symbols:** `app/di/adapters.py` → `BrokerFactory.__init__(self, event_bus: EventBus, exness_client: ExnessClient, position_repository: PositionRepository)`, `create` and `get_available_types`. `app/di/services.py` → the `default_broker_config` dict in the `StrategyAppService` factory.
- **Steps:**
  1. Add the branch `elif broker_type == "exness":`. If `not self._exness_client.is_configured`, raise `ValueError("exness broker requires EXNESS_* settings")`. Otherwise return `ExnessBroker(self._exness_client, self._event_bus, self._position_repository, daily_loss_cap=config.get("exness_daily_loss_cap"), max_lots=config.get("exness_max_lots"))`.
  2. `get_available_types()` returns `["paper", "okx", "exness"]`.
  3. In the services factory, add `"exness_daily_loss_cap": settings.exness_daily_loss_cap` and `"exness_max_lots": settings.exness_max_lots` to `default_broker_config`.
  4. Update `test_reconcile_restart_resume_integration.py` to pass an unconfigured `ExnessClient` (Settings stub with `exness_*` set to None) and the test's own position repository object. Read that test's lines 55–80 to find the variable name.
  5. Update `test_di_resolution_characterization.py`: `get_available_types() == ["paper","okx","exness"]`, and `create("exness", {})` raises `ValueError` when Exness is unconfigured.
- **Success criteria:** The paper and OKX branches are byte-identical.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/app_test/integration/test_di_resolution_characterization.py tests/engine_test/test_reconcile_restart_resume_integration.py -q` exits 0 with `passed`.

### T7.7 Explicit broker choice per subscription
- **Goal:** A subscription opts into a live broker explicitly, with `paper` as the default. Without this, the engine always builds `StrategyConfig(broker="paper")` (`main_extensions.py:152`, `strategy_reconcile_service.py:141`).
- **Target files and symbols:** `Subscription.broker`, `CreateSubscriptionBody.broker`, `AddSymbolCommand.broker`, `StrategyCommandService.add_symbol`, `StrategyQueryService.list_symbols` and the two `StrategyConfig(...)` sites.
- **Steps:**
  1. `Subscription`: append the field `broker: str = "paper"` after `actual_state`, write `"broker": self.broker` in `to_mongo`, and read `broker=doc.get("broker", "paper")` in `from_mongo`.
  2. `CreateSubscriptionBody`: add `broker: Literal["paper", "okx", "exness"] = "paper"`. `AddSymbolCommand`: add `broker: str = "paper"`. In the route, pass `broker=body.broker`. `add_symbol` sets `broker=cmd.broker` on the `Subscription` and includes `"broker"` in the returned dict. `list_symbols` includes `"broker": sub.broker`.
  3. Add `broker=sub.broker` to the `StrategyConfig(...)` calls at `main_extensions.py:152` and `strategy_reconcile_service.py:141`.
  4. Regenerate the snapshot with `BASELINE_UPDATE=1 .venv/Scripts/python.exe -m pytest tests/baseline/test_openapi_snapshot.py -q`.
- **Success criteria:** The only OpenAPI change is the new optional property.
- **Verify:**
  - `uv run python -c "import json,subprocess;old=json.loads(subprocess.check_output(['git','show','HEAD:tests/baseline/openapi_app_snapshot.json']));new=json.load(open('tests/baseline/openapi_app_snapshot.json',encoding='utf-8'));del new['components']['schemas']['CreateSubscriptionBody']['properties']['broker'];print(old==new)"` prints `True`.
  - `.venv/Scripts/python.exe -m pytest tests/baseline tests/core_test/unit/domain/subscription tests/app_test/integration/test_strategy_subscriptions_api.py -q` exits 0.

### T7.8 Phase gate
- **Goal:** Full green.
- **Target files and symbols:** whole repo
- **Steps:**
  1. `just test 2>&1 | tail -n 3`
  2. `uv run ruff check`
  3. `uv run pyright`
  4. `uv run lint-imports`
  5. The venue command.
  6. `uv run python scripts/code_metrics.py --json > /tmp/m.json`
- **Success criteria:** Green, with no function over 60 lines in `exness/broker.py`.
- **Verify:**
  - Steps 1–4 meet the same pass conditions as T4.6.
  - Step 5's count equals the baseline.
  - `uv run python -c "import json;d=json.load(open('/tmp/m.json'));print([f for f in d['functions_over_60'] if 'exness' in f])"` prints `[]`.

### T7.9 Ship (no live order yet)
- **Goal:** The broker is deployed. No subscription uses it yet.
- **Target files and symbols:** git
- **Steps:**
  1. `git add -A src tests`
  2. `git commit -m "feat(exness): add exness broker with lot conversion, async fill mapping and live risk caps"`
  3. Ask the user for approval, then merge, push and watch CI.
- **Success criteria:** Deployed.
- **Verify:** `gh run watch` exits 0.

## Verification
T7.2 (wiring), T7.5 (safety and mapping), T7.6 (factory), T7.7 (OpenAPI diff limited to `broker`) and T7.8 (gate).

## Risks
- **A fill arrives before the ACK** (M/H). Handled by the `_pending_ack` and `_early` stash with the `create_task` hand-off, so `OrderAppService` holds its lock while running `order.submit`. T7.5 step 5 covers it.
- **A hedging account opens a hedge instead of closing** (M/H). Mitigation: an opposite-direction order closes the held position, and a same-direction order is rejected.
- **The position map is lost on restart** (M/M). Mitigation: it is rebuilt from `trading_state_snapshot` plus `PositionRepository.find_open()`. During validation, each strategy trades a different instrument, so the matching stays unambiguous.
- **Sizing above the minimum lot** (L/H). The cap defaults to `volume_min`. If the user asks to raise `EXNESS_MAX_LOTS`, that is a stop-and-ask decision for the user.

## Security
Every live-money rule is in code: SL required, the minimum-lot cap, the daily loss cap and market orders only. Secrets are never logged, which T7.5 asserts.

## Rollback
`git revert` the merge commit and push. Old code ignores the extra `broker` key in subscription docs, because `from_mongo` reads explicit keys only.

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

<!-- FILE: phase-08-validation-spread-backtests-live.md -->
---
phase: 8
title: "Validation: spread, backtests, live round trip"
status: pending
priority: P1
effort: 7d + weekend
dependencies: [7]
---

# Phase 08: Validation (spread, backtests, live round trip, weekend)

## Context Links
- Advice §2.8 and §3 (bid-only backtests flatter shorts; never go above the minimum lot).
- PaperBroker price function: `src/pocketquant/core/infra/brokers/paper/paper_broker.py:436` (`_apply_slippage`), with call sites at :199, :261, :617 and :678. Constructor at :93.
- Backtest plumbing:
  - `src/pocketquant/backtest/backtest_command_service.py:22` (`RunBacktestCommand`, `run` config dict)
  - `src/pocketquant/backtest/workers/backtest_dispatch.py` (`_config_from_dict`, `run_single` → `sandbox.create_broker`)
  - `src/pocketquant/backtest/models/backtest_config.py:9`
  - `src/pocketquant/backtest/engine/backtest_engine_sandbox.py:110` (`create_broker`)
- Run API: `POST /api/v1/backtest/run` returns 202 `{"request_id"}`. `GET /api/v1/backtest/{run_id}` returns `status` started, finished or failed. `GET /api/v1/backtest/{run_id}/trades`.
- Spike journal median spreads: `docs/journals/*-exness-api-spike.md`.

## Goal
Make D3 and D2 true. CFD backtests must account for the spread, and each strategy completes one minimum-lot live round trip with SL. One week including a weekend is then observed.

## Files to Create or Modify
- Modify: `paper_broker.py`, `backtest_command_service.py`, `backtest_dispatch.py`, `backtest_config.py`, `backtest_engine_sandbox.py` and `tests/baseline/openapi_app_snapshot.json`.
- Create: `tests/backtest_test/engine/test_paper_broker_spread.py`.
- Create reports: `plans/261009-0858-exness-venue-lean-sync-refactor/reports/exness-backtest-results.md` and `.../reports/exness-live-week.md`.

## Tasks

### T8.1 Branch and the PaperBroker `spread` parameter
- **Goal:** Longs fill at the price plus half the spread, shorts at the price minus half the spread. The default `0.0` keeps today's results.
- **Target files and symbols:** `PaperBroker.__init__(..., spread: float = 0.0)` and `_apply_slippage`, renamed to `_execution_price`.
- **Steps:**
  1. `git switch master && git pull --ff-only && git switch -c feat/paper-spread-validation`
  2. Store `self._spread = spread`. Rename `_apply_slippage` to `_execution_price` and update its 4 call sites. The body becomes `price * (1 + self._slippage) + self._spread / 2` for BUY and `price * (1 - self._slippage) - self._spread / 2` for SELL.
  3. Write `tests/backtest_test/engine/test_paper_broker_spread.py`:
     - a MARKET BUY with `price=100`, `slippage_percent=0` and `spread=0.4` fills at `100.2`;
     - a SELL fills at `99.8`;
     - a long SL synthetic exit at `sl=95` fills at `94.8`, driven through `_on_bar_completed` with a bar whose low is below 95;
     - `spread=0` gives the same fills as before.
- **Success criteria:** Existing paper tests are untouched and still pass.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/backtest_test/engine/test_paper_broker_spread.py -q` exits 0 with `passed`. The venue command's `passed` count equals the baseline.

### T8.2 Backtest plumbing for `spread`
- **Goal:** The API accepts a constant spread in price units.
- **Target files and symbols:**
  - `RunBacktestCommand.spread: float = Field(default=0.0, ge=0, description="Constant bid/ask spread in price units; longs fill +spread/2, shorts -spread/2")`
  - `BacktestCommandService.run` config key `"spread"`
  - `BacktestConfig.spread: float = 0.0`
  - `_config_from_dict` with `spread=payload.get("spread", 0.0)`
  - `BacktestSandbox.create_broker(..., spread: float = 0.0)`, which passes it to `PaperBroker`
  - `run_single`, which passes `spread=config.spread`
- **Steps:**
  1. Apply each of the edits above.
  2. Regenerate the snapshot with `BASELINE_UPDATE=1 .venv/Scripts/python.exe -m pytest tests/baseline/test_openapi_snapshot.py -q`.
- **Success criteria:** The only OpenAPI change is `RunBacktestCommand.spread`.
- **Verify:** `uv run python -c "import json,subprocess;old=json.loads(subprocess.check_output(['git','show','HEAD:tests/baseline/openapi_app_snapshot.json']));new=json.load(open('tests/baseline/openapi_app_snapshot.json',encoding='utf-8'));del new['components']['schemas']['RunBacktestCommand']['properties']['spread'];print(old==new)"` prints `True`.

### T8.3 Gate and ship
- **Goal:** `spread` is in prod.
- **Target files and symbols:** git
- **Steps:**
  1. Run the gate (`just test`, `uv run ruff check`, `uv run pyright`, `uv run lint-imports` and the venue command).
  2. `git add -A src tests`
  3. `git commit -m "feat(backtest): add constant spread parameter to paper broker fills"`
  4. Ask the user for approval, then merge, push and watch CI.
- **Success criteria:** Green.
- **Verify:** The gate meets the T4.6 pass conditions. `gh run watch` exits 0.

### T8.4 Backfill Exness history in prod
- **Goal:** Enough Exness bars for backtests: M1 for 90 days and H1 for 730 days, on 3 instruments.
- **Target files and symbols:** `scripts/backfill/exness_bars.py` on the VPS
- **Steps:**
  1. Run for each `S` in XAUUSD, EURUSD and BTCUSD, using the remote pattern:
     ```bash
     ssh -i "$KEY" "$HOST" 'docker exec -i pocketquant-app sh -s' <<'EOF'
     python scripts/backfill/exness_bars.py --symbol XAUUSD:EXNESS --interval 1m --days 90
     python scripts/backfill/exness_bars.py --symbol XAUUSD:EXNESS --interval 1h --days 730
     EOF
     ```
     Substitute `S` for XAUUSD on the other instruments. Run one instrument per ssh call, to stay under the 10-minute command limit.
- **Success criteria:** The bar counts are plausible for each calendar.
- **Verify:** On each output line, `total_bars` meets these minimums:
  - 1m: EURUSD and XAUUSD ≥ 60000, BTCUSD ≥ 120000
  - 1h: EURUSD and XAUUSD ≥ 8000, BTCUSD ≥ 16000

### T8.5 Backtests of both strategies on Exness bars
- **Goal:** D3 holds.
- **Target files and symbols:** `POST /api/v1/backtest/run`, `GET /api/v1/backtest/{run_id}`, `GET /api/v1/backtest/{run_id}/trades?limit=1`
- **Steps:**
  1. For each `S` in XAUUSD, EURUSD and BTCUSD, post two runs, using `SPREAD_S` = the journal's median spread for S:
     - `{"strategy_id":"hitnrun2","symbol":"S:EXNESS","interval":"1m","start_date":"<now-30d ISO, minute precision>","end_date":"<now ISO>","initial_capital":10000,"slippage_bps":0,"commission_bps":0,"spread":SPREAD_S}`
     - `{"strategy_id":"engulfing","symbol":"S:EXNESS","interval":"1h","start_date":"<now-365d>","end_date":"<now>","initial_capital":10000,"slippage_bps":0,"commission_bps":0,"spread":SPREAD_S}`
  2. Record each `request_id`. Poll `GET /api/v1/backtest/{id}` every 60 s (at most 30 times per run) until `status` is not `started`.
  3. Write `exness-backtest-results.md` with one table row per run: strategy, symbol, run_id, status, trade count (from `/trades`), total return and max drawdown.
- **Success criteria:** All 6 runs are `finished`, and each strategy has at least one run with trades.
- **Verify:** Each `GET /api/v1/backtest/{id}` contains `"status":"finished"`. For each strategy, at least one `GET .../trades?limit=1` returns a non-empty JSON list (`python -c "import json,sys;print(len(json.load(sys.stdin))>0)"` prints `True`).

### T8.6 Live risk-cap precondition (stop-and-ask gate)
- **Goal:** Live money moves only under the user's explicit, recorded consent.
- **Target files and symbols:** `.../reports/user-preconditions.md`
- **Steps:**
  1. Ask the user verbatim: "U3: Is EXNESS_DAILY_LOSS_CAP set in pocketquant-config and deployed, with EXNESS_MAX_LOTS unset so orders use the minimum lot, and do you approve starting one live Exness subscription per strategy (hitnrun2 on XAUUSD:EXNESS 1m, engulfing on EURUSD:EXNESS 1h)?"
  2. Append `U3: approved` or `U3: declined` to `user-preconditions.md`. On `declined`, STOP.
  3. If the user wants a lot size above the minimum, STOP. That is a stop-and-ask condition outside this plan.
- **Success criteria:** Approval is recorded.
- **Verify:** `grep -c "U3: approved" .../reports/user-preconditions.md` prints `1`.

### T8.7 Live round trip per strategy
- **Goal:** D2 holds.
- **Target files and symbols:** `POST /api/v1/strategies/{code}/subscriptions`, `POST /api/v1/subscriptions/{id}/start`, `GET /api/v1/trading/positions`, `GET /api/v1/trading/orders`, `GET /api/v1/subscriptions/{id}/trades`, container logs
- **Steps:**
  1. Using the remote pattern, create the two subscriptions:
     ```bash
     curl -s -X POST http://localhost:41921/api/v1/strategies/hitnrun2/subscriptions -H "Content-Type: application/json" -d '{"symbol":"XAUUSD:EXNESS","interval":"1m","broker":"exness"}'
     curl -s -X POST http://localhost:41921/api/v1/strategies/engulfing/subscriptions -H "Content-Type: application/json" -d '{"symbol":"EURUSD:EXNESS","interval":"1h","broker":"exness"}'
     ```
     Record the returned `id`s, then `POST /api/v1/subscriptions/<id>/start` for each.
  2. Every 4 hours during market hours, for at most 5 trading days, run `ssh -i "$KEY" "$HOST" "docker logs pocketquant-app --since 5h 2>&1 | grep -E 'exness\.(order_submitted|order_filled|order_rejected_async|position_closed_by_broker|lots_clamped)'"`. If 5 trading days pass without a fill for a strategy, STOP and report to the user. A missing signal is not a code failure.
  3. Whenever an `exness.order_submitted` line has `volume` different from `volume_min`, STOP at once, stop both subscriptions with `POST /api/v1/subscriptions/<id>/stop`, and ask the user. That is the stop-and-ask condition.
  4. After the fill, `curl -s http://localhost:41921/api/v1/trading/positions` must show the subscription id. After the exit, `curl -s http://localhost:41921/api/v1/subscriptions/<id>/trades` must be non-empty.
- **Success criteria:** Each strategy has one entry fill, a position, and an exit.
- **Verify:** For each strategy:
  - at least one `exness.order_filled` log line has `ack_to_fill_ms` ≤ 10000;
  - `GET /trading/positions` output contains the subscription id while the position is open;
  - after the exit, `GET /subscriptions/<id>/trades` returns a non-empty list (`python -c` length check prints `True`);
  - every `exness.order_submitted` line has `volume` equal to `volume_min`.

### T8.8 One week including a weekend
- **Goal:** Calendar and staleness behave correctly. This is the advice §9 success metric.
- **Target files and symbols:** `.../reports/exness-live-week.md`, container logs
- **Steps:**
  1. On the Monday after the weekend, run:
     - `ssh -i "$KEY" "$HOST" "docker logs pocketquant-app --since 168h 2>&1 | grep -c 'exness_ws.circuit_breaker_open'"`
     - `ssh -i "$KEY" "$HOST" "docker logs pocketquant-app --since 168h 2>&1 | grep 'integrity.issues_found' | grep -cE 'XAUUSD:EXNESS|EURUSD:EXNESS'"`
     - `ssh -i "$KEY" "$HOST" "docker logs pocketquant-app --since 168h 2>&1 | grep -c 'exness_ws.reconnecting'"`
  2. Write the three numbers and the `exness-backtest-results.md` summary to `exness-live-week.md`.
  3. Ask the user whether to keep the two live subscriptions running or stop them. Run `POST /api/v1/subscriptions/<id>/stop` if they say stop.
- **Success criteria:** Zero circuit-breaker trips and zero FX integrity alarms.
- **Verify:** The first command prints `0` and the second prints `0`. The third has no pass condition; record its value only.

## Verification
T8.1 and T8.2 (spread, OpenAPI diff), T8.4 and T8.5 (D3), T8.7 (D2) and T8.8 (week metrics).

## Risks
- **Swap costs are not modelled** (known, accepted in the advice). They are noted in the results report and not built.
- **The account is too small for the sizer**: a quantity below the minimum lot is REJECTED, so no live trade happens. Mitigation: T8.7 step 2 makes this a stop-and-report.
- **Live funds** (L/H). Mitigation: the minimum lot, SL and daily cap are in code, the user's approval gates the step, and step 3 stops the run immediately on any oversized order.

## Security
No credentials are printed. The admin token and keys stay in the container env.

## Rollback
Stop the subscriptions with `POST /api/v1/subscriptions/<id>/stop` and close any open position from the Exness Personal Area. Then `git revert` the spread merge commit. `spread` defaults to 0, so reverting is safe.

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

<!-- FILE: phase-09-docs-architecture-deployment-mt5.md -->
---
phase: 9
title: "Architecture, deployment and MT5 docs"
status: pending
priority: P2
effort: 1d
dependencies: [8]
---

# Phase 09: Architecture, deployment and MT5 docs

## Context Links
- Advice §2.9. `CLAUDE.md` docs rules: Vietnamese prose, English terms, AS-IS only, no banners, Mermaid v11 for 2+ parts.
- `docs/system-architecture.md` sections: "Where Does X Live?" (:455), "Real-Time Streaming" (:553), "Broker & Middleware" (:573), "Dependency Injection (Dishka)" (:604). The stale rows to fix are "Dishka DI container (6 providers)" (:472) and "Background sync job registration" (:483).
- `docs/deployment.md` "Environment & Credentials" (:62, the key prod env table). `scripts/README.md`. `README.md` lines 3 and 11 (Binance-only wording). `docs/project-overview-pdr.md:260` ("Max 200 LOC per file"). `docs/README.md` code-standards row.

## Goal
The docs describe the system as it is now (D7): the Exness adapters, the sync-policy pattern and shared runner, 3 DI providers, the new env keys, and MT5 as a documented future provider that is not built.

## Files to Create or Modify
- Modify: `docs/system-architecture.md`, `docs/deployment.md`, `scripts/README.md`, `README.md`, `docs/project-overview-pdr.md` and `docs/README.md`.

## Tasks

### T9.1 Branch and `system-architecture.md`
- **Goal:** D7 holds.
- **Target files and symbols:** `docs/system-architecture.md`
- **Steps:**
  1. `git switch master && git pull --ff-only && git switch -c docs/exness-architecture`
  2. Add `## Market Data Sync Policy`: the `SyncPolicy` fields table, the Binance and Exness policy values, a Mermaid v11 `flowchart` of `APScheduler → sync_runner → (SyncPolicy) → SyncService → DataProviderRouter → BinanceClient | ExnessDataProvider → BarRepository (+ cascade_aggregator when cascade)`, and the 3-file flow list (`routes/market_data.py → sync_service.py → bar_repository.py`; `sync_runner.py → sync_service.py → bar_integrity.py | cascade_aggregator.py`).
  3. "Real-Time Streaming": add the Exness ticks WS (`ExnessQuoteProvider` via `QuoteProviderRouter`, at most 1 tick per 500 ms, bid used as `last_price`) and the Exness events WS (`ExnessBroker`, fills and broker-side closes).
  4. "Broker & Middleware": add `ExnessBroker` with its rules: market orders only, SL required, lots computed inside the adapter (`contract_size`, `volume_step`, `volume_min` cap unless `EXNESS_MAX_LOTS`), the daily loss cap, `fills_async`, and subscription `broker` opt-in.
  5. "Dependency Injection": 3 providers (`InfrastructureProvider`, `AdaptersProvider`, `ServicesProvider`), `Settings` via `from_context`, and `STRICT_VALIDATION`.
  6. "Where Does X Live?": fix the rows at :472 and :483, and add rows for `engine/market_data/sync_policy.py`, `sync_runner.py`, `bar_integrity.py`, `core/infra/exness/`, `core/infra/venue_router.py` and `scripts/code_metrics.py`.
  7. Add `## MT5 (future provider, not built)`: the same 3 ports, a policy sketch (bar source `copy_rates_from`, live source `copy_ticks_from`, `order_send` behind `IBroker`), the Windows host or Wine bridge (`mt5linux`/`mt5-remote`) deployment constraint, and the fact that Exness API keys apply to Exness-platform accounts, not MT5 accounts.
- **Success criteria:** No stale statements remain.
- **Verify:**
  - `grep -cE "SyncPolicy|sync_runner.py|core/infra/exness|copy_rates_from|ExnessBroker" docs/system-architecture.md` is ≥ 5.
  - `grep -cE "sync_jobs|sync_internals|6 providers|Last Updated" docs/system-architecture.md` prints `0`.

### T9.2 Deployment, scripts and README
- **Goal:** Operators can configure and run Exness.
- **Target files and symbols:** `docs/deployment.md` (the env table and a new runbook section `## Exness History Backfill`), `scripts/README.md`, `README.md`, `docs/project-overview-pdr.md:260` and `docs/README.md`.
- **Steps:**
  1. `deployment.md`: add these rows to the env table: `EXNESS_API_BASE_URL`, `EXNESS_ACCOUNT_ID`, `EXNESS_API_KEY`, `EXNESS_PRIVATE_KEY` / `EXNESS_PRIVATE_KEY_PATH` (No, live Exness only), `EXNESS_DAILY_LOSS_CAP` (required for live Exness orders) and `EXNESS_MAX_LOTS` (No; unset means the minimum lot). Add the runbook section with the `docker exec pocketquant-app python scripts/backfill/exness_bars.py ...` command from Phase 08 T8.4.
  2. `scripts/README.md`: one line each for `exness_spike.py` (read-only diagnostics), `backfill/exness_bars.py` and `code_metrics.py` (soft gate).
  3. `README.md` line 3: mention Exness (REST/WS, signed) next to Binance. Line 11: add `exness` to the adapter list.
  4. `docs/project-overview-pdr.md:260`: replace `Max 200 LOC per file (exceptions documented)` with `File ~400 LOC soft guidance, functions ≲60 lines (xem code-standards.md)`.
  5. `docs/README.md` code-standards row: replace `file-size rules` with `rules of thumb, sync policy pattern, quality gate`.
- **Success criteria:** No stale claims remain and the links are valid.
- **Verify:**
  - `grep -c "EXNESS_DAILY_LOSS_CAP" docs/deployment.md` is ≥ 1.
  - `grep -c "200 LOC" docs/project-overview-pdr.md` prints `0`.
  - `grep -c "Exness" README.md` is ≥ 1.
  - `grep -c "code_metrics.py" scripts/README.md` prints `1`.

### T9.3 Ship
- **Goal:** The docs are merged. CI `paths-ignore` skips the deploy for docs-only changes.
- **Target files and symbols:** git
- **Steps:**
  1. `git add docs README.md scripts/README.md`
  2. `git commit -m "docs: describe exness adapters, sync policy pattern and mt5 future provider"`
  3. Ask the user for approval, then `git switch master && git merge --ff-only docs/exness-architecture && git push origin master`.
- **Success criteria:** The commit is on master.
- **Verify:** `git log origin/master -1 --format=%s` prints `docs: describe exness adapters, sync policy pattern and mt5 future provider`.

## Verification
T9.1 and T9.2 greps, plus T9.3.

## Risks
- **The docs drift into change narrative.** Mitigation: the greps for banned words, and the AS-IS rule in `CLAUDE.md`.

## Rollback
`git revert` the docs commit.

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
