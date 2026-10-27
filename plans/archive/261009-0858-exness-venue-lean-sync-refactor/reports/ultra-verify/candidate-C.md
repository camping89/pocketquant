<!-- FILE: plan.md -->
---
title: "Exness venue + lean sync-policy refactor"
description: "Refactor market-data sync into one per-provider SyncPolicy plus a shared runner (Binance first, pinned by characterization tests), rewrite the coding standard, then add Exness REST/WS data, quotes and broker as a third venue and validate it at minimum lot."
status: pending
priority: P1
effort: 252h
branch: master
tags: [exness, market-data, sync-policy, refactor, broker, cfd]
blockedBy: []
blocks: []
created: 2026-10-09
---

# Exness venue + lean sync-policy refactor

## Overview

Exness becomes a third live venue behind the existing ports (`IDataProvider`, `IRealtimeQuoteProvider`, `IBroker`). Binance, OKX, PaperBroker, `hitnrun2` and `engulfing` all stay. Before any Exness code lands, the market-data sync pipeline is refactored with Binance as the only provider: one declarative `SyncPolicy` per provider plus one shared runner replaces `sync_jobs.py`, `cascade_aggregator.py`, `integrity_jobs.py` and `sync_internals/`. `docs/code-standards.md` is then rewritten as the standard the code follows. MT5 is documented only. There is no MCP work and the deployment topology does not change.

Data flow after the plan: tracked symbol `CODE:EXCHANGE` → `policy_for(symbol)` (`engine/market_data/sync_policy.py`) → shared runner (`sync_runner.py`) → `SyncService` (`sync_service.py`) → `IDataProvider` router → Binance or Exness adapter → `BarRepository`. Live: WS ticks → quote router → `QuoteAppService` → `BarAppService` → Redis/SSE. Orders: `StrategyAppService` → `BrokerFactory` → `ExnessBroker` → REST ACK → events WS fill → `OrderAppService.on_order_update` → `PositionAppService`.

## Goals

- G1: Exness is a usable live venue alongside Binance and OKX (D1, D2, D3).
- G2: Adding a provider means one adapter package plus one policy object, and every sync flow reads in 3 files or fewer (D4).
- G3: The coding standard matches the code and is enforced by ruff, 3 import-linter contracts and a soft metric gate (D5).

## Phases

| # | Phase | Effort | Depends on |
|---|-------|--------|------------|
| 01 | [Exness read-only spike](./phase-01-exness-read-only-spike.md) | 12h | none |
| 02 | [Baseline, characterization tests and metric script](./phase-02-baseline-characterization-and-metrics.md) | 16h | none |
| 03 | [Sync policy and shared runner (Binance)](./phase-03-sync-policy-and-shared-runner.md) | 40h | 02 |
| 04 | [DI, route and wrapper consolidation](./phase-04-di-routes-and-wrapper-consolidation.md) | 16h | 03 |
| 05 | [Lean pass, contracts and coding standard](./phase-05-lean-pass-contracts-and-standard.md) | 32h | 04 |
| 06 | [Exness signer and REST client](./phase-06-exness-signer-and-rest-client.md) | 24h | 01, 05 |
| 07 | [Exness market data and sync policy](./phase-07-exness-market-data-and-sync-policy.md) | 32h | 06 |
| 08 | [Exness broker and live routing](./phase-08-exness-broker-and-live-routing.md) | 32h | 07 |
| 09 | [CFD validation and live round trip](./phase-09-cfd-validation-and-live-round-trip.md) | 40h | 08 |
| 10 | [Architecture docs and MT5 note](./phase-10-architecture-docs-and-mt5-note.md) | 8h | 09 |

Phases 01 and 02 share no files and may run in parallel. Every later phase is sequential. Each code phase ends with the full gate green and a prod deploy that has been approved by the user.

## Dependencies

- Phase 06 needs the spike numbers and fixtures from Phase 01, and the refactored pipeline and standard from Phase 05.
- Live checks in Phases 07-09 need the user preconditions below to be in place in `pocketquant-config` (prod `.env`).

## Success Criteria (D1-D7)

- D1: `POST /api/v1/market-data/sync` with `{"symbol":"XAUUSD:EXNESS","interval":"1m","n_bars":1000,"source":"bulk_sync_api"}` returns `status=completed` and `total_bars>=1000`. The bar SSE for `XAUUSD%3AEXNESS` emits `"is_in_progress": true` within 60 s during market hours, and the quote SSE emits that symbol.
- D2: One minimum-lot live order per strategy reaches `filled` within 10 s of the ACK via the events WS, and appears in `GET /api/v1/trading/positions`.
- D3: The `hitnrun2` and `engulfing` Exness backtests finish (`status=finished`) with `total_trades>0`. `PaperBroker` has a `spread` parameter.
- D4: `engine/market_data/sync_internals/` is gone, `app/di` holds 3 provider modules, market-data routes live in 2 files, and `scripts/code_metrics.py` reports a tiny share of 30% or less and 20 or fewer pure delegations (subject to the Phase 05 feasibility gate).
- D5: `docs/code-standards.md` is rewritten and `uv run lint-imports` reports `Contracts: 3 kept, 0 broken.`
- D6: The Binance and OKX tests pass with passed count ≥ the Phase 02 baseline, the test suite, ruff, pyright and lint-imports are green, and the CI deploy verdict shows `0 failures`.
- D7: `docs/system-architecture.md` shows the Exness adapters and the sync-policy pattern, and lists MT5 as a future provider.
- Test matrix: unit tests (policy, runner, signer, mappers, client, data/quote providers, broker) → integration tests (testcontainers app boot, OpenAPI/route snapshots) → e2e on prod (D1 smoke, D2 live round trip, D3 backtests, one-week observation).

## User preconditions (the plan gates on these and never performs them)

1. The Developer Portal link from the Exness Personal Area resolves to `exness-api.com`. If it does not, STOP.
2. A scoped API key exists (one account, VPS IP allowlist), stored as `EXNESS_ACCOUNT_ID`, `EXNESS_API_KEY`, and `EXNESS_PRIVATE_KEY` or `EXNESS_PRIVATE_KEY_PATH` in `pocketquant-config` / `.env`.
3. A live risk cap is set before Phase 09 live steps: `EXNESS_MAX_LOTS` = instrument minimum lot, SL always attached (enforced in code), and `EXNESS_DAILY_LOSS_CAP_PCT`.

Key material is never printed, logged, or committed.

<!-- FILE: phase-01-exness-read-only-spike.md -->
---
phase: 1
title: "Exness read-only spike"
status: pending
priority: P1
effort: 12h
dependencies: []
---

# Phase 01: Exness read-only spike

## Goal

A read-only script (`scripts/exness_spike.py`) settles assumptions A-i..A-v against the live Exness API: instrument names, `volume_min/step`, contract size, `max_candles_per_request`, rate limits, candle alignment, the in-progress candle, the key format, WS handshake shape and tick cadence. It saves raw responses outside the repo as the fixture source for Phases 06-08, and records the numbers in a journal note. It sends no trading request.

## Context Links

- Advice: `D:/w/_me/algotrading/plans/reports/advise-261008-1148-exness-api-replacement.md` (sections 2.1, 8)
- Interview state: `D:/w/_me/algotrading/plans/reports/advise-261008-1148-exness-api-replacement-state.md` (Exness API facts)
- Spec: `https://www.exness-api.com/exness_api.yaml` (v1.0.2). Discovery doc: `https://www.exness-api.com/documentation/access-point-host-discovery`
- Verified spec facts: signed `EXN-API-KEY`, `EXN-IDEMPOTENCY-KEY` (empty for GET), `EXN-TIMESTAMP` (ms), `EXN-SIGN-VERSION: 1`, `EXN-DATA` (base64url, no padding, JSON with `api_key, idempotency_key, timestamp, sign_version, method, path` (incl. query), `body_hash` = base64url SHA-256 of body), `EXN-SIGN` = Ed25519 over the decoded `EXN-DATA` bytes. Discovery: signed `GET https://api.exness.com/v1/trading/access-point?account_id={id}` → `{"access_point": "<host>", "account_id": ...}`. Endpoints: `GET /v1/configuration/accounts/{id}/limits` (`limits.rest.global_account_rate.{limit,window_seconds}`, `limits.rest.methods[].{api_operation_id, rate_limit, limits.max_candles_per_request}`, `limits.websocket`), `GET .../instruments`, `GET .../instruments/{instrument}/conditions` (`contract_size, volume_min, volume_max, volume_step, point_digits, trade_mode, trade_sessions`), `GET .../account`, `GET /v1/market-data/accounts/{id}/candles?instrument=&timeframe=&price_type=bid&from=&count=` (operationId `getCandleHistory`, response `{"candles":[{time,open,high,low,close,volume}]}`), WS `/v1/server-events/accounts/{id}/ws/ticks` (handshake signed as GET, subscribe `{"id":"...","subscribe":{"event":"ticks","instruments":["XAUUSD"]}}`).

## Files to Create or Modify

- Create: `scripts/exness_spike.py`
- Modify: `pyproject.toml`, `uv.lock` (via `uv add cryptography`), `scripts/README.md` (one bullet)
- Create: `docs/journals/{YYMMDD}-exness-api-spike-findings.md` (YYMMDD = run date, Asia/Bangkok)
- Create (outside git): `D:/w/_me/algotrading/exness-spike-out/` (raw responses, never committed)
- Create: `plans/261009-0858-exness-venue-lean-sync-refactor/reports/preconditions.md`

## Tasks

### T1: Gate on user preconditions (stop-and-ask)
- **Goal:** Record the user's confirmation of the portal domain, the key storage, and where the spike may run.
- **Target files and symbols:** `plans/261009-0858-exness-venue-lean-sync-refactor/reports/preconditions.md`
- **Steps:**
  1. Ask the user these three questions, one message, and wait for the answer:
     (a) "Does the Developer Portal link inside your Exness Personal Area resolve to exness-api.com? (yes/no)"
     (b) "Is a scoped API key created and stored as EXNESS_ACCOUNT_ID, EXNESS_API_KEY and EXNESS_PRIVATE_KEY (or EXNESS_PRIVATE_KEY_PATH) in the local `.env` of this repo and in pocketquant-config `vps/default/.env`? (yes/no)"
     (c) "Is this machine's public IP on the key's allowlist? Answer `local` to run the spike here, or `vps` to run it inside the prod app container."
  2. If (a) is `no`, STOP the whole plan and report "Developer Portal link does not resolve to exness-api.com". This is a stop-and-ask condition.
  3. If (b) is `no`, STOP and wait for the user.
  4. Write `preconditions.md` with exactly three lines: `portal_domain_confirmed: yes`, `key_stored: yes`, `spike_host: local` or `spike_host: vps`.
- **Success criteria:** The file exists with both `yes` lines and a `spike_host` line.
- **Verify:** `grep -cE "^(portal_domain_confirmed: yes|key_stored: yes|spike_host: (local|vps))$" plans/261009-0858-exness-venue-lean-sync-refactor/reports/preconditions.md` prints `3`.

### T2: Install dependencies and add `cryptography`
- **Goal:** Ed25519 signing is available as a direct dependency.
- **Target files and symbols:** `pyproject.toml` `[project].dependencies`, `uv.lock`
- **Steps:**
  1. From repo root `D:/w/_me/algotrading/pocketquant`, run `uv sync`.
  2. Run `uv add cryptography`.
- **Success criteria:** `pyproject.toml` lists `cryptography` and the Ed25519 module imports.
- **Verify:** `grep -c '"cryptography' pyproject.toml` prints `1`, and `.venv/Scripts/python.exe -c "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey; print('ed25519-ok')"` prints `ed25519-ok`.

### T3: Write `scripts/exness_spike.py`
- **Goal:** A self-contained read-only probe exists. It is not imported by `src/`.
- **Target files and symbols:** `scripts/exness_spike.py` with `SpikeSettings(BaseSettings)`, `sign_headers()`, `main()`
- **Steps:**
  1. Define `SpikeSettings(BaseSettings)` with fields `exness_account_id: str`, `exness_api_key: SecretStr`, `exness_private_key: SecretStr | None = None`, `exness_private_key_path: str | None = None`, `exness_discovery_url: str = "https://api.exness.com"`, and `model_config = SettingsConfigDict(env_file=".env", extra="ignore")`.
  2. Load the key. If the value starts with `-----BEGIN`, replace literal `\n` with newlines and load it with `serialization.load_pem_private_key(..., password=None)`. Otherwise base64/base64url-decode it to 32 bytes and use `Ed25519PrivateKey.from_private_bytes`. Record which branch was used as `key_format` (`pem` or `raw32`). If neither works, exit 2 with the message `unsupported key format` and nothing else.
  3. `sign_headers(method, path_with_query, body: bytes, idempotency_key="")` builds the payload dict in the spec order. Serialize it with `json.dumps(payload, separators=(",", ":")).encode()` and return the six `EXN-*` headers. Use base64url without `=` for `EXN-DATA`, `EXN-SIGN` and `body_hash`. The timestamp is `int(time.time()*1000) + clock_offset_ms`, where `clock_offset_ms` is updated from each response `Date` header.
  4. CLI: `--out DIR` (required unless `--check-env` or `--scan`), `--ticks-minutes` (default 10), `--instruments` (default `XAUUSD,EURUSD,BTCUSD`), `--check-env` (prints exactly `EXNESS_ACCOUNT_ID=set|missing`, `EXNESS_API_KEY=set|missing`, `EXNESS_PRIVATE_KEY=set|missing`, `EXNESS_PRIVATE_KEY_PATH=set|missing` and exits 0), and `--scan PATH...` (reads every file under the paths and prints `CLEAN`, or `LEAK in <file>` for any file containing the account id, the API key, or the key value; it never prints the secret).
  5. The probe sequence uses only `httpx.AsyncClient.get` and the ticks WebSocket. Write each response JSON to `--out`:
     - `access_point.json`: signed GET `{discovery}/v1/trading/access-point?account_id={id}`. All later calls go to `https://{access_point}`.
     - `limits.json`, `instruments.json`, `account.json`
     - `conditions_{INSTR}.json` for each instrument. Match the instrument name case-insensitively against `instruments.json` and record the exact names.
     - `candles_{INSTR}_M1.json`: `from=<now UTC ISO, seconds zeroed>`, `count=-1000`, `price_type=bid`. Split into pages by `max_candles_per_request` if that is under 1000.
     - `candles_{INSTR}_{H4,D1,W1}.json`: `count=-10`
     - `count_probe.json`: `from=<an M1 open time T taken from the M1 file>`, `count=-3`. Record whether the candle at `T` is included.
  6. Ticks: open `wss://{access_point}/v1/server-events/accounts/{id}/ws/ticks` with the signed GET headers as `additional_headers`. If the handshake fails with HTTP 4xx, retry once with `subprotocols=["exness-ws-protocol"]`. Send the subscribe frame for all instruments and save every raw frame to `ticks.jsonl` for `--ticks-minutes`. Then send `{"id":"unsub-1","unsubscribe":{"event":"ticks","instruments":[<first instrument>]}}` and record the reply as `unsubscribe_reply.json`.
  7. Write `summary.json` with these keys: `key_format`, `access_point_host_present` (bool, not the host), `max_candles_per_request`, `global_rate` `{limit, window_seconds}`, `candle_rate` (the `rate_limit` of `api_operation_id == "getCandleHistory"`), `websocket_limits`, `instrument_names` `{code: exact}`, per instrument `{contract_size, volume_min, volume_step, volume_max, point_digits, trade_mode, trade_sessions}`, `candle_alignment` `{H4, D1, W1: bool}` (open times equal `get_bar_start(t, interval)`; for W1 that is Monday 00:00 UTC), `in_progress_candle_returned` (newest M1 `time + 60s > request time`), `count_negative_includes_from` (bool), `ws_subprotocol` (`null` or the string used), `tick_frame_shape` (keys of the first tick frame), per-instrument tick stats `{count, p50_gap_ms, p95_gap_ms, median_spread}` (spread = ask-bid), and `date_header_present` (bool).
  8. Never write request headers, the access-point host, the account id or key material to any file or stdout. Print only `summary.json` to stdout.
- **Success criteria:** The script has no write HTTP verbs and passes ruff.
- **Verify:** `grep -nE "\.(post|put|patch|delete)\(" scripts/exness_spike.py` prints nothing (exit 1), `uv run ruff check scripts/exness_spike.py` exits 0, and `.venv/Scripts/python.exe scripts/exness_spike.py --help` exits 0 with output containing `--out`.

### T4: Run the spike
- **Goal:** Raw responses and `summary.json` exist outside the repo.
- **Target files and symbols:** `D:/w/_me/algotrading/exness-spike-out/`
- **Steps:**
  1. Run `.venv/Scripts/python.exe scripts/exness_spike.py --check-env`. Every name except one of `EXNESS_PRIVATE_KEY` / `EXNESS_PRIVATE_KEY_PATH` must be `set`.
  2. If `spike_host: local`, run `.venv/Scripts/python.exe scripts/exness_spike.py --out ../exness-spike-out` during FX market hours (Mon-Fri, not 21:00-22:00 UTC).
  3. If `spike_host: vps`, the prod image needs `cryptography` and the script first. Today `cryptography` is only a transitive dev dependency (via `secretstorage`), and the Dockerfile copies `scripts/` into `/app/scripts`. Run T7 (release of T2+T3) now. Once the deploy is green, run from repo root:
     `ssh -i ../pocketquant-config/vps/default/id_rsa "$(cat ../pocketquant-config/vps/default/host)" "docker exec pocketquant-app python scripts/exness_spike.py --out /tmp/exness-spike-out && docker cp pocketquant-app:/tmp/exness-spike-out /tmp/"`
     then `scp -r -i ../pocketquant-config/vps/default/id_rsa "$(cat ../pocketquant-config/vps/default/host)":/tmp/exness-spike-out ../`, then `ssh -i ../pocketquant-config/vps/default/id_rsa "$(cat ../pocketquant-config/vps/default/host)" "rm -rf /tmp/exness-spike-out && docker exec pocketquant-app rm -rf /tmp/exness-spike-out"`. The EXNESS_* values must already be in the deployed container env (precondition 2). After T6, run T7 again for the journal commit.
- **Success criteria:** `summary.json` parses and holds every key from T3 step 7.
- **Verify:** `.venv/Scripts/python.exe -c "import json;s=json.load(open('../exness-spike-out/summary.json'));req=['key_format','max_candles_per_request','global_rate','candle_rate','instrument_names','candle_alignment','in_progress_candle_returned','count_negative_includes_from','ws_subprotocol','tick_frame_shape','date_header_present'];m=[k for k in req if k not in s];print('SUMMARY_OK' if not m else m)"` prints `SUMMARY_OK`.

### T5: Feasibility check of sync policy A-v (stop-and-ask)
- **Goal:** Prove that "WS ticks live + REST native candles M1..D1 polled each minute, no cascade" fits the rate budget for 3 instruments.
- **Target files and symbols:** `../exness-spike-out/summary.json`
- **Steps:**
  1. Compute `budget = floor(0.5 * min(global_rate.limit*60/global_rate.window_seconds, candle_rate.limit*60/candle_rate.window_seconds))`.
  2. Compute `needed = 3 * 6` (instruments × M1,M5,M15,H1,H4,D1).
  3. If `needed > budget`, or the XAUUSD tick `count` is 0 during market hours, STOP and report "Exness limits make the confirmed sync policy infeasible" with the two numbers. This is a stop-and-ask condition.
- **Success criteria:** The budget covers the poll plan and ticks flow.
- **Verify:** `.venv/Scripts/python.exe -c "import json,math;s=json.load(open('../exness-spike-out/summary.json'));g,c=s['global_rate'],s['candle_rate'];b=math.floor(0.5*min(g['limit']*60/g['window_seconds'],c['limit']*60/c['window_seconds']));print('A-v FEASIBLE' if 18<=b else f'A-v INFEASIBLE budget={b}')"` prints `A-v FEASIBLE`.

### T6: Record findings in a journal note
- **Goal:** The numbers are durable and secret-free.
- **Target files and symbols:** `docs/journals/{YYMMDD}-exness-api-spike-findings.md`, `scripts/README.md`
- **Steps:**
  1. Write the journal with Vietnamese prose and English technical terms (CLAUDE.md docs rule). Include one table per topic from `summary.json`: limits, instruments (names, contract size, volume min/step/max), candle alignment, in-progress candle, count semantics, WS handshake (subprotocol yes/no), tick cadence and median spread, key format, and `trade_sessions` per instrument. Leave out the account id, the access-point host and any key.
  2. Add one bullet to `scripts/README.md`: "`exness_spike.py` — read-only Exness API probe (limits, instruments, candles, ticks); writes raw responses to a directory outside the repo; `--scan` checks files for leaked credentials."
- **Success criteria:** The journal exists and is clean.
- **Verify:** `.venv/Scripts/python.exe scripts/exness_spike.py --scan docs/journals scripts` prints `CLEAN`.

### T7: Release the phase
- **Goal:** The phase is on master and the prod deploy is green.
- **Target files and symbols:** git, `.github/workflows/cicd.yml`, `deploy/vps/11-verify.sh`
- **Steps:**
  1. `git status --short`. Every changed path must be in this phase's file list. `../exness-spike-out` is outside the repo.
  2. Ask the user to approve commit and push. Suggested message: `feat(scripts): add read-only Exness API spike`. Do not push without approval.
  3. After the push, run `gh run list --workflow cicd.yml --branch master --limit 1 --json databaseId,headSha --jq '.[0]'` and check that `headSha` equals `git rev-parse HEAD`.
  4. Run `gh run watch <databaseId> --exit-status`.
  5. If the commit touches only `*.md` files, `cicd.yml` `paths-ignore` skips CI. Skip steps 3-4 and use the docs-only Verify below.
- **Success criteria:** The CI run succeeds and the verify verdict has 0 failures, or the commit is docs-only.
- **Verify:** `gh run watch <databaseId> --exit-status` exits 0, and `gh run view <databaseId> --log | grep -c ", 0 failures)"` prints a number ≥ 1. For a docs-only commit: `git log -1 --name-only --pretty=format: | grep -vc "\.md$"` prints `0`.

## Verification

T1-T7 Verify commands all pass. `summary.json` exists outside the repo and `git status --short` shows no files under `exness-spike-out`.

## Risks

- The portal is not official (likelihood low, impact high): T1 stops the plan.
- The IP allowlist blocks the local run (medium, low): T1 (c) chooses the VPS procedure.
- Rate limits are too tight for A-v (low, high): T5 stops and asks.
- Ticks are absent because the market is closed: run during FX hours. T5 checks the tick count.

## Security

- The spike only reads. T3 Verify proves it has no POST/PUT/PATCH/DELETE.
- Raw output stays in `D:/w/_me/algotrading/exness-spike-out/`, outside git.
- `--scan` guards every committed artefact that is derived from the spike.

## Rollback

`git revert` the phase commit, then delete `../exness-spike-out`. No runtime code changed.

## Stop-and-ask conditions in this phase

- The portal link does not resolve to `exness-api.com` (T1).
- Exness limits make A-v infeasible (T5).

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

<!-- FILE: phase-02-baseline-characterization-and-metrics.md -->
---
phase: 2
title: "Baseline, characterization tests and metric script"
status: pending
priority: P1
effort: 16h
dependencies: []
---

# Phase 02: Baseline, characterization tests and metric script

## Goal

Before any production code moves: record a green baseline, add `scripts/code_metrics.py` (the soft-gate metric), and pin today's Binance sync-pipeline and OKX broker behaviour with characterization tests that later phases must keep passing without editing their `assert` lines. This phase changes no production code.

## Context Links

- Advice section 4.2 (characterization tests first) and section 9 success metrics
- Current pipeline: `src/pocketquant/engine/market_data/app_services/sync_jobs.py` (729 LOC), `cascade_aggregator.py` (235), `integrity_jobs.py` (137), `sync_service.py` (181), `sync_internals/` (5 files)
- OKX: `src/pocketquant/core/infra/brokers/okx/okx_broker.py:335-374` (`_handle_ws_message`, `_handle_order_update`, terminal dedupe), `okx_mapper.py:32-60` (`map_order_to_okx_params`)
- No test file covers OKX today. The pass count is pinned by the new tests in T5.

## Files to Create or Modify

- Create: `scripts/code_metrics.py`, `tests/scripts/test_code_metrics.py`
- Create: `tests/engine_test/market_data/test_sync_pipeline_characterization.py`
- Create: `tests/core_test/infra/brokers/test_okx_broker_characterization.py`
- Create: `plans/261009-0858-exness-venue-lean-sync-refactor/reports/baseline.md`

## Tasks

### T1: Environment ready
- **Goal:** The venv exists and Docker is up for the testcontainers tests.
- **Target files and symbols:** `.venv/`, Docker daemon
- **Steps:** 1. `uv sync`. 2. `docker info > /dev/null; echo "docker=$?"`.
- **Success criteria:** The venv is present and Docker responds.
- **Verify:** `ls .venv/Scripts/python.exe` exits 0 and the docker command prints `docker=0`. If Docker is not available, STOP and ask the user to start Docker Desktop.

### T2: Record the green baseline
- **Goal:** The pre-refactor gate results are written down.
- **Target files and symbols:** `reports/baseline.md`
- **Steps:**
  1. `git rev-parse --short HEAD` and `git diff --stat 29f2f67 -- src | tail -n 1`. The second command must print nothing (src unchanged since planning).
  2. `.venv/Scripts/python.exe -m pytest -q > /tmp/pq-pytest.txt 2>&1; echo "exit=$?"; tail -n 1 /tmp/pq-pytest.txt`
  3. `uv run ruff check; echo "exit=$?"`, `uv run pyright | tail -n 1`, `uv run lint-imports | grep Contracts`
  4. Write `baseline.md` with lines `head: <sha>`, `pytest_baseline: <tail line>`, `ruff: pass`, `pyright: <tail line>`, `lint_imports: <Contracts line>`.
- **Success criteria:** All four gates are green on unmodified master.
- **Verify:** pytest prints `exit=0` and a tail line containing `passed` and not containing `failed` or `error`. Ruff prints `exit=0`. Pyright's tail contains `0 errors`. lint-imports prints `Contracts: 7 kept, 0 broken.` If any gate is red, STOP: an unexplained failure on a clean baseline is a stop-and-ask condition.

### T3: Add the metric script
- **Goal:** One reproducible definition of tiny share, pure delegation and long functions.
- **Target files and symbols:** `scripts/code_metrics.py` (`measure()`, `main()`), `tests/scripts/test_code_metrics.py`
- **Steps:**
  1. Create `scripts/code_metrics.py` with exactly this content:

```python
"""Soft-gate code metrics: tiny-function share, pure delegations, long functions.

Counted functions exclude shapes the language or a kept port mandates: abstract
stubs (body is only ``...``/``pass``), dunder methods, ``@property``/setters and
``@abstractmethod``. A leading docstring is not a statement.

- tiny: at most 2 top-level statements.
- pure delegation: exactly 1 statement that is ``[return] [await] obj.method(...)``.
- long: more than 60 source lines (def line to last line).
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

_EXCLUDED_DECORATORS = {"property", "setter", "abstractmethod"}


def _body(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
    body = fn.body
    first = body[0] if body else None
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return body[1:]
    return body


def _decorator_names(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names = set()
    for d in fn.decorator_list:
        if isinstance(d, ast.Name):
            names.add(d.id)
        elif isinstance(d, ast.Attribute):
            names.add(d.attr)
    return names


def _is_counted(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    body = _body(fn)
    is_stub = all(
        isinstance(s, ast.Pass)
        or (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and s.value.value is ...)
        for s in body
    )
    return not (
        is_stub or fn.name.startswith("__") or _decorator_names(fn) & _EXCLUDED_DECORATORS
    )


def _is_delegation(body: list[ast.stmt]) -> bool:
    if len(body) != 1 or not isinstance(body[0], (ast.Return, ast.Expr)):
        return False
    value = body[0].value
    if isinstance(value, ast.Await):
        value = value.value
    return isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)


def measure(root: Path) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {"all": [], "tiny": [], "delegation": [], "long": []}
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or not _is_counted(fn):
                continue
            ref = f"{path.as_posix()}:{fn.lineno} {fn.name}"
            body = _body(fn)
            found["all"].append(ref)
            if len(body) <= 2:
                found["tiny"].append(ref)
            if _is_delegation(body):
                found["delegation"].append(ref)
            if (fn.end_lineno or fn.lineno) - fn.lineno + 1 > 60:
                found["long"].append(ref)
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default="src/pocketquant")
    parser.add_argument("--list", choices=["tiny", "delegation", "long"])
    parser.add_argument("--max-tiny-share", type=float, default=30.0)
    parser.add_argument("--max-delegations", type=int, default=20)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    found = measure(Path(args.path))
    total = len(found["all"])
    share = round(100 * len(found["tiny"]) / total, 1) if total else 0.0
    print(f"functions: {total}")
    print(f"tiny: {len(found['tiny'])} ({share}%)")
    print(f"pure_delegations: {len(found['delegation'])}")
    print(f"over_60_lines: {len(found['long'])}")
    if args.list:
        print("\n".join(found[args.list]))
    over = share > args.max_tiny_share or len(found["delegation"]) > args.max_delegations
    if over:
        print(
            f"ABOVE THRESHOLD: tiny share <= {args.max_tiny_share}% "
            f"and pure delegations <= {args.max_delegations} required"
        )
    return 1 if (over and args.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
```

  2. Create `tests/scripts/test_code_metrics.py`. It writes a temp package with these functions: a 1-statement `def a(): return 1` (tiny, not delegation), `def b(x): return x.y()` (tiny + delegation), `async def c(x): await x.y()` (tiny + delegation), `def d(): """doc"""; s1; s2; s3` (not tiny), `@property def p(self): return 1` (excluded), `def __init__(self): pass` (excluded), and a 61-line function (long). It asserts `measure()` counts `all=5, tiny=3, delegation=2, long=1`. Import with `from scripts.code_metrics import measure` (the `tests/scripts/conftest.py` puts the repo root on `sys.path`).
- **Success criteria:** On unmodified src, the script reproduces the planning baseline.
- **Verify:** `.venv/Scripts/python.exe scripts/code_metrics.py` prints exactly `functions: 661`, `tiny: 315 (47.7%)`, `pure_delegations: 59`, `over_60_lines: 22` (first 4 lines), and `.venv/Scripts/python.exe -m pytest tests/scripts/test_code_metrics.py -q` exits 0. Append these 4 lines to `baseline.md`. The advice's figures (48% of 794, 63 delegations) came from an interview script that was not preserved. The thresholds (tiny ≤30%, delegations ≤20) apply to this script from now on. The definition must not change after this task.

### T4: Characterize the Binance sync pipeline
- **Goal:** Golden tests pin today's job behaviour at seams that survive the Phase 03 refactor.
- **Target files and symbols:** `tests/engine_test/market_data/test_sync_pipeline_characterization.py`
- **Steps:**
  1. At the top, two alias imports, each on its own line, with nothing else from those modules imported:
     `from pocketquant.engine.market_data.app_services import sync_jobs as runner`
     `from pocketquant.engine.market_data.app_services import cascade_aggregator as cascade`
     Import `SyncService`, `SyncResponse`, `SyncSymbolCommand` from `pocketquant.engine.market_data.sync_service`, plus `JobHistoryRepository`, `TrackedSymbolRepository`, `BarRepository`, `IDataProvider`, and `Interval`.
  2. In-file fakes:
     - `FakeHistory`: `record_start(job_id)` appends and returns `"doc-1"`. `record_detail(doc_id, **kw)` and `record_finish(doc_id, **kw)` append kwargs. `get_last_successful_started_at` returns `None`.
     - `FakeTracked.list_all()` returns `[SimpleNamespace(symbol="BTCUSDT:BINANCE"), SimpleNamespace(symbol="ETHUSDT:BINANCE")]`.
     - `class RecordingSync(SyncService)` is built with the fakes below (`RecordingSync(FakeProvider(), FakeCache(), bar_repo, FakeSymbolRepo(), FakeStatusRepo())`, sharing the same `FakeBarRepo` instance as the container). It overrides BOTH `async def sync_one(self, request)` and `async def sync(self, symbol, interval, *, n_bars, source, skip_filter=False)`. Both append `(symbol, interval.value, n_bars, source, skip_filter)` and return `SyncResponse(symbol=symbol, interval=interval.value, status="completed", bars_synced=1, bars_fetched=2)`. Subclassing the real service means that after Phase 03 the inherited `check_integrity` / `repair_integrity` run for real and still route their resync through the recording `sync`, so the fixture needs no edit.
     - `FakeBarRepo`: `find(**kw)` records kwargs and returns `[]`. `find_datetimes(symbol, interval, start, end)` records `(symbol, interval.value)` and returns `[]`. `upsert_bar`, `delete_many_by_ids` (returns 0), `count` (returns 0) and `get_latest` (returns `None`) record calls.
     - `FakeProvider(IDataProvider)`: `fetch_ohlcv` records `(symbol, interval.value, n_bars)` and returns `[]`.
     - `FakeCache.delete_pattern(p)` records. `FakeSymbolRepo.upsert(s)` records. `FakeStatusRepo` has `upsert(...)`, `reset_empty_fetch(...)`, and `bump_empty_fetch(...)` (returns `1`).
     - `FakeContainer.get(t)` returns the instance mapped by type `{JobHistoryRepository: ..., SyncService: ..., TrackedSymbolRepository: ..., BarRepository: ..., IDataProvider: ...}`.
     - A fixture calls `runner.set_container(container)` and patches `asyncio.sleep` with `monkeypatch.setattr(asyncio, "sleep", _no_sleep)`.
  3. Two helpers whose bodies are the only lines Phase 03 may change:
     - `async def _sync(svc, symbol, interval, n_bars, source, skip_filter=False)` with body `return await svc.sync_one(SyncSymbolCommand(symbol=symbol, interval=interval, n_bars=n_bars, source=source, skip_filter=skip_filter))`.
     - `async def _check(bar_repo, symbol, interval, days_back)` with body `from pocketquant.engine.market_data.app_services import integrity_jobs` then `return await integrity_jobs.check_integrity(symbol, interval, bar_repo, days_back)`. Tests always pass a `FakeBarRepo` as `bar_repo`.
  4. Tests and exact expectations:
     - `test_sync_1m_polls_each_symbol_1m_100_bars`: after `await runner.sync_1m()`, recorded == `[("BTCUSDT:BINANCE","1m",100,"rest_sync_1m",False),("ETHUSDT:BINANCE","1m",100,"rest_sync_1m",False)]`, history starts == `["sync_1m"]`, 2 detail rows, and the last finish kwargs include `status="completed"`, `total_inserted=2`, `total_fetched=4`.
     - `test_sync_1m_cascades_every_symbol`: the set of `symbol` values in `FakeBarRepo.find` calls == `{"BTCUSDT:BINANCE","ETHUSDT:BINANCE"}`.
     - `test_sync_backfill_all_seven_intervals_5000`: recorded == `[(s, iv, 5000, "rest_backfill", False) for s in SYMS for iv in ["1m","5m","15m","1h","4h","1d","1w"]]`.
     - `test_sync_repair_resyncs_every_gap_with_skip_filter`: recorded == `[(s, iv, 5000, "rest_repair", True) for s in SYMS for iv in SEVEN]`.
     - `test_sync_integrity_scans_seven_intervals_without_sync`: the `find_datetimes` calls, deduplicated in order, == `[(s, iv) for s in SYMS for iv in SEVEN]`, and recorded == `[]`.
     - `test_verify_cascade_fetches_12_5m_bars_per_symbol`: provider calls == `[(s, "5m", 12) for s in SYMS]`.
     - `test_register_sync_jobs_five_crons`: use a fake scheduler that records `add_cron_job(func, **kw)`. Assert job ids `["sync_1m","sync_verify_cascade","sync_backfill","sync_integrity","sync_repair"]` in order, with `sync_1m`: `cron_expression="*/1 * * * *", second=2, misfire_grace_time=120`; `sync_verify_cascade`: `"0 * * * *"`, 600; `sync_backfill`: `hour=3, minute=0`, 3600; `sync_integrity`: `hour=4, minute=0`, 3600; `sync_repair`: `"0 */12 * * *"`, 1800. Each `func` string ends with `f":{job_id}"`.
     - `test_cascade_aggregate_ohlcv_golden`: `cascade.aggregate_ohlcv` over five 1m bars with opens 1..5, highs 10..14, lows 0.5..4.5, closes 2..6, volume 1 each == `{"open":1,"high":14,"low":0.5,"close":6,"volume":5}`. Before writing the literal, read `cascade_aggregator.py:70-97` and match its exact output keys.
     - `test_sync_service_golden_paths`: build `SyncService(provider, cache, bar_repository, symbol_repository, sync_status_repository)` with fakes. (a) 3 aligned 1m bars, empty DB → `status="completed", bars_synced=3, bars_fetched=3, filtered_existing=0, filtered_misaligned=0`. (b) one of the 3 already exists → `filtered_existing=1, bars_synced=2`. (c) 2 aligned + 1 bar at `:30` seconds → `filtered_misaligned=1`. (d) provider returns `[]` and DB empty → `status="error", message="No data returned from provider"`. Call through `_sync`.
     - `test_check_integrity_golden`: 1h docs for the last 24 h with one hour missing and one misaligned doc (`minute=30`) → `misaligned_count=1`, `missing_count=1`. Call through `_check`.
- **Success criteria:** All tests pass on unmodified src.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/engine_test/market_data/test_sync_pipeline_characterization.py -q` exits 0 with `10 passed`.

### T5: Characterize the OKX broker
- **Goal:** OKX order-update mapping, dedupe and factory creation are pinned before any OKX file is touched.
- **Target files and symbols:** `tests/core_test/infra/brokers/test_okx_broker_characterization.py`
- **Steps:**
  1. On its own line: `from pocketquant.app.di.broker_factory import BrokerFactory`. Phase 04 edits only this line.
  2. Tests:
     - `test_factory_creates_okx_demo_broker`: `BrokerFactory(EventBus()).create("okx", {"api_key":"k","api_secret":"s","passphrase":"p","demo":True})` is an `OKXBroker` and `.name == "okx-demo"`.
     - `test_factory_rejects_missing_okx_credentials`: `pytest.raises(ValueError, match="OKX broker requires api_key, api_secret, passphrase")`.
     - `test_filled_order_update_notifies_once`: `b = OKXBroker("k","s","p")`, register a sync callback with `subscribe_order_updates`, call `_handle_ws_message({"arg":{"channel":"orders"},"data":[{"ordId":"9001","clOrdId":"ord-1","state":"filled","accFillSz":"0.5","avgPx":"100.5","sCode":"0"}]})` twice → exactly 1 result with `order_id="ord-1", broker_order_id="9001", status=OrderStatus.FILLED, filled_quantity=0.5, filled_price=100.5, error_message=None`.
     - `test_live_update_maps_submitted_and_is_not_deduped`: `state="live", accFillSz="0", avgPx=""` twice → 2 results, `status=OrderStatus.SUBMITTED, filled_quantity=0.0, filled_price=None`.
     - `test_error_code_maps_message`: `sCode="51000", msg="Parameter error", state="canceled"` → `error_message="Parameter error", status=OrderStatus.CANCELLED`.
     - `test_event_messages_are_ignored`: `{"event":"subscribe","arg":{"channel":"orders"}}` → 0 results.
     - `test_market_order_params_golden`: `map_order_to_okx_params(OrderAggregate.create(subscription_id="sub-1", symbol="BTC", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=0.01))` == `{"instId":"BTC-USDT","tdMode":"cash","side":"buy","ordType":"market","sz":"0.01","clOrdId":str(order.id)}`.
- **Success criteria:** All 7 pass.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/brokers/test_okx_broker_characterization.py -q` exits 0 with `7 passed`.

### T6: Record the post-characterization baseline N1
- **Goal:** One number that later phases compare against.
- **Target files and symbols:** `reports/baseline.md`
- **Steps:** 1. Run the full gate (T2 commands). 2. Append `pytest_N1: <passed count>` to `baseline.md`.
- **Success criteria:** The gate is green and N1 is recorded.
- **Verify:** `grep -c "^pytest_N1: [0-9]\+$" plans/261009-0858-exness-venue-lean-sync-refactor/reports/baseline.md` prints `1`, and the T2 Verify conditions hold.

### T7: Release the phase
- **Goal:** Tests and the metric script are on master and CI is green.
- **Target files and symbols:** git, `cicd.yml`
- **Steps:** Same as Phase 01 T7 steps 1-4. Suggested message: `test: pin sync pipeline and OKX broker behaviour; add code metrics script`.
- **Success criteria:** CI is green.
- **Verify:** `gh run watch <databaseId> --exit-status` exits 0, and `gh run view <databaseId> --log | grep -c ", 0 failures)"` is ≥ 1.

## Verification

N1 is recorded, the metric baseline reproduces exactly, and 17 new characterization tests pass.

## Risks

- A characterization test bakes in a wrong expectation (medium, medium). Every golden comes from running against unmodified src. A mismatch at first run triggers the Failure Protocol, never an edit to production code.
- Time-dependent flake in `_check` around the hour boundary (low, low). Compute `end` in the test with the same `get_bar_start` call.

## Security

No secrets are involved. The tests use literal fake credentials (`"k"`, `"s"`, `"p"`).

## Rollback

Revert the phase commit. Production code is untouched.

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
title: "Sync policy and shared runner (Binance)"
status: pending
priority: P1
effort: 40h
dependencies: [2]
---

# Phase 03: Sync policy and shared runner (Binance)

## Goal

Replace the per-step job modules with one declarative `SyncPolicy` per provider and one shared runner. Binance is the only policy. Its behaviour must be identical, as proven by the Phase 02 characterization tests with their `assert` lines unchanged. `sync_internals/`, `sync_dtos.py`, `sync_jobs.py`, `cascade_aggregator.py` and `integrity_jobs.py` are deleted.

## Context Links

- Advice section 2.2 (policy fields: live source, authoritative bar source, cascade flag, timeframes, poll cadence, market calendar, rate budget, history depth) and section 3 (do not remove the Binance cascade)
- Today's behaviour: `sync_jobs.py:53-61` (`SYNC_INTERVALS`), `:381-450` (`sync_1m`: 1m × 100 bars, then cascade lookback 100), `:600-601` (`sync_backfill`: 7 intervals × 5000), `:680-729` (5 crons + catch-up). `sync_service.py:48-142`. `integrity_jobs.py:33-137`. `cascade_aggregator.py:31-235`.
- APScheduler persists jobs as text refs in Mongo `apscheduler_jobs` (`scheduler.py:1-9`). Job ids stay the same. Only the module path in the func ref changes.

## Architecture

```
APScheduler cron (job ids unchanged)
  -> sync_runner.sync_1m / sync_backfill / sync_integrity / sync_repair / sync_verify_cascade
       -> policy_for(symbol)              (sync_policy.py: pure data)
       -> SyncService.sync / check_integrity / repair_integrity   (sync_service.py)
            -> IDataProvider (Binance today)  -> BarRepository / SyncStatusRepository / Cache
       -> cascade_for_symbol (sync_runner.py) when policy.cascade
POST /market-data/sync -> SyncService.sync      (route -> service -> policy: 3 files)
```

## Files to Create or Modify

- Create: `src/pocketquant/engine/market_data/sync_policy.py`, `src/pocketquant/engine/market_data/sync_runner.py`, `tests/engine_test/market_data/test_sync_policy.py`
- Modify: `src/pocketquant/engine/market_data/sync_service.py`, `src/pocketquant/engine/market_data/tracked_symbols_backfill.py`, `src/pocketquant/app/main.py` (line 31-33 import), `src/pocketquant/app/main_extensions.py` (`start_background_jobs`, line 300), `src/pocketquant/app/routes/integrity.py`, `src/pocketquant/app/routes/market_data_sync.py`, `scripts/backfill/binance_bars.py` (lines 65-68 import)
- Delete: `src/pocketquant/engine/market_data/sync_internals/` (all 6 files), `src/pocketquant/engine/market_data/sync_dtos.py`, `src/pocketquant/engine/market_data/app_services/sync_jobs.py`, `.../app_services/cascade_aggregator.py`, `.../app_services/integrity_jobs.py`
- Modify (test ports, listed in T5): 14 test files + `tests/engine_test/market_data/test_sync_pipeline_characterization.py` (only the 2 alias lines and the `_sync` / `_check` helper bodies)

## Tasks

### T1: Create `sync_policy.py`
- **Goal:** A pure, testable policy type and the Binance policy exist.
- **Target files and symbols:** `sync_policy.py`: `ClosedWindow`, `MarketCalendar.is_open(at)`, `ALWAYS_OPEN`, `SyncPolicy`, `SyncPolicy.calendar_for(symbol)`, `BINANCE_POLICY`, `POLICIES`, `policy_for(symbol)`
- **Steps:**
  1. `@dataclass(frozen=True) class ClosedWindow: start_weekday: int; start: time; end_weekday: int; end: time` (Monday = 0, UTC).
  2. `@dataclass(frozen=True) class MarketCalendar: closed: tuple[ClosedWindow, ...] = ()` with `is_open(at: datetime) -> bool`. Treat a naive `at` as UTC. Compute `minute_of_week = at.weekday()*1440 + at.hour*60 + at.minute`. The time is closed if it falls in `[start, end)` of any window. A window whose start > end wraps across Sunday→Monday.
  3. `ALWAYS_OPEN = MarketCalendar()`.
  4. `@dataclass(frozen=True) class SyncPolicy` with fields in this order: `exchange: str`, `live_source: str`, `bar_source: str`, `poll_intervals: tuple[Interval, ...]`, `poll_bars: int`, `cascade: bool`, `sync_intervals: tuple[Interval, ...]`, `backfill_bars: Mapping[Interval, int]`, `calendar: MarketCalendar`, `rate_budget_per_minute: int`, `calendar_overrides: Mapping[str, MarketCalendar] = field(default_factory=dict)`. Method `calendar_for(symbol)` returns `calendar_overrides.get(symbol.split(":")[0].upper(), calendar)`.
  5. `BINANCE_POLICY = SyncPolicy(exchange="BINANCE", live_source="ws_aggtrade", bar_source="rest_klines", poll_intervals=(Interval.MINUTE_1,), poll_bars=100, cascade=True, sync_intervals=(1m,5m,15m,1h,4h,1d,1w as Interval members), backfill_bars={iv: 5000 for iv in those 7}, calendar=ALWAYS_OPEN, rate_budget_per_minute=600)`. The 600 comes from `binance_client.py:3`: 1200 weight/min ÷ 2 weight per call.
  6. `POLICIES: dict[str, SyncPolicy] = {BINANCE_POLICY.exchange: BINANCE_POLICY}`. `policy_for(symbol: str) -> SyncPolicy | None` uses the upper-cased part after the last `:`.
  7. `tests/engine_test/market_data/test_sync_policy.py` covers: `policy_for("btcusdt:binance") is BINANCE_POLICY`, `policy_for("XAUUSD:NOPE") is None`, `ALWAYS_OPEN.is_open` is True for 7 sample datetimes, a Fri 21:00 → Sun 21:00 window (Sat 12:00 closed, Fri 20:59 open, Sun 21:00 open, naive Sat 12:00 closed), and a wrap window Sun 23:00 → Mon 01:00 (Mon 00:30 closed, Mon 01:00 open).
- **Success criteria:** The policy tests pass and the module imports nothing from `core.infra`.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/engine_test/market_data/test_sync_policy.py -q` exits 0, and `grep -c "core.infra" src/pocketquant/engine/market_data/sync_policy.py` prints `0`.

### T2: Fold `sync_internals/` and `sync_dtos.py` into `sync_service.py`; add integrity methods
- **Goal:** One file owns fetch → align → persist plus integrity check/repair.
- **Target files and symbols:** `sync_service.py`: `SyncSymbolCommand`, `BulkSyncCommand`, `SyncResponse` (moved verbatim from `sync_dtos.py`), module functions `fetch_with_retry`, `filter_new_bars`, `drop_misaligned_bars`, `emit_no_progress` (moved verbatim with the same names and log event names), `SyncService.sync(symbol, interval, *, n_bars, source, skip_filter=False) -> SyncResponse`, `SyncService.sync_bulk(cmd)`, `SyncService.check_integrity(symbol, interval, days_back=7) -> dict`, `SyncService.repair_integrity(symbol, interval, *, source, days_back=7) -> dict`
- **Steps:**
  1. Move the DTO classes and the four module functions into `sync_service.py`. Inline `has_aligned_bar` (`bar_alignment.py`) into `fetch_with_retry` and `build_success` (`responses.py`) into `sync`. Keep `_BACKOFF_SECONDS`, `_TIME_BUDGET_SECONDS` and `_STUCK_STREAK_THRESHOLD` as module constants. Keep only the comments that explain why (comment policy).
  2. Rename `sync_one(request)` to `sync(symbol, interval, *, n_bars, source, skip_filter=False)`. It runs the same steps in the same order: upsert `syncing` → `fetch_with_retry` → existing filter unless `skip_filter` → misaligned drop → `insert_many` + `Symbol` upsert → count/latest → empty-and-no-data → `_fail` → mark completed → invalidate cache → progress tracker → response. Inline the single-use private helpers (`_persist_bars`, `_get_bar_stats`, `_mark_completed`, `_invalidate_cache`) only where every resulting function stays ≤ 60 lines. If inlining would push a function over 60 lines, extract one named step instead (for example `_record_progress`).
  3. `sync_bulk(cmd)` calls `self.sync(...)` per symbol with `source=SOURCE_BULK_SYNC`.
  4. Move `_group_gaps`, `check_integrity` and `repair_integrity` from `integrity_jobs.py` into `SyncService` methods (`_group_gaps` stays a module function). Use `self._bar_repo`. Make `check_integrity` calendar-aware: `calendar = (policy_for(symbol) or BINANCE_POLICY).calendar_for(symbol)`, and keep only expected timestamps with `calendar.is_open(ts)`. For Binance (`ALWAYS_OPEN`) the output is unchanged. `repair_integrity` calls `self.sync(symbol, interval, n_bars=5000, source=source, skip_filter=True)`.
  5. Delete `sync_internals/` and `sync_dtos.py`.
- **Success criteria:** No module imports `sync_internals` or `sync_dtos`. `sync_one` no longer exists.
- **Verify:** `grep -rnE "sync_internals|sync_dtos|sync_one\b" src scripts` prints nothing (exit 1), and `ls src/pocketquant/engine/market_data/sync_internals 2>/dev/null | wc -l` prints `0`.

### T3: Create `sync_runner.py` and delete the job modules
- **Goal:** One runner executes fetch → align → persist → cascade? → integrity → repair for each policy.
- **Target files and symbols:** `sync_runner.py`: `_MODULE = "pocketquant.engine.market_data.sync_runner"`, `CATCHUP_TARGETS`, `PRICE_THRESHOLD_PCT`, `VOLUME_THRESHOLD_PCT`, `DIVERGENCE_ALERT_FRACTION`, `CASCADE_TFS`, `set_container`, `tf_seconds`, `aggregate_ohlcv`, `compute_boundaries`, `cascade_for_symbol`, `compare_bar_fields`, `_verify_one_symbol`, `sync_1m`, `sync_verify_cascade`, `sync_backfill`, `sync_integrity`, `sync_repair`, `enqueue_missed_catchups`, `register_sync_jobs`
- **Steps:**
  1. Move the cascade code from `cascade_aggregator.py` with the same names and values. Split `cascade_for_symbol` (96 lines today) so that the per-timeframe bucket loop becomes `_cascade_tf(sym, tf, range_start, now, bar_repo) -> int`.
  2. Move `compare_bar_fields`, `_diff_pct`, `_verify_one_symbol` and the threshold constants unchanged. `sync_verify_cascade` iterates only symbols whose `policy_for(symbol).cascade` is True.
  3. Write one bookkeeping helper `_run_tracked(job_id, body)`. It records start (a failure only warns), awaits `body(doc_id)` → `dict` totals, records finish `status="completed", duration_ms, **totals`, and on exception records `status="failed", error=str(exc)` (guarded) and re-raises. This replaces the five copies in `sync_jobs.py`.
  4. `_group_by_policy(tracked) -> list[tuple[SyncPolicy, list[str]]]` keeps tracked order, preserves `POLICIES` order, and logs `market_data.sync.no_policy` (warning) for unknown exchanges.
  5. `sync_1m` (body): for each policy, take symbols whose `calendar_for(s).is_open(now)`. Build pairs interval-major: `[(s, iv) for iv in policy.poll_intervals for s in open_symbols]`. If `len(pairs) > policy.rate_budget_per_minute`, log `market_data.sync.rate_budget_exceeded` and truncate. Call `sync_service.sync(s, iv, n_bars=policy.poll_bars, source=SOURCE_REST_SYNC_1M)`, record a job-history detail per pair exactly as `sync_jobs.py:150-201` does (the error path included), then run `cascade_for_symbol(s, lookback_minutes=100, bar_repo)` for each open symbol only if `policy.cascade` and that policy had no sync error. Raise the first error after all policies. Empty tracked keeps the `market_data.sync_1m.skipped` warning and finishes `completed` with zero totals.
  6. `sync_backfill`: pairs symbol-major over `policy.sync_intervals` with `n_bars=policy.backfill_bars[iv]`, `source=SOURCE_REST_BACKFILL`. `sync_integrity` / `sync_repair`: symbol-major over `policy.sync_intervals`, calling `sync_service.check_integrity` / `repair_integrity(source=SOURCE_REST_REPAIR)` with the same log events as today.
  7. `register_sync_jobs` and `enqueue_missed_catchups` move with the same cron arguments. The func refs become `f"{_MODULE}:<name>"`. `CATCHUP_TARGETS` keep the same ids and gaps.
  8. Update importers: `app/main.py:31-33` → `from pocketquant.engine.market_data.sync_runner import set_container as set_sync_container`. `main_extensions.py:300` → `from pocketquant.engine.market_data.sync_runner import register_sync_jobs`. `routes/integrity.py` → call `sync_service.check_integrity(symbol, body.interval, body.days_back)` and `sync_service.repair_integrity(symbol, body.interval, source=SOURCE_REST_REPAIR, days_back=body.days_back)`, injecting only `SyncService`. `routes/market_data_sync.py` → `sync_service.sync(cmd.symbol, cmd.interval, n_bars=cmd.n_bars, source=cmd.source, skip_filter=cmd.skip_filter)` in both `/sync` and `/sync/background`. `tracked_symbols_backfill.py` → import `cascade_for_symbol, tf_seconds` from `sync_runner`, and in `run()` use `mode = "direct" if (policy := policy_for(symbol)) is not None and not policy.cascade else cmd.resolved_mode()`. `scripts/backfill/binance_bars.py:65-68` → import `CASCADE_TFS, cascade_for_symbol` from `pocketquant.engine.market_data.sync_runner`.
  9. Delete `sync_jobs.py`, `cascade_aggregator.py` and `integrity_jobs.py`.
- **Success criteria:** No reference to the deleted modules remains. The new files have no function over 60 lines.
- **Verify:** `grep -rnE "app_services(\.| import )(sync_jobs|cascade_aggregator|integrity_jobs)" src scripts tests` prints nothing (exit 1). `.venv/Scripts/python.exe scripts/code_metrics.py --list long | grep -E "sync_(runner|service|policy)\.py"` prints nothing (exit 1). `grep -oE "engine\.market_data\.[a-z_]+" src/pocketquant/engine/market_data/sync_runner.py | sort -u` prints exactly `engine.market_data.sync_policy` and `engine.market_data.sync_service`, which keeps the flow at 3 files.

### T4: Re-point the characterization tests
- **Goal:** The Phase 02 goldens run against the new modules with assertions untouched.
- **Target files and symbols:** `tests/engine_test/market_data/test_sync_pipeline_characterization.py`
- **Steps:**
  1. Change the two alias lines to `from pocketquant.engine.market_data import sync_runner as runner` and `from pocketquant.engine.market_data import sync_runner as cascade`.
  2. Change the `_sync` body to `return await svc.sync(symbol, interval, n_bars=n_bars, source=source, skip_filter=skip_filter)`. Change the `_check` body to `svc = SyncService(FakeProvider(), FakeCache(), bar_repo, FakeSymbolRepo(), FakeStatusRepo())` then `return await svc.check_integrity(symbol, interval, days_back)`.
  3. Change nothing else.
- **Success criteria:** All 10 goldens pass and no `assert` line changed.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/engine_test/market_data/test_sync_pipeline_characterization.py -q` shows `10 passed`, and `git diff -U0 tests/engine_test/market_data/test_sync_pipeline_characterization.py | grep -E "^[-+].*assert"` prints nothing (exit 1).

### T5: Port the existing tests to the new symbols
- **Goal:** Every pre-existing sync test keeps its name and expected literals and passes.
- **Target files and symbols (old → new):** `sync_internals.bar_filters.*`, `sync_internals.provider_fetch.*`, `sync_internals.anomaly_log.*`, `sync_dtos.*` → `pocketquant.engine.market_data.sync_service.*`. `app_services.sync_jobs.*` and `app_services.cascade_aggregator.*` → `pocketquant.engine.market_data.sync_runner.*`. `integrity_jobs.repair_integrity(symbol, interval, bar_repo, sync_service, source=...)` → `SyncService(...).repair_integrity(symbol, interval, source=...)`. `sync_service.sync_one(SyncSymbolCommand(symbol=A, interval=B, n_bars=C, source=D, skip_filter=E))` → `sync_service.sync(A, B, n_bars=C, source=D, skip_filter=E)`. Mocks of `.sync_one` → `.sync`, reading `call.args[0], call.kwargs[...]`.
- **Steps:** Edit exactly these files:
  `tests/app_test/test_sync_jobs_phase.py`, `tests/app_test/market_data/test_sync_jobs_source_labels.py`, `tests/app_test/market_data/test_cascade_aggregator.py`, `tests/app_test/market_data/test_cascade_aggregator_source.py`, `tests/app_test/market_data/test_integrity_jobs_repair_source.py`, `tests/app_test/unit/market_data/test_sync_jobs_catchup.py`, `tests/app_test/unit/market_data/test_sync_verify_cascade.py`, `tests/app_test/unit/handlers/sync/conftest.py` (re-bind `logger` on `sync_service` only), `tests/app_test/unit/handlers/sync/test_bar_filters.py`, `tests/app_test/unit/handlers/sync/test_provider_fetch.py`, `tests/app_test/unit/handlers/sync/test_no_progress_tracking.py`, `tests/app_test/integration/test_sync_backfill_gap_fill.py`, `tests/app_test/integration/app_factory.py` (line 31-33 import), `tests/engine_test/market_data/test_sync_service.py`.
  Keep every `def test_` name. Do not change expected values.
- **Success criteria:** Each listed file has the same number of `def test_` / `async def test_` lines as before.
- **Verify:** For each listed file, `git show HEAD:<file> | grep -cE "def test_"` equals `grep -cE "def test_" <file>`. Then `.venv/Scripts/python.exe -m pytest tests/app_test tests/engine_test -q` exits 0, and `.venv/Scripts/python.exe -m pytest scripts/backfill/test_binance_bars.py -q` exits 0.

### T6: Full gate
- **Goal:** Phase green with Binance behaviour unchanged.
- **Target files and symbols:** whole repo
- **Steps:** Run the four gate commands from Phase 02 T2, then the metric script.
- **Success criteria:** Passed count ≥ N1 and the gates are green.
- **Verify:** pytest `exit=0`, its tail has no `failed`/`error`, and the passed number ≥ `pytest_N1` in `baseline.md`. `uv run ruff check` exits 0. `uv run pyright | tail -n 1` contains `0 errors`. `uv run lint-imports | grep Contracts` prints `Contracts: 7 kept, 0 broken.` `ls src/pocketquant/engine/market_data/sync_internals 2>/dev/null | wc -l` prints `0`.

### T7: Release and verify the scheduler in prod
- **Goal:** Prod runs the five jobs from the new module.
- **Target files and symbols:** git, `cicd.yml`, prod `GET /api/v1/system/jobs`, `GET /api/v1/system/jobs/sync_1m/runs`
- **Steps:**
  1. Phase 01 T7 steps 1-4. Suggested message: `refactor(market-data): drive sync jobs from per-provider SyncPolicy and one runner`.
  2. Five minutes after the deploy finishes, run from repo root:
```bash
ssh -i ../pocketquant-config/vps/default/id_rsa "$(cat ../pocketquant-config/vps/default/host)" 'docker exec -i pocketquant-app sh -s' <<'EOF'
curl -s http://localhost:41921/api/v1/system/jobs | python -c 'import json,sys; j=json.load(sys.stdin); ids={x["id"] for x in j if x["next_run"]}; print("JOBS_OK" if {"sync_1m","sync_verify_cascade","sync_backfill","sync_integrity","sync_repair"} <= ids else sorted(ids))'
curl -s "http://localhost:41921/api/v1/system/jobs/sync_1m/runs?limit=1" | python -c 'import json,sys; print("LAST_RUN", json.load(sys.stdin)[0]["status"])'
EOF
```
- **Success criteria:** All five jobs are scheduled and the last `sync_1m` run completed. APScheduler removes stale docs that still hold the old func ref by itself, and `register_sync_jobs` re-adds them with `replace_existing=True`.
- **Verify:** CI `gh run watch <id> --exit-status` exits 0 with `0 failures)` in the log, and the ssh output contains `JOBS_OK` and `LAST_RUN completed`.

## Verification

Goldens unchanged (T4), test counts preserved (T5), gate green (T6), prod jobs healthy (T7).

## Risks

- Behaviour drift hidden in the bookkeeping helper (medium, high): T4 goldens assert detail and finish rows.
- A stale APScheduler job ref fails to restore after deploy (high, low): APScheduler deletes unrestorable jobs and re-registration replaces them. T7 checks.
- Calendar-aware integrity changes Binance output (low, medium): `ALWAYS_OPEN` keeps every timestamp. `test_check_integrity_golden` pins it.

## Security

No new inputs or secrets.

## Rollback

`git revert` the phase commit and redeploy. The old func refs re-register through `replace_existing=True`. Bar data is untouched because the schema is the same.

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

<!-- FILE: phase-04-di-routes-and-wrapper-consolidation.md -->
---
phase: 4
title: "DI, route and wrapper consolidation"
status: pending
priority: P2
effort: 16h
dependencies: [3]
---

# Phase 04: DI, route and wrapper consolidation

## Goal

`app/di` shrinks from 8 provider modules plus `container.py` and `broker_factory.py` to 3 provider modules (`infrastructure.py`, `adapters.py`, `services.py`) plus `__init__.py`, with Settings supplied through Dishka context so that no duplicate registration exists. The eight market-data route files collapse into two. The 22 Query/Command classes that wrap 0-2 scalars are removed. The API contract stays byte-identical: the OpenAPI and route-inventory snapshots are not regenerated.

## Context Links

- `src/pocketquant/app/di/*.py` (11 files, 493 LOC). `di/services.py:6-9` documents the "Dishka silently lets the last duplicate registration win" hazard.
- Routes under `/market-data`: `routes/market_data.py`, `market_data_sync.py`, `market_data_status.py`, `market_data_ohlcv.py`, `integrity.py`, `list_symbols.py`, `tracked_symbols.py`, plus `market_data_quotes.py` (`/quotes`). Mounted in `main_extensions.py:488-528`.
- Snapshots: `tests/baseline/openapi_app_snapshot.json`, `tests/baseline/route_inventory_app_snapshot.json`. The route `name` is the function name, so keep every function name.

## Files to Create or Modify

- Create: `src/pocketquant/app/di/adapters.py`, `src/pocketquant/app/routes/market_data_streams.py`
- Rewrite: `src/pocketquant/app/di/__init__.py`, `app/di/infrastructure.py`, `app/di/services.py`, `app/routes/market_data.py`
- Delete: `app/di/backtest_worker.py`, `broker_factory.py`, `container.py`, `core.py`, `execution.py`, `market_data.py`, `persistence.py`, `trading_services.py`. Also `app/routes/market_data_sync.py`, `market_data_status.py`, `market_data_ohlcv.py`, `market_data_quotes.py`, `integrity.py`, `list_symbols.py`, `tracked_symbols.py`.
- Modify: `app/main.py`, `app/main_extensions.py` (`register_routes`), the services listed in T3, the routes `strategy.py`, `backtest.py`, `trading_orders_positions.py`, and the tests listed in T1/T3.

## Tasks

### T1: Three DI provider modules with context-supplied Settings
- **Goal:** Every type has exactly one provider, and tests inject Settings through context.
- **Target files and symbols:** `InfrastructureProvider` (`settings = from_context(provides=Settings, scope=Scope.APP)`, EventBus, HealthCoordinator, Database and Cache async generators, all 11 repositories, JobScheduler async generator); `AdaptersProvider` (`get_data_provider` → `BinanceClient`, `get_realtime_quote_provider` → `BinanceWebSocketClient`, class `BrokerFactory` moved verbatim from `broker_factory.py`, `broker_factory = provide(BrokerFactory, scope=Scope.APP)`); `ServicesProvider` (SyncService, BarAppService, QuoteAppService, WsSubscriptionManager, RiskCheckHandler, OrderAppService async factory with `load_pending_orders`, PositionAppService async factory with `start`, StrategyAppService generator with start/stop and the same `default_broker_config`, StrategyReconcileService, every feature service from today's `services.py` and `trading_services.py`, BacktestDispatchDeps, BacktestExecutionService); `app/di/__init__.py` with `PROVIDERS` and `create_container(settings: Settings | None = None) -> AsyncContainer` returning `make_async_container(*PROVIDERS, context={Settings: settings or get_settings()}, validation_settings=STRICT_VALIDATION)` (`from dishka import STRICT_VALIDATION`, installed dishka 1.9.1). Strict validation makes a duplicate or implicit override raise at container build instead of silently winning.
- **Steps:**
  1. Write the three modules by moving the provider bodies verbatim. Use `provide(Class, scope=Scope.APP)` wherever a factory only passes its parameters through to the constructor.
  2. Write `__init__.py`. Delete the 8 files listed above.
  3. `app/main.py:8` → `from pocketquant.app.di import create_container`.
  4. Tests: in `tests/app_test/integration/app_factory.py`, delete `TestCoreProvider` and build `make_async_container(InfrastructureProvider(), AdaptersProvider(), ServicesProvider(), context={Settings: settings})`. Do the same in `test_app_standalone_runtime.py` and `test_reconcile_di_resolution.py`. In `tests/app_test/unit/di/test_di_data_provider.py`, call `AdaptersProvider()` methods. In `tests/engine_test/test_reconcile_restart_resume_integration.py` and `tests/core_test/infra/brokers/test_okx_broker_characterization.py`, import `BrokerFactory` from `pocketquant.app.di.adapters`.
- **Success criteria:** Exactly 3 non-`__init__` modules exist and no type is provided twice.
- **Verify:** `ls src/pocketquant/app/di/*.py | grep -v __init__ | wc -l` prints `3`. `.venv/Scripts/python.exe -c "from pocketquant.core.config import Settings; from pocketquant.app.di import create_container; import inspect; print('STRICT' if 'STRICT_VALIDATION' in inspect.getsource(create_container) else 'LOOSE')"` prints `STRICT`. `.venv/Scripts/python.exe -m pytest tests/app_test tests/engine_test tests/baseline tests/core_test/infra/brokers -q` exits 0 (the app boot smoke test builds the strict container, so any duplicate fails here).

### T2: Market-data routes in two files
- **Goal:** The `/market-data` and `/quotes` routes live in 2 files with identical API output.
- **Target files and symbols:** `routes/market_data.py`: `router = APIRouter(prefix="/market-data", tags=["Market Data"], route_class=DishkaRoute)` holding `sync_symbol`, `sync_symbol_background`, `sync_bulk`, `integrity_check`, `integrity_repair` (`IntegrityRequest`), `get_sync_statuses`, `get_symbol_sync_status`, `list_symbols`; and `tracked_symbols_router = APIRouter(tags=["Tracked Symbols"], route_class=DishkaRoute)` holding `list_tracked_symbols`, `add_tracked_symbol`, `update_tracked_symbol`, `remove_tracked_symbol`, `backfill_tracked_symbol`. `routes/market_data_streams.py`: `ohlcv_router = APIRouter(prefix="/market-data", tags=["Market Data"], route_class=DishkaRoute)` holding `get_ohlcv` (`OHLCVResponse`) and `stream_bars`; and `quote_router = APIRouter(prefix="/quotes", tags=["Real-time Quotes"], route_class=DishkaRoute)` holding `get_latest_quote`, `get_current_bar`, `stream_quote`. Rename the two `_make_payload` helpers to `_bar_payload` and `_quote_payload`.
- **Steps:**
  1. Move each handler with the same function name, decorator path, `response_model`, `status_code`, `dependencies`, parameters and docstring.
  2. In `main_extensions.register_routes`, include `market_data.router`, `market_data.tracked_symbols_router` (with `prefix="/market-data"`), `market_data_streams.ohlcv_router` and `market_data_streams.quote_router` in place of the old imports.
  3. Delete the 7 old route files.
- **Success criteria:** The snapshots match without regeneration.
- **Verify:** `ls src/pocketquant/app/routes/market_data*.py | wc -l` prints `2`. `ls src/pocketquant/app/routes/{integrity,list_symbols,tracked_symbols}.py 2>/dev/null | wc -l` prints `0`. `.venv/Scripts/python.exe -m pytest tests/baseline -q` exits 0 with `BASELINE_UPDATE` unset, and `git diff --stat tests/baseline` prints nothing.

### T3: Remove the 0-2-scalar Query/Command wrappers
- **Goal:** Routes pass scalars straight to services. Real request bodies keep their Pydantic models.
- **Target files and symbols (old → new signature):**
  `backtest_command_service.py:74 set_verdict(cmd: SetVerdictCommand)` → `set_verdict(run_id: str, verdict: str | None)`. `backtest_query_service.py:51 get_result(query: GetBacktestQuery)` → `get_result(run_id: str)`. `quotes_service.py:54 get_latest(request: GetLatestQuoteQuery)` → `get_latest(symbol: str)`. `symbols_service.py:14 list_symbols(request)` → `list_symbols()`. `sync_status_service.py:96 get_sync_status(request)` → `get_sync_status()`. `:135 get_symbol_sync_status(request)` → `get_symbol_sync_status(symbol: str, interval: str = "1d")`. `tracked_symbols_service.py:78 update(request)` → `update(symbol: str)`. `:91 remove(request)` → `remove(symbol: str)`. `:102 list_all(request)` → `list_all()`. `orders_positions_service.py:50 get_order(query)` → `get_order(order_id: str)`. `:67 list_orders(query)` → `list_orders()`. `:86 get_position(query)` → `get_position(strategy_id: str)`. `:92 list_positions(query)` → `list_positions()`. `strategy_command_service.py:73 start(cmd)` → `start(subscription_id: str)`. `:83 stop(cmd)` → `stop(subscription_id: str)`. `:131 remove_symbol(cmd)` → `remove_symbol(sub_id: str)`. `:140 delete_strategy(cmd)` → `delete_strategy(strategy_id: str)`. `strategy_query_service.py:56 get_all(query)` → `get_all()`. `:59 get_one(query)` → `get_one(strategy_code: str)`. `:71 list_symbols(query)` → `list_symbols(strategy_code: str | None = None)`. `:101 get_positions(query)` → `get_positions(subscription_id: str)`. `:117 get_trades(query)` → `get_trades(subscription_id: str, limit: int = 100)`.
  Keep (real bodies or ≥3 fields): `RunBacktestCommand`, `ListBacktestsQuery`, `ListTradesQuery`, `GetOHLCVQuery`, `SyncSymbolCommand`, `BulkSyncCommand`, `AddTrackedSymbolCommand`, `BackfillTrackedSymbolCommand`, `AddSymbolCommand`.
- **Steps:**
  1. Change each signature, replacing `query.x` / `cmd.x` / `request.x` with the parameter. Delete the 22 classes.
  2. Update the route call sites in `routes/strategy.py`, `routes/backtest.py`, `routes/trading_orders_positions.py`, `routes/market_data.py` and `routes/market_data_streams.py`.
  3. Update the tests: `tests/app_test/unit/handlers/status/test_get_symbol_sync_status.py`, `test_get_sync_status.py`, `tests/engine_test/market_data/test_quotes_service.py`, `test_tracked_symbols_service.py`, `tests/engine_test/test_orders_positions_service.py`, `test_strategy_handlers_declarative.py`, `test_strategy_position_and_trade_handlers.py`, `test_strategy_service.py`. Keep test names and expected values.
- **Success criteria:** None of the 22 class names remains, and the snapshots are unchanged.
- **Verify:** `grep -rnwE "SetVerdictCommand|GetBacktestQuery|GetLatestQuoteQuery|ListSymbolsQuery|GetSyncStatusQuery|GetSymbolSyncStatusQuery|UpdateTrackedSymbolCommand|RemoveTrackedSymbolCommand|ListTrackedSymbolsQuery|GetOrderQuery|ListOrdersQuery|GetPositionQuery|ListPositionsQuery|StartStrategyCommand|StopStrategyCommand|RemoveSymbolCommand|DeleteStrategyCommand|GetStrategiesQuery|GetStrategyQuery|GetStrategyPositionsQuery|GetStrategyTradesQuery" src tests` prints nothing (exit 1). `.venv/Scripts/python.exe -m pytest tests/baseline -q` exits 0 and `git diff --stat tests/baseline` prints nothing.

### T4: Full gate
- **Goal:** The phase is green.
- **Target files and symbols:** repo
- **Steps:** Run the Phase 03 T6 commands.
- **Success criteria:** Passed ≥ N1 and every gate is green.
- **Verify:** pytest prints `exit=0`, its tail has no `failed`/`error`, and the passed number ≥ `pytest_N1`. `uv run ruff check` exits 0. `uv run pyright | tail -n 1` contains `0 errors`. `uv run lint-imports | grep Contracts` prints `Contracts: 7 kept, 0 broken.` `git diff -U0 "$(git log --diff-filter=A --format=%H -1 -- tests/engine_test/market_data/test_sync_pipeline_characterization.py)" -- tests/engine_test/market_data/test_sync_pipeline_characterization.py | grep -E "^[-+].*assert"` prints nothing (exit 1). That is a diff against the commit that added the file.

### T5: Release
- **Goal:** Deployed and green.
- **Target files and symbols:** git, `cicd.yml`
- **Steps:** Phase 01 T7 steps 1-4. Suggested message: `refactor(app): three DI providers, two market-data route modules, scalar service args`.
- **Success criteria:** CI green.
- **Verify:** `gh run watch <id> --exit-status` exits 0 and the log contains `0 failures)`.

## Verification

Snapshots unchanged (T2, T3), `app/di` has 3 provider modules (T1), and the gate is green (T4).

## Risks

- A duplicate provider silently wins (medium, high): the T1 duplicate check plus the integration tests that resolve the full graph.
- Route tag or prefix drift (medium, medium): T2 makes any drift fail the OpenAPI snapshot.

## Security

`verify_admin_token` dependencies move unchanged with their routes. The OpenAPI snapshot would reveal any dropped `dependencies`, because the security headers would disappear from it.

## Rollback

`git revert` the phase commit. This phase has no data migration.

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

<!-- FILE: phase-05-lean-pass-contracts-and-standard.md -->
---
phase: 5
title: "Lean pass, contracts and coding standard"
status: pending
priority: P2
effort: 32h
dependencies: [4]
---

# Phase 05: Lean pass, contracts and coding standard

## Goal

Reach the confirmed "balanced" thresholds with sanctioned rules only: tiny share ≤ 30%, pure delegations ≤ 20, no new function over 60 lines. Reduce import-linter to 3 contracts, rewrite `docs/code-standards.md` as the standard the code follows, and add the metric script to CI as a soft gate. Ports, `OrderAggregate` and `PositionAggregate` stay.

## Context Links

- Advice sections 2.3, 2.4, 3 ("do not overshoot"; soft gate, not tight) and 7 (soft gate drift)
- `pyproject.toml:74-140`: 7 contracts. Contracts 3-5 duplicate the layers contract. Contract 7 (bson) duplicates ruff `TID` banned-api (`pyproject.toml:50-58`).
- Docs that state the old rules: `CLAUDE.md:3` ("7 contracts") and the Routes rule; `README.md:87`; `docs/project-overview-pdr.md:260` ("Max 200 LOC per file"); `docs/code-standards.md:132-188` (Command/Query Service and Extract-Method patterns), `:381-394` (200-LOC rule); `docs/system-architecture.md:472,606` (DI provider count).

## Files to Create or Modify

- Modify: `pyproject.toml` (`[tool.importlinter]`), `.github/workflows/cicd.yml` (`tests` job), `docs/code-standards.md` (rewrite), `CLAUDE.md`, `README.md`, `docs/project-overview-pdr.md`, `docs/system-architecture.md` (DI and route-file facts only), `scripts/README.md`
- Modify (lean pass): only files printed by `scripts/code_metrics.py --list tiny|delegation` under `src/pocketquant/`, following rules R1-R4 below

## Lean rules (the only sanctioned changes)

- **R1 Inline single-use helper:** the name starts with `_`, it is in the `--list tiny` output, `grep -rnw "<name>" src` returns exactly 2 lines (def + 1 call), and `grep -rnw "<name>" tests` prints nothing. Paste the body at the call site and delete the def.
- **R2 Delete dead function:** `grep -rnw "<name>" src tests scripts` returns only the def line. Not a route handler, not a port method, not decorated (`@event_handler`, `@provide`, `@field_validator`, `@router.*`, `@staticmethod` used through the class), and not an APScheduler text ref.
- **R3 Collapse forwarding method:** in the `--list delegation` output, with ≤2 call sites in `src` and no reference in `tests` (`grep -rnw "<name>" tests` prints nothing). Callers call the target directly and the method is deleted. Never apply R3 to: methods of a class implementing `IBroker`, `IDataProvider`, `IRealtimeQuoteProvider` or `IStrategy`; route handlers; `core/common` facades (`get_logger`, `utc_now`); repository public methods.
- **R4 OKX websocket getters:** folding `OkxMessageParser` (`okx_message_parser.py`) and the `get_*` staticmethods in `okx_order_mapper.py` / `okx_position_mapper.py` into dict access at the call sites deletes OKX files. STOP-and-ask first (stop condition: "a change would delete Binance/OKX code"). Apply only after the user says yes.
- Never: change behaviour pinned by a test; merge unrelated files; create a function over 60 lines; edit strategy signal logic; touch `core/domain/order`, `core/domain/position` invariants.

## Tasks

### T1: Reduce import-linter to 3 contracts
- **Goal:** Only layers, core-domain-free-of-infra and fastapi-only-in-app remain.
- **Target files and symbols:** `pyproject.toml` `[[tool.importlinter.contracts]]` blocks
- **Steps:** Delete the blocks named "Core imports no inner package", "Engine imports no sibling/upper package", "Backtest imports no upper package" and "No bson/ObjectId usage — UUID7 only". Keep "Layered architecture — app top tier", "Core domain stays free of infra adapters" and "fastapi only in app" unchanged.
- **Success criteria:** 3 contracts, all kept, and bson still blocked by ruff.
- **Verify:** `uv run lint-imports | grep Contracts` prints `Contracts: 3 kept, 0 broken.`, and `uv run ruff check` exits 0. `grep -c 'bson' pyproject.toml` prints a number ≥ 2 (ruff banned-api entries remain).

### T2: Feasibility gate for the metric thresholds (stop-and-ask)
- **Goal:** Decide honestly whether the thresholds are reachable with R1-R3 before editing code.
- **Target files and symbols:** `reports/lean-feasibility.md`
- **Steps:**
  1. Run `.venv/Scripts/python.exe scripts/code_metrics.py --list tiny > /tmp/tiny.txt` and `--list delegation > /tmp/deleg.txt`.
  2. Classify each listed function as `R1`, `R2`, `R3`, `R4` or `floor` (route handler, port method, facade, decorated, multi-use). Count the reachable result: `tiny_after = tiny - (R1+R2+R3 [+R4 if approved])`, `functions_after = functions - same`, and `deleg_after` likewise.
  3. Write `lean-feasibility.md` with the counts and the predicted share.
  4. If the predicted share is over 30% or `deleg_after` is over 20, STOP and present to the user: the original decision (≤30% / ≤20), the gap with numbers, the trade-off (reaching it requires inlining route handlers or port methods, which the advice forbids), and the options: (a) accept the predicted numbers as the soft-gate thresholds, (b) authorize R4, (c) name extra files to collapse. Wait for the answer and record it in `lean-feasibility.md` as `decision: <a|b|c + detail>`.
- **Success criteria:** The prediction is recorded, and the user decided if a gap exists.
- **Verify:** `grep -cE "^(predicted_tiny_share|predicted_delegations|decision): " plans/261009-0858-exness-venue-lean-sync-refactor/reports/lean-feasibility.md` prints `3`.

### T3: Apply R1-R3 (and R4 if approved), one file at a time
- **Goal:** The metric numbers drop through sanctioned edits only.
- **Target files and symbols:** files from `/tmp/tiny.txt` and `/tmp/deleg.txt`, processed in descending order of listed count. Planning-time order: `core/infra/brokers/paper/paper_broker.py`, `core/domain/backtest/value_objects.py`, `engine/app_services/strategy_app_service.py`, `backtest/engine/backtest_engine_sandbox.py`, `core/infra/brokers/okx/okx_broker.py`, `engine/app_services/order_app_service.py`, `backtest/engine/result_collector.py`, `core/common/messaging/event_bus.py`, `core/domain/bar/services/bar_builder.py`, `core/domain/symbol/entities.py`, `core/infra/binance/binance_websocket_client.py`, `engine/app_services/position_app_service.py`, then the rest.
- **Steps (per file):**
  1. Apply the rules to that file's listed functions.
  2. Run `.venv/Scripts/python.exe -m pytest -q -x` and continue only if it exits 0.
  3. Run the metric script and append `<file>: <functions> <tiny%> <delegations>` to `reports/lean-feasibility.md`.
  4. Stop iterating once the thresholds (or the user-accepted numbers from T2) are met.
- **Success criteria:** The thresholds are met, no test changed, and characterization asserts are untouched.
- **Verify:** `.venv/Scripts/python.exe scripts/code_metrics.py --strict` exits 0, or with the user-accepted values from T2: `--max-tiny-share <a> --max-delegations <b> --strict` exits 0. Before the T7 commit, `git diff --stat HEAD -- tests` prints nothing, so no test changed in the lean pass. `.venv/Scripts/python.exe scripts/code_metrics.py | sed -n 4p` shows `over_60_lines:` ≤ 22 (the baseline).

### T4: Rewrite `docs/code-standards.md`
- **Goal:** One standard the code follows, in Vietnamese prose with English technical terms, AS-IS only.
- **Target files and symbols:** `docs/code-standards.md`
- **Steps:** Replace the file with these sections in this order (keep the marked sections' content and code examples, edited only to remove stale claims):
  1. `# Code Standards` (short intro)
  2. `## Dependency Direction`: `core ◁ engine ◁ backtest ◁ app`, the 3 import-linter contracts by name, bson banned by ruff `TID`
  3. `## Khi nào tách hàm (When to extract)`: extract only when the name adds meaning or the code is reused; a flow should read in one file where possible, 3 at most; functions ≲60 lines; files ~400 LOC soft guidance, not a split trigger; examples of R1-R3
  4. `## Naming`: suffix table trimmed to `Repository`, `Service`, `Event`, `Error`, `Provider` (DI); `AppService/CommandService/QueryService` are not distinct roles
  5. `## Routes & Services`: `FromDishka[...]` + `DishkaRoute`, never `Depends()` for services; path/query scalars go straight to service methods; Pydantic models only for real request bodies
  6. `## Dependency Injection`: 3 providers (`InfrastructureProvider`, `AdaptersProvider`, `ServicesProvider`), Settings via context, one provider per type
  7. `## Sync Policy Pattern`: `SyncPolicy` fields, `POLICIES`, `policy_for`, shared runner, how to add a provider (adapter package + policy + DI registration)
  8. `## Comment Policy`: keep the current section verbatim (lines 428-463)
  9. `## Async Suspension Points — Await Is Preemption`: keep verbatim (lines 583-731)
  10. `## Primary Keys — UUIDv7`, `## Composite Symbol Format`, `## Datetime Serialization`: keep verbatim
  11. `## Testing`: characterization-before-refactor rule; fixtures, no network in unit tests
  12. `## Quality Gates`: `.venv/Scripts/python.exe -m pytest`, `uv run ruff check`, `uv run pyright`, `uv run lint-imports`, `scripts/code_metrics.py` soft gate with the current thresholds
  Delete: "Service Extract-Method Pattern", "Command/Query Service Pattern", "Module Size" (200 LOC), and any "Current Status" or largest-file claim.
- **Success criteria:** None of the stale rules remain.
- **Verify:** `grep -cE "200 LOC|Extract-Method|Current Status|8 private helpers" docs/code-standards.md` prints `0`. `grep -c "Sync Policy Pattern" docs/code-standards.md` prints `1`. `grep -c "Await Is Preemption" docs/code-standards.md` prints a number ≥ 1.

### T5: Align repo instructions and docs with the new facts
- **Goal:** No doc states 7 contracts, a 200-LOC cap, or the old DI and route layout.
- **Target files and symbols:** `CLAUDE.md` line 3 ("7 contracts" → "3 contracts") and the Routes bullet ("Service methods take Pydantic command/query models" → "Service methods take scalars for path/query values and Pydantic models for request bodies"); `README.md:87` ("7 import-linter contracts" → "3"); `docs/project-overview-pdr.md:260` (replace the 200-LOC rule with "functions ≲60 lines; files ~400 LOC soft guidance"); `docs/system-architecture.md:472` ("Dishka DI container (6 providers)" → "(3 providers)"), `:606` (same fact), and the "Where Does X Live" row for sync job registration → `engine/market_data/sync_runner.py` → `register_sync_jobs()`; `scripts/README.md` (add a `code_metrics.py` bullet).
- **Steps:** Edit exactly those lines. Vietnamese prose for docs, AS-IS wording.
- **Success criteria:** No stale counts remain.
- **Verify:** `grep -rnE "7 contracts|7 import-linter|200 LOC per file|6 providers" CLAUDE.md README.md docs/*.md` prints nothing (exit 1).

### T6: CI soft gate
- **Goal:** CI shows the metric on every run without blocking.
- **Target files and symbols:** `.github/workflows/cicd.yml`, `tests` job
- **Steps:** After the "Check import contracts (layered architecture)" step, add:
```yaml
      - name: Code metrics (soft gate)
        continue-on-error: true
        run: uv run python scripts/code_metrics.py --strict
```
  If T2 recorded user-accepted thresholds, append `--max-tiny-share <a> --max-delegations <b>`.
- **Success criteria:** The step exists with `continue-on-error: true`.
- **Verify:** `grep -A2 "Code metrics (soft gate)" .github/workflows/cicd.yml | grep -c "continue-on-error: true"` prints `1`.

### T7: Full gate and release
- **Goal:** Green and deployed.
- **Target files and symbols:** repo, `cicd.yml`
- **Steps:** Phase 03 T6 commands, but expect `Contracts: 3 kept, 0 broken.`. Then Phase 01 T7 steps 1-4. Suggested message: `refactor: lean pass, three import contracts, rewritten code standards`.
- **Success criteria:** Passed ≥ N1, gates green, CI green.
- **Verify:** pytest `exit=0` with passed ≥ N1. `uv run lint-imports | grep Contracts` prints `Contracts: 3 kept, 0 broken.` `gh run watch <id> --exit-status` exits 0 and the log contains `0 failures)`.

## Verification

D4 (metric part, per the T2 decision) and D5 hold. The CI soft gate is visible.

## Risks

- The thresholds are unreachable without gaming (high, medium). Planning measurement: 32 route handlers and several port methods are inherently tiny or delegating. T2 stops and asks before any edit.
- An inlining changes behaviour (medium, high): tests run after every file (T3 step 2), and characterization asserts stay untouched.
- Deleting OKX helper files without consent (low, high): R4 requires explicit approval.

## Security

No change to auth or secrets.

## Rollback

Revert per-file commits, or the phase commit. The contract removal is config-only.

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

<!-- FILE: phase-06-exness-signer-and-rest-client.md -->
---
phase: 6
title: "Exness signer and REST client"
status: pending
priority: P1
effort: 24h
dependencies: [1, 5]
---

# Phase 06: Exness signer and REST client

## Goal

Hand-written (not generated), fixture-tested Exness foundations in `src/pocketquant/core/infra/exness/`: `signer.py` (Ed25519 `EXN-*` headers, clock offset), `mappers.py` (pure Exness ↔ domain conversions) and `client.py` (access point, limits-fed token bucket, the REST endpoints). Settings gain the Exness fields. Nothing is wired into DI yet.

## Context Links

- Phase 01 outputs: `D:/w/_me/algotrading/exness-spike-out/summary.json` and raw JSON, plus `docs/journals/*-exness-api-spike-findings.md`
- Spec facts: see Phase 01 Context Links. Close position = `DELETE /v1/trading/accounts/{id}/positions/{position_id}` (no volume closes all). Pending limit = `POST /v1/trading/accounts/{id}/orders` (`instrument, side, type:"limit", volume, price, stop_loss_price, take_profit_price`). Cancel = `DELETE .../orders/{order_id}`. Open = `POST .../positions` (`instrument, side buy|sell, volume` decimal string, optional `stop_loss_price`, `take_profit_price`, `comment`). ACK = `{"operation_id","client_request_id","status":"accepted"}`. Snapshot `GET .../snapshot`. Operation status `GET .../operations/{operation_id}`. Deals history `GET /v1/history/accounts/{id}/deals`. Idempotency key: 5-128 chars of `A-Za-z0-9._-~`. Errors use the public error model (`error.code`, `error_message`).
- Advice section 2.5 ("six files, not sixteen"), section 3 ("do not generate a client")

## Files to Create or Modify

- Create: `src/pocketquant/core/infra/exness/__init__.py` (empty), `signer.py`, `mappers.py`, `client.py`
- Create: `tests/core_test/infra/exness/__init__.py`, `test_signer.py`, `test_mappers.py`, `test_client.py`, `fixtures/` (sanitized JSON)
- Modify: `src/pocketquant/core/config.py` (`Settings`)

## Tasks

### T1: Sanitized fixtures
- **Goal:** Tests use real response shapes with no personal data.
- **Target files and symbols:** `tests/core_test/infra/exness/fixtures/`: `limits.json`, `instruments.json`, `conditions_XAUUSD.json`, `conditions_EURUSD.json`, `conditions_BTCUSD.json`, `account.json`, `candles_XAUUSD_M1.json` (first 60 candles), `candles_XAUUSD_H4.json`, `ticks_XAUUSD.jsonl` (first 20 tick frames), `transaction_event_open.json`, `transaction_event_rejected.json`, `trading_state_snapshot.json`
- **Steps:**
  1. Copy from `../exness-spike-out/`. Replace the account id everywhere with `123456`. In `account.json`, set balance/equity to `"1000.00"` and used_margin to `"0.00"`.
  2. The last three files come from the spec examples under `/v1/server-events/accounts/{account_id}/ws/events`, with the summaries "Trading transaction event", "Rejected processing result event" and "Initial trading state snapshot", converted YAML → JSON. In `transaction_event_open.json`, set `client_request_id` to `"0192c0de-0000-7000-8000-000000000001"`.
- **Success criteria:** The fixtures exist and are clean.
- **Verify:** `.venv/Scripts/python.exe scripts/exness_spike.py --scan tests/core_test/infra/exness/fixtures` prints `CLEAN`, and `ls tests/core_test/infra/exness/fixtures | wc -l` prints `12`.

### T2: Settings fields
- **Goal:** The Exness config is typed and secret-safe.
- **Target files and symbols:** `core/config.py` `Settings`: `exness_account_id: str | None = None`, `exness_api_key: SecretStr | None = None`, `exness_private_key: SecretStr | None = None`, `exness_private_key_path: str | None = None`, `exness_discovery_url: str = "https://api.exness.com"`, `exness_max_lots: float | None = None`, `exness_daily_loss_cap_pct: float | None = None`, and property `exness_configured -> bool` (account id, API key, and one of key/key path all set).
- **Steps:** Add the fields after `okx_demo_mode` (`config.py:61`). Add the property.
- **Success criteria:** Existing Settings construction is unaffected.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test tests/baseline -q` exits 0.

### T3: `signer.py`
- **Goal:** Correct `EXN-*` headers per the spec.
- **Target files and symbols:** `b64url(data: bytes) -> str`, `load_private_key(value: str | None, path: str | None) -> Ed25519PrivateKey` (PEM with literal `\n` normalization, or base64/base64url 32-byte raw seed, the format recorded as `key_format` in the spike), `class ExnessSigner` with `__init__(api_key: str, key: Ed25519PrivateKey)`, `headers(method, path_with_query, body: bytes = b"", idempotency_key: str = "") -> dict[str, str]`, `observe_date(date_header: str | None) -> None` (sets the clock offset in ms)
- **Steps:**
  1. Build the payload `{"api_key","idempotency_key","timestamp","sign_version":1,"method","path","body_hash"}`, serialize it with `json.dumps(..., separators=(",", ":")).encode()`, and sign the bytes.
  2. Use `timestamp = int(time.time()*1000) + offset_ms`. `observe_date` parses the RFC 7231 `Date` header via `email.utils.parsedate_to_datetime`.
- **Success criteria:** The headers match the spec rules.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_signer.py -q` exits 0 with tests asserting: `b64url(hashlib.sha256(b"").digest()) == "47DEQpj8HBSa-_TImW-5JCeuQeRkm5NMpJWZG3hSuFU"`; the six header names exactly; `EXN-SIGN-VERSION == "1"`; GET `EXN-IDEMPOTENCY-KEY == ""`; decoded `EXN-DATA` has `path == "/v1/x?a=1&b=2"` exactly as passed; the signature verifies with the generated key's public key; no `=` in `EXN-DATA`/`EXN-SIGN`; `observe_date` with a header 5 s ahead shifts the timestamp by 4-6 s; both key formats load (generated in-test with `Ed25519PrivateKey.generate()`).

### T4: `mappers.py`
- **Goal:** Pure conversions in one place. All CFD unit logic lives here or in the broker, never in `core/domain`.
- **Target files and symbols:** `INTERVAL_TO_TIMEFRAME` (`1m→M1, 5m→M5, 15m→M15, 1h→H1, 4h→H4, 1d→D1, 1w→W1`), `HISTORY_DAYS` (`M1: 365, M5: 730, M15: 1095`, others unlimited), `candle_to_bar(c: dict, symbol: str, interval: Interval) -> Bar` (bid OHLC, `volume` → `Bar.volume`, `time` → aware UTC datetime), `tick_to_quote(frame: dict, symbol: str) -> dict` returning `{"symbol", "last_price": bid, "bid", "ask", "timestamp"}` (shape from `summary.json` `tick_frame_shape`), `units_to_lots(qty: float, cond: dict) -> float` (`qty / contract_size`, floored to `volume_step` with `Decimal`), `lots_to_units(lots: float, cond: dict) -> float`, `transaction_to_fill(event: dict) -> dict | None` (`client_request_id`, `operation_id`, status, the first `deals[]` with `type in ("open","close")`: `direction`, `volume`, `price`, `position_id`)
- **Steps:** Implement with `Decimal` for lot rounding. No I/O.
- **Success criteria:** The fixture-driven tests pass.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_mappers.py -q` exits 0 with assertions: the first fixture candle maps to a `Bar` with `symbol="XAUUSD:EXNESS"`, `interval=Interval.MINUTE_1` and the same OHLCV; `units_to_lots(150, {"contract_size":"100","volume_step":"0.01"}) == 1.5`; `units_to_lots(0.4, same) == 0.0`; `tick_to_quote` returns `last_price == bid`; `transaction_to_fill(transaction_event_open.json)["client_request_id"] == "0192c0de-0000-7000-8000-000000000001"`.

### T5: `client.py`
- **Goal:** One REST client for all Exness endpoints used by the plan.
- **Target files and symbols:** `class ExnessApiError(Exception)` (`status`, `code`, `message`); `class ExnessClient` with `__init__(settings, *, transport: httpx.AsyncBaseTransport | None = None, access_point: str | None = None, ws_scheme: str = "wss")`, `async request(method, path, *, params=None, json_body=None, idempotency_key="")`, `ws_url(path) -> str`, `ws_headers(path) -> dict`, `account_path(suffix) -> str`, `instrument_name(code) -> str` (case-insensitive lookup in the cached `/instruments`), `conditions(instrument) -> dict` (cached), `limits()`, `account()`, `candles(instrument, timeframe, from_dt, count)`, `open_position(instrument, side, volume, sl, tp, idempotency_key)`, `close_position(position_id, idempotency_key)`, `place_limit_order(instrument, side, volume, price, sl, tp, idempotency_key)`, `cancel_order(order_id, idempotency_key)`, `snapshot()`, `operation_status(operation_id)`, `deals_history(from_dt, to_dt)`, `aclose()`
- **Steps:**
  1. Resolve the access point lazily with a signed GET to `{settings.exness_discovery_url}/v1/trading/access-point?account_id=...`. Keep the host for the process lifetime. On network error retry with backoff 1, 2, 4 s; never switch hosts.
  2. Build the query string once with `urllib.parse.urlencode(params)`. Sign `path + "?" + query` and send exactly that URL (the spec forbids reordering).
  3. After `limits()` first loads, build a token bucket at 80% of `limits.rest.global_account_rate` and `await` it before each request. Call `signer.observe_date(response.headers.get("Date"))` on every response.
  4. Non-2xx → `ExnessApiError` from `error.code` / `error_message`. Never put headers or the body of a signed request into a log line.
- **Success criteria:** `httpx.MockTransport` tests prove signing, discovery, pacing and errors.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_client.py -q` exits 0 with tests: discovery is called once for two requests; every request carries the 6 `EXN-*` headers; the decoded `EXN-DATA.path` equals the request URL path + query; `instrument_name("xauusd")` resolves from `instruments.json`; `candles(...)` sends `timeframe=M1&price_type=bid&count=-60`; a 429 body maps to `ExnessApiError(code="REQUEST_RATE_LIMIT")`; `open_position` sends `EXN-IDEMPOTENCY-KEY` equal to the given key and `volume` as a decimal string.

### T6: Gate and release
- **Goal:** Green and deployed (no runtime wiring yet).
- **Target files and symbols:** repo
- **Steps:** Phase 05 T7 commands (3 contracts). Then the metric must not exceed the Phase 05 thresholds. Then Phase 01 T7 steps 1-4. Suggested message: `feat(exness): signer, REST client and mappers`.
- **Success criteria:** Green, the metric holds, and no secret is in git.
- **Verify:** Phase 05 T7 Verify conditions. `.venv/Scripts/python.exe scripts/code_metrics.py --strict` (with the Phase 05 accepted args if any) exits 0. `git grep -nE "exnsk|BEGIN (OPENSSH )?PRIVATE KEY" -- . ':!plans'` prints nothing (exit 1).

## Verification

D-relevant: the adapter foundation is tested without network. Gate green.

## Risks

- Key format mismatch (medium, medium): the loader accepts both formats and the spike recorded which one is in use.
- Query re-encoding breaks signatures (medium, high): T5 asserts that the signed path equals the sent path.
- Undocumented 4xx shape (low, medium): `ExnessApiError` falls back to the status code when `error` is missing.

## Security

- `SecretStr` for the API key and private key. `get_secret_value()` is called only inside `load_private_key` and `ExnessSigner.__init__`.
- Tests generate throwaway keys. Fixtures pass `--scan`.

## Rollback

Revert the phase commit. Nothing is wired at runtime.

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

<!-- FILE: phase-07-exness-market-data-and-sync-policy.md -->
---
phase: 7
title: "Exness market data and sync policy"
status: pending
priority: P1
effort: 32h
dependencies: [6]
---

# Phase 07: Exness market data and sync policy

## Goal

Exness serves bars and live quotes through the existing ports. `websocket.py`, `data_provider.py` and `quote_provider.py` join the Exness package. A small exchange router lets one `IDataProvider` / `IRealtimeQuoteProvider` binding serve both venues, so `SyncService`, `QuoteAppService` and `WsSubscriptionManager` stay unchanged. `EXNESS_POLICY` (WS ticks live, REST native candles each minute, no cascade) is the second policy. Prod passes D1.

## Context Links

- Assumptions A-i (XAUUSD, EURUSD, BTCUSD), A-ii (bid candles), A-iii (tick volume in `Bar.volume`), A-v (policy)
- `IRealtimeQuoteProvider` members: `core/domain/market_data/interfaces.py:39-81`. `QuoteAppService.on_quote_update` requires `symbol` and `last_price` (`app/market_data/app_services/quote_app_service.py:40-48`).
- OKX backoff shape to reuse: 1 s ×2 up to 30 s, circuit breaker after 10 consecutive failures, 300 s pause (`okx_reconnection_handler.py:16-20`)
- Spike `summary.json`: `ws_subprotocol`, `tick_frame_shape`, `in_progress_candle_returned`, `count_negative_includes_from`, `candle_alignment`, `trade_sessions`, rates

## Architecture

```
WsSubscriptionManager -> ExchangeRoutedQuoteProvider.subscribe("XAUUSD:EXNESS")
     -> ExnessQuoteProvider (ExnessWebSocket /ws/ticks) -> tick_to_quote -> QuoteAppService.on_quote_update
sync_runner -> SyncService.sync -> ExchangeRoutedDataProvider.fetch_ohlcv("XAUUSD:EXNESS", 1m, n)
     -> ExnessDataProvider -> ExnessClient.candles(from=now, count=-k) pages -> candle_to_bar
```

## Files to Create or Modify

- Create: `src/pocketquant/core/infra/exness/websocket.py`, `data_provider.py`, `quote_provider.py`, `src/pocketquant/core/infra/exchange_router.py`
- Create: `tests/core_test/infra/exness/test_websocket.py`, `test_data_provider.py`, `test_quote_provider.py`, `tests/core_test/infra/test_exchange_router.py`
- Modify: `src/pocketquant/engine/market_data/sync_policy.py` (`EXNESS_FX`, `EXNESS_POLICY`, `POLICIES`), `tests/engine_test/market_data/test_sync_policy.py`, `src/pocketquant/app/di/adapters.py`, `tests/app_test/unit/di/test_di_data_provider.py`

## Tasks

### T1: `websocket.py`
- **Goal:** One signed, reconnecting WS helper used by the quote provider and the broker.
- **Target files and symbols:** `class ExnessWebSocket` with `__init__(client: ExnessClient, path: str)`, `async connect()`, `async send_json(obj)`, `async messages() -> AsyncIterator[dict]`, `async close()`, `async run(on_open: Callable[[], Awaitable[None]], on_message: Callable[[dict], Awaitable[None]])` (reconnect loop: delays 1, 2, 4 … 30 s; after 10 consecutive failures log `exness_ws.circuit_breaker_triggered` and sleep 300 s; reset after a successful open); module constant `SUBPROTOCOLS` = `None` or `["exness-ws-protocol"]` per spike `ws_subprotocol`
- **Steps:** `websockets.connect(client.ws_url(path), additional_headers=client.ws_headers(path), subprotocols=SUBPROTOCOLS, ping_interval=20, ping_timeout=10)`. Sign every (re)connect fresh. Log `exness_ws.connected`, `exness_ws.reconnecting` (with delay and failures) and `exness_ws.closed`. Never log headers.
- **Success criteria:** Reconnect and circuit behaviour are tested against a local server.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_websocket.py -q` exits 0 with tests using `websockets.serve(handler, "127.0.0.1", 0)` and `ExnessClient(..., access_point="127.0.0.1:<port>", ws_scheme="ws")`: the handshake request carries `EXN-SIGN`; after the server closes, the client reconnects and `on_open` runs twice; with `asyncio.sleep` patched, 10 refused connects log `exness_ws.circuit_breaker_triggered` once.

### T2: `data_provider.py`
- **Goal:** `IDataProvider` over native candles with no in-progress bar.
- **Target files and symbols:** `class ExnessDataProvider(IDataProvider)`: `fetch_ohlcv(symbol, interval, n_bars=1000) -> list[Bar]`, `search_symbols(query) -> []`, `close()` (no-op; the client is owned by DI)
- **Steps:**
  1. `instrument = client.instrument_name(symbol.split(":")[0])`, `timeframe = INTERVAL_TO_TIMEFRAME[interval]`, `page = limits max_candles_per_request`.
  2. Page backwards from `from = now UTC (seconds zeroed)` with `count = -min(remaining, page)`. The next `from` is the oldest candle time of the previous page. Dedupe by time (the spike `count_negative_includes_from` says whether the boundary repeats). Stop on an empty page, at `HISTORY_DAYS` age, or when `n_bars` is reached.
  3. Drop any candle whose `time + interval_seconds > now` (in-progress). Return ascending, mapped with `candle_to_bar(..., f"{code}:EXNESS", interval)`.
- **Success criteria:** Pagination, dedupe and in-progress exclusion are tested.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_data_provider.py -q` exits 0 with tests: with page size 20 and `n_bars=50`, 3 requests yield 50 unique ascending bars; a candle opened 30 s ago is excluded; `fetch_ohlcv("XAUUSD:EXNESS", Interval.HOUR_1, 5)` sends `timeframe=H1`.

### T3: `quote_provider.py`
- **Goal:** `IRealtimeQuoteProvider` over the ticks stream.
- **Target files and symbols:** `class ExnessQuoteProvider` with `last_tick_at`, `connect`, `disconnect`, `subscribe(symbol, callback) -> str`, `unsubscribe(symbol)`, `run_forever()`, `is_connected()`, `subscription_count`, `subscriptions` (dict composite → `(instrument, callback)`)
- **Steps:**
  1. `run_forever` uses `ExnessWebSocket(client, f"/v1/server-events/accounts/{id}/ws/ticks").run(on_open, on_message)`. `on_open` sends one subscribe frame `{"id": "ticks-<n>", "subscribe": {"event": "ticks", "instruments": [...]}}` for all current subscriptions.
  2. `subscribe` / `unsubscribe` while connected send the single-instrument frame (unsubscribe shape from spike `unsubscribe_reply.json`).
  3. `on_message`: a tick frame → `tick_to_quote` → callback, then set `last_tick_at`. An error frame mentioning `trading_disabled` → log `exness_quotes.trading_disabled` (warning) and leave `last_tick_at` unchanged (stale). Any other error → log `exness_quotes.error_frame`. Never raise out of `on_message`.
- **Success criteria:** Protocol satisfied; the tick path is tested.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_quote_provider.py -q` exits 0 with tests: `isinstance(ExnessQuoteProvider(client), IRealtimeQuoteProvider)` is True; replaying `ticks_XAUUSD.jsonl` from a local server calls the callback with `symbol="XAUUSD:EXNESS"` and `last_price == bid`; an error frame `{"error":{"code":"...","message":"trading_disabled"}}` does not stop the loop and does not update `last_tick_at`.

### T4: `exchange_router.py`
- **Goal:** One port binding serves several venues by the composite suffix.
- **Target files and symbols:** `class ExchangeRoutedDataProvider(IDataProvider)` (`__init__(providers: dict[str, IDataProvider])`, `fetch_ohlcv` dispatches on the exchange suffix, unknown → `ValueError(f"No data provider for exchange {ex}")`, `search_symbols` → `[]`, `close` closes all); `class ExchangeRoutedQuoteProvider` (`__init__(providers: dict[str, IRealtimeQuoteProvider])`, `subscribe` / `unsubscribe` dispatch, `run_forever` = `asyncio.gather` of the children, `connect` / `disconnect` all, `is_connected` all, `subscriptions` merged dict, `subscription_count` sum, `last_tick_at` = latest of the children)
- **Steps:** Implement as above. No venue-specific code.
- **Success criteria:** Dispatch and the Protocol are tested.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/test_exchange_router.py -q` exits 0 with tests: the BINANCE symbol reaches fake A and EXNESS reaches fake B; an unknown suffix raises `ValueError`; the router `isinstance(..., IRealtimeQuoteProvider)`; merged `subscriptions` holds both keys.

### T5: `EXNESS_POLICY`
- **Goal:** Exness becomes policy #2 with spike-derived values.
- **Target files and symbols:** `sync_policy.py`: `EXNESS_FX: MarketCalendar` (closed windows from spike `trade_sessions` of XAUUSD/EURUSD: the weekly close and any daily break), `EXNESS_POLICY`, `POLICIES` (adds `"EXNESS"`)
- **Steps:**
  1. `poll_intervals` = those of `(1m, 5m, 15m, 1h, 4h, 1d)` that are aligned. 1m/5m/15m/1h are assumed aligned; include 4h and 1d only if `candle_alignment.H4` / `.D1` is true.
  2. `sync_intervals` = `poll_intervals` + `(1w,)` if `candle_alignment.W1` is true.
  3. `backfill_bars = {1m: 43_200, every other interval: 5_000}`. `poll_bars = 100`. `cascade = False`. `live_source = "ws_ticks"`. `bar_source = "rest_candles_bid"`.
  4. `calendar = EXNESS_FX`. `calendar_overrides = {"BTCUSD": ALWAYS_OPEN}` if BTCUSD `trade_sessions` cover all 7 days, else `{}`.
  5. `rate_budget_per_minute` = the Phase 01 T5 `budget` value.
  6. Tests: `policy_for("XAUUSD:EXNESS") is EXNESS_POLICY`; `EXNESS_POLICY.cascade is False`; `3 * len(EXNESS_POLICY.poll_intervals) <= EXNESS_POLICY.rate_budget_per_minute`; `EXNESS_POLICY.calendar_for("EURUSD:EXNESS").is_open(<a Saturday 12:00 UTC>) is False`; `BINANCE_POLICY` is unchanged.
- **Success criteria:** The A-v budget assertion passes. If it cannot, STOP (stop-and-ask: limits make A-v infeasible).
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/engine_test/market_data/test_sync_policy.py tests/engine_test/market_data/test_sync_pipeline_characterization.py -q` exits 0.

### T6: DI wiring
- **Goal:** The routers are bound, and Exness is included only when configured.
- **Target files and symbols:** `app/di/adapters.py`: `get_exness_client(settings) -> AsyncIterator[ExnessClient]` (yield, then `aclose`); `get_data_provider(settings, exness: ExnessClient) -> IDataProvider` returning `ExchangeRoutedDataProvider({"BINANCE": BinanceClient(settings=settings), **({"EXNESS": ExnessDataProvider(exness)} if settings.exness_configured else {})})`; `get_realtime_quote_provider(settings, exness) -> IRealtimeQuoteProvider` built the same way with `BinanceWebSocketClient()` and `ExnessQuoteProvider(exness)`
- **Steps:** Edit `adapters.py`. Update `test_di_data_provider.py`: the provider is an `ExchangeRoutedDataProvider`, `BTCUSDT:BINANCE` routes to `BinanceClient`, and with `exness_account_id=None` an EXNESS symbol raises `ValueError`.
- **Success criteria:** Without Exness env the app behaves exactly as before.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/app_test tests/baseline -q` exits 0 and `git diff --stat tests/baseline` prints nothing.

### T7: Gate, release and prod smoke (D1)
- **Goal:** Prod serves Exness bars and quotes.
- **Target files and symbols:** prod API `POST /api/v1/market-data/tracked-symbols`, `POST /api/v1/market-data/sync`, `GET /api/v1/market-data/bars/stream/{symbol}`, `GET /api/v1/quotes/stream/{symbol}`
- **Steps:**
  1. Phase 06 T6 gate. Then Phase 01 T7 steps 1-4. Suggested message: `feat(exness): market data provider, tick quotes and sync policy`.
  2. Confirm with the user that prod `.env` holds the EXNESS_* values (precondition 2).
  3. During FX market hours, run from repo root:
```bash
ssh -i ../pocketquant-config/vps/default/id_rsa "$(cat ../pocketquant-config/vps/default/host)" 'docker exec -i pocketquant-app sh -s' <<'EOF'
for s in XAUUSD EURUSD BTCUSD; do curl -s -X POST http://localhost:41921/api/v1/market-data/tracked-symbols -H "X-Admin-Token: $ADMIN_TOKEN" -H 'Content-Type: application/json' -d "{\"symbol\":\"$s:EXNESS\"}" > /dev/null; done
curl -s -X POST http://localhost:41921/api/v1/market-data/sync -H 'Content-Type: application/json' -d '{"symbol":"XAUUSD:EXNESS","interval":"1m","n_bars":1000,"source":"bulk_sync_api"}' | python -c 'import json,sys; r=json.load(sys.stdin); print("SYNC", r["status"], "TOTAL_OK" if (r.get("total_bars") or 0) >= 1000 else r.get("total_bars"))'
sleep 15
timeout 70 curl -s -N "http://localhost:41921/api/v1/market-data/bars/stream/XAUUSD%3AEXNESS?interval=1m" | grep -m1 -c '"is_in_progress": true'
timeout 30 curl -s -N "http://localhost:41921/api/v1/quotes/stream/XAUUSD%3AEXNESS" | grep -m1 -c '"symbol": "XAUUSD:EXNESS"'
EOF
```
- **Success criteria:** D1 holds.
- **Verify:** CI `gh run watch <id> --exit-status` exits 0 with `0 failures)`. The ssh output contains `SYNC completed TOTAL_OK` and then two lines `1`. If the API rejects with `REQUEST_RATE_LIMIT` or the candle limits contradict the spike, STOP (stop-and-ask: A-v infeasible).

## Verification

D1 on prod. Binance goldens still pass. Without EXNESS_* the app is unchanged (T6).

## Risks

- WS subprotocol/handshake differs from the spike (medium, medium): `SUBPROTOCOLS` comes from spike evidence and T1 tests the reconnect path.
- Subscribe strikes on non-existent instruments (low, medium): `instrument_name` resolves exact names before any subscribe.
- Log spam when an EXNESS symbol is tracked without credentials (medium, low): `WsSubscriptionManager` logs `subscribe_failed` each 5 s. Track Exness symbols only after the env is set (T7 step 2).

## Security

The signed handshake is regenerated per connect. No header logging. The admin token is used only inside the container (`$ADMIN_TOKEN` expands there and is never printed locally).

## Rollback

Remove the EXNESS_* values from prod `.env` and redeploy: the routers then hold Binance only. Or `git revert` the phase commit. Optionally `DELETE /api/v1/market-data/tracked-symbols/{XAUUSD%3AEXNESS}` (admin).

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

<!-- FILE: phase-08-exness-broker-and-live-routing.md -->
---
phase: 8
title: "Exness broker and live routing"
status: pending
priority: P1
effort: 32h
dependencies: [7]
---

# Phase 08: Exness broker and live routing

## Goal

`ExnessBroker(IBroker)` converts quantities to lots inside the adapter, attaches SL/TP on open, returns `SUBMITTED` with the `operation_id`, and turns events-WS `transaction_event`s into fills. A subscription can choose its broker (`paper` by default). Live brokers' async fills reach `OrderAppService.on_order_update`. Safety guards refuse any order without SL, any order above `EXNESS_MAX_LOTS`, and any order after the daily loss cap is hit. No live order is placed in this phase.

## Context Links

- Live routing gaps verified at planning time: `Subscription` (`core/domain/subscription/entities.py:32-73`) has no broker field, and `StrategyConfig` is built without `broker` in `engine/app_services/strategy_reconcile_service.py:141` and `app/main_extensions.py:152`, so every subscription runs on `paper` today. No code calls `subscribe_order_updates` with `OrderAppService.on_order_update` (`engine/app_services/order_app_service.py:169-198`).
- `OrderAggregate` transitions: SUBMITTED → FILLED/CANCELLED only (`core/domain/order/entities.py:52-57`). Post-ACK venue rejects therefore map to `CANCELLED` with an error message, and the domain is not changed.
- PaperBroker publishes `OrderFilledEvent` for synthetic SL/TP exits (`core/infra/brokers/paper/paper_broker.py:671-718`). Venue-side SL/TP closes mirror that.
- OKX terminal dedupe set: `okx_broker.py:59, 358-362`

## Files to Create or Modify

- Create: `src/pocketquant/core/infra/exness/broker.py`, `tests/core_test/infra/exness/test_broker.py`
- Modify: `src/pocketquant/app/di/adapters.py` (`BrokerFactory`), `src/pocketquant/core/domain/subscription/entities.py`, `src/pocketquant/engine/strategy_command_service.py` (`AddSymbolCommand`, `add_symbol`), `src/pocketquant/app/routes/strategy.py` (`CreateSubscriptionBody`, `create_subscription`), `src/pocketquant/engine/app_services/strategy_reconcile_service.py` (line 141), `src/pocketquant/app/main_extensions.py` (line 152), `src/pocketquant/engine/app_services/strategy_app_service.py` (`_get_or_create_broker`), `tests/baseline/openapi_app_snapshot.json` (regenerated), and the tests in T3/T4

## Tasks

### T1: `broker.py`
- **Goal:** A complete Exness `IBroker` with CFD logic contained in it.
- **Target files and symbols:** `class ExnessBroker(IBroker)`: `__init__(client, event_bus, max_lots: float | None, daily_loss_cap_pct: float | None)`, `name` → `"exness"`, `is_connected`, `connect`, `disconnect`, `submit_order`, `cancel_order`, `get_positions`, `get_balance`, `subscribe_order_updates`, `unsubscribe_order_updates`, and private `_on_event(msg)`, `_guard(order) -> str | None`
- **Steps:**
  1. `connect`: load conditions for nothing up-front. Start `ExnessWebSocket(client, f"/v1/server-events/accounts/{id}/ws/events").run(on_open, _on_event)` as a task. `on_open` sends `{"id":"tx-1","subscribe":{"event":"transactions"}}` and re-sends `hmr` subscriptions for already-traded instruments.
  2. `_guard(order)` returns a reason or `None`: symbol suffix not `:EXNESS` → `"symbol is not an EXNESS instrument"`; `max_lots is None` → `"EXNESS_MAX_LOTS not configured"`; `daily_loss_cap_pct is None` → `"EXNESS_DAILY_LOSS_CAP_PCT not configured"`; `order.sl_price is None` and the order opens a position → `"stop loss required"`; equity fell ≥ cap% since the first equity seen on this UTC day → `"daily loss cap reached"`.
  3. `submit_order`: if the guard fails → `OrderResult(order_id=str(order.id), broker_order_id="", status=OrderStatus.REJECTED, error_message=reason)`. `cond = client.conditions(instr)`. `lots = min(units_to_lots(order.quantity, cond), float(cond["volume_max"]), max_lots)`. If `lots < float(cond["volume_min"])` → REJECTED `"rounded lot below volume_min"`. If this subscription has a tracked open position in the opposite direction on the same instrument → `client.close_position(position_id, idempotency_key=str(order.id))`. Else MARKET → `client.open_position(instr, side, lots, sl=order.sl_price, tp=order.tp_price, idempotency_key=str(order.id))`, LIMIT → `client.place_limit_order(...)`. Remember `pending[str(order.id)] = (order.subscription_id, order.symbol, order.side, cond)`. Log `exness.order_ack` with `order_id`, `operation_id` and `lots`. Return `OrderResult(order_id, broker_order_id=operation_id, status=OrderStatus.SUBMITTED, sl_price, tp_price, side)`. On `ExnessApiError` return REJECTED with `f"{code}: {message}"`.
  4. `_on_event(msg)`: `transaction_event` with `status=="success"` and a `client_request_id` in `pending` → dedupe on `operation_id` (set), then `transaction_to_fill` → `OrderResult(status=FILLED, filled_quantity=lots_to_units(volume, cond), filled_price=price, side=...)`, record `positions[position_id] = (subscription_id, symbol, side, units)` for `open` deals and remove it for `close` deals, log `exness.order_filled`, and notify callbacks. `rejected`/`failed` for a pending id → `OrderResult(status=OrderStatus.CANCELLED, error_message=f"{error_code}: {error_message}")` and log `exness.order_rejected_after_ack`. A `close` deal for a tracked position with no pending id (venue SL/TP) → publish `OrderFilledEvent(order_id=generate_id_str(), subscription_id, symbol, side=<exit side>, filled_quantity=units, filled_price=price)` on the event bus and log `exness.venue_exit`. `hmr_snapshot` / `hmr_update` → log `exness.hmr_event`. `trading_state_snapshot` → log `exness.snapshot` with the open position count. Never raise out of `_on_event`.
  5. `get_balance`: from `client.account()`, `AccountBalance(total_equity=equity, available_balance=equity-used_margin, currency=<account currency field from the spike account.json>, margin_used=used_margin)`. Record the first equity of the UTC day.
  6. `get_positions`: from `client.snapshot()` positions → `PositionAggregate` with quantity in units (`lots_to_units`) and `subscription_id` from `positions` or `"exness"` when unknown.
  7. `cancel_order(broker_order_id)` → `client.cancel_order(...)` → `True` on ACK.
- **Success criteria:** Guards, conversion, ACK, fills, rejects and venue exits are tested with a fake client and a local events WS.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_broker.py -q` exits 0 with tests: no SL → REJECTED `stop loss required` and no client call; `max_lots=None` → REJECTED; a 150-unit XAUUSD order with `contract_size=100, volume_step=0.01, max_lots=0.01` sends `volume="0.01"`; the ACK yields `SUBMITTED` with `broker_order_id == operation_id`; `transaction_event_open.json` → one FILLED callback with `order_id` = `client_request_id` and `filled_quantity == lots_to_units(volume)`; the same event twice → one callback; `transaction_event_rejected.json` for a pending id → CANCELLED with an error message; a close deal for a tracked position without pending → `OrderFilledEvent` published once; a daily equity drop ≥ cap → REJECTED `daily loss cap reached`.

### T2: Broker factory entry `exness`
- **Goal:** Strategies can obtain the Exness broker.
- **Target files and symbols:** `app/di/adapters.py` `BrokerFactory.__init__(event_bus, settings: Settings, exness_client: ExnessClient)`, `create("exness", config)`, `get_available_types()` → `["paper", "okx", "exness"]`
- **Steps:** Add the branch. If `not settings.exness_configured`, raise `ValueError("Exness broker requires EXNESS_ACCOUNT_ID, EXNESS_API_KEY and a private key")`. Otherwise return `ExnessBroker(exness_client, self._event_bus, settings.exness_max_lots, settings.exness_daily_loss_cap_pct)`.
- **Success criteria:** The OKX and paper branches are unchanged.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/brokers/test_okx_broker_characterization.py tests/core_test/infra/exness/test_broker.py -q` exits 0 (OKX characterization asserts are untouched; only constructor arguments in the factory fixture may change).

### T3: Subscription carries its broker
- **Goal:** A subscription chooses `paper` (default), `okx` or `exness`. Old docs load as `paper`.
- **Target files and symbols:** `Subscription.broker: str = "paper"` (last field), `to_mongo` adds `"broker"`, `from_mongo` uses `doc.get("broker", "paper")`; `AddSymbolCommand.broker: str = "paper"` and `add_symbol` passes it and returns `"broker"` in the dict; `CreateSubscriptionBody.broker: Literal["paper", "okx", "exness"] = "paper"` and `create_subscription` passes it; `StrategyConfig(..., broker=sub.broker)` at `strategy_reconcile_service.py:141` and `main_extensions.py:152`
- **Steps:**
  1. Make the edits.
  2. Add tests: a Subscription round-trip with and without `broker`; reconcile loads `StrategyConfig.broker == "exness"` for an exness subscription (extend `tests/engine_test/test_strategy_reconcile_service.py` with one new test).
  3. Regenerate the OpenAPI snapshot: `BASELINE_UPDATE=1 .venv/Scripts/python.exe -m pytest tests/baseline/test_openapi_snapshot.py -q`.
- **Success criteria:** Only the `broker` property was added to the API schema.
- **Verify:**
```bash
.venv/Scripts/python.exe - <<'EOF'
import json, subprocess
new = json.load(open("tests/baseline/openapi_app_snapshot.json", encoding="utf-8"))
old = json.loads(subprocess.run(["git", "show", "HEAD:tests/baseline/openapi_app_snapshot.json"], capture_output=True, text=True, encoding="utf-8", check=True).stdout)
new["components"]["schemas"]["CreateSubscriptionBody"]["properties"].pop("broker")
print("ONLY_BROKER_ADDED" if new == old else "UNEXPECTED_DIFF")
EOF
```
  prints `ONLY_BROKER_ADDED`, and `.venv/Scripts/python.exe -m pytest tests/baseline tests/core_test/unit/domain/subscription tests/engine_test -q` exits 0.

### T4: Wire async fills from live brokers
- **Goal:** Venue fills move orders to FILLED and open positions.
- **Target files and symbols:** `StrategyAppService._get_or_create_broker` (`strategy_app_service.py:409-416`)
- **Steps:** After `self._broker_factory.create(...)`, if `broker_type != "paper"`, run `await broker.subscribe_order_updates(self._order_app_service.on_order_update)`. Add one comment line explaining why: paper fills synchronously inside `submit_order`, so subscribing it would double-fill. Reused brokers are not subscribed again.
- **Success criteria:** Paper is not subscribed. A live type is subscribed once.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/engine_test/test_strategy_service.py -q` exits 0 with two new tests: a fake factory returning a recording broker for `"exness"` → `subscribe_order_updates` called exactly once across two `load_strategy` calls; for `"paper"` → never called.

### T5: Gate and release (still no live orders)
- **Goal:** Deployed safely with trading inert.
- **Target files and symbols:** repo, prod logs
- **Steps:**
  1. Phase 06 T6 gate. Then Phase 01 T7 steps 1-4. Suggested message: `feat(exness): broker with lot conversion, async fills and per-subscription broker`.
  2. Confirm that prod `.env` does NOT yet set `EXNESS_MAX_LOTS`: ask the user (yes/no). This keeps the guard rejecting every order until Phase 09.
- **Success criteria:** Deploy green and the broker is inert.
- **Verify:** `gh run watch <id> --exit-status` exits 0 with `0 failures)` in the log, and the user answered that `EXNESS_MAX_LOTS` is unset.

## Verification

Broker behaviour is unit-proven, routing is opt-in per subscription, and the default stays paper.

## Risks

- Hedging account opens an opposite position instead of closing (medium, high): T1 step 3 closes the tracked opposite position.
- Restart loses the position → subscription link (medium, medium): venue SL/TP still closes at the venue, but the engine position stays open. Operational rule in Phase 09: do not deploy while an Exness position is open. Documented in Phase 10 Known Limitations.
- A fill event is missed during a WS gap (low, medium): `trading_state_snapshot` after reconnect is logged, and `operation_status` is available for manual reconciliation.

## Security

Guards default to refusing (`None` caps reject every order). Idempotency key = order UUIDv7, so retries never double-submit.

## Rollback

Leave `EXNESS_MAX_LOTS` unset (kill switch), or `git revert`. Subscriptions without `broker` read as `paper`.

## Stop-and-ask conditions in this phase

- Any change that would let a live Exness order exceed the minimum lot or go without SL. The guards must stay.

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

<!-- FILE: phase-09-cfd-validation-and-live-round-trip.md -->
---
phase: 9
title: "CFD validation and live round trip"
status: pending
priority: P1
effort: 40h
dependencies: [8]
---

# Phase 09: CFD validation and live round trip

## Goal

Prove G1 honestly. `PaperBroker` gains a constant `spread`. Exness M1/H1 history is backfilled. `hitnrun2` and `engulfing` backtests on Exness bars finish with trades (D3). One minimum-lot live round trip per strategy fills via the events WS and shows in `/trading/positions` (D2). One week including a weekend close shows no WS reconnect loops, no circuit-breaker trips and no FX weekend integrity false alarms.

## Context Links

- Advice section 2.8 and section 3 (spread; minimum lot only)
- `PaperBroker._apply_slippage` (`paper_broker.py:436-439`) is used by every fill path (`:199, :261, :617, :678`)
- Backtest plumbing: `RunBacktestCommand` (`backtest/backtest_command_service.py:22-35`), the config dict (`:61-70`), `BacktestConfig` (`backtest/models/backtest_config.py:25-34`), `_config_from_dict` (`backtest/workers/backtest_dispatch.py:43-54`), `run_single` → `sandbox.create_broker` (`:91-95`), `BacktestSandbox.create_broker` (`backtest/engine/backtest_engine_sandbox.py:110-127`), `BacktestAppService.run` sets slippage (`backtest/engine/backtest_app_service.py:102`)
- Backtest result: `GET /api/v1/backtest/{run_id}` → `status` (`started` | `finished` | `failed`) and `metrics.total_trades`

## Files to Create or Modify

- Modify: `src/pocketquant/core/infra/brokers/paper/paper_broker.py`, `backtest/backtest_command_service.py`, `backtest/models/backtest_config.py`, `backtest/workers/backtest_dispatch.py`, `backtest/engine/backtest_engine_sandbox.py`, `backtest/engine/backtest_app_service.py`, `tests/baseline/openapi_app_snapshot.json` (regenerated)
- Create: `tests/core_test/infra/brokers/test_paper_broker_spread.py`, `plans/261009-0858-exness-venue-lean-sync-refactor/reports/validation.md`

## Tasks

### T1: `spread` in PaperBroker and the backtest request
- **Goal:** CFD backtests pay the spread. Default 0 keeps every existing result.
- **Target files and symbols:** `PaperBroker.__init__(..., spread: float = 0.0)`, property and setter `spread`, `_apply_slippage` (BUY: `price*(1+slippage) + spread/2`; SELL: `price*(1-slippage) - spread/2`); `RunBacktestCommand.spread: float = Field(default=0.0, ge=0, description="Constant spread in price units; longs fill at +spread/2, shorts at -spread/2")`; config dict key `"spread"`; `BacktestConfig.spread: float = 0.0` (after `commission_bps`); `_config_from_dict` → `spread=payload.get("spread", 0.0)`; `run_single` → `sandbox.create_broker(..., spread=config.spread)`; `BacktestSandbox.create_broker(..., spread: float = 0.0)`; `BacktestAppService.run` → `self._broker.spread = config.spread` next to line 102
- **Steps:**
  1. Make the edits.
  2. Write `test_paper_broker_spread.py`: market BUY at bar close 100 with `slippage_percent=0, spread=0.2` fills at 100.1; SELL fills at 99.9; with `spread=0` fills equal the current behaviour.
  3. Regenerate the OpenAPI snapshot (`BASELINE_UPDATE=1 .venv/Scripts/python.exe -m pytest tests/baseline/test_openapi_snapshot.py -q`).
- **Success criteria:** Existing PaperBroker and backtest tests are unchanged and green. Only `spread` was added to the schema.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/brokers tests/backtest_test -q` exits 0, and the Phase 08 T3 Verify script with `RunBacktestCommand` / `spread` in place of `CreateSubscriptionBody` / `broker` prints `ONLY_SPREAD_ADDED`.

### T2: Gate and release
- **Goal:** Spread is live in prod.
- **Target files and symbols:** repo
- **Steps:** Phase 06 T6 gate. Then Phase 01 T7 steps 1-4. Suggested message: `feat(backtest): constant spread parameter for CFD backtests`.
- **Success criteria:** The gate is green and the deploy succeeded.
- **Verify:** The Phase 06 T6 Verify conditions hold. `gh run watch <id> --exit-status` exits 0, and `gh run view <id> --log | grep -c ", 0 failures)"` prints a number ≥ 1.

### T3: Confirm the backfill
- **Goal:** Enough Exness history exists for both strategies.
- **Target files and symbols:** daily `sync_backfill` (03:00 UTC), `GET /api/v1/market-data/sync-status/{symbol}?interval=`
- **Steps:** After the first 03:00 UTC run following Phase 07 T7, run:
```bash
ssh -i ../pocketquant-config/vps/default/id_rsa "$(cat ../pocketquant-config/vps/default/host)" 'docker exec -i pocketquant-app sh -s' <<'EOF'
for s in XAUUSD EURUSD BTCUSD; do for i in 1m 1h; do curl -s "http://localhost:41921/api/v1/market-data/sync-status/$s%3AEXNESS?interval=$i" | python -c "import json,sys; r=json.load(sys.stdin); print('$s','$i', r['bar_count'])"; done; done
EOF
```
- **Success criteria:** Every 1m count ≥ 40000 and every 1h count ≥ 4900.
- **Verify:** All six printed counts meet those floors. Record them in `validation.md`.

### T4: Exness backtests for both strategies (D3)
- **Goal:** `hitnrun2` (1m) and `engulfing` (1h) finish on Exness bars with spread applied.
- **Target files and symbols:** `POST /api/v1/backtest/run`, `GET /api/v1/backtest/{run_id}`
- **Steps:**
  1. Per instrument, `spread = median_spread` from the spike `summary.json`. `commission_bps = 0` unless the instrument's `commission_settings` in `conditions_*.json` is non-zero (then convert to bps and record the conversion in `validation.md`). `slippage_bps = 0`.
  2. For each of the 3 instruments, submit `hitnrun2` on `1m` over the last 30 days and `engulfing` on `1h` over the last 180 days:
     `curl -s -X POST http://localhost:41921/api/v1/backtest/run -H 'Content-Type: application/json' -d '{"strategy_id":"<code>","symbol":"<S>:EXNESS","interval":"<iv>","start_date":"<ISO>","end_date":"<ISO>","initial_capital":10000,"slippage_bps":0,"commission_bps":0,"spread":<median_spread>}'` (inside the container, same ssh pattern). Record each `request_id`.
  3. Poll `GET /api/v1/backtest/{run_id}` until `status` is not `started`.
- **Success criteria:** All 6 runs are `finished`. For each strategy, at least one run has `metrics.total_trades > 0`.
- **Verify:** For each run id, `curl -s http://localhost:41921/api/v1/backtest/<id> | python -c 'import json,sys; r=json.load(sys.stdin); print(r["status"], r["metrics"]["total_trades"])'` prints `finished <n>`, and per strategy max(n) > 0. Record a table in `validation.md`.

### T5: Live preconditions (stop-and-ask)
- **Goal:** Explicit user approval and risk caps before money moves.
- **Target files and symbols:** `reports/validation.md`
- **Steps:**
  1. Ask the user to confirm: (a) prod `.env` sets `EXNESS_MAX_LOTS` equal to `volume_min` of XAUUSD from the spike, (b) `EXNESS_DAILY_LOSS_CAP_PCT` is set, (c) approval to start live subscriptions now, (d) agreement not to deploy while an Exness position is open.
  2. Record the answers as `live_max_lots_equals_min: yes`, `daily_cap_set: yes`, `live_approved: yes`, `no_deploy_with_open_position: yes`.
  3. If `EXNESS_MAX_LOTS` would exceed the minimum lot, STOP (stop-and-ask condition).
- **Success criteria:** 4 `yes` lines.
- **Verify:** `grep -cE "^(live_max_lots_equals_min|daily_cap_set|live_approved|no_deploy_with_open_position): yes$" plans/261009-0858-exness-venue-lean-sync-refactor/reports/validation.md` prints `4`.

### T6: Start one live subscription per strategy
- **Goal:** Both strategies run on the Exness broker at minimum lot.
- **Target files and symbols:** `POST /api/v1/strategies/{strategy_code}/subscriptions`, `POST /api/v1/subscriptions/{sub_id}/start`
- **Steps:** Inside the container (ssh pattern), create `{"symbol":"XAUUSD:EXNESS","interval":"1m","broker":"exness"}` for `hitnrun2` and `{"symbol":"XAUUSD:EXNESS","interval":"1h","broker":"exness"}` for `engulfing`. Record both `id`s and start each.
- **Success criteria:** Both subscriptions return `"broker": "exness"` and start.
- **Verify:** The create responses contain `"broker": "exness"`, and `curl -s http://localhost:41921/api/v1/subscriptions/` lists both ids.

### T7: Verify the round trips (D2)
- **Goal:** Each strategy's first live order fills within 10 s via the events WS, shows as a position, and closes at the venue SL/TP.
- **Target files and symbols:** prod logs (`exness.order_ack`, `exness.order_filled`, `exness.venue_exit`), `GET /api/v1/trading/orders`, `GET /api/v1/trading/positions`, `ExnessClient.deals_history`
- **Steps:**
  1. Re-run this check (not a sleep loop) until both subscriptions have a filled entry:
     `ssh ... "docker logs pocketquant-app --since 24h 2>&1 | grep -E 'exness.order_(ack|filled)'"`, then `curl -s http://localhost:41921/api/v1/trading/orders` and `curl -s http://localhost:41921/api/v1/trading/positions` inside the container.
  2. For each strategy, compute `filled_ts - ack_ts` from the two log lines with the same `order_id`.
  3. Wait for `exness.venue_exit` (or an engine-initiated close) for each, then confirm the position summary `is_closed: true`.
  4. Inside the container, run `python -c` with `ExnessClient(get_settings())` → `deals_history(<entry day>, <now>)`. Confirm one `open` and one `close` deal per round trip with `volume == volume_min`. Print only types, volumes and prices.
- **Success criteria:** D2 for both strategies. Every venue lot equals the minimum.
- **Verify:** For each strategy: `filled_ts - ack_ts <= 10s`; the order shows `"status": "filled"`; the position appears in `/trading/positions` and later reports `"is_closed": true`; `deals_history` shows `open` + `close` with `volume` == `volume_min`. Record everything in `validation.md`. If any venue volume exceeds `volume_min` or an order went out without SL, stop the subscriptions immediately (`POST /api/v1/subscriptions/{id}/stop`) and STOP (stop-and-ask).

### T8: One-week observation including a weekend close
- **Goal:** Stable WS, no circuit trips, no FX weekend integrity false alarms.
- **Target files and symbols:** prod logs, `POST /api/v1/market-data/integrity/check`
- **Steps:** On the Monday after ≥7 days live, inside the container:
  1. `docker logs pocketquant-app --since 168h 2>&1 | grep -c "exness_ws.circuit_breaker_triggered"`
  2. `docker logs pocketquant-app --since 168h 2>&1 | grep -c "exness_ws.reconnecting"` and inspect the delays (backoff grows, no tight loop)
  3. `curl -s -X POST http://localhost:41921/api/v1/market-data/integrity/check -H 'Content-Type: application/json' -d '{"symbol":"EURUSD:EXNESS","interval":"1m","days_back":4}'` and the same for `XAUUSD:EXNESS`
- **Success criteria:** Zero circuit trips. Reconnects show increasing delays. No `gap_ranges` entry starts inside the `EXNESS_FX` weekend window.
- **Verify:** Step 1 prints `0`. No two consecutive `exness_ws.reconnecting` lines less than 1 s apart. A python check over the integrity JSON prints `NO_WEEKEND_GAPS` (every `gap_ranges[i][0]` is open per `EXNESS_POLICY.calendar_for(...)`). Record in `validation.md`.

### T9: Close the validation
- **Goal:** Live exposure ends or continues by user choice.
- **Target files and symbols:** `POST /api/v1/subscriptions/{sub_id}/stop`
- **Steps:** Ask the user: keep or stop the two subscriptions. If stop, call `stop` for both and confirm no open Exness position via `/trading/positions`.
- **Success criteria:** The user's decision is applied.
- **Verify:** `validation.md` line `live_after_validation: kept|stopped` exists. If `stopped`, `/trading/positions` shows no `XAUUSD:EXNESS` entry with `"is_closed": false`.

## Verification

D2 and D3 recorded in `validation.md` with timings, run ids and deal checks. One-week stability evidenced.

## Risks

- No signal arrives for days (medium, low): the engulfing H1 cadence is slow. The observation week covers it. Record if nothing fires and ask the user.
- A spread-free backtest flatters shorts (fixed by T1).
- Swap/financing is not modelled (accepted trade-off, documented in Phase 10).
- Live loss beyond plan (low, high): min-lot cap + SL guard + daily cap + T7 stop rule.

## Security

The admin token and Exness keys stay inside the container. Commands print no secrets. `deals_history` output is limited to type, volume and price.

## Rollback

Stop the subscriptions. Unset `EXNESS_MAX_LOTS` and redeploy (kill switch). Reverting `spread` is a single commit, and the default 0 already keeps old behaviour.

## Stop-and-ask conditions in this phase

- A live order would exceed the minimum lot or run without SL (T5, T7).
- An unexplained test failure after one focused investigation (Failure Protocol).

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

<!-- FILE: phase-10-architecture-docs-and-mt5-note.md -->
---
phase: 10
title: "Architecture docs and MT5 note"
status: pending
priority: P3
effort: 8h
dependencies: [9]
---

# Phase 10: Architecture docs and MT5 note

## Goal

The docs describe the system as it now is (D7): the Exness adapters, the sync-policy pattern with the shared runner, the exchange router, the per-subscription broker, the Exness env vars, known limitations, and MT5 as a documented future provider behind the same ports (not built).

## Context Links

- `docs/system-architecture.md` sections: "Layer 4: Adapters" (line ~255), "Where Does X Live?" (~455), "Real-Time Streaming" (~553), "Broker & Middleware" (~573), "Dependency Injection (Dishka)" (~604), "Configuration" (~702), "Known Limitations" (~710)
- `docs/deployment.md` env table (lines ~83-96)
- Advice section 2.9 (MT5: `copy_rates_from` bar source, `copy_ticks_from` live source, Windows host or Wine bridge, explicitly not built)

## Files to Create or Modify

- Modify: `docs/system-architecture.md`, `docs/deployment.md`

## Tasks

### T1: System architecture
- **Goal:** D7 content is present, AS-IS, in Vietnamese prose with English technical terms.
- **Target files and symbols:** `docs/system-architecture.md`
- **Steps:**
  1. "Layer 4: Adapters": add `core/infra/exness/` (`signer`, `client`, `websocket`, `data_provider`, `quote_provider`, `broker`, `mappers`) and `core/infra/exchange_router.py`.
  2. Add a section `## Sync Policy Pattern` with a Mermaid v11 flowchart (tracked symbol → `policy_for` → `sync_runner` → `SyncService` → router → adapter → `bars`) and a table of `BINANCE_POLICY` vs `EXNESS_POLICY` fields.
  3. "Real-Time Streaming": the ticks path for Exness (bid as `last_price`, 500 ms throttle).
  4. "Broker & Middleware": `ExnessBroker` (lot conversion, SL required, max-lot and daily-cap guards, async fills via events WS, venue SL/TP exits publish `OrderFilledEvent`), the subscription `broker` field, and the async-fill wiring for non-paper brokers.
  5. "Where Does X Live?": rows for the sync policy, shared runner, Exness adapters and exchange router.
  6. "Known Limitations": the position-to-subscription link is lost on restart while an Exness position is open; swap/financing not modelled in PaperBroker; bid-only candles.
  7. Add a section `## Future Provider: MT5 (not built)`: same three ports; policy sketch (bar source `copy_rates_from`, live source `copy_ticks_from`, cascade off); needs a Windows host or a Wine/RPC bridge, which conflicts with the Linux VPS topology; Exness API keys are for platform accounts, not MT5 accounts.
- **Success criteria:** All sections exist with no changelog wording.
- **Verify:** `grep -cE "^## (Sync Policy Pattern|Future Provider: MT5)" docs/system-architecture.md` prints `2`. `grep -c "core/infra/exness" docs/system-architecture.md` prints a number ≥ 1. `grep -cE "Previously|no longer|Last Updated" docs/system-architecture.md` prints `0`.

### T2: Deployment env vars
- **Goal:** Operators know the Exness variables.
- **Target files and symbols:** `docs/deployment.md` env table
- **Steps:** Add rows for `EXNESS_ACCOUNT_ID`, `EXNESS_API_KEY`, `EXNESS_PRIVATE_KEY` / `EXNESS_PRIVATE_KEY_PATH`, `EXNESS_DISCOVERY_URL` (default `https://api.exness.com`), `EXNESS_MAX_LOTS` (unset = Exness orders rejected; kill switch), `EXNESS_DAILY_LOSS_CAP_PCT`. Required: No. Note that the values live only in `pocketquant-config`.
- **Success criteria:** 6 rows.
- **Verify:** `grep -cE "\`EXNESS_(ACCOUNT_ID|API_KEY|PRIVATE_KEY|DISCOVERY_URL|MAX_LOTS|DAILY_LOSS_CAP_PCT)" docs/deployment.md` prints a number ≥ 6.

### T3: Link check and release
- **Goal:** Docs are accurate and committed.
- **Target files and symbols:** the two docs
- **Steps:**
  1. For every code path named in the new text, `ls <path>` must succeed.
  2. Ask the user to approve the commit. Suggested message: `docs: Exness adapters, sync policy pattern and MT5 future provider`. Docs-only changes do not trigger CI (`paths-ignore`).
- **Success criteria:** The paths exist and the commit is made.
- **Verify:** `git log -1 --name-only --pretty=format:` lists only `docs/system-architecture.md` and `docs/deployment.md`, and each `ls` of a referenced path exits 0.

## Verification

D7 holds. The deployment doc lists the Exness env vars.

## Risks

Docs drift from code (low, low): T3 step 1 checks every referenced path.

## Security

The docs name variables only, never values.

## Rollback

Revert the docs commit.

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
