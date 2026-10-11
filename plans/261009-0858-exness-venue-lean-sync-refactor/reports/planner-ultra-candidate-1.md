<!-- FILE: plan.md -->
---
title: "Exness venue + lean sync-policy refactor"
description: "Refactor the market-data sync into one SyncPolicy runner (Binance first, behaviour pinned), slim DI/routes/standard, then add Exness REST+WS data, quotes and broker as policy #2 and validate both strategies on CFD data."
status: pending
priority: P1
effort: 33.5d
branch: master
tags: [exness, market-data, refactor, broker, sync-policy, code-standards]
blockedBy: []
blocks: []
created: 2026-10-09
---

# Exness venue + lean sync-policy refactor

## Overview

Exness becomes a third live venue behind the existing ports (`IDataProvider`, `IRealtimeQuoteProvider`, `IBroker`). Before that, the sync pipeline is rebuilt as one shared runner driven by a per-exchange `SyncPolicy`, with Binance as the proving provider and its behaviour pinned by characterization tests. Binance, OKX, PaperBroker, `hitnrun2` and `engulfing` all stay. MT5 is documented only. No MCP, no deployment-topology change.

Source of truth: advice `D:/w/_me/algotrading/plans/reports/advise-261008-1148-exness-api-replacement.md` (§2, §9) and state `...-state.md` (R1-R8, D1-D7, A-i..A-v).

## Goals

- G1 Exness is a usable live venue (candles, ticks, orders, account) next to Binance/OKX.
- G2 Adding a provider = adapter package + one policy; any flow readable in ≤3 files.
- G3 `docs/code-standards.md` is a standard the code actually follows, enforced by ruff, 3 import-linter contracts and a soft metric gate.

## Phases

| # | Phase | Effort | Depends on |
|---|-------|--------|------------|
| 01 | [Exness read-only spike](./phase-01-exness-read-only-spike.md) | 1.5d | user preconditions |
| 02 | [Characterization tests and metrics baseline](./phase-02-characterization-and-metrics-baseline.md) | 2d | - |
| 03 | [SyncPolicy and shared runner (Binance)](./phase-03-sync-policy-and-shared-runner.md) | 5d | 02 |
| 04 | [DI, routes and import contracts consolidation](./phase-04-di-routes-and-contracts-consolidation.md) | 2d | 03 |
| 05 | [Lean pass, metric gate and code standard](./phase-05-lean-pass-and-code-standard.md) | 5d | 04 |
| 06 | [Exness market-data adapters (policy #2)](./phase-06-exness-market-data-adapters.md) | 6d | 01, 05 |
| 07 | [Exness broker and live routing](./phase-07-exness-broker-and-live-routing.md) | 5d | 06 |
| 08 | [CFD validation and live round trip](./phase-08-cfd-validation-and-live-round-trip.md) | 6d + 1 weekend | 07 |
| 09 | [Architecture and deployment docs](./phase-09-architecture-and-deployment-docs.md) | 1d | 08 |

## Dependencies

- 01 and 02 touch disjoint files and may run in parallel; everything from 03 on is sequential (shared files: `sync_service.py`, `app/di/*`, `main_extensions.py`, `pyproject.toml`).
- 06 needs 01's fixtures/findings and 05's final module layout.
- Every phase ends with the gate (`just test`, `uv run ruff check`, `uv run pyright`, `uv run lint-imports`) and a user-approved commit + push (CI deploys `master`).

## Success Criteria (from advice §9, measurable)

- D1 `POST /api/v1/market-data/sync` `{"symbol":"XAUUSD:EXNESS","interval":"1m","n_bars":1000}` returns `status=completed`, `total_bars>=1000`; bar SSE for `XAUUSD%3AEXNESS` emits `"is_in_progress": true` within 60 s in market hours; quote SSE emits a `bid`.
- D2 One min-lot live order per strategy reaches `FILLED` via events WS ≤10 s after ACK and appears in `GET /api/v1/trading/positions`.
- D3 `hitnrun2` and `engulfing` Exness backtests finish (`status=finished`) with ≥1 trade; PaperBroker has `spread`.
- D4 `engine/market_data/sync_internals/` absent; `app/di` has 3 provider modules; market-data routes in 2 files; `scripts/code_metrics.py` tiny share ≤0.30, delegations ≤20.
- D5 `docs/code-standards.md` rewritten, no stale status claims; `uv run lint-imports` → `Contracts: 3 kept, 0 broken.`
- D6 Binance/OKX characterization + existing tests green with unchanged pass counts; full gate green; CI deploy (incl. `11-verify.sh`) green.
- D7 `docs/system-architecture.md` shows Exness adapters, the sync-policy pattern, and MT5 as a future provider.

## User preconditions (plan gates on them; executor never performs them)

- Follow the Developer Portal link from the Exness Personal Area and confirm it resolves to `exness-api.com`.
- Create a scoped API key (one account; IP allowlist = VPS IP, plus the spike host if different); put `EXNESS_BASE_URL`, `EXNESS_ACCOUNT_ID`, `EXNESS_API_KEY`, `EXNESS_PRIVATE_KEY` (or `EXNESS_PRIVATE_KEY_PATH`, file outside the repo) in `pocketquant-config` / local env.
- Before Phase 08 live steps: set `EXNESS_MAX_LOTS` (= instrument minimum lot), `EXNESS_DAILY_LOSS_LIMIT`, then `EXNESS_LIVE_TRADING=true`. SL is always enforced in code.
- Key material is never printed, logged or committed.

## Open decisions (flagged, not reopened)

- Metric definitions (Phase 02): delegation reproduces the advice's 63 exactly; tiny is counted recursively (338/794 = 42.6%; a top-level count gives 46.9% and calls try-wrapped 80-line functions tiny). Projection: tiny ≈0.30-0.32 and delegations ≈35-45 after legitimate packages, because 14 of the 63 are FastAPI route one-liners. Phase 05 Task 5.6 stops for a user decision if either threshold is missed.
- Live routing uses an env kill switch (`EXNESS_LIVE_TRADING` → `*:EXNESS` subscriptions trade on Exness) instead of a per-subscription API field, so the subscription API and stored docs stay unchanged.

<!-- FILE: phase-01-exness-read-only-spike.md -->
---
phase: 1
title: "Exness read-only spike"
status: pending
priority: P1
effort: 1.5d
dependencies: []
---

# Phase 01: Exness read-only spike

## Context Links

- Advice §2.1, §8 (unverified items): `D:/w/_me/algotrading/plans/reports/advise-261008-1148-exness-api-replacement.md`
- Exness facts: `D:/w/_me/algotrading/plans/reports/advise-261008-1148-exness-api-replacement-state.md` (scout-findings → Exness API)
- Spec: `https://www.exness-api.com/exness_api.yaml` v1.0.2 — signing rules in `info.description`; candles `/v1/market-data/accounts/{account_id}/candles`; limits `/v1/configuration/accounts/{account_id}/limits` (`limits.rest.methods[].limits.max_candles_per_request`, `rate_limit.{limit,window_seconds}`, `limits.rest.global_account_rate`); WS `/v1/server-events/accounts/{account_id}/ws/ticks` and `/ws/events` (handshake signed as GET); `InstrumentConditionResponse.trade_sessions[].{week_start_time,week_end_time}` (UTC).
- The spec has `servers: - url: /` — the REST host is not in the spec; it comes from the Developer Portal (user supplies `EXNESS_BASE_URL`).

## Goal

Settle A-i..A-v and the advice's unverified items with real numbers from a read-only script, and save redacted responses as test fixtures. No `src/` change in this phase (keeps the Phase 02 metric baseline exact).

## Files to Create or Modify

- Create: `scripts/exness_spike.py`, `tests/scripts/test_exness_spike.py`, `tests/core_test/infra/exness/fixtures/*.json|*.jsonl`, `plans/261009-0858-exness-venue-lean-sync-refactor/reports/exness-spike-findings.md`
- Modify: `pyproject.toml` (`[project].dependencies` add `cryptography`), `uv.lock`

## Tasks

### Task 1.1 — Confirm user preconditions
- **Goal:** the portal domain and key are confirmed by the user before any key is used.
- **Target files and symbols:** none (chat with user).
- **Steps:**
  1. Ask the user: "Does the Developer Portal link in your Exness Personal Area resolve to exness-api.com? Is the API key created with an IP allowlist that includes the machine that will run the spike? Are EXNESS_BASE_URL, EXNESS_ACCOUNT_ID, EXNESS_API_KEY and EXNESS_PRIVATE_KEY (or EXNESS_PRIVATE_KEY_PATH, a file outside the repo) exported in this shell?"
  2. If the portal link does not resolve to `exness-api.com`: STOP and report to the user (stop-and-ask condition). Do not continue any Exness phase.
- **Success criteria:** user answers yes to all three.
- **Verify:** `python -c "import os;k=['EXNESS_BASE_URL','EXNESS_ACCOUNT_ID','EXNESS_API_KEY'];print(all(os.environ.get(x) for x in k) and bool(os.environ.get('EXNESS_PRIVATE_KEY') or os.environ.get('EXNESS_PRIVATE_KEY_PATH')))"` prints exactly `True` (values are never printed).

### Task 1.2 — Environment and dependency
- **Goal:** project venv exists and `cryptography` (Ed25519) is a runtime dependency (today it is only transitive via the dev-only `secretstorage`).
- **Target files and symbols:** `pyproject.toml` `[project].dependencies`; `uv.lock`.
- **Steps:**
  1. `uv sync`
  2. `uv add "cryptography>=46.0"`
- **Success criteria:** `pyproject.toml` lists `cryptography>=46.0` under `[project].dependencies`.
- **Verify:** `uv run python -c "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey;print('ok')"` prints `ok`; `grep -c '"cryptography>=46.0"' pyproject.toml` prints `1`.

### Task 1.3 — Write the read-only spike script
- **Goal:** `scripts/exness_spike.py` signs requests per spec and performs only GET calls and WS reads.
- **Target files and symbols:** `scripts/exness_spike.py` with module functions `b64url(data: bytes) -> str` (base64url, no `=`), `body_hash(body: bytes) -> str`, `load_private_key(raw: str) -> Ed25519PrivateKey`, `signed_headers(api_key, private_key, method, path_with_query, body: bytes, idempotency_key: str, timestamp_ms: int) -> dict[str, str]`, `redact(text: str, account_id: str) -> str`, `async def main(argv) -> int`.
- **Steps:**
  1. Env inputs: `EXNESS_BASE_URL` (https), optional `EXNESS_WS_BASE_URL` (default = base URL with `https` → `wss`), `EXNESS_ACCOUNT_ID`, `EXNESS_API_KEY`, `EXNESS_PRIVATE_KEY` or `EXNESS_PRIVATE_KEY_PATH`. CLI: `--out` (default `tests/core_test/infra/exness/fixtures`), `--instruments` (default `XAUUSD,EURUSD,BTCUSD`), `--tick-seconds` (default 600).
  2. `load_private_key`: if text contains `BEGIN`, use `serialization.load_pem_private_key(raw.encode(), password=None)`; else decode as hex, then base64url, then base64 and require exactly 32 bytes → `Ed25519PrivateKey.from_private_bytes`. Record which branch worked (`pem` or `seed`) without printing the key.
  3. `signed_headers`: payload dict in this key order: `api_key`, `idempotency_key` (empty string for GET), `timestamp` (int ms), `sign_version` (1), `method` (upper), `path` (path + `?` + query exactly as sent), `body_hash` (`b64url(sha256(body))`). `data = json.dumps(payload, separators=(",", ":")).encode()`. Headers: `EXN-API-KEY`, `EXN-IDEMPOTENCY-KEY` (empty for GET), `EXN-TIMESTAMP` (str), `EXN-SIGN-VERSION` = `1`, `EXN-DATA` = `b64url(data)`, `EXN-SIGN` = `b64url(private_key.sign(data))`.
  4. Query strings: build with `urllib.parse.urlencode`; format datetimes as `YYYY-MM-DDTHH:MM:SSZ`; send the exact `path?query` string that was signed (`httpx.AsyncClient.get(base_url + path_with_query)`); never pass `params=`.
  5. Calls, in order, each response saved via `redact()` to `--out`: `GET /v1/configuration/accounts/{id}/limits` → `limits.json`; `/instruments` → `instruments.json`; for each requested code pick the instrument whose `name.upper() == code` (if none, print names containing the code and exit 2); `/instruments/{name}/conditions` → `conditions_{CODE}.json`; `/account` → `account.json`; candles `timeframe=M1&price_type=bid&from=<floor(now,1m)>&count=-1000` → `candles_{CODE}_M1.json`; `timeframe=H1 ... count=-200` → `candles_{CODE}_H1.json`; `GET /v1/trading/accounts/{id}/snapshot` → `snapshot.json`.
  6. Record per response: HTTP status, the `Date` header vs local UTC (offset seconds).
  7. Ticks WS: connect `websockets.asyncio.client.connect(ws_base + path, additional_headers=signed_headers("GET", path, b"", ""))` to `/v1/server-events/accounts/{id}/ws/ticks`; if the handshake is rejected, retry once with `subprotocols=["exness-ws-protocol"]`; record which variant worked. Send `{"id":"ticks-1","subscribe":{"event":"ticks","instruments":[...]}}`; read for `--tick-seconds`; save the first 300 frames to `ticks_sample.jsonl`; per instrument compute frame count, median inter-tick ms, median `ask-bid`; then send `{"id":"ticks-2","unsubscribe":{"event":"ticks","instruments":[first instrument]}}` and record the reply frame.
  8. Events WS `/ws/events`: send `{"id":"events-1","subscribe":{"event":"transactions"}}`; save the first message (`trading_state_snapshot`) to `events_snapshot.json`; close.
  9. Print one JSON summary to stdout (no headers, no key, no account id).
- **Success criteria:** script contains no REST mutation; never prints secrets.
- **Verify:** `grep -nE "\b(post|put|patch|delete)\(|\"(POST|PUT|PATCH|DELETE)\"" scripts/exness_spike.py` prints nothing (exit 1); `uv run ruff check scripts/exness_spike.py` prints `All checks passed!`.

### Task 1.4 — Unit-test the signing helpers
- **Goal:** signing is proven against the spec vector before touching the live API.
- **Target files and symbols:** `tests/scripts/test_exness_spike.py` importing from `scripts.exness_spike` (pattern: `tests/scripts/test_audit_bar_quality.py`).
- **Steps:**
  1. `test_empty_body_hash_matches_spec_vector`: `body_hash(b"") == "47DEQpj8HBSa-_TImW-5JCeuQeRkm5NMpJWZG3hSuFU"`.
  2. `test_signed_get_headers_verify_with_public_key`: generate `Ed25519PrivateKey.generate()`; headers for GET; decode `EXN-DATA` (re-pad) → JSON has `idempotency_key == ""`, `method == "GET"`, `path` equal to input; `public_key.verify(b64url-decoded EXN-SIGN, decoded EXN-DATA)` raises nothing; no header value contains `=`.
  3. `test_load_private_key_accepts_pem_and_seed`: round-trip a generated key as PEM and as base64url seed.
- **Success criteria:** 3 tests pass.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/scripts/test_exness_spike.py -q` → exit 0, output contains `3 passed`.

### Task 1.5 — Run the spike and store redacted fixtures
- **Goal:** fixtures exist for adapter tests and contain no account id or key.
- **Target files and symbols:** `tests/core_test/infra/exness/fixtures/`.
- **Steps:**
  1. Run `uv run python scripts/exness_spike.py` on a host allowed by the key's IP allowlist. If only the VPS is allowed, ask the user to run it there (scripts are in the image: `docker exec pocketquant-app python scripts/exness_spike.py --out /tmp/exness_fixtures` then `docker cp`), or ask the user to add the dev IP.
  2. If any call returns `AUTH_INVALID_SIGNATURE`, apply the Failure Protocol (do not tweak signing by trial).
- **Success criteria:** `limits.json`, `instruments.json`, three `conditions_*.json`, three `candles_*_M1.json`, three `candles_*_H1.json`, `account.json`, `snapshot.json`, `ticks_sample.jsonl`, `events_snapshot.json` exist.
- **Verify:** `ls tests/core_test/infra/exness/fixtures | wc -l` prints `15`; `grep -rl "$EXNESS_ACCOUNT_ID" tests/core_test/infra/exness/fixtures | wc -l` prints `0`; `grep -rl "exnsk-" tests/core_test/infra/exness/fixtures | wc -l` prints `0`.

### Task 1.6 — Findings report and A-v feasibility gate
- **Goal:** every assumption is settled in one report that later phases read.
- **Target files and symbols:** `plans/261009-0858-exness-venue-lean-sync-refactor/reports/exness-spike-findings.md`.
- **Steps:**
  1. Write a table with keys, one per line, `key: value`: `rest_base_host`, `ws_base_url`, `ws_subprotocol_required` (yes/no), `private_key_format` (pem/seed), `date_offset_seconds`, `global_rate_per_min` (= `limit*60/window_seconds`), `candles_rate_per_min` (method `getCandleHistory`), `max_candles_per_request`, `history_range_days`, `history_age_days`, per instrument: `instrument_name_<CODE>`, `contract_size_<CODE>`, `volume_min/step/max_<CODE>`, `point_digits_<CODE>`, `trade_sessions_<CODE>` (raw list), `median_spread_<CODE>`, `median_tick_ms_<CODE>`, `m1_aligned` (all M1 `time` seconds==0), `h1_aligned`, `in_progress_candle_returned` (newest candle time == floor(now)), `ticks_unsubscribe_supported`, `btcusd_weekend_sessions` (trade_sessions cover Sat/Sun: yes/no).
  2. A-v feasibility: required candle calls per minute = 3 instruments × 6 timeframes = 18. Feasible iff `candles_rate_per_min >= 36` and `global_rate_per_min >= 60` and `max_candles_per_request >= 10`.
  3. If not feasible, or `m1_aligned`/`h1_aligned` is `no`: STOP and ask the user (stop-and-ask: limits make A-v infeasible). Write `av_feasible: no` and the numbers.
  4. If instrument names differ from `XAUUSD`/`EURUSD`/`BTCUSD`, write `composite_<CODE>: <NAME.upper()>:EXNESS` and use those composites everywhere the plan says `XAUUSD:EXNESS` etc.
- **Success criteria:** report contains `av_feasible: yes`.
- **Verify:** `grep -c "^av_feasible: yes" plans/261009-0858-exness-venue-lean-sync-refactor/reports/exness-spike-findings.md` prints `1`.

### Task 1.7 — Phase gate
- **Goal:** repo stays green; nothing secret is tracked.
- **Target files and symbols:** whole repo.
- **Steps:** run the four commands below; then ask the user to approve a commit (`chore(scripts): add read-only exness api spike and fixtures`) and push.
- **Success criteria:** all green; no key file tracked.
- **Verify:** `just test` exit 0 and last line has `passed` without `failed`/`error`; `uv run ruff check` → `All checks passed!`; `uv run pyright` → `0 errors`; `uv run lint-imports` → `Contracts: 7 kept, 0 broken.`; `git status --porcelain | grep -E "\.pem|\.env$" | wc -l` prints `0`.

## Verification (test matrix)

- Unit: signing helpers (Task 1.4). Integration: live read-only calls (Task 1.5). E2E: none.

## Risks

| Risk | L×I | Mitigation |
|------|-----|------------|
| Signature mismatch from query re-encoding | M×M | sign the exact transmitted `path?query`; `Z` timestamps; Failure Protocol on `AUTH_INVALID_SIGNATURE` |
| Key IP allowlist excludes dev host | M×L | run inside `pocketquant-app` on VPS |
| Limits make A-v infeasible | L×H | hard gate in Task 1.6 → stop-and-ask |

## Security

Secrets only from env; `redact()` replaces the account id in every fixture; no request headers are logged or saved; private-key file stays outside the repo.

## Rollback

`git revert` the phase commit; delete fixtures. No runtime impact (no `src/` change).

## Stop and ask

Portal link not on `exness-api.com`; `av_feasible: no`; misaligned candles.

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

<!-- FILE: phase-02-characterization-and-metrics-baseline.md -->
---
phase: 2
title: "Characterization tests and metrics baseline"
status: pending
priority: P1
effort: 2d
dependencies: []
---

# Phase 02: Characterization tests and metrics baseline

## Context Links

- Advice §4.2 (characterization first), §2.4 (metric script, soft gate).
- Current sync job behaviour: `src/pocketquant/engine/market_data/app_services/sync_jobs.py` (`sync_1m`:382, `_sync_by_intervals`:130, `sync_verify_cascade`:511, `sync_backfill`/`sync_integrity`/`sync_repair`, `register_sync_jobs`:663, `CATCHUP_TARGETS`); `integrity_jobs.py`; `cascade_aggregator.py:140 cascade_for_symbol`.
- Existing patterns: `tests/app_test/market_data/test_sync_jobs_source_labels.py` (`_wire_container`, monkeypatch of `sync_jobs._container`), `tests/app_test/test_sync_jobs_phase.py` (`_FakeContainer`, `_build_scheduler`).
- OKX: `src/pocketquant/core/infra/brokers/okx/okx_broker.py` (`_handle_ws_message`:333-347, `_handle_order_update`:349), `okx_mapper.py` (`map_order_to_okx_params`), `websocket/okx_message_parser.py`, `okx_order_mapper.py`, `okx_position_mapper.py`. No OKX test exists today.

## Goal

Pin today's Binance sync behaviour and OKX broker mapping so Phases 03-05 can refactor aggressively, and ship the AST metric script with an exact baseline.

**Characterization rule:** assertions pin CURRENT output. Get expected values by running the code once and hard-coding them; never change production code in this phase. Test names describe behaviour; no plan/phase words.

## Files to Create or Modify

- Create: `scripts/code_metrics.py`, `tests/scripts/test_code_metrics.py`, `tests/app_test/market_data/test_sync_job_schedule_characterization.py`, `tests/app_test/market_data/test_sync_jobs_characterization.py`, `tests/app_test/market_data/test_cascade_golden.py`, `tests/app_test/market_data/cascade_golden.json`, `tests/engine_test/market_data/test_sync_response_characterization.py`, `tests/core_test/infra/brokers/test_okx_broker_characterization.py`, `plans/261009-0858-exness-venue-lean-sync-refactor/reports/baseline-test-counts.md`
- Modify: none in `src/`.

## Tasks

### Task 2.1 — Record the test baseline
- **Goal:** pass counts exist to compare against after each refactor phase.
- **Target files and symbols:** `reports/baseline-test-counts.md`.
- **Steps:**
  1. `uv sync` (if not done); Docker must be running (testcontainers).
  2. Run and record the final summary line of each: (a) `.venv/Scripts/python.exe -m pytest -q`; (b) `.venv/Scripts/python.exe -m pytest tests/core_test/infra/binance -q`; (c) `.venv/Scripts/python.exe -m pytest tests/app_test/market_data tests/app_test/unit tests/app_test/test_sync_jobs_phase.py tests/engine_test/market_data -q`.
  3. Write them as `full: <line>`, `binance: <line>`, `sync: <line>`.
- **Success criteria:** three lines, all `passed` with no `failed`.
- **Verify:** `grep -cE "^(full|binance|sync): .*passed" plans/261009-0858-exness-venue-lean-sync-refactor/reports/baseline-test-counts.md` prints `3`.

### Task 2.2 — AST metric script
- **Goal:** one deterministic definition of tiny functions, pure delegations and long functions.
- **Target files and symbols:** `scripts/code_metrics.py`: `count_statements(stmts) -> int`, `is_delegation(node) -> bool`, `measure(root: Path, max_lines: int) -> list[FunctionMetric]`, `main(argv) -> int`.
- **Steps:**
  1. Definitions (write exactly these):
     - function = every `ast.FunctionDef`/`ast.AsyncFunctionDef` in every `*.py` under `--root` (a dir, recursive; or a single file), nested ones included.
     - statements = after dropping a leading docstring, count every statement recursively through `body`, `orelse`, `finalbody`, `handlers[].body`, `cases[].body`, but do not descend into nested `def`/`class` (they count as 1).
     - tiny = statements ≤ 2. (Recursive on purpose: a single `try:` wrapping 80 lines, e.g. `paper_broker.py:_handle_limit`, is not tiny. A top-level count gives 372/794 = 46.9%; this definition gives 338/794 = 42.6%.)
     - delegation = after dropping the docstring the body is exactly one `Return` or `Expr` whose value, after unwrapping `Await`, is a `Call` whose `func` is an `ast.Attribute`. (Reproduces the advice's 63.)
     - long = `end_lineno - lineno + 1 > --max-function-lines` (default 60).
  2. CLI: `--root` (default `src/pocketquant`), `--list`, `--max-tiny-share FLOAT`, `--max-delegations INT`, `--max-function-lines INT` (default 60, used for the count), `--fail-on-long` (flag).
  3. Output line 1 exactly: `functions=<n> tiny=<t> tiny_share=<t/n:.3f> delegations=<d> long_functions=<l>`. With `--list`, then one line per item: `tiny <relpath>:<line> <name>`, `delegation ...`, `long ... <lines>`.
  4. Exit 1 and print `THRESHOLD BREACHED: <which>` when a given threshold is exceeded (or any long function with `--fail-on-long`); else exit 0.
  5. `tests/scripts/test_code_metrics.py`: write small source files to `tmp_path` and assert: a function with docstring + 2 statements is tiny; a `try` with 5 inner statements is not tiny; `return self.x.y()` and `await self.x.y()` are delegations, `return f()` is not; a 61-line function is long; thresholds produce exit 1.
- **Success criteria:** baseline matches the scouted tree exactly.
- **Verify:** `uv run python scripts/code_metrics.py` prints exactly `functions=794 tiny=338 tiny_share=0.426 delegations=63 long_functions=22`; `.venv/Scripts/python.exe -m pytest tests/scripts/test_code_metrics.py -q` exit 0.

### Task 2.3 — Pin the job schedule
- **Goal:** job ids, triggers, misfire grace and catch-up targets cannot drift during the refactor.
- **Target files and symbols:** `tests/app_test/market_data/test_sync_job_schedule_characterization.py`; uses `register_sync_jobs`, `CATCHUP_TARGETS` from `pocketquant.engine.market_data.app_services.sync_jobs`.
- **Steps:**
  1. Copy `_FakeContainer` and `_build_scheduler` from `tests/app_test/test_sync_jobs_phase.py`.
  2. After `await register_sync_jobs(_FakeContainer(), scheduler)`, collect from the underlying APScheduler (same access path that file uses) per job: id, `func_ref` text after `:`, trigger `str()`, `misfire_grace_time`.
  3. Assert the dict equals the current values: `sync_1m` (`*/1` minute, second 2, grace 120), `sync_verify_cascade` (hourly, 600), `sync_backfill` (03:00, 3600), `sync_integrity` (04:00, 3600), `sync_repair` (`*/12` hours, 1800); assert `[(id, gap) for id, _, gap in CATCHUP_TARGETS] == [("sync_backfill", 90000), ("sync_integrity", 90000), ("sync_repair", 45000)]` and each func ref ends with `:<id>`.
- **Success criteria:** test passes on current code.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/app_test/market_data/test_sync_job_schedule_characterization.py -q` exit 0.

### Task 2.4 — Pin job call sequences
- **Goal:** what each job asks of `SyncService`, `cascade_for_symbol`, `check_integrity`/`repair_integrity` and `JobHistoryRepository` is pinned.
- **Target files and symbols:** `tests/app_test/market_data/test_sync_jobs_characterization.py`.
- **Steps:**
  1. Fake container (pattern `_wire_container`): `TrackedSymbolRepository.list_all` → objects with `.symbol` `BTCUSDT:BINANCE`, `ETHUSDT:BINANCE`; `SyncService.sync_one` AsyncMock returning `SyncResponse(symbol=..., interval=..., status="completed", bars_synced=1, bars_fetched=2)`; `JobHistoryRepository` AsyncMock (`record_start` → `"doc-1"`); `BarRepository` AsyncMock; `IDataProvider` AsyncMock.
  2. Monkeypatch module attributes `sync_jobs.cascade_for_symbol`, `sync_jobs.check_integrity`, `sync_jobs.repair_integrity` with AsyncMocks returning `{Interval.MINUTE_5: 1}`, `{"misaligned_count":0,"missing_count":0}`, `{"deleted":0,"gaps_resynced":0}`.
  3. Tests: `test_sync_1m_syncs_each_symbol_then_cascades` — ordered `(symbol, interval, n_bars, source)` of `sync_one` calls = `[(BTC,1m,100,"rest_sync_1m"),(ETH,1m,100,"rest_sync_1m")]`, cascade awaited for BTC then ETH with `lookback_minutes=100`, `record_finish` kwargs `status="completed", total_inserted=2, total_fetched=4`; `test_sync_backfill_is_symbol_major_over_seven_intervals` — 14 calls, order BTC×(1m,5m,15m,1h,4h,1d,1w) then ETH×same, n_bars 5000, source `rest_backfill`; `test_integrity_and_repair_cover_seven_intervals` — 14 calls each, repair `source="rest_repair"`; `test_sync_1m_error_skips_cascade_and_fails_job` — `sync_one` raises for BTC → cascade not awaited, `record_finish` with `status="failed"`, job raises.
- **Success criteria:** 4 tests pass on current code.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/app_test/market_data/test_sync_jobs_characterization.py -q` exit 0, `4 passed`.

### Task 2.5 — Cascade golden output
- **Goal:** cascade OHLCV values are frozen.
- **Target files and symbols:** `tests/app_test/market_data/test_cascade_golden.py`, `cascade_golden.json`; `cascade_for_symbol` (import path stays `pocketquant.engine.market_data.app_services.cascade_aggregator` for the whole plan).
- **Steps:**
  1. 1440 `Bar`s for `BTCUSDT:BINANCE` 1m from `2026-01-05T00:00Z` with `open=100+i%37`, `high=open+3`, `low=open-2`, `close=open+(i%5)-2`, `volume=1+i%7` (pattern `_make_1m_bars` in `test_cascade_aggregator_source.py`); AsyncMock repo `find` returns them; record every `upsert_bar` call as `[interval, iso datetime, o, h, l, c, v]`.
  2. When env `GOLDEN_UPDATE=1`, write the JSON; otherwise compare.
  3. Generate once with `GOLDEN_UPDATE=1`, then run without.
- **Success criteria:** golden file committed; comparison passes.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/app_test/market_data/test_cascade_golden.py -q` (no env var) exit 0; `test -s tests/app_test/market_data/cascade_golden.json && echo ok` prints `ok`.

### Task 2.6 — Sync response golden
- **Goal:** `SyncService.sync_one` response fields are pinned.
- **Target files and symbols:** `tests/engine_test/market_data/test_sync_response_characterization.py`; build `SyncService` like `tests/engine_test/market_data/test_sync_service.py`.
- **Steps:** provider returns 5 aligned 1m bars + 1 bar at `:30` seconds; `find_datetimes` returns the first aligned bar's datetime; `insert_many` returns 4; `count` 10; `get_latest` a bar at a fixed datetime. Assert `result.model_dump()` equals the full dict observed on current code (`status="completed"`, `bars_fetched=6`, `filtered_existing=1`, `filtered_misaligned=1`, `bars_synced=4`, `total_bars=10`, `last_bar_at=<iso>`, `message=None`); second test: provider raises → `status="error"`, `message` = exception text.
- **Success criteria:** 2 tests pass.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/engine_test/market_data/test_sync_response_characterization.py -q` exit 0.

### Task 2.7 — OKX broker characterization
- **Goal:** OKX order/position message handling and order params are pinned before Phase 05 touches OKX helpers.
- **Target files and symbols:** `tests/core_test/infra/brokers/test_okx_broker_characterization.py`; `OKXBroker._handle_ws_message`, `map_order_to_okx_params`.
- **Steps:**
  1. Build messages with the field names read from `okx_message_parser.py`, `okx_order_mapper.py`, `okx_position_mapper.py` (orders channel: states `live`, `filled`, duplicate `filled`, `canceled`; positions channel: one item).
  2. `broker = OKXBroker(api_key="k", api_secret="s", passphrase="p", demo=True)`; append an async recorder to `broker._order_callbacks` (do NOT call `subscribe_order_updates`, it starts a WS task).
  3. Assert recorded `OrderResult`s (status, order_id, broker_order_id, filled_quantity, filled_price) for live/filled/canceled; duplicate filled produces no second callback; positions message produces no callback and no exception.
  4. `map_order_to_okx_params` for market BUY, market SELL, limit BUY with SL/TP, limit SELL: assert full dicts.
- **Success criteria:** tests pass on current code.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/brokers/test_okx_broker_characterization.py -q` exit 0.

### Task 2.8 — Phase gate
- **Goal:** all green; counts recorded for later comparison.
- **Target files and symbols:** repo; `reports/baseline-test-counts.md` (append `characterization: <line>` from `.venv/Scripts/python.exe -m pytest tests/app_test/market_data tests/engine_test/market_data/test_sync_response_characterization.py tests/core_test/infra/brokers/test_okx_broker_characterization.py -q`).
- **Steps:** run gate; append line; ask user to approve commit `test: pin sync job, cascade and okx broker behaviour; add code metrics script` + push.
- **Success criteria:** gate green.
- **Verify:** `just test` exit 0 with `passed`, no `failed`; `uv run ruff check` → `All checks passed!`; `uv run pyright` → `0 errors`; `uv run lint-imports` → `Contracts: 7 kept, 0 broken.`

## Verification (test matrix)

- Unit: metric script, OKX mapping, sync response, job sequences. Integration: none new. E2E: OpenAPI + route inventory snapshots (existing `tests/baseline/`) are the HTTP contract lock for Phases 03-05.

## Risks

| Risk | L×I | Mitigation |
|------|-----|------------|
| Characterization pins a bug | M×L | intended; behaviour changes need a separate decision |
| Metric numbers differ (tree changed) | L×M | Phase 01 adds no `src/`; if numbers differ, Failure Protocol |

## Rollback

`git revert` the commit (tests and script only).

## Stop and ask

Any existing test failing on the untouched tree (unexplained failure).

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

<!-- FILE: phase-03-sync-policy-and-shared-runner.md -->
---
phase: 3
title: "SyncPolicy and shared runner (Binance)"
status: pending
priority: P1
effort: 5d
dependencies: [2]
---

# Phase 03: SyncPolicy and shared runner (Binance)

## Context Links

- Advice §2.2, §3 bullet 1/3; state R3.
- Today one `IDataProvider` (Binance) and one `IRealtimeQuoteProvider` (Binance WS) serve every tracked symbol regardless of exchange: `app/di/infrastructure.py:30 get_data_provider`, `app/di/market_data.py:31 get_realtime_quote_provider`; `BinanceClient.fetch_ohlcv` strips the exchange (`binance_client.py:61`). A tracked `XAUUSD:EXNESS` would be fetched from Binance. Routing by exchange is the core of this phase.
- APScheduler persists jobs in MongoDB with text refs `pocketquant.engine.market_data.app_services.sync_jobs:<func>` (`scheduler.py:60`). Re-registration uses `replace_existing=True` with the same job ids; APScheduler 3.11 drops a stored job whose ref no longer imports and logs `Unable to restore job`.
- OpenAPI descriptions come from Pydantic docstrings/Field descriptions (e.g. snapshot line 488 `Bypass _filter_new_bars — used by repair to fill gaps`) — copy DTOs verbatim.

## Goal

One `SyncPolicy` per exchange and one runner (`fetch → align → persist → cascade? → integrity → repair`). Binance policy reproduces today's behaviour exactly. `sync_internals/`, `sync_dtos.py`, `app_services/sync_jobs.py`, `app_services/integrity_jobs.py` are deleted.

## Data flow (after)

```
HTTP POST /market-data/sync ─► SyncService.sync_one (sync_service.py)
   └─ policies.for_symbol(sym).bar_source.fetch_ohlcv (≤3 tries) → drop existing → drop misaligned
      → BarRepository.insert_many → SymbolRepository.upsert → SyncStatusRepository.upsert → Cache.delete_pattern
APScheduler ─► sync_runner.sync_1m/backfill/integrity/repair/verify (sync_runner.py)
   └─ per policy: tracked symbols of that exchange (open now if calendar=venue_sessions)
      → SyncService.sync_one per (symbol, interval) → cascade_for_symbol if policy.cascade
      → bar_integrity.check/repair (bar_integrity.py) → JobHistoryRepository
WS ticks ─► policy.live_source ─► QuoteAppService.on_quote_update ─► Cache + BarAppService.add_tick ─► BarCompletedEvent
```

## Files to Create or Modify

- Create: `src/pocketquant/engine/market_data/sync_policy.py`, `src/pocketquant/engine/market_data/sync_runner.py`, `src/pocketquant/engine/market_data/bar_integrity.py`
- Modify: `src/pocketquant/core/domain/market_data/interfaces.py`, `src/pocketquant/engine/market_data/sync_service.py`, `src/pocketquant/engine/market_data/tracked_symbols_backfill.py`, `src/pocketquant/app/market_data/app_services/quote_app_service.py`, `src/pocketquant/app/market_data/app_services/ws_subscription_manager.py`, `src/pocketquant/app/main.py`, `src/pocketquant/app/main_extensions.py`, `src/pocketquant/app/routes/integrity.py`, `src/pocketquant/app/di/infrastructure.py`, `src/pocketquant/app/di/market_data.py`
- Delete: `src/pocketquant/engine/market_data/sync_internals/` (6 files), `src/pocketquant/engine/market_data/sync_dtos.py`, `src/pocketquant/engine/market_data/app_services/sync_jobs.py`, `src/pocketquant/engine/market_data/app_services/integrity_jobs.py`
- Tests to retarget (imports, monkeypatch targets, constructor args only; assertions unchanged): `tests/app_test/integration/app_factory.py`, `tests/app_test/integration/test_sync_backfill_gap_fill.py`, `tests/app_test/market_data/test_integrity_jobs_repair_source.py`, `tests/app_test/market_data/test_sync_jobs_source_labels.py`, `tests/app_test/market_data/test_sync_job_schedule_characterization.py`, `tests/app_test/market_data/test_sync_jobs_characterization.py`, `tests/app_test/test_sync_jobs_phase.py`, `tests/app_test/unit/di/test_di_data_provider.py`, `tests/app_test/unit/handlers/sync/conftest.py`, `tests/app_test/unit/handlers/sync/test_bar_filters.py`, `tests/app_test/unit/handlers/sync/test_no_progress_tracking.py`, `tests/app_test/unit/handlers/sync/test_provider_fetch.py`, `tests/app_test/unit/handlers/sync/test_sync_symbol_command_source.py`, `tests/app_test/unit/market_data/test_sync_jobs_catchup.py`, `tests/app_test/unit/market_data/test_sync_verify_cascade.py`, `tests/app_test/unit/market_data/test_quote_app_service.py`, `tests/engine_test/market_data/test_sync_service.py`, `tests/engine_test/market_data/test_sync_response_characterization.py`

## Tasks

### Task 3.1 — Market-hours hook on the data port
- **Goal:** the runner can ask any provider whether a symbol trades at a time; Binance keeps "always open".
- **Target files and symbols:** `core/domain/market_data/interfaces.py` class `IDataProvider`: new concrete method `async def is_market_open(self, symbol: str, at: datetime) -> bool: return True`.
- **Steps:** add the method (not abstract); no override in `BinanceClient`.
- **Success criteria:** domain purity test still passes.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/unit/domain/test_domain_purity.py tests/core_test/infra/binance -q` exit 0.

### Task 3.2 — `sync_policy.py`
- **Goal:** one readable object per venue.
- **Target files and symbols:** `engine/market_data/sync_policy.py`: `@dataclass(frozen=True) class SyncPolicy` fields `exchange: str`, `bar_source: IDataProvider`, `live_source: IRealtimeQuoteProvider`, `poll_intervals: tuple[Interval, ...]`, `stored_intervals: tuple[Interval, ...]`, `cascade: bool`, `poll_n_bars: int`, `poll_every_minutes: int = 1`, `calendar: Literal["24x7", "venue_sessions"] = "24x7"`, `min_request_interval_s: float = 0.0`, `history_days: Mapping[Interval, int | None] = field(default_factory=dict)`; `class SyncPolicies(dict[str, SyncPolicy])` with `def for_symbol(self, symbol: str) -> SyncPolicy` (exchange = text after `:` upper-cased; raises `ValueError(f"No sync policy for exchange '{exchange}'")`); `def binance_policy(bar_source, live_source) -> SyncPolicy`.
- **Steps:**
  1. `binance_policy`: `exchange="BINANCE"`, `poll_intervals=(Interval.MINUTE_1,)`, `stored_intervals=(1m,5m,15m,1h,4h,1d,1w)` (today's `SYNC_INTERVALS`), `cascade=True`, `poll_n_bars=100`, calendar `24x7`.
  2. Unit test `tests/engine_test/market_data/test_sync_policy.py`: `for_symbol("btcusdt:binance")` returns the Binance policy; unknown exchange raises `ValueError`.
- **Success criteria:** module < 120 lines; no import from `core.infra`.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/engine_test/market_data/test_sync_policy.py -q` exit 0; `grep -c "core.infra" src/pocketquant/engine/market_data/sync_policy.py` prints `0`.

### Task 3.3 — Fold `sync_internals` and DTOs into `sync_service.py`
- **Goal:** a sync request reads in one file after the route.
- **Target files and symbols:** `engine/market_data/sync_service.py`: classes `SyncSymbolCommand`, `BulkSyncCommand`, `SyncResponse` (moved verbatim from `sync_dtos.py`, docstrings and `Field(description=...)` unchanged); `SyncService.__init__(self, policies: SyncPolicies, cache: Cache, bar_repository: BarRepository, symbol_repository: SymbolRepository, sync_status_repository: SyncStatusRepository)`; module functions `_fetch_with_retry` (from `provider_fetch.py`, with `has_aligned_bar` inlined), `_filter_new_bars`, `_drop_misaligned_bars` (from `bar_filters.py`), `_emit_no_progress` (from `anomaly_log.py`); `build_success`, `_mark_completed`, `_invalidate_cache`, `_get_bar_stats`, `_persist_bars` inlined at their single call sites; `_fail` kept.
- **Steps:**
  1. Move code; keep log event names, constants (`_BACKOFF_SECONDS=(0,3,8)`, `_TIME_BUDGET_SECONDS=15`, `_STUCK_STREAK_THRESHOLD=3`) and behaviour identical.
  2. In `sync_one`, resolve `provider = self._policies.for_symbol(symbol).bar_source` inside the existing `try`; a `ValueError` therefore becomes the existing error response (`status="error"`, message `No sync policy for exchange 'X'`).
  3. Keep every function ≤60 lines: split `sync_one` into `sync_one` + `async def _fetch_filtered(...) -> tuple[list[Bar], int, int, int, int]` (records, fetched, filtered_existing, filtered_misaligned, attempts).
  4. Update import sites: `grep -rn "sync_dtos\|sync_internals" src tests scripts` must end empty; tests import from `pocketquant.engine.market_data.sync_service` and private functions by their new names (`_filter_new_bars`, `_drop_misaligned_bars`, `_fetch_with_retry`); `test_provider_fetch.py` monkeypatches `asyncio.sleep` inside `pocketquant.engine.market_data.sync_service`.
  5. Tests constructing `SyncService(provider=...)` pass `policies=SyncPolicies({"BINANCE": binance_policy(provider, MagicMock())})`.
  6. Delete `sync_internals/` and `sync_dtos.py`.
- **Success criteria:** OpenAPI unchanged; sync tests green with same counts.
- **Verify:** `test ! -e src/pocketquant/engine/market_data/sync_internals && test ! -e src/pocketquant/engine/market_data/sync_dtos.py && echo gone` prints `gone`; `.venv/Scripts/python.exe -m pytest tests/baseline tests/engine_test/market_data tests/app_test/unit/handlers -q` exit 0; `uv run python scripts/code_metrics.py --root src/pocketquant/engine/market_data/sync_service.py --fail-on-long` exit 0.

### Task 3.4 — `bar_integrity.py` with market calendar
- **Goal:** integrity check/repair are policy-aware so closed markets are not reported as gaps; Binance output unchanged.
- **Target files and symbols:** `engine/market_data/bar_integrity.py`: `check_integrity(symbol, interval, bar_repo, days_back=7, *, policy: SyncPolicy | None = None) -> dict`, `repair_integrity(symbol, interval, bar_repo, sync_service, *, source, days_back=7, policy: SyncPolicy | None = None) -> dict`, `_group_gaps` (moved from `integrity_jobs.py`).
- **Steps:**
  1. Move code; same return dict keys.
  2. If `policy` and `policy.calendar == "venue_sessions"`: keep an expected slot only if `await policy.bar_source.is_market_open(symbol, slot)` or `... (symbol, slot + step - 1 minute)` is true (use tz-aware UTC for the call; grid stays naive as today).
  3. `app/routes/integrity.py`: import from `bar_integrity`; inject `policies: FromDishka[SyncPolicies]` and pass `policy=policies.for_symbol(symbol)` (catch `ValueError` → `HTTPException(400, {"error_code":"UNKNOWN_EXCHANGE"})`). Note: adding a `FromDishka` param does not change OpenAPI.
  4. Retarget `test_integrity_jobs_repair_source.py`; add `tests/engine_test/market_data/test_bar_integrity_calendar.py`: fake provider closed on Saturday → Saturday 1m slots absent from `missing_count`; `policy=None` gives today's count.
- **Success criteria:** identical output for 24x7.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/app_test/market_data/test_integrity_jobs_repair_source.py tests/engine_test/market_data/test_bar_integrity_calendar.py tests/baseline -q` exit 0.

### Task 3.5 — `sync_runner.py`, the shared runner
- **Goal:** all five jobs run from policies through one history wrapper; same job ids, crons, grace, catch-ups, log event names.
- **Target files and symbols:** `engine/market_data/sync_runner.py`: `_MODULE = "pocketquant.engine.market_data.sync_runner"`; `_container`, `set_container`, `_get_container` (same error text); constants `PRICE_THRESHOLD_PCT`, `VOLUME_THRESHOLD_PCT`, `DIVERGENCE_ALERT_FRACTION`, `CATCHUP_TARGETS` (same ids/gaps, new module refs); `compare_bar_fields`; `async def _run_job(name, work)` (record_start → work(doc_id) → record_finish completed/failed, re-raise; replaces the five copies); `async def _policy_symbols(job_name) -> list[tuple[SyncPolicy, list[str]]]` (tracked symbols grouped by exchange in `list_all()` order; unknown exchange → `logger.warning("market_data.sync.no_policy", symbol=...)`); `async def _sync_intervals(...)` (body of today's `_sync_by_intervals` per policy; `asyncio.sleep(policy.min_request_interval_s)` between items when > 0; returns `(inserted, fetched, first_error)`); entrypoints `sync_1m`, `sync_verify_cascade`, `sync_backfill`, `sync_integrity`, `sync_repair`; `_verify_one_symbol`; `enqueue_missed_catchups`; `register_sync_jobs`.
- **Steps:**
  1. `sync_1m`: for each `(policy, symbols)`: skip when `now.minute % policy.poll_every_minutes != 0`; when `calendar == "venue_sessions"` keep symbols with `await policy.bar_source.is_market_open(symbol, now)`; `_sync_intervals(policy.poll_intervals, policy.poll_n_bars, SOURCE_REST_SYNC_1M)`; if it returned an error remember the first and skip cascade for that policy; elif `policy.cascade`, run `cascade_for_symbol(symbol, lookback_minutes=100, bar_repo=...)` per symbol with today's error logging and `sync_1m.cascade_summary`. After all policies, raise the first error.
  2. `sync_backfill`: `policy.stored_intervals`, n_bars 5000, `SOURCE_REST_BACKFILL`. `sync_integrity`/`sync_repair`: loop `policy.stored_intervals`, call `bar_integrity` with `policy=policy`, same logs. `sync_verify_cascade`: only policies with `cascade=True`, provider = `policy.bar_source`.
  3. Every function ≤60 lines; `SyncPolicies` resolved via `await container.get(SyncPolicies)`.
  4. Retarget the Phase 02 characterization tests and existing job tests: import from `pocketquant.engine.market_data.sync_runner`; monkeypatch `sync_runner._container`, `sync_runner.cascade_for_symbol`, `sync_runner.check_integrity`/`repair_integrity` (import those names into `sync_runner`); fake containers also return `SyncPolicies({"BINANCE": binance_policy(provider_mock, MagicMock())})` for `get(SyncPolicies)`. In the schedule test, assert func refs end with `:<id>` (module part changes).
  5. Delete `app_services/sync_jobs.py` and `app_services/integrity_jobs.py`.
- **Success criteria:** all Phase 02 characterization assertions pass unchanged.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/app_test/market_data tests/app_test/unit tests/app_test/test_sync_jobs_phase.py tests/engine_test/market_data -q` exit 0 and its `N passed` is ≥ the `N passed` of the `sync:` line in `reports/baseline-test-counts.md`; `uv run python scripts/code_metrics.py --root src/pocketquant/engine/market_data/sync_runner.py --fail-on-long` exit 0; `test ! -e src/pocketquant/engine/market_data/app_services/sync_jobs.py && echo gone` prints `gone`.

### Task 3.6 — Quote feed per policy
- **Goal:** each tracked symbol subscribes on its own venue's live source; every live source runs.
- **Target files and symbols:** `QuoteAppService.__init__(self, settings, cache, bar_manager, policies: SyncPolicies)`; attribute `ws_tasks: list[asyncio.Task]`; `start()` creates one `run_forever()` task per distinct `policy.live_source`. `WsSubscriptionManager.__init__(self, policies, tracked_symbol_repo, quote_app_service, interval_s=5.0)`; `_reconcile` diffs per policy (`desired` = tracked symbols of that exchange; `current` = `policy.live_source.subscriptions.keys()`); unknown exchange → warning once per reconcile. `main_extensions.start_quote_feed` stores `app.state.ws_tasks = quote_svc.ws_tasks`; `stop_quote_feed` cancels each task in `ws_tasks` and `subscription_task`, then `await policy.live_source.disconnect()` for each policy (resolve `SyncPolicies`, no longer `IRealtimeQuoteProvider`).
- **Steps:** implement; update `test_quote_app_service.py` construction; add a test: two policies with mock live sources → `start()` creates 2 tasks; reconcile subscribes `XAUUSD:EXNESS` only on the EXNESS mock.
- **Success criteria:** Binance-only runtime behaves as before (one task).
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/app_test/unit/market_data/test_quote_app_service.py tests/app_test/integration/test_lifespan_boot.py -q` exit 0.

### Task 3.7 — Backfill service and DI wiring
- **Goal:** `TrackedSymbolBackfillService` and DI use policies; `IDataProvider`/`IRealtimeQuoteProvider` are no longer DI keys.
- **Target files and symbols:** `TrackedSymbolBackfillService.__init__(self, policies: SyncPolicies, bar_repository)`; `run()` picks `policy.bar_source`; mode `auto` resolves to `cascade` only if `policy.cascade` and interval in `_CASCADE_DEFAULT_TFS`, else `direct` (move `resolved_mode` logic into `run`). DI: `infrastructure.py` `get_data_provider` → `def get_binance_client(self, settings) -> BinanceClient`; `market_data.py` `get_realtime_quote_provider` → `def get_binance_ws(self) -> BinanceWebSocketClient`, new `def get_sync_policies(self, binance: BinanceClient, binance_ws: BinanceWebSocketClient) -> SyncPolicies`, quote service / subscription manager factories take `SyncPolicies`. `main.py` and `main_extensions.start_background_jobs` import `set_container`/`register_sync_jobs` from `sync_runner`. `tests/app_test/integration/app_factory.py` imports `set_container` from `sync_runner`.
- **Steps:** implement; rewrite `test_di_data_provider.py` to assert `get_sync_policies(...)["BINANCE"].bar_source` is the `BinanceClient` and `live_source` the `BinanceWebSocketClient` and satisfies `IRealtimeQuoteProvider`.
- **Success criteria:** `grep -rn "container.get(IDataProvider)\|container.get(IRealtimeQuoteProvider)" src` empty.
- **Verify:** `grep -rn "get(IDataProvider)\|get(IRealtimeQuoteProvider)" src | wc -l` prints `0`; `.venv/Scripts/python.exe -m pytest tests/app_test -q` exit 0.

### Task 3.8 — Flow-length check and phase gate
- **Goal:** refactor is green, OpenAPI unchanged, Binance counts unchanged.
- **Target files and symbols:** repo; `reports/baseline-test-counts.md`.
- **Steps:**
  1. Run gate. Compare `binance:` count (must be equal) and `characterization:` count (equal) with Task 2.1/2.8 lines; append `after-phase-03: <full line>`.
  2. `uv run python scripts/code_metrics.py` and append the line to `reports/lean-pass-metrics.md` as `after-phase-03`.
  3. Ask the user to approve commit `refactor(market-data): drive sync jobs from per-exchange sync policies` and push. Tell the user: no local process with `ENABLE_JOBS=true` may run old code against the prod DB from now on (shared APScheduler job store).
  4. After CI is green: check jobs on the VPS.
- **Success criteria:** gate green; 5 jobs re-registered in prod.
- **Verify:** `just test` exit 0 (`passed`, no `failed`); `uv run ruff check` → `All checks passed!`; `uv run pyright` → `0 errors`; `uv run lint-imports` → `Contracts: 7 kept, 0 broken.`; `.venv/Scripts/python.exe -m pytest tests/core_test/infra/binance -q` summary equals the recorded `binance:` line; `gh run list --workflow cicd.yml --limit 1 --json conclusion -q ".[0].conclusion"` prints `success`; `ssh -i ../pocketquant-config/vps/default/id_rsa "$(cat ../pocketquant-config/vps/default/host)" "docker exec pocketquant-app curl -s localhost:41921/api/v1/system/jobs" | grep -o '"id": *"sync_[a-z0-9_]*"' | sort -u | wc -l` prints `5`.

## Verification (test matrix)

- Unit: policy routing, calendar filter, quote fan-out, sync service (retargeted). Integration: lifespan boot, gap-fill (testcontainers). E2E: OpenAPI/route snapshots unchanged; prod job list.

## Risks

| Risk | L×I | Mitigation |
|------|-----|------------|
| Persisted APScheduler refs to deleted module | H×M | same job ids + `replace_existing`; stale docs dropped on first boot; verify job list after deploy |
| Old local process re-adds old refs to shared job store | L×H | user warned in Task 3.8 |
| Silent behaviour change in Binance sync | M×H | Phase 02 characterization + golden must pass unchanged |
| OpenAPI drift from moved DTO docstrings | M×M | verbatim move; snapshot test |

## Rollback

`git revert` the phase commit and push; CI redeploys; old refs are re-registered on boot (same ids).

## Stop and ask

A change would remove Binance capability; an unexplained test failure after one investigation.

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

<!-- FILE: phase-04-di-routes-and-contracts-consolidation.md -->
---
phase: 4
title: "DI, routes and import contracts consolidation"
status: pending
priority: P1
effort: 2d
dependencies: [3]
---

# Phase 04: DI, routes and import contracts consolidation

## Context Links

- Advice §2.3; state R4/R5. DI today: 8 provider modules + `broker_factory.py` + `container.py` in `src/pocketquant/app/di/`; `services.py` docstring warns "Dishka silently lets the last duplicate registration win".
- Routes mounted in `app/main_extensions.py:366 register_routes`: `market_data` router (includes sync, integrity, ohlcv, status, list_symbols) + `tracked_symbols_router` with `prefix="/market-data"` + quotes router.
- Import contracts: `pyproject.toml` `[tool.importlinter]` (7). Contracts 3-5 are implied by the `layers` contract; the bson contract duplicates ruff `TID` banned-api (`[tool.ruff.lint.flake8-tidy-imports.banned-api]`).

## Goal

`app/di` = 3 provider modules; market-data HTTP surface = 2 route files; scalar Query/Command wrappers gone; import-linter = 3 contracts. HTTP contract byte-identical.

## Files to Create or Modify

- Create: `src/pocketquant/app/di/adapters.py`
- Modify: `src/pocketquant/app/di/__init__.py`, `src/pocketquant/app/di/infrastructure.py`, `src/pocketquant/app/di/services.py`, `src/pocketquant/app/main.py`, `src/pocketquant/app/main_extensions.py`, `src/pocketquant/app/routes/market_data.py`, `src/pocketquant/app/routes/market_data_quotes.py`, `src/pocketquant/app/routes/strategy.py`, `src/pocketquant/app/routes/trading_orders_positions.py`, `src/pocketquant/app/routes/backtest.py`, service modules listed in Task 4.3, `pyproject.toml`, `CLAUDE.md`
- Delete: `app/di/backtest_worker.py`, `app/di/broker_factory.py`, `app/di/container.py`, `app/di/core.py`, `app/di/execution.py`, `app/di/market_data.py`, `app/di/persistence.py`, `app/di/trading_services.py`, `app/routes/market_data_sync.py`, `app/routes/market_data_status.py`, `app/routes/market_data_ohlcv.py`, `app/routes/list_symbols.py`, `app/routes/integrity.py`, `app/routes/tracked_symbols.py`
- Tests to retarget: `tests/app_test/integration/app_factory.py`, `tests/app_test/integration/test_app_standalone_runtime.py`, `tests/app_test/integration/test_reconcile_di_resolution.py`, `tests/app_test/unit/di/test_di_data_provider.py`, `tests/engine_test/test_reconcile_restart_resume_integration.py`, tests referencing removed Query/Command classes (`grep` in Task 4.3).

## Tasks

### Task 4.1 — Three DI provider modules
- **Goal:** every type registered exactly once, in one of three modules.
- **Target files and symbols:** `app/di/infrastructure.py` → `InfrastructureProvider` (Settings, EventBus, Database, Cache, all 11 repositories, JobScheduler, HealthCoordinator); `app/di/adapters.py` → `class BrokerFactory` (moved verbatim from `broker_factory.py`) and `AdaptersProvider` (BinanceClient, BinanceWebSocketClient, SyncPolicies, BrokerFactory); `app/di/services.py` → `ServicesProvider` (SyncService, BarAppService, QuoteAppService, WsSubscriptionManager, RiskCheckHandler, OrderAppService, PositionAppService, StrategyAppService, StrategyReconcileService, TrackedSymbolService, TrackedSymbolBackfillService, OhlcvService, QuoteQueryService, SyncStatusQueryService, SymbolQueryService, StrategyCommandService, StrategyQueryService, OrderPositionQueryService, BacktestCommandService, BacktestQueryService, BacktestStatsService, BacktestDispatchDeps, BacktestExecutionService); `app/di/__init__.py` → `PROVIDERS` list and `create_container()` (from `container.py`).
- **Steps:**
  1. Move each factory unchanged. Replace an `@provide` method by `x = provide(Class, scope=Scope.APP)` only when every non-default `__init__` parameter has a runtime-resolvable type annotation and the method does nothing but construct; keep factories for generators, async init, keyword constants (`EventBus(max_history=100)`, `HealthCoordinator(timeout=5.0)`, `StrategyReconcileService(interval_s=...)`, `StrategyAppService` config dict), and forward-ref params (`WsSubscriptionManager`).
  2. `main.py`: `from pocketquant.app.di import create_container`.
  3. Test containers: replace provider imports with `InfrastructureProvider, AdaptersProvider, ServicesProvider`; in `app_factory.py` list `TestCoreProvider(settings)` LAST (its Settings/EventBus must win); `test_reconcile_restart_resume_integration.py` imports `BrokerFactory` from `pocketquant.app.di.adapters`.
  4. Delete the 8 old modules.
- **Success criteria:** 4 `.py` files in `app/di` (3 providers + `__init__`).
- **Verify:** `ls src/pocketquant/app/di/*.py | wc -l` prints `4`; `grep -c "class .*Provider(Provider)" src/pocketquant/app/di/*.py | awk -F: '{s+=$2} END {print s}'` prints `3`; `.venv/Scripts/python.exe -m pytest tests/app_test/integration tests/engine_test/test_reconcile_restart_resume_integration.py -q` exit 0.

### Task 4.2 — Two market-data route files
- **Goal:** all `/market-data` routes in `routes/market_data.py`; `/quotes` stays in `routes/market_data_quotes.py`.
- **Target files and symbols:** `routes/market_data.py` holds `router = APIRouter(prefix="/market-data", tags=["Market Data"], route_class=DishkaRoute)` with handlers moved verbatim (names, decorators, docstrings, models `IntegrityRequest`, `OHLCVResponse`, `_make_payload`, `_POLL_INTERVAL`) from `market_data_sync.py`, `market_data_status.py`, `list_symbols.py`, `integrity.py`, `market_data_ohlcv.py`; and `tracked_symbols_router = APIRouter(tags=["Tracked Symbols"], route_class=DishkaRoute)` with the handlers from `tracked_symbols.py` (separate router keeps tags identical). `main_extensions.register_routes` imports `tracked_symbols_router` from `routes.market_data` (still `include_router(..., prefix="/market-data")`).
- **Steps:** move; in `sync_symbol_background` replace the `run_sync` closure with `background_tasks.add_task(sync_service.sync_one, cmd)`; delete the six files.
- **Success criteria:** OpenAPI and route inventory snapshots identical (do NOT set `BASELINE_UPDATE`).
- **Verify:** `ls src/pocketquant/app/routes/market_data*.py | wc -l` prints `2`; `ls src/pocketquant/app/routes/{integrity,list_symbols,tracked_symbols}.py 2>/dev/null | wc -l` prints `0`; `.venv/Scripts/python.exe -m pytest tests/baseline -q` exit 0.

### Task 4.3 — Drop scalar Query/Command wrappers
- **Goal:** services take scalars where the wrapper held 0-2 scalars and was not a request body.
- **Target files and symbols:** remove classes and change the matching service method signatures: `backtest/backtest_query_service.py` `GetBacktestQuery`; `backtest/backtest_command_service.py` `SetVerdictCommand`; `engine/orders_positions_service.py` `GetOrderQuery`, `ListOrdersQuery`, `GetPositionQuery`, `ListPositionsQuery`; `engine/strategy_command_service.py` `StartStrategyCommand`, `StopStrategyCommand`, `RemoveSymbolCommand`, `DeleteStrategyCommand`; `engine/strategy_query_service.py` `GetStrategiesQuery`, `GetStrategyQuery`, `ListSymbolsQuery`, `GetStrategyPositionsQuery`, `GetStrategyTradesQuery`; `engine/market_data/symbols_service.py` `ListSymbolsQuery`; `engine/market_data/quotes_service.py` `GetLatestQuoteQuery`; `engine/market_data/sync_status_service.py` `GetSyncStatusQuery`, `GetSymbolSyncStatusQuery`; `engine/market_data/tracked_symbols_service.py` `UpdateTrackedSymbolCommand`, `RemoveTrackedSymbolCommand`, `ListTrackedSymbolsQuery`. Keep: `RunBacktestCommand`, `ListBacktestsQuery`, `ListTradesQuery`, `AddSymbolCommand`, `GetOHLCVQuery`, `SyncSymbolCommand`, `BulkSyncCommand`, `BackfillTrackedSymbolCommand`, `AddTrackedSymbolCommand`, `SetVerdictBody`, `CreateSubscriptionBody`.
- **Steps:** for each class: change the service method to take the fields as parameters with the same names; update every caller in routes and tests (`grep -rn "\b<ClassName>\b" src tests` must end empty).
- **Success criteria:** HTTP contract unchanged.
- **Verify:** `grep -rnE "\b(GetBacktestQuery|SetVerdictCommand|GetOrderQuery|ListOrdersQuery|GetPositionQuery|ListPositionsQuery|StartStrategyCommand|StopStrategyCommand|RemoveSymbolCommand|DeleteStrategyCommand|GetStrategiesQuery|GetStrategyQuery|ListSymbolsQuery|GetStrategyPositionsQuery|GetStrategyTradesQuery|GetLatestQuoteQuery|GetSyncStatusQuery|GetSymbolSyncStatusQuery|UpdateTrackedSymbolCommand|RemoveTrackedSymbolCommand|ListTrackedSymbolsQuery)\b" src tests | wc -l` prints `0`; `.venv/Scripts/python.exe -m pytest tests/baseline tests/engine_test tests/app_test -q` exit 0.

### Task 4.4 — Three import-linter contracts
- **Goal:** keep only `layers`, `core.domain` free of `core.infra`, `fastapi only in app`.
- **Target files and symbols:** `pyproject.toml` `[[tool.importlinter.contracts]]` blocks named `Core imports no inner package`, `Engine imports no sibling/upper package`, `Backtest imports no upper package`, `No bson/ObjectId usage — UUID7 only` (removed); `CLAUDE.md` line `(7 contracts)` → `(3 contracts)`.
- **Steps:** delete the four blocks; edit `CLAUDE.md` text only in that parenthesis.
- **Success criteria:** bson stays banned through ruff `TID`.
- **Verify:** `uv run lint-imports` output contains `Contracts: 3 kept, 0 broken.`; `uv run ruff check` → `All checks passed!`; `grep -c "3 contracts" CLAUDE.md` prints `1`.

### Task 4.5 — Phase gate
- **Goal:** green and deployed.
- **Target files and symbols:** repo; `reports/lean-pass-metrics.md` (append `after-phase-04: <metrics line>`).
- **Steps:** gate; metrics line; user-approved commit `refactor(app): consolidate di providers, market-data routes and import contracts` + push.
- **Success criteria:** green; CI green.
- **Verify:** `just test` exit 0 (`passed`, no `failed`); `uv run ruff check` → `All checks passed!`; `uv run pyright` → `0 errors`; `uv run lint-imports` → `Contracts: 3 kept, 0 broken.`; `gh run list --workflow cicd.yml --limit 1 --json conclusion -q ".[0].conclusion"` prints `success`.

## Verification (test matrix)

- Unit: service signature changes via existing engine tests. Integration: full container resolution tests. E2E: OpenAPI + route inventory byte-identical.

## Risks

| Risk | L×I | Mitigation |
|------|-----|------------|
| Test container picks prod Settings after merge | M×M | `TestCoreProvider` last; integration tests fail loudly if wrong |
| OpenAPI drift from moved route docstrings/tags | M×M | verbatim move, separate tracked router; snapshot |
| Dishka cannot auto-resolve a converted `provide(Class)` | M×L | conversion rule in 4.1; container tests |

## Rollback

`git revert` + push. No data changes.

## Stop and ask

Unexplained test failure; any change to the public HTTP contract.

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

<!-- FILE: phase-05-lean-pass-and-code-standard.md -->
---
phase: 5
title: "Lean pass, metric gate and code standard"
status: pending
priority: P1
effort: 5d
dependencies: [4]
---

# Phase 05: Lean pass, metric gate and code standard

## Context Links

- Advice §2.3-2.4, §3 "do not overshoot", §7 soft-gate trade-off; thresholds A-iv: tiny share ≤0.30, delegations ≤20, functions ≲60 lines.
- Baseline (Phase 02): `functions=794 tiny=338 tiny_share=0.426 delegations=63 long_functions=22`. Reaching ≤0.30 needs ≈140 net tiny removals; delegations need −43.
- Current doc: `docs/code-standards.md` (799 lines; mandates "Service Extract-Method Pattern" §9 and file splitting; stale status claims).

## Goal

Remove indirection that buys nothing, measured by `scripts/code_metrics.py`, without gaming; rewrite the standard to describe the resulting code; wire the metric into CI as a soft gate.

## Rules for every package (binding)

- Allowed: delete a function with zero references in `src/`, `tests/`, `scripts/` (`grep -rnw "<name>" src tests scripts` shows only its `def`); inline a private helper whose name appears exactly twice in `src/` (def + one call) and 0 times in `tests/`, and is not passed as a callback/task target; convert an `@property` that is exactly `return self._<x>` on a non-port class to a public attribute; convert a dependency-only `__init__` (only `self._a = a` lines) of a service class to `@dataclass` with fields named like the current parameters, replacing `self._a` uses with `self.<param>`.
- Forbidden: adding statements or docstrings to escape the metric; removing port members (`IBroker`, `IDataProvider`, `IRealtimeQuoteProvider`, `IStrategy`); creating functions >60 lines; changing HTTP contract; removing `OrderAppService.on_order_update` (needed in Phase 07); removing any Binance/OKX capability (class, public method used by engine/routes, module).
- After each package: `just test` exit 0 and append `uv run python scripts/code_metrics.py` output to `reports/lean-pass-metrics.md` as `after-package-<X>: <line>`.

## Files to Create or Modify

- Modify (packages): files named in Tasks 5.2-5.6; `.github/workflows/cicd.yml`; `docs/code-standards.md`.
- Create: none (report lines go to `plans/261009-0858-exness-venue-lean-sync-refactor/reports/lean-pass-metrics.md`).

## Tasks

### Task 5.1 — Work list
- **Goal:** the current tiny/delegation list is captured.
- **Target files and symbols:** `reports/lean-pass-metrics.md`.
- **Steps:** `uv run python scripts/code_metrics.py --list > /tmp/metrics-list.txt`; append its first line to the report as `start-phase-05: <line>`.
- **Success criteria:** line present.
- **Verify:** `grep -c "^start-phase-05: functions=" plans/261009-0858-exness-venue-lean-sync-refactor/reports/lean-pass-metrics.md` prints `1`.

### Task 5.2 — Package A: dead code
- **Goal:** remove functions with zero references.
- **Target files and symbols (re-verify each with grep before deleting):** `backtest/jobs/backtest_strategy_loader.py:41 build_backtest_config`; `core/common/messaging/event_bus.py:45 clear_history`; `core/common/messaging/event_registry.py:67 get_registered`; `core/common/time/simulation.py:38 is_simulation_active`; `core/domain/strategy/interfaces.py:89 get_parameter`; `core/domain/symbol/entities.py:72 deactivate`, `:75 activate`; `core/infra/brokers/okx/okx_mapper.py:7 map_okx_order_state`; `core/infra/brokers/okx/websocket/okx_message_parser.py:51 get_event_type`, `:55 get_event_code`, `:59 get_event_message`; `okx_order_mapper.py:80 get_client_order_id`, `:88 get_symbol`, `:93 get_side`; `okx_position_mapper.py:86 get_position_id`, `:90 get_inst_id`, `:94 is_position_closed`; `engine/app_services/order_app_service.py:170 get_orders_by_strategy`, `:222 get_orders_by_strategy_async`; `engine/app_services/strategy_app_service.py:205 get_strategies`; `engine/market_data/app_services/quote_dto.py:91 to_ohlcv_dict`.
- **Steps:** for each: grep; delete if zero refs; skip and note in report otherwise.
- **Success criteria:** OKX characterization still green.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/brokers -q` exit 0; `just test` exit 0.

### Task 5.3 — Package B: single-use helpers
- **Goal:** inline one-call helpers that only rename a line.
- **Target files and symbols (re-verify rule):** `backtest/backtest_stats_service.py:149 _trade_to_dto`; `backtest/engine/backtest_app_service.py:179 _load_bars`, `:190 _wrap_bars_with_price_update`; `backtest/engine/result_collector.py:88 set_run_id`, `:209 _create_stub_order`, `:227 _append_fill`, `:251 _emit_trades`, `:364 _consumed_pnl`; `backtest/workers/backtest_dispatch.py:43 _config_from_dict`; `core/common/health/coordinator.py:29 _run_check`; `core/domain/risk/services/position_sizer.py:80 _fixed_size`; `core/infra/binance/binance_websocket_client.py:209 _invoke_callback`; `core/infra/brokers/okx/okx_mapper.py:18 map_order_side_to_okx`, `:22 map_order_type_to_okx`; `okx_message_parser.py:13 is_event`, `:17 is_data`, `:21 get_channel`, `:25 get_data`; `okx_order_mapper.py:76 get_order_id`, `:84 get_state`; `okx_reconnection_handler.py:193 _fetch_open_orders`; `core/infra/brokers/paper/paper_broker.py:454 _limit_crosses`, `:460 _limit_crosses_bar`; `core/infra/http_client/client.py:27 _get_client`; `core/infra/persistence/repositories/job_history_repository.py:348 _serialize`; `engine/market_data/quotes_service.py:32 from_quote`.
- **Steps:** inline one at a time; skip if the caller would exceed 60 lines.
- **Success criteria:** behaviour unchanged.
- **Verify:** `just test` exit 0; `.venv/Scripts/python.exe -m pytest tests/core_test/infra/brokers tests/core_test/infra/binance -q` summary for binance equals the recorded `binance:` line.

### Task 5.4 — Package C: dependency-only service constructors and plain properties
- **Goal:** remove boilerplate constructors/getters.
- **Target files and symbols:** `@dataclass` conversion candidates: `engine/market_data/ohlcv_service.py OhlcvService`, `quotes_service.py QuoteQueryService`, `symbols_service.py SymbolQueryService`, `sync_status_service.py SyncStatusQueryService`, `tracked_symbols_service.py TrackedSymbolService`, `tracked_symbols_backfill.py TrackedSymbolBackfillService`, `engine/strategy_query_service.py StrategyQueryService`, `engine/orders_positions_service.py OrderPositionQueryService`, `engine/strategy_command_service.py StrategyCommandService`, `backtest/backtest_command_service.py BacktestCommandService`, `backtest/backtest_query_service.py BacktestQueryService`, `backtest/backtest_execution_service.py BacktestExecutionService`, `backtest/backtest_stats_service.py BacktestStatsService`. Property candidates: `PaperBroker.slippage` (+setter → attribute `slippage`), `OKXBroker.trade_api`, `OKXBroker.seen_terminal_orders`, `Database.database`, `LotTracker.lots` — only if the body is exactly `return self._x`.
- **Steps:** convert one class at a time; Dishka resolves dataclass `__init__` from annotations (types must be imported at runtime, not under `TYPE_CHECKING`); update tests that read `obj._x`.
- **Success criteria:** container tests green.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/app_test/integration tests/engine_test tests/backtest_test -q` exit 0.

### Task 5.5 — Package D: remaining backlog from `--list`
- **Goal:** continue only while the rules hold, prioritising `core/infra` and `engine` items listed as `tiny`/`delegation`.
- **Target files and symbols:** items from `/tmp/metrics-list.txt` that satisfy the allowed rules; never routes, ports, `to_mongo`/`from_mongo`, dunder methods.
- **Steps:** process in file order; stop when both thresholds are met or no item satisfies the rules.
- **Success criteria:** each change obeys the rules.
- **Verify:** `just test` exit 0 after each file.

### Task 5.6 — Threshold gate
- **Goal:** D4 metric targets met honestly.
- **Target files and symbols:** `scripts/code_metrics.py`.
- **Steps:** run with thresholds. If it fails, apply the Failure Protocol and report the projection to the user (see Risks): the decision to accept, relax, or change the definition belongs to the user (confirmed threshold).
- **Success criteria:** both thresholds met.
- **Verify:** `uv run python scripts/code_metrics.py --max-tiny-share 0.30 --max-delegations 20` exit 0.

### Task 5.7 — CI soft gate
- **Goal:** numbers visible on every push without blocking deploys.
- **Target files and symbols:** `.github/workflows/cicd.yml` job `tests`, new step after `Check import contracts (layered architecture)`.
- **Steps:** add:
  ```yaml
      - name: Code metrics (soft gate)
        continue-on-error: true
        run: uv run python scripts/code_metrics.py --max-tiny-share 0.30 --max-delegations 20
  ```
- **Success criteria:** step present with `continue-on-error: true`.
- **Verify:** `grep -A2 "Code metrics (soft gate)" .github/workflows/cicd.yml | grep -c "continue-on-error: true"` prints `1`.

### Task 5.8 — Rewrite `docs/code-standards.md`
- **Goal:** the standard describes the code as it is now (Vietnamese prose, English technical terms, AS-IS, no banners/changelog).
- **Target files and symbols:** `docs/code-standards.md`.
- **Steps:**
  1. Keep (edit to match code): Comment Policy section (binding, from `CLAUDE.md`), "Await Is Preemption", UUIDv7 primary key, composite symbol, datetime serialization, configuration & secrets.
  2. Replace: extract-method mandate and 200-LOC cap with rules of thumb — extract only when the name adds meaning or the code is reused; one flow readable in one file where possible, ≤3 files; functions ≲60 lines; file ~400 LOC soft guidance, not a split trigger.
  3. Suffix table trimmed to `Repository`, `Service`, `Event`, `Error`, `Provider` (DI); `AppService`/`CommandService`/`QueryService` are not separate roles (existing class names stay).
  4. Routes: `FromDishka[...]` + `DishkaRoute`; scalars for simple reads, Pydantic models for request bodies.
  5. DI: three provider modules (`infrastructure`, `adapters`, `services`), one registration per type.
  6. New section "Sync policy pattern": `SyncPolicy` field table, the runner pipeline, how to add a provider (adapter package + policy factory + DI registration).
  7. Quality gates: ruff, pyright, `lint-imports` (3 contracts listed by name), `scripts/code_metrics.py` soft gate with thresholds and definitions, characterization tests before refactors.
  8. Remove every "Current Status"/largest-file claim and the "Deprecated Patterns" list items that refer to code that no longer exists.
- **Success criteria:** no stale claims.
- **Verify:** `grep -ci "current status\|Extract-Method\|200 LOC\|7 contracts" docs/code-standards.md` prints `0`; `grep -c "SyncPolicy" docs/code-standards.md` prints ≥ `1`; `grep -c "code_metrics.py" docs/code-standards.md` prints ≥ `1`.

### Task 5.9 — Phase gate
- **Goal:** green, measured, deployed.
- **Target files and symbols:** repo.
- **Steps:** gate; append final metrics line; user-approved commit `refactor: inline single-use helpers, drop dead code; rewrite code standard` + push.
- **Success criteria:** green; CI green.
- **Verify:** `just test` exit 0 (`passed`, no `failed`); `uv run ruff check` → `All checks passed!`; `uv run pyright` → `0 errors`; `uv run lint-imports` → `Contracts: 3 kept, 0 broken.`; `uv run python scripts/code_metrics.py --max-tiny-share 0.30 --max-delegations 20` exit 0; `gh run list --workflow cicd.yml --limit 1 --json conclusion -q ".[0].conclusion"` prints `success`.

## Verification (test matrix)

- Unit/integration: full suite after each package. E2E: OpenAPI snapshot. Metric: per-package lines in the report.

## Risks

| Risk | L×I | Mitigation |
|------|-----|------------|
| ≤20 delegations unreachable without gaming: 14 of the 63 are FastAPI route handlers (`return await svc.x(...)`) and ~10 are port/repository methods; legitimate packages project ≈35-45 | H×M | gate in 5.6 stops; user decides (plan.md "Open decisions") |
| Tiny share lands ≈0.30-0.32 | M×M | Package D backlog; Exness code (Phases 06-07) is written to the standard |
| Inlining breaks OKX paths without tests | M×H | Phase 02 OKX characterization must stay green |
| Gaming via docstrings | L×M | forbidden by rules; reviewer checks diff for added docstrings |

## Rollback

`git revert` per package commit if split, else the phase commit.

## Stop and ask

Metric gate fails after Package D; any OKX/Binance capability removal.

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

<!-- FILE: phase-06-exness-market-data-adapters.md -->
---
phase: 6
title: "Exness market-data adapters (policy #2)"
status: pending
priority: P1
effort: 6d
dependencies: [1, 5]
---

# Phase 06: Exness market-data adapters (policy #2)

## Context Links

- Advice §2.5, §2.7, §3 (no generated client); state R1/R2, A-ii, A-iii, A-v.
- Spike results: `plans/261009-0858-exness-venue-lean-sync-refactor/reports/exness-spike-findings.md`; fixtures `tests/core_test/infra/exness/fixtures/`.
- Spec v1.0.2: candles (`from` inclusive, `to` exclusive, `count` bidirectional, `price_type` default `bid`); `WSTick {instrument,bid,ask,timestamp}`; tick throttle up to 500 ms; last tick sent on subscribe; ticks unavailable when `trade_mode=trading_disabled`; WS strikes for unknown instruments.
- Quote dict consumed by `QuoteAppService.on_quote_update` (`app/market_data/app_services/quote_app_service.py:35`): keys `symbol` (composite), `last_price`, `bid`, `ask`, `volume`, `timestamp`.
- Reconnect shape: OKX `okx_reconnection_handler.py:16-20` (1 s → 30 s, ×2; circuit breaker after 10 failures, 300 s pause).

## Goal

`core/infra/exness/` provides `IDataProvider` and `IRealtimeQuoteProvider`; `exness_policy` is registered when credentials exist. D1 holds in prod. Lots/spread/contract size stay inside the adapter.

## Files to Create or Modify

- Create: `src/pocketquant/core/infra/exness/__init__.py`, `signer.py`, `client.py`, `websocket.py`, `mappers.py`, `data_provider.py`, `quote_provider.py`; tests `tests/core_test/infra/exness/test_signer.py`, `test_client.py`, `test_websocket.py`, `test_mappers.py`, `test_data_provider.py`, `test_quote_provider.py`
- Modify: `src/pocketquant/core/config.py`, `src/pocketquant/engine/market_data/sync_policy.py`, `src/pocketquant/app/di/adapters.py`, `scripts/exness_spike.py`, `tests/scripts/test_exness_spike.py` (moved), `tests/app_test/unit/di/test_di_data_provider.py`
- Not touched: `deploy/`, `core/domain/` (no CFD concepts in domain).

## Tasks

### Task 6.1 — Settings
- **Goal:** all Exness configuration in one place, optional, secrets masked.
- **Target files and symbols:** `core/config.py` `Settings`: `exness_base_url: str = ""`, `exness_ws_base_url: str = ""`, `exness_account_id: str = ""`, `exness_api_key: SecretStr | None = None`, `exness_private_key: SecretStr | None = None`, `exness_private_key_path: str = ""`, `exness_live_trading: bool = False`, `exness_max_lots: float = 0.0`, `exness_daily_loss_limit: float = 0.0`.
- **Steps:** add after the OKX block.
- **Success criteria:** tests hermetic (defaults disable Exness).
- **Verify:** `uv run python -c "from pocketquant.core.config import Settings;s=Settings(_env_file=None,app_name='a',app_version='0',environment='development',mongodb_url='mongodb://x:1/d',mongodb_database='d',mongodb_min_pool_size=1,mongodb_max_pool_size=2,redis_url='redis://x:1/0',redis_cache_ttl=1,log_level='INFO',log_format='json',exness_api_key='zzsecretzz');print('zzsecretzz' in repr(s))"` prints `False`.

### Task 6.2 — `signer.py`
- **Goal:** signing lives in `src`; the spike reuses it (DRY).
- **Target files and symbols:** `core/infra/exness/signer.py`: `b64url`, `body_hash`, `load_private_key(settings_or_raw)`, `signed_headers(...)` moved from `scripts/exness_spike.py`; spike imports them; tests move to `tests/core_test/infra/exness/test_signer.py` (delete `tests/scripts/test_exness_spike.py`).
- **Steps:** move; `load_private_key(raw: str)` plus `def private_key_from_settings(settings) -> Ed25519PrivateKey` (reads `exness_private_key` or file at `exness_private_key_path`).
- **Success criteria:** spec vector test passes from new location.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_signer.py -q` exit 0; `grep -c "def signed_headers" scripts/exness_spike.py` prints `0`.

### Task 6.3 — `client.py`
- **Goal:** one signed REST client shared by data provider, quote provider and broker, with self-tracked rate budget.
- **Target files and symbols:** `class ExnessClient`: `__init__(self, settings: Settings)` (no I/O), `is_configured: bool`, `async request(method, path, *, query: dict | None = None, body: dict | None = None, idempotency_key: str = "") -> Any`, `async limits() -> dict` (cached), `async candle_page_size() -> int` (`max_candles_per_request` of `getCandleHistory`), `async instruments() -> list[str]` (cached 24 h), `async resolve_instrument(code: str) -> str` (exact `name.upper() == code`, else `ValueError`), `async conditions(instrument) -> dict` (cached 24 h), `async account() -> dict`, `async candles(instrument, timeframe, start: datetime, count: int) -> list[dict]`, `async snapshot() -> dict`, `async operation(operation_id) -> dict`, `async open_position(body, key) -> dict`, `async close_position(position_id, volume: str, key) -> dict`, `async place_order(body, key) -> dict`, `async cancel_order(order_id, key) -> dict`, `async aclose()`; private `_TokenBucket` (capacity `global_account_rate.limit`, refill `limit/window_seconds`).
- **Steps:**
  1. Query encoding and signing exactly as the spike (`path?query`, `Z` timestamps); `httpx.AsyncClient(base_url=settings.exness_base_url, timeout=15)`.
  2. Timestamp = local ms + offset; offset updated from each response `Date` header when |offset| > 1 s.
  3. On HTTP 429: sleep `Retry-After` (default 1 s) and retry once; then raise `ExnessApiError(code, message)` built from the error body (`error.code`); never include headers in exceptions or logs.
  4. Tests with `httpx.MockTransport` + fixtures: headers present and verify; GET has empty `EXN-IDEMPOTENCY-KEY`; POST body hash matches; 429 retried once; `resolve_instrument("XAUUSD")` uses `instruments.json`; bucket waits when empty (monkeypatch clock).
- **Success criteria:** no secret in logs.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_client.py -q` exit 0; `grep -nE "logger\.[a-z]+\(.*(header|EXN-|api_key|private)" src/pocketquant/core/infra/exness/client.py | wc -l` prints `0`.

### Task 6.4 — `websocket.py`
- **Goal:** one reconnecting signed stream used for `ticks` (quotes) and `events` (broker).
- **Target files and symbols:** `class ExnessStream`: `__init__(self, client: ExnessClient, path: str, on_open: Callable[[], Awaitable[None]], on_message: Callable[[dict], Awaitable[None]])`, `async send(msg: dict)`, `async run_forever()`, `async close()`, `is_connected() -> bool`; constants `_INITIAL_DELAY=1.0`, `_MAX_DELAY=30.0`, `_MULTIPLIER=2.0`, `_BREAKER_FAILURES=10`, `_BREAKER_PAUSE=300.0`.
- **Steps:** fresh signed GET headers per connect; `subprotocols` per `ws_subprotocol_required` in findings; on open call `on_open` (re-subscribe); reset backoff on successful open; after 10 consecutive failures log `exness_ws.circuit_breaker_open` and pause 300 s; handshake 400 with `trading_disabled` → log `exness_ws.trading_disabled` and back off (no crash). Tests: fake `connect` raising 3 times → sleeps `[1,2,4]`; 10 failures → pause 300 and one breaker log.
- **Success criteria:** never raises out of `run_forever` except `CancelledError`.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_websocket.py -q` exit 0.

### Task 6.5 — `mappers.py` (market data part)
- **Goal:** pure conversions, unit-tested on fixtures.
- **Target files and symbols:** `INTERVAL_TO_TIMEFRAME = {1m:"M1",5m:"M5",15m:"M15",1h:"H1",4h:"H4",1d:"D1",1w:"W1"}`; `candle_to_bar(candle: dict, symbol: str, interval: Interval) -> Bar` (bid prices, `volume=float(candle["volume"])` tick volume, pattern `binance_mappers.kline_to_bar`); `tick_to_quote(tick: dict, code: str) -> dict` (`{"symbol": f"{code}:EXNESS", "last_price": bid, "bid": bid, "ask": ask, "volume": None, "timestamp": parsed}`); `parse_sessions(trade_sessions: list[dict]) -> list[tuple[int, int]]` (minutes from Monday 00:00 UTC; "Mon, 10:00:00"); `is_open_at(sessions, at: datetime) -> bool`.
- **Steps:** implement; tests use `candles_XAUUSD_M1.json`, `ticks_sample.jsonl`, `conditions_*.json` (FX instrument closed Saturday 12:00 UTC; BTCUSD per `btcusd_weekend_sessions`).
- **Success criteria:** every fixture candle maps to an aligned `Bar`.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_mappers.py -q` exit 0.

### Task 6.6 — `data_provider.py`
- **Goal:** `IDataProvider` over native Exness candles (A-ii bid, A-iii tick volume).
- **Target files and symbols:** `class ExnessDataProvider(IDataProvider)`: `fetch_ohlcv(symbol, interval, n_bars=1000)`, `search_symbols(query)`, `close()`, `is_market_open(symbol, at)`.
- **Steps:**
  1. `fetch_ohlcv`: instrument = `resolve_instrument(code)`; `cutoff = get_bar_start(now, interval)`; page with `from=cutoff, count=-min(remaining, page_size)`, next `from` = oldest returned time; stop on empty/short page or `ExnessApiError` with history-range code (return collected); drop candles with time ≥ cutoff (in-progress); dedupe by time; ascending.
  2. `is_market_open`: `is_open_at(parse_sessions(conditions(instrument)["trade_sessions"]), at)`; missing sessions → `True`.
  3. `search_symbols`: instruments containing `query.upper()` as `[{"symbol": f"{name.upper()}:EXNESS"}]`.
  4. Tests (fake client): 2500 bars over page size 1000 → 3 pages, ascending, no duplicates, none ≥ cutoff.
- **Success criteria:** no lot/contract logic here.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_data_provider.py -q` exit 0.

### Task 6.7 — `quote_provider.py`
- **Goal:** `IRealtimeQuoteProvider` over the ticks stream.
- **Target files and symbols:** `class ExnessQuoteProvider` with all 9 protocol members (`last_tick_at`, `connect`, `disconnect`, `subscribe`, `unsubscribe`, `run_forever`, `is_connected`, `subscription_count`, `subscriptions`).
- **Steps:** `subscribe(symbol, cb)` resolves the instrument first (unknown → `ValueError`, no WS message → no strike), stores `{composite: (instrument, cb)}`, sends subscribe if connected; `on_open` re-subscribes all; `on_message`: tick frames → drop if `now - timestamp > 120 s` (log `exness_ticks.stale_tick_dropped`; prevents a stale weekend tick from closing a bar), else set `last_tick_at` and call `cb(tick_to_quote(...))`; error frames → warning log. Tests: protocol `isinstance`; stale tick dropped; fresh tick produces the quote dict.
- **Success criteria:** `isinstance(ExnessQuoteProvider(...), IRealtimeQuoteProvider)` is true.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_quote_provider.py -q` exit 0.

### Task 6.8 — Exness policy and DI registration
- **Goal:** adding Exness touched only the adapter package, one policy factory and DI.
- **Target files and symbols:** `sync_policy.py` `def exness_policy(bar_source, live_source, min_request_interval_s: float) -> SyncPolicy` (`exchange="EXNESS"`, `poll_intervals=stored_intervals=(1m,5m,15m,1h,4h,1d)`, `cascade=False`, `poll_n_bars=10`, `calendar="venue_sessions"`, `history_days={1m:365,5m:730,15m:1095,1h:None,4h:None,1d:None}`); `app/di/adapters.py`: `ExnessClient` (always constructed), `get_sync_policies(binance, binance_ws, exness_client)` adds `EXNESS` only when `exness_client.is_configured`; `min_request_interval_s` = `0.0` if findings `candles_rate_per_min >= 72`, else `60 / candles_rate_per_min` (write the computed constant into the factory call).
- **Steps:** implement; extend `test_di_data_provider.py`: unconfigured → only `BINANCE`; configured (fake settings) → `EXNESS` policy with `ExnessDataProvider`/`ExnessQuoteProvider`.
- **Success criteria:** without env, runtime identical to Phase 05.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/app_test/unit/di tests/baseline -q` exit 0; `git diff --stat HEAD -- src/pocketquant/engine/market_data/sync_runner.py src/pocketquant/engine/market_data/sync_service.py | wc -l` prints `0` (runner untouched — G2 proof).

### Task 6.9 — Phase gate and deploy
- **Goal:** green and live in prod with Exness data only (no trading).
- **Target files and symbols:** repo; `pocketquant-config` (user).
- **Steps:** gate; metrics line `after-phase-06`; user-approved commit `feat(exness): add exness market data and quote adapters as a sync policy` + push; ask the user to add the Exness env vars (not live-trading ones) to `pocketquant-config/vps/default/.env` and redeploy.
- **Success criteria:** CI green.
- **Verify:** `just test` exit 0; `uv run ruff check` → `All checks passed!`; `uv run pyright` → `0 errors`; `uv run lint-imports` → `Contracts: 3 kept, 0 broken.`; `uv run python scripts/code_metrics.py --root src/pocketquant/core/infra/exness --fail-on-long` exit 0; `gh run list --workflow cicd.yml --limit 1 --json conclusion -q ".[0].conclusion"` prints `success`.

### Task 6.10 — D1 end-to-end in prod
- **Goal:** Exness bars and streams work through the existing API/SPA.
- **Target files and symbols:** `POST /api/v1/market-data/tracked-symbols`, `POST /api/v1/market-data/sync`, `GET /api/v1/market-data/bars/stream/{symbol}`, `GET /api/v1/quotes/stream/{symbol}`.
- **Steps:** in Git Bash at the repo root define `vps() { ssh -i ../pocketquant-config/vps/default/id_rsa "$(cat ../pocketquant-config/vps/default/host)" "$@"; }` (same key/host as `docs/deployment.md`). Commands run inside the app container read `$ADMIN_TOKEN` from the container env; the quoted heredoc stops local expansion:
  1. Track symbols (use composites from findings if renamed):
     ```bash
     vps 'docker exec -i pocketquant-app sh -s' <<'EOF'
     for s in XAUUSD EURUSD BTCUSD; do
       curl -s -X POST localhost:41921/api/v1/market-data/tracked-symbols -H "X-Admin-Token: $ADMIN_TOKEN" -H "Content-Type: application/json" -d "{\"symbol\":\"$s:EXNESS\"}"; echo
     done
     EOF
     ```
  2. Sync, saving the response locally:
     ```bash
     vps 'docker exec -i pocketquant-app sh -s' > /tmp/d1-sync.json <<'EOF'
     curl -s -X POST localhost:41921/api/v1/market-data/sync -H "Content-Type: application/json" -d '{"symbol":"XAUUSD:EXNESS","interval":"1m","n_bars":1000}'
     EOF
     ```
  3. During market hours, bar and quote SSE (commands in Verify).
- **Success criteria:** D1.
- **Verify:** `uv run python -c "import json;d=json.load(open('/tmp/d1-sync.json'));print(d['status']=='completed' and d['total_bars']>=1000)"` prints `True`; `vps "docker exec pocketquant-app curl -sN --max-time 60 'localhost:41921/api/v1/market-data/bars/stream/XAUUSD%3AEXNESS?interval=1m'" | grep -c '"is_in_progress": true'` prints ≥ `1`; `vps "docker exec pocketquant-app curl -sN --max-time 30 localhost:41921/api/v1/quotes/stream/XAUUSD%3AEXNESS" | grep -c '"bid"'` prints ≥ `1`.

## Verification (test matrix)

- Unit: signer, client (MockTransport), stream backoff, mappers, data provider paging, quote provider. Integration: DI policy registration. E2E: Task 6.10 in prod.

## Risks

| Risk | L×I | Mitigation |
|------|-----|------------|
| Rate budget exceeded (18 calls/min) | M×M | token bucket from `/limits`; `min_request_interval_s` |
| Stale initial tick closes a bar | M×H | 120 s staleness drop |
| WS strikes → 1008 close | L×M | resolve instruments before subscribe |
| Exness drift on weekends floods no-progress logs | M×L | `venue_sessions` calendar skips closed symbols |

## Security

`SecretStr` for key/private key; private key from env or a file outside the repo; never log headers or exception bodies containing headers; fixtures redacted.

## Rollback

Remove Exness env vars from `pocketquant-config` and redeploy → policy not registered (kill switch without code change); or `git revert` + push. Tracked `*:EXNESS` symbols are then skipped with `market_data.sync.no_policy`.

## Stop and ask

Limits make A-v infeasible in prod (`REQUEST_RATE_LIMIT` on candles in steady state); any change under `deploy/` would be needed.

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

<!-- FILE: phase-07-exness-broker-and-live-routing.md -->
---
phase: 7
title: "Exness broker and live routing"
status: pending
priority: P1
effort: 5d
dependencies: [6]
---

# Phase 07: Exness broker and live routing

## Context Links

- Advice §2.6, §3 (no domain fork); state R1.
- Today no live broker fill reaches `OrderAppService`: `OrderAppService.on_order_update` (`engine/app_services/order_app_service.py:174`) has no caller; `StrategyAppService._get_or_create_broker` (`strategy_app_service.py:409`) never subscribes. Every subscription trades `paper` (`StrategyConfig.broker="paper"`, rehydrate/reconcile pass no broker; `Settings.default_broker` unused).
- Order state machine: `SUBMITTED → {PARTIALLY_FILLED, FILLED, CANCELLED}` only (`core/domain/order/entities.py:52-57`); an async venue rejection must map to `CANCELLED`.
- PaperBroker publishes `OrderFilledEvent` for venue-side exits itself (`paper_broker.py:710-723`) — same pattern for Exness SL/TP closes.
- Spec: `POST /positions` (`OpenPositionRequest`: `instrument`, `side`, `volume`, `stop_loss_price`, `take_profit_price`); `DELETE /positions/{position_id}?volume=`; `POST /orders` / `DELETE /orders/{order_id}`; ACK `{operation_id, client_request_id, status:"accepted"}`; `transaction_event {operation_id, client_request_id, status, error_code, payload{orders,positions,deals,account_state}}`; idempotency key 5-128 chars `[A-Za-z0-9._~-]` echoed as `client_request_id`; `Deal.type` `open|close|...`.

## Goal

`ExnessBroker(IBroker)` with lot conversion, SL enforcement, user risk caps and async fills; Exness symbols route to it only when `EXNESS_LIVE_TRADING=true`; Binance/OKX/paper routing unchanged.

## Data flow

```
Signal → StrategyAppService._process_signal → OrderAppService.submit → ExnessBroker.submit_order
  → guards (SL, max lots, daily loss) → qty→lots (contract_size, volume_step/min/max) → POST /positions (key = order.id)
  → OrderResult(SUBMITTED, broker_order_id=operation_id)
events WS transaction_event(client_request_id=order.id) → OrderResult(FILLED|CANCELLED) → OrderAppService.on_order_update
  → OrderFilledEvent → PositionAppService / strategy
venue SL/TP close (no known client_request_id, deal type close) → ExnessBroker publishes OrderFilledEvent(opposite side)
```

## Files to Create or Modify

- Create: `src/pocketquant/core/infra/exness/broker.py`, `tests/core_test/infra/exness/test_broker.py`, `tests/engine_test/test_strategy_live_broker_routing.py`
- Modify: `src/pocketquant/core/infra/exness/mappers.py`, `src/pocketquant/app/di/adapters.py` (`BrokerFactory`), `src/pocketquant/app/di/services.py` (StrategyAppService factory), `src/pocketquant/engine/app_services/strategy_app_service.py`

## Tasks

### Task 7.1 — Trading mappers
- **Goal:** lot math and event mapping are pure and tested.
- **Target files and symbols:** `mappers.py`: `quantity_to_lots(quantity: float, conditions: dict, max_lots: float) -> tuple[Decimal | None, str | None]` (Decimal; `raw = qty / contract_size`; `raw < volume_min` → `(None, "volume below minimum lot")`; `lots = volume_min + floor((raw-volume_min)/step)*step`; cap = min(`volume_max`, `max_lots` floored to step); `max_lots <= 0` → `(None, "EXNESS_MAX_LOTS not set")`; cap < volume_min → `(None, "EXNESS_MAX_LOTS below minimum lot")`); `format_price(price, point_digits) -> str`; `account_to_balance(snapshot: dict, currency: str) -> AccountBalance` (`total_equity=equity`, `available_balance=equity-used_margin`, `margin_used=used_margin`, `unrealized_pnl=equity-balance`); `position_to_aggregate(...)` (pattern `okx_mapper.map_okx_position_to_domain`).
- **Steps:** implement; table tests: XAUUSD contract 100, min 0.01, step 0.01: qty 0.5 → below min; qty 3.7 with cap 0.01 → 0.01; qty 1 with cap 0 → not set.
- **Success criteria:** no float rounding errors (Decimal string out, e.g. `"0.01"`).
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_mappers.py -q` exit 0.

### Task 7.2 — `broker.py`
- **Goal:** full `IBroker` with async fills and guards.
- **Target files and symbols:** `class ExnessBroker(IBroker)`: `__init__(self, client: ExnessClient, event_bus: EventBus, max_lots: float, daily_loss_limit: float)`; `name` → `"exness"`; `is_connected`; `connect()` (start `ExnessStream` on `/v1/server-events/accounts/{id}/ws/events`, `on_open` sends `{"id": "events-<n>", "subscribe": {"event": "transactions"}}`); `disconnect()`; `submit_order(order)`; `cancel_order(broker_order_id)`; `get_positions()`; `get_balance()`; `subscribe_order_updates(cb)`; `unsubscribe_order_updates()`; private `_on_event(msg)`, `_on_transaction(event)`, `_confirm_after_ack(operation_id, order_id)`; state `_requests: dict[str, _Request]` (order id → subscription id, symbol, side, contract_size, kind open/close/pending, position_id), `_positions: dict[str, _Tracked]` (position id → subscription id, symbol, side, contract_size), `_seen: set[str]`, `_day_equity: tuple[date, float] | None`.
- **Steps:**
  1. `submit_order`: if an open tracked position exists for `order.subscription_id` + `order.symbol` with the opposite side → `close_position(position_id, volume=<its lots>, key=str(order.id))`, kind `close`. Else (open): require `order.sl_price` (`REJECTED`, `"stop loss required"`); daily loss: `bal = await get_balance()`; reset `_day_equity` on new UTC date; if `start - bal.total_equity >= daily_loss_limit` or `daily_loss_limit <= 0` → `REJECTED`; `quantity_to_lots` → `REJECTED` with its reason; MARKET → `open_position` with `stop_loss_price`/`take_profit_price` formatted to `point_digits`; LIMIT → `place_order` (`NewLimitOrderRequest`, spec lines ~3336-3375). Return `OrderResult(order_id=str(order.id), broker_order_id=ack["operation_id"], status=SUBMITTED, submitted_at=now, sl_price, tp_price, side)`; log `exness.order_submitted` with `lots`, `instrument`; `asyncio.create_task(_confirm_after_ack(...))`.
  2. `_on_transaction`: dedupe on `client_request_id or operation_id`; known request + `status=success` → use the first deal with `type` in (`open`,`close`): `filled_quantity = float(deal.volume) * contract_size`, `filled_price = float(deal.price)`; record/remove `_positions` from `payload.positions`; notify `OrderResult(FILLED)`; known request + rejected/failed → notify `OrderResult(CANCELLED, error_message=f"{error_code}: {error_message}")`; unknown request + success + close deals on a tracked position → publish `OrderFilledEvent(order_id=f"exness-deal-{deal_id}", subscription_id, symbol, side=opposite, filled_quantity, filled_price)` on `event_bus`, log `exness.venue_close`; untracked position close → log `exness.close_unrouted`.
  3. Other events: `trading_state_snapshot` (log open position count), `account_state_event` (debug), `hmr_snapshot`/`hmr_update` (info `exness.hmr_event`), `instrument_event` (debug); never raise.
  4. `_confirm_after_ack`: sleep 10 s; if still pending → `operation(op_id)`; `rejected`/`failed` → CANCELLED result; `confirmed` → `snapshot()` and match a new position by instrument+direction → FILLED; else log `exness.operation_unresolved`.
  5. Tests (fake client + recorded callbacks + real `EventBus`): open → SUBMITTED then FILLED via event with `client_request_id`; duplicate event ignored; async reject → CANCELLED; venue SL close publishes one opposite-side `OrderFilledEvent`; no SL → REJECTED without HTTP call; cap 0 → REJECTED; daily loss reached → REJECTED; opposite order closes tracked position via `close_position`.
- **Success criteria:** no lot/CFD logic outside `core/infra/exness/`.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_broker.py -q` exit 0; `grep -rniE "contract_size|volume_step|volume_min|max_lots" src/pocketquant/core/domain src/pocketquant/engine | wc -l` prints `0` (it is `0` today).

### Task 7.3 — Broker factory entry
- **Goal:** `broker_type == "exness"` builds the broker from settings.
- **Target files and symbols:** `app/di/adapters.py` `BrokerFactory.__init__(self, event_bus: EventBus, settings: Settings | None = None, exness_client: ExnessClient | None = None)`; `create("exness", config)` → `ValueError("Exness broker requires EXNESS_ACCOUNT_ID, EXNESS_API_KEY, EXNESS_PRIVATE_KEY")` when not configured; else `ExnessBroker(exness_client, event_bus, settings.exness_max_lots, settings.exness_daily_loss_limit)`; add `"exness"` to `get_available_types` if that method still exists. DI factory passes settings and client.
- **Steps:** implement; existing `BrokerFactory(event_bus)` test call keeps working.
- **Success criteria:** paper/okx branches unchanged.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/engine_test/test_reconcile_restart_resume_integration.py tests/app_test/unit/di -q` exit 0.

### Task 7.4 — Live routing for Exness symbols
- **Goal:** `*:EXNESS` subscriptions use the Exness broker only when the live flag is on; fills reach `OrderAppService`.
- **Target files and symbols:** `StrategyAppService.__init__(..., live_broker_by_exchange: dict[str, str] | None = None)`; in `load_strategy` the broker type = `self._live_broker_by_exchange.get(<exchange of config.symbol>, config.broker)`; in `_get_or_create_broker`, after `create(...)`, `if broker_type == "exness": await broker.subscribe_order_updates(self._order_app_service.on_order_update)`. DI (`services.py`): pass `{"EXNESS": "exness"} if settings.exness_live_trading else {}`.
- **Steps:** implement; `tests/engine_test/test_strategy_live_broker_routing.py`: flag map `{"EXNESS":"exness"}` → `XAUUSD:EXNESS` gets broker type `exness` and `subscribe_order_updates` awaited once across two strategies; `BTCUSDT:BINANCE` stays `paper`; empty map → `paper` for both.
- **Success criteria:** default behaviour identical (empty map).
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/engine_test -q` exit 0.

### Task 7.5 — Phase gate and deploy (live flag off)
- **Goal:** broker shipped dark.
- **Target files and symbols:** repo.
- **Steps:** gate; metrics; user-approved commit `feat(exness): add exness broker with lot conversion, sl enforcement and async fills` + push. Confirm with the user that `EXNESS_LIVE_TRADING` is still unset/false in prod.
- **Success criteria:** green; flag off.
- **Verify:** `just test` exit 0; `uv run ruff check` → `All checks passed!`; `uv run pyright` → `0 errors`; `uv run lint-imports` → `Contracts: 3 kept, 0 broken.`; `uv run python scripts/code_metrics.py --max-tiny-share 0.30 --max-delegations 20` exit 0; `uv run python scripts/code_metrics.py --root src/pocketquant/core/infra/exness --fail-on-long` exit 0; `gh run list --workflow cicd.yml --limit 1 --json conclusion -q ".[0].conclusion"` prints `success`.

## Verification (test matrix)

- Unit: lot math, event mapping, guards, routing. Integration: DI/factory. E2E: Phase 08 live round trip.

## Risks

| Risk | L×I | Mitigation |
|------|-----|------------|
| Order above minimum lot | L×H | user cap `EXNESS_MAX_LOTS`, floor to step; cap 0 rejects all |
| Position without SL | L×H | broker rejects opens without `sl_price` |
| Missed `transaction_event` | M×M | 10 s operation-status/snapshot fallback |
| Restart loses position→subscription map | M×M | documented limitation; no deploy while a validation position is open (Phase 08) |
| Hedging account opens opposite position | M×M | opposite order closes tracked position |

## Security

No key material in logs; idempotency key = order UUIDv7 (no secrets); live flag defaults false.

## Rollback

Set `EXNESS_LIVE_TRADING=false` in `pocketquant-config` and redeploy (Exness subscriptions fall back to paper); `git revert` + push for code.

## Stop and ask

Any live order that would exceed minimum lot or lack SL; deployment topology change.

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

<!-- FILE: phase-08-cfd-validation-and-live-round-trip.md -->
---
phase: 8
title: "CFD validation and live round trip"
status: pending
priority: P1
effort: 6d + 1 weekend
dependencies: [7]
---

# Phase 08: CFD validation and live round trip

## Context Links

- Advice §2.8, §3 (no bid-only shorts, min lot), §9 success metrics; state R7, D2, D3.
- PaperBroker fills: `_apply_slippage(price, side)` (`paper_broker.py:436`) used by market, limit and synthetic-exit fills; backtest broker built in `backtest/engine/backtest_engine_sandbox.py:111 create_broker`, called from `backtest/workers/backtest_dispatch.py:91`; config path `RunBacktestCommand` (`backtest/backtest_command_service.py:22`) → config dict → `BacktestConfig` (`backtest/models/backtest_config.py`). Run status values: `started|finished|failed`.
- Backfill precedent: `scripts/backfill/binance_bars.py`.
- Remote commands: in Git Bash at the repo root define `vps() { ssh -i ../pocketquant-config/vps/default/id_rsa "$(cat ../pocketquant-config/vps/default/host)" "$@"; }`; HTTP calls run inside the app container (`vps 'docker exec -i pocketquant-app sh -s' <<'EOF' ... EOF`, as in Phase 06 Task 6.10).

## Goal

Spread-aware CFD backtests for both strategies on Exness bars, then one minimum-lot live round trip per strategy and one observed weekend close/reopen.

## Files to Create or Modify

- Modify: `src/pocketquant/core/infra/brokers/paper/paper_broker.py`, `src/pocketquant/backtest/backtest_command_service.py`, `src/pocketquant/backtest/models/backtest_config.py`, `src/pocketquant/backtest/workers/backtest_dispatch.py`, `src/pocketquant/backtest/engine/backtest_engine_sandbox.py`, `tests/baseline/openapi_app_snapshot.json` (regenerated, intentional), `tests/core_test/infra/exness/fixtures/` (+ `transaction_event_open.json`, `transaction_event_close.json`), `tests/core_test/infra/exness/test_broker.py`
- Create: `scripts/backfill/exness_bars.py`, `tests/scripts/test_exness_bars.py`, `tests/core_test/infra/brokers/test_paper_broker_spread.py`, `plans/261009-0858-exness-venue-lean-sync-refactor/reports/validation-results.md`

## Tasks

### Task 8.1 — PaperBroker `spread`
- **Goal:** buys fill at +spread/2, sells at −spread/2 (price units), default 0 keeps every existing result.
- **Target files and symbols:** `PaperBroker.__init__(..., spread: float = 0.0)`; `_apply_slippage`: `base = price + spread/2` for BUY, `price - spread/2` for SELL, then today's slippage multiplier.
- **Steps:** implement; tests: spread 2.0, slippage 0 → market BUY at close 100 fills 101, SELL fills 99; synthetic SL exit of a long fills at trigger −1.
- **Success criteria:** existing PaperBroker tests unchanged.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/brokers tests/backtest_test -q` exit 0.

### Task 8.2 — Backtest spread plumbing
- **Goal:** `POST /api/v1/backtest/run` accepts `spread`.
- **Target files and symbols:** `RunBacktestCommand.spread: float = Field(default=0.0, ge=0, description="Constant bid/ask spread in price units; buys fill +spread/2, sells -spread/2")`; config dict key `"spread"`; `BacktestConfig.spread: float = 0.0` (insert right after `commission_bps`); `_config_from_dict` reads `payload.get("spread", 0.0)`; `BacktestSandbox.create_broker(..., spread: float = 0.0)`; `run_single` passes `spread=config.spread`.
- **Steps:** implement; regenerate the snapshot intentionally: `BASELINE_UPDATE=1 .venv/Scripts/python.exe -m pytest tests/baseline/test_openapi_snapshot.py -q`; inspect `git diff tests/baseline/openapi_app_snapshot.json` — the only change is the new `spread` property.
- **Success criteria:** snapshot diff is a pure addition of the `spread` property (keys are sorted, so it lands between `slippage_bps` and `start_date` without touching other lines).
- **Verify:** `git diff --numstat tests/baseline/openapi_app_snapshot.json | awk '{print $2}'` prints `0` (no deleted lines); `grep -c '"spread": {' tests/baseline/openapi_app_snapshot.json` prints `1`; `.venv/Scripts/python.exe -m pytest tests/baseline tests/backtest_test -q` exit 0.

### Task 8.3 — Exness backfill script
- **Goal:** deep history beyond the 5000-bar API cap.
- **Target files and symbols:** `scripts/backfill/exness_bars.py`: args `--symbol` (composite), `--interval`, `--days`; reads Settings; `days` capped at `exness_policy(...).history_days[interval]` when not None; builds `ExnessClient` + `ExnessDataProvider`; computes `n_bars = days*86400/interval_seconds`; `fetch_ohlcv`; `BarRepository.insert_many(bars, source=SOURCE_REST_BACKFILL)` in chunks of 5000; prints `fetched=<n> inserted=<m>`; exit 1 on zero fetched.
- **Steps:** implement; `tests/scripts/test_exness_bars.py` with mocked provider/repo: day cap applied; chunked inserts; exit codes.
- **Success criteria:** insert-only, no deletes.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/scripts/test_exness_bars.py -q` exit 0; `grep -c "delete" scripts/backfill/exness_bars.py` prints `0`.

### Task 8.4 — Gate, deploy, backfill in prod
- **Goal:** Exness M1/H1 history for the three instruments.
- **Target files and symbols:** prod Mongo `bars`.
- **Steps:** gate; user-approved commit `feat(backtest): add constant spread to paper broker and exness backfill script` + push; then for each of XAUUSD, EURUSD, BTCUSD: `vps "docker exec pocketquant-app python scripts/backfill/exness_bars.py --symbol <S>:EXNESS --interval 1m --days 180"` and `--interval 1h --days 730`.
- **Success criteria:** six runs print `fetched=` with value > 0.
- **Verify:** `just test` exit 0; `uv run ruff check` → `All checks passed!`; `uv run pyright` → `0 errors`; `uv run lint-imports` → `Contracts: 3 kept, 0 broken.`; each backfill run exit code 0.

### Task 8.5 — Backtests on Exness bars
- **Goal:** D3.
- **Target files and symbols:** `POST /api/v1/backtest/run`, `GET /api/v1/backtest/{run_id}`, `GET /api/v1/backtest/{run_id}/trades`.
- **Steps:**
  1. `hitnrun2` on `XAUUSD:EXNESS` `1m`, last 90 days; `engulfing` on `XAUUSD:EXNESS` `1h`, last 365 days; body includes `"initial_capital":10000,"slippage_bps":0,"commission_bps":0,"spread":<median_spread_XAUUSD from findings>`.
  2. Poll `GET /api/v1/backtest/{request_id}` every 10 s until `status` is `finished` or `failed`.
  3. If a run has 0 trades, repeat on `EURUSD:EXNESS` then `BTCUSD:EXNESS`; record all runs in `reports/validation-results.md` (run id, symbol, interval, spread, total_return, trades).
- **Success criteria:** each strategy has ≥1 finished run with trades.
- **Verify:** for each recorded run id: `GET /api/v1/backtest/<id>` JSON `status == "finished"` and `GET /api/v1/backtest/<id>/trades` JSON `total >= 1` (check with `uv run python -c "import json,sys;d=json.load(sys.stdin);print(d['total']>=1)"` → `True`).

### Task 8.6 — Live preconditions gate
- **Goal:** live money only under the user's caps.
- **Target files and symbols:** `pocketquant-config/vps/default/.env` (user-owned).
- **Steps:** ask the user to set `EXNESS_MAX_LOTS` = `volume_min_XAUUSD` from findings, `EXNESS_DAILY_LOSS_LIMIT` (their value), `EXNESS_LIVE_TRADING=true`, and redeploy; ask them to confirm.
- **Success criteria:** user confirms values; app healthy.
- **Verify:** `vps "docker exec pocketquant-app python -c \"from pocketquant.core.config import get_settings as g;s=g();print(s.exness_live_trading, s.exness_max_lots>0, s.exness_daily_loss_limit>0)\""` prints `True True True`.

### Task 8.7 — One minimum-lot round trip per strategy
- **Goal:** D2.
- **Target files and symbols:** `POST /api/v1/strategies/{code}/subscriptions`, `POST /api/v1/subscriptions/{sub_id}/start`, `GET /api/v1/trading/positions`; logs `exness.order_submitted`, `order_filled`, `exness.venue_close`.
- **Steps:**
  1. Create + start `hitnrun2` on `XAUUSD:EXNESS` `1m` and `engulfing` on `XAUUSD:EXNESS` `1h`.
  2. Do not deploy or restart the app while a validation position is open (in-memory position map).
  3. On each first `exness.order_submitted`: read `lots` and `sl` from the log line. If `lots` > `EXNESS_MAX_LOTS` or no SL: stop both subscriptions immediately (`POST /subscriptions/{id}/stop`) and STOP and ask the user.
  4. If every signal is rejected with `volume below minimum lot`: STOP and ask the user (sizing vs. minimum lot is a money decision).
  5. After the fill: confirm the position in `/trading/positions`; after SL/TP: `exness.venue_close` and position closed.
  6. Save the real `transaction_event` frames (redacted, via `redact()`) as `transaction_event_open.json` / `transaction_event_close.json`; add a regression test in `test_broker.py` feeding them.
- **Success criteria:** each strategy: fill ≤10 s after ACK, position shown, then closed.
- **Verify:** `vps "docker logs pocketquant-app --since 7d 2>&1" | grep -c "order_filled"` ≥ `2`; time between each `exness.order_submitted` and its `order_filled` ≤ 10 s (record both timestamps in `validation-results.md`); `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_broker.py -q` exit 0.

### Task 8.8 — Weekend close and one-week stability
- **Goal:** calendar and reconnect behaviour proven on a real weekend.
- **Target files and symbols:** prod logs.
- **Steps:** observe Friday close → Monday open; then 7 days total.
- **Success criteria:** no FX integrity false alarms over the weekend; reconnects with backoff; zero breaker trips.
- **Verify:** `vps "docker logs pocketquant-app --since 7d 2>&1" | grep "integrity.issues_found" | grep -cE "XAUUSD:EXNESS|EURUSD:EXNESS"` prints `0`; `vps "docker logs pocketquant-app --since 7d 2>&1" | grep -c "exness_ws.circuit_breaker_open"` prints `0`; results appended to `validation-results.md`.

## Verification (test matrix)

- Unit: spread math, backfill script, broker regression on real frames. Integration: backtest API path. E2E: prod backtests, live round trips, weekend.

## Risks

| Risk | L×I | Mitigation |
|------|-----|------------|
| Sizer below 0.01 lot on a small account | H×M | explicit stop-and-ask (no silent round-up) |
| No signal for days (H1 engulfing) | M×L | week-long window; record status |
| Swap not modelled in PaperBroker | M×L | advice trade-off; note in results |
| Sharpe annualisation uses 365-day crypto year | M×L | out of scope; note in results |

## Security

Only user-owned config holds live flags; no secrets in reports; fixtures redacted.

## Rollback

Stop subscriptions; set `EXNESS_LIVE_TRADING=false` and redeploy; close any open position in the Exness terminal; `git revert` for code.

## Stop and ask

Live order above minimum lot or without SL; all signals below minimum lot; unexplained fill/close mismatch.

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

<!-- FILE: phase-09-architecture-and-deployment-docs.md -->
---
phase: 9
title: "Architecture and deployment docs"
status: pending
priority: P2
effort: 1d
dependencies: [8]
---

# Phase 09: Architecture and deployment docs

## Context Links

- Advice §2.9, D7; `CLAUDE.md` "Writing docs & prose" (Vietnamese prose, English technical terms, AS-IS, no banners/changelog, Mermaid v11 or ASCII for 2+ parts).
- Targets: `docs/system-architecture.md` (sections "High-Level Architecture", "Layer 4: Adapters", "Where Does X Live?", "Real-Time Streaming", "Dependency Injection (Dishka)", "Startup Sequence", "Known Limitations"), `docs/deployment.md` env table (lines ~85-96), `scripts/README.md`.

## Goal

Docs describe the system as it is: Exness adapters, sync-policy pattern, 3 DI modules, routing, MT5 as a future provider.

## Files to Create or Modify

- Modify: `docs/system-architecture.md`, `docs/deployment.md`, `scripts/README.md`

## Tasks

### Task 9.1 — `system-architecture.md`
- **Goal:** D7.
- **Target files and symbols:** sections listed above + new "Sync policy pattern" and "MT5 (provider tương lai)".
- **Steps:** describe `SyncPolicy` fields and the runner pipeline with one Mermaid diagram; adapters table (Binance, OKX, Paper, Exness: files, ports); live routing (`EXNESS_LIVE_TRADING`, `live_broker_by_exchange`); DI modules `infrastructure/adapters/services`; Known Limitations: Exness position map is in-memory (restart while a position is open leaves its close unrouted); MT5 section: same three ports, policy sketch (`copy_rates_from` bar source, `copy_ticks_from` live source, Windows host or Wine bridge), explicitly not built.
- **Success criteria:** no stale references to removed modules.
- **Verify:** `grep -cE "sync_internals|sync_jobs\.py|integrity_jobs|app/di/(core|execution|market_data|persistence|trading_services|backtest_worker)\.py" docs/system-architecture.md` prints `0`; `grep -c "SyncPolicy" docs/system-architecture.md` ≥ `1`; `grep -c "MT5" docs/system-architecture.md` ≥ `1`; `grep -c "ExnessBroker" docs/system-architecture.md` ≥ `1`.

### Task 9.2 — `deployment.md` env rows
- **Goal:** operators know the Exness variables.
- **Target files and symbols:** env table rows `EXNESS_BASE_URL`, `EXNESS_WS_BASE_URL`, `EXNESS_ACCOUNT_ID`, `EXNESS_API_KEY`, `EXNESS_PRIVATE_KEY` / `EXNESS_PRIVATE_KEY_PATH`, `EXNESS_LIVE_TRADING`, `EXNESS_MAX_LOTS`, `EXNESS_DAILY_LOSS_LIMIT` (Req = No; purpose).
- **Steps:** add rows after the OKX rows.
- **Success criteria:** rows present, no values.
- **Verify:** `grep -c "EXNESS_" docs/deployment.md` ≥ `8`.

### Task 9.3 — `scripts/README.md`
- **Goal:** new scripts discoverable.
- **Target files and symbols:** entries for `exness_spike.py`, `code_metrics.py`, `backfill/exness_bars.py`.
- **Steps:** one bullet each, same style as existing bullets.
- **Success criteria:** 3 bullets.
- **Verify:** `grep -cE "exness_spike.py|code_metrics.py|exness_bars.py" scripts/README.md` prints `3`.

### Task 9.4 — Final acceptance sweep
- **Goal:** D1-D7 checked mechanically in one place.
- **Target files and symbols:** `reports/validation-results.md` (append `acceptance:` block).
- **Steps:** run and record: `test ! -e src/pocketquant/engine/market_data/sync_internals && echo D4a-ok`; `ls src/pocketquant/app/di/*.py | wc -l` (4); `ls src/pocketquant/app/routes/market_data*.py | wc -l` (2); `uv run python scripts/code_metrics.py --max-tiny-share 0.30 --max-delegations 20`; `uv run lint-imports`; full gate; latest CI conclusion; links to D1/D2/D3 evidence lines. Ask the user to approve commit `docs: describe exness adapters, sync policy pattern and mt5 provider path` + push.
- **Success criteria:** every D item has evidence.
- **Verify:** `just test` exit 0; `uv run lint-imports` contains `Contracts: 3 kept, 0 broken.`; `uv run python scripts/code_metrics.py --max-tiny-share 0.30 --max-delegations 20` exit 0; `gh run list --workflow cicd.yml --limit 1 --json conclusion -q ".[0].conclusion"` prints `success` (docs-only pushes skip CI by `paths-ignore`; then use the last code push run).

## Verification (test matrix)

Docs: grep checks above; links resolve (`grep -o "](\./[^)]*)" docs/system-architecture.md` targets exist).

## Risks

| Risk | L×I | Mitigation |
|------|-----|------------|
| Change-narrative slips into docs | M×L | AS-IS rule; reviewer check |

## Rollback

`git revert` the docs commit.

## Stop and ask

None beyond the Failure Protocol.

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
