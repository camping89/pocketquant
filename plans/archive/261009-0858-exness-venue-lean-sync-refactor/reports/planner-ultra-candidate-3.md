<!-- FILE: plan.md -->
---
title: "Exness venue + lean sync-policy refactor"
description: "Refactor market-data sync into per-provider SyncPolicy + one runner (Binance proves it), rewrite the coding standard, then add Exness REST/WS data, quotes and broker as venue #3."
status: pending
priority: P1
effort: 27d work + 1 week live market observation
branch: master
tags: [exness, market-data, sync-policy, refactor, broker, code-standards]
blockedBy: []
blocks: []
created: 2026-10-09
---

# Exness venue + lean sync-policy refactor

## Overview
Exness becomes a third live venue behind the existing ports (`IDataProvider`, `IRealtimeQuoteProvider`, `IBroker`). Binance, OKX, PaperBroker, `hitnrun2` and `engulfing` all stay. First comes a read-only spike. Then the sync pipeline is refactored into one `SyncPolicy` per provider plus one shared runner, with Binance as the proving provider and characterization tests pinning its behaviour. Exness is added as policy #2. Validation follows (PaperBroker `spread`, backtests, a min-lot live round trip per strategy), then docs. MT5 is documented only. There is no MCP work and no deployment topology change.

## Goals
- G1: Exness works as a live venue (candles, ticks, orders, positions) through the same ports and strategies.
- G2: a provider is one adapter package plus one policy; a sync flow is readable in ≤3 files.
- G3: `docs/code-standards.md` matches the code. It is enforced by ruff, 3 import-linter contracts and a soft metric gate.

## Phases
| # | Phase | Effort | Depends on |
|---|-------|--------|-----------|
| 01 | [Exness read-only spike and user gate](./phase-01-exness-read-only-spike.md) | 1.5d | user preconditions |
| 02 | [Characterization tests, metric script, gate baseline](./phase-02-characterization-and-baseline.md) | 2d | 01 |
| 03 | [SyncPolicy and shared runner with Binance](./phase-03-sync-policy-runner-binance.md) | 5d | 02 |
| 04 | [Lean consolidation: DI, routes, wrappers, contracts](./phase-04-lean-consolidation.md) | 3d | 03 |
| 05 | [Coding standard rewrite and CI soft gate](./phase-05-coding-standard-rewrite.md) | 1d | 04 |
| 06 | [Exness signer, REST client, mappers](./phase-06-exness-signer-client.md) | 2.5d | 01, 05 |
| 07 | [Exness market data, quotes, sync policy](./phase-07-exness-market-data-policy.md) | 3.5d | 06 |
| 08 | [Exness broker and async fill wiring](./phase-08-exness-broker.md) | 3.5d | 07 |
| 09 | [Spread parameter, backfill, backtests](./phase-09-spread-backfill-backtests.md) | 2d | 08 |
| 10 | [Live min-lot round trip and week observation](./phase-10-live-validation.md) | 2d + 1 week | 09 |
| 11 | [Architecture and deployment docs, final gate](./phase-11-docs-final-gate.md) | 1d | 10 |

## Dependencies
- The phases run strictly in sequence on one branch per phase (`feat/exness-pNN-<slug>`). Each phase merges to `master` only after its gate is green and the user approves the push, because CI deploys `master`.
- No two phases run in parallel, so file ownership never overlaps.
- Phases 06 and later need the fixtures and numbers produced in Phase 01 (`reports/exness-spike-results.md`).
- Shell conventions used in every phase:
  - `BASE_SHA=$(sed -n 's/^BASE_SHA=//p' plans/261009-0858-exness-venue-lean-sync-refactor/reports/baseline-gates.md)`.
  - `ssh ...` means `ssh -i ../pocketquant-config/vps/default/id_rsa "$(cat ../pocketquant-config/vps/default/host)"`.
  - "Gate" means `just test` (Docker running), `uv run ruff check`, `uv run pyright` and `uv run lint-imports`.

## User preconditions (the executor gates on these and never performs them)
1. The user confirms that the Developer Portal link inside the Exness Personal Area resolves to `exness-api.com`. Phase 01 cannot start without this.
2. The user creates a scoped API key (one account, VPS IP allowlist) and stores `EXNESS_ACCOUNT_ID`, `EXNESS_API_KEY`, and `EXNESS_PRIVATE_KEY` or `EXNESS_PRIVATE_KEY_PATH` in `pocketquant-config/vps/default/.env`. Phase 01 needs these.
3. The user sets the live-test risk cap: `EXNESS_DAILY_LOSS_CAP_PCT`, `EXNESS_MAX_LOTS` (unset means instrument minimum lot only), and `EXNESS_LIVE_TRADING=true`. SL is always enforced in code. Phase 10 needs these.
The executor must never print, log or commit key material.

## Success criteria (D1-D7, advice section 9)
- D1: `POST /api/v1/market-data/sync` with `{"symbol":"XAUUSD:EXNESS","interval":"1m","n_bars":1000,"source":"bulk_sync_api"}` returns `status=completed` and `total_bars>=1000`. During market hours, the SSE bar stream for `XAUUSD%3AEXNESS` emits `"is_in_progress": true` within 60 s and the quote stream emits a quote.
- D2: one min-lot live order per strategy reaches `FILLED` via the events WS within 10 s of the ACK, appears in `GET /api/v1/trading/positions`, and closes by SL/TP.
- D3: `hitnrun2` (1m) and `engulfing` (1h) backtests on Exness bars finish in `backtest_runs` with a non-empty trades list. PaperBroker has a `spread` parameter.
- D4: `sync_internals/` is gone, `app/di` has 3 provider modules, market-data routes live in 2 files, and `scripts/code_metrics.py` reports tiny share ≤30% and pure delegations ≤20 (see question 1).
- D5: `docs/code-standards.md` is rewritten with no stale status claims, and `uv run lint-imports` reports exactly 3 contracts kept.
- D6: the Binance tests are unchanged and pass, and the OKX characterization tests pass. `just test`, ruff, pyright and lint-imports are green, and the CI deploy is green with `11-verify.sh` at 19/19.
- D7: `docs/system-architecture.md` shows the Exness adapters and the sync-policy pattern, and lists MT5 as a future provider.
- After one live week: no reconnect loops, zero `exness_ws.circuit_breaker_triggered` events, and no FX weekend integrity alarms.

## Unresolved questions (answer before Phase 04 ends)
1. Metric feasibility: with the exact metric reproduced (794 functions, 380 tiny (47.9%), 63 delegations), the named reductions are projected to reach about 41% tiny and about 45 delegations. Even after excluding ports, properties, routes and serializers, the baseline is still 42.7% and 43. Reaching ≤30% and ≤20 would mean inlining route handlers, ports or properties, which the advice warns is gaming. Phase 04 Task 04.9 stops and asks: (a) accept the measured numbers as the new soft thresholds, (b) authorize a listed extra inlining tranche, or (c) redefine the metric.
2. Live broker selection: subscriptions have no broker field today, and every live strategy runs on `paper`. This plan adds `EXNESS_LIVE_TRADING`, which maps `:EXNESS` symbols to the `exness` broker. Please confirm that is acceptable rather than a per-subscription broker field (which would be an API change).

<!-- FILE: phase-01-exness-read-only-spike.md -->
---
phase: 1
title: "Exness read-only spike and user gate"
status: pending
priority: P1
effort: 1.5d
dependencies: []
---

# Phase 01: Exness read-only spike and user gate

## Context Links
- Advice: `D:/w/_me/algotrading/plans/reports/advise-261008-1148-exness-api-replacement.md` (section 2 step 1; section 8)
- Spec: `https://www.exness-api.com/exness_api.yaml` (v1.0.2). Discovery doc: `https://www.exness-api.com/documentation/access-point-host-discovery` documents `GET https://api.exness.com/v1/trading/access-point?account_id={id}` (alternative host `https://api.exness-api.com`), with response `{"access_point": "<host>", "account_id": <id>}`.
- Deploy access: `docs/deployment.md` (lines 41-68): VPS host and key under `../pocketquant-config/vps/default/`; prod `.env` is synced from `pocketquant-config`; the container is `pocketquant-app`; `deploy/Dockerfile` copies `scripts/` into the image.

## Goal
One read-only script records the facts that settle assumptions A-i to A-v, produces the redacted fixtures the adapter tests use, and checks whether the confirmed Exness policy (WS ticks live plus REST native candles each minute, no cascade) is feasible. No `src/` file changes in this phase.

## Files to Create or Modify
- Create: `scripts/exness_spike.py`
- Create: `tests/core_test/infra/exness/__init__.py` (empty), `tests/core_test/infra/exness/fixtures/*.json` and `ticks_sample.jsonl` (spike output, redacted)
- Create: `plans/261009-0858-exness-venue-lean-sync-refactor/reports/exness-spike-results.md`

## Tasks

### Task 01.1: Gate on user preconditions
- **Goal:** the user has confirmed the portal domain and that the key exists in config.
- **Target files and symbols:** `reports/exness-spike-results.md` (section "Preconditions").
- **Steps:**
  1. Ask the user verbatim: "Does the Developer Portal link inside your Exness Personal Area resolve to exness-api.com, and have you added EXNESS_ACCOUNT_ID, EXNESS_API_KEY and EXNESS_PRIVATE_KEY (or EXNESS_PRIVATE_KEY_PATH) to pocketquant-config/vps/default/.env?"
  2. If either answer is no, STOP. This is a stop-and-ask condition: the portal link does not resolve to exness-api.com. Do not continue the phase.
  3. Create `reports/exness-spike-results.md` with a `## Preconditions` section that records the user's answer and the date. Do not record any key values.
- **Success criteria:** the results file exists and contains the user's "yes" for both questions.
- **Verify:** `grep -c "exness-api.com" plans/261009-0858-exness-venue-lean-sync-refactor/reports/exness-spike-results.md` prints a number ≥1.

### Task 01.2: Write the spike script
- **Goal:** `scripts/exness_spike.py` signs requests and performs the reads only.
- **Target files and symbols:** `scripts/exness_spike.py`, with functions `sign_headers(method, path, body, idempotency_key)`, `main(argv)`, and a module-level `SpikeSettings(BaseSettings)` reading `EXNESS_ACCOUNT_ID`, `EXNESS_API_KEY`, `EXNESS_PRIVATE_KEY`, `EXNESS_PRIVATE_KEY_PATH`, `EXNESS_DISCOVERY_URL` (default `https://api.exness.com`) from env or `.env` with `extra="ignore"`.
- **Steps:**
  1. Build signing exactly as the spec header text says. The payload is the dict `{"api_key","idempotency_key","timestamp","sign_version":1,"method","path","body_hash"}`. `body_hash` is base64url without padding of SHA-256(body bytes); an empty body gives `47DEQpj8HBSa-_TImW-5JCeuQeRkm5NMpJWZG3hSuFU`. `EXN-DATA` is base64url without padding of `json.dumps(payload, separators=(",", ":"))` bytes. `EXN-SIGN` is base64url without padding of the Ed25519 signature over those same bytes. Send headers `EXN-API-KEY`, `EXN-IDEMPOTENCY-KEY` (empty for GET), `EXN-TIMESTAMP` (ms), `EXN-SIGN-VERSION: 1`, `EXN-DATA`, `EXN-SIGN`. Build `path` including the query string with `urllib.parse.urlencode` and request that exact string; do not pass `params=` to httpx.
  2. Load the key with `cryptography.hazmat.primitives.asymmetric.ed25519`. If the value starts with `-----BEGIN`, use `serialization.load_pem_private_key(..., password=None)`. Otherwise decode base64url, base64 or hex to 32 bytes and use `Ed25519PrivateKey.from_private_bytes`. Record which format worked as `key_format`.
  3. Clock offset: on each response, parse the `Date` header and store `offset_ms = server - local`. Sign later requests with `local_ms + offset_ms`.
  4. Read sequence: access point (`GET {discovery}/v1/trading/access-point?account_id={id}`, with base `https://{access_point}`); `GET /v1/configuration/accounts/{id}/limits`; `/instruments`; `/instruments/{name}/conditions` for XAUUSD, EURUSD and BTCUSD (resolve exact names case-insensitively from `/instruments`); `/account`; `GET /v1/trading/accounts/{id}/snapshot`; candles XAUUSD M1 `from=<now ISO>&count=-N`, where N = min(1000, `max_candles_per_request` of `getCandleHistory`); candles XAUUSD M5, M15, H1, H4 and D1 with `count=-10`.
  5. Ticks WS: connect to `wss://{access_point}/v1/server-events/accounts/{id}/ws/ticks` using signed GET headers (path signed exactly) as `additional_headers`. First try `subprotocols=["exness-ws-protocol"]`, and on handshake failure retry without it. Record `ws_subprotocol_required`. Use `websockets.connect(..., ping_interval=20, ping_timeout=10)`. Send `{"id":"ticks-1","subscribe":{"event":"ticks","instruments":[<3 names>]}}` and keep the connection open for `--ticks-minutes` (default 10). Record per-instrument tick count, median inter-tick ms, median `ask-bid`, whether the socket stayed open for the whole window, and the first 50 frames.
  6. Events WS: connect to `/v1/server-events/accounts/{id}/ws/events`, send `{"id":"tx-1","subscribe":{"event":"transactions"}}`, save the first message (`trading_state_snapshot`), then close.
  7. Derived checks, printed as a Markdown summary to stdout:
     - Alignment: every candle `time` satisfies `pocketquant.core.domain.bar.services.bar_builder.is_bar_aligned` for its interval.
     - `last_candle_in_progress`: the last candle `time + duration > now`.
     - Feasibility: `need_per_min = 3 instruments × 6 timeframes = 18`. `have_per_min = getCandleHistory limit × 60 / window_seconds`. Feasible when `have_per_min ≥ 36` AND global `global_account_rate` gives ≥36/min AND `websocket.max_active_connections ≥ 2`.
     - `rate_budget_per_poll = floor(have_per_min / 2)`.
     - `closed_windows`: the complement of the union of each instrument's `trade_sessions` (`week_start_time`/`week_end_time`, format `"Mon, 10:00:00"`, UTC), each closed window widened by 60 minutes on both sides. Print them as Python literal tuples `((weekday, hour, minute), (weekday, hour, minute))` with Monday=0.
  8. Writes: `--out DIR` receives `access_point.json`, `limits.json`, `instruments.json`, `conditions_<NAME>.json`, `account.json`, `snapshot.json`, `candles_XAUUSD_M1.json`, `candles_XAUUSD_<TF>.json`, `events_first_message.json` and `ticks_sample.jsonl`. Before writing, replace every occurrence of the account id string with `ACCOUNT_ID`. Never write or print headers, the API key or the private key.
  9. The script performs no POST, PATCH or DELETE.
- **Success criteria:** the script parses and has no mutating calls.
- **Verify:** `uv run python -c "import ast,sys;t=open('scripts/exness_spike.py',encoding='utf-8').read();ast.parse(t);sys.exit(1 if any(s in t for s in ('.post(','.patch(','.delete(','\"POST\"','\"DELETE\"','\"PATCH\"')) else 0)"` exits 0.

### Task 01.3: Run the spike on the VPS (key is IP-allowlisted to the VPS)
- **Goal:** fixtures and the numbers are captured from the allowlisted host.
- **Target files and symbols:** `tests/core_test/infra/exness/fixtures/`, `reports/exness-spike-results.md`.
- **Steps:**
  1. Commit `scripts/exness_spike.py` on branch `feat/exness-p01-spike` with the message `chore(scripts): add read-only exness api spike`. Ask the user to approve merging to `master` (CI deploys it). STOP until the user approves.
  2. After the deploy succeeds, run `HOST="$(cat ../pocketquant-config/vps/default/host)"; KEY="../pocketquant-config/vps/default/id_rsa"; ssh -i "$KEY" "$HOST" 'docker exec pocketquant-app python scripts/exness_spike.py --out /tmp/exness-spike --ticks-minutes 10' > /tmp/spike-summary.md`.
  3. Run `ssh -i "$KEY" "$HOST" 'rm -rf /tmp/exness-spike && docker cp pocketquant-app:/tmp/exness-spike /tmp/exness-spike'`, then `scp -i "$KEY" -r "$HOST:/tmp/exness-spike/*" tests/core_test/infra/exness/fixtures/`.
  4. Append `/tmp/spike-summary.md` to `reports/exness-spike-results.md` under `## Measured values`.
  5. On a Saturday (UTC), run step 2 again with `--ticks-minutes 10` and append the BTCUSD weekend tick count under `## Weekend observation`. If Phase 07 starts before Saturday, record `pending` there. Phase 10 completes it.
- **Success criteria:** the fixtures exist, they contain no secrets, and the results file holds every value listed in Task 01.2 step 7.
- **Verify:** all of the following:
  - `ls tests/core_test/infra/exness/fixtures/limits.json tests/core_test/infra/exness/fixtures/candles_XAUUSD_M1.json tests/core_test/infra/exness/fixtures/ticks_sample.jsonl` exits 0.
  - `ssh -i "$KEY" "$HOST" 'docker exec pocketquant-app sh -c "grep -rqF \"\$EXNESS_API_KEY\" /tmp/exness-spike; echo \$?"'` prints `1`.
  - `ssh -i "$KEY" "$HOST" 'docker exec pocketquant-app sh -c "grep -rqF \"\$EXNESS_ACCOUNT_ID\" /tmp/exness-spike; echo \$?"'` prints `1`.
  - `grep -c "feasible\|closed_windows\|rate_budget_per_poll\|key_format\|ws_subprotocol_required" plans/261009-0858-exness-venue-lean-sync-refactor/reports/exness-spike-results.md` prints ≥5.

### Task 01.4: Feasibility and assumption gate
- **Goal:** decide whether the confirmed policy and instruments hold.
- **Target files and symbols:** `reports/exness-spike-results.md`, section `## Gate`.
- **Steps:**
  1. If `feasible` is false, STOP and ask the user. This is the stop condition "Exness limits make policy A-v infeasible". Quote `have_per_min`, the global rate and `max_active_connections`.
  2. If any of XAUUSD, EURUSD or BTCUSD is missing from `/instruments`, STOP and ask the user (A-i cannot hold).
  3. If any alignment check failed, write `alignment=failed` with the failing timeframe and STOP and ask the user. Misaligned native candles would be dropped by the sync filter.
  4. Otherwise write `## Gate` with `PASS`. Under it, record the exact instrument names, `contract_size`, `volume_min`/`volume_step`/`volume_max`, `point_digits`, median spread per instrument, `rate_budget_per_poll`, `closed_windows` literals, `key_format`, `ws_subprotocol_required`, and `last_candle_in_progress`.
- **Success criteria:** the gate reads `PASS` with all values present.
- **Verify:** `grep -c "^PASS" plans/261009-0858-exness-venue-lean-sync-refactor/reports/exness-spike-results.md` prints `1`.

### Task 01.5: Commit fixtures
- **Goal:** the redacted fixtures are versioned for the adapter tests.
- **Target files and symbols:** `tests/core_test/infra/exness/__init__.py`, `tests/core_test/infra/exness/fixtures/`.
- **Steps:** create the empty `__init__.py`, then commit with the message `test(exness): add redacted api fixtures from read-only spike`.
- **Success criteria:** `git status --short tests/core_test/infra/exness` is empty after the commit.
- **Verify:** `git log -1 --name-only | grep -c "tests/core_test/infra/exness/fixtures/"` prints ≥10.

## Verification (phase gate)
- `uv run ruff check scripts/exness_spike.py` exits 0.
- `just test` exits 0. No `src/` changes, so this only confirms the fixture files do not break collection.

## Risks
- Spike numbers (e.g. weekend BTCUSD) arrive late (likelihood medium, impact low). `trade_sessions` remains the authoritative calendar, and the weekend observation only confirms it.
- The key leaks into a fixture (likelihood low, impact high). Redaction runs before any write, and the grep checks above must print `1`.

## Security
- The script never echoes headers or keys. All SSH commands quote remote expansions so secrets expand only inside the container.

## Rollback
- Revert the spike commit (`git revert <sha>`). Nothing in `src/` changed, and no data was written to Mongo or Exness.

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

<!-- FILE: phase-02-characterization-and-baseline.md -->
---
phase: 2
title: "Characterization tests, metric script, gate baseline"
status: pending
priority: P1
effort: 2d
dependencies: [1]
---

# Phase 02: Characterization tests, metric script, gate baseline

## Context Links
- Sync jobs and registrations: `src/pocketquant/engine/market_data/app_services/sync_jobs.py:382` (`sync_1m`), `:511` (`sync_verify_cascade`), `:609-618` (backfill/integrity/repair), `:663` (`register_sync_jobs`), `:72` (`CATCHUP_TARGETS`)
- Test app factory: `tests/app_test/integration/app_factory.py:66` (`make_test_app`), `tests/app_test/integration/conftest.py:20` (`app_client`), `tests/app_test/conftest.py:16` (`settings`, `enable_jobs=False`)
- Scheduler API (stable): `src/pocketquant/core/infra/scheduling/scheduler.py:56` (`initialize`), `:83` (`start`), `:141` (`shutdown`), `:192` (`add_cron_job`), `:258` (`add_one_off_job`)
- Binance adapter (stable seam): `src/pocketquant/core/infra/binance/binance_client.py:50` (`BinanceClient.fetch_ohlcv`)
- OKX surfaces: `src/pocketquant/core/infra/brokers/okx/okx_broker.py:335` (`_handle_ws_message`), `okx_mapper.py:32` (`map_order_to_okx_params`), `:63`, `:108`; `src/pocketquant/app/di/broker_factory.py:18` (`BrokerFactory.create`)

## Goal
Before any refactor, pin the behaviour that the refactor must keep, measure the metric baseline with an exact and reproducible definition, and make the four gates green.

## Files to Create or Modify
- Create: `scripts/code_metrics.py`, `tests/scripts/test_code_metrics.py`
- Create: `tests/app_test/integration/test_sync_pipeline_characterization.py`, `tests/app_test/integration/golden/sync_jobs.json`, `tests/app_test/integration/golden/sync_api.json`
- Create: `tests/core_test/infra/brokers/test_okx_characterization.py`
- Create: `plans/261009-0858-exness-venue-lean-sync-refactor/reports/baseline-gates.md`
- Modify: `pyproject.toml`, `uv.lock` (dev dependency `freezegun`)
- Modify (pre-existing gate failures only): `tests/app_test/unit/market_data/test_quote_app_service.py`, `tests/backtest_test/engine/test_lot_tracker.py`, `tests/core_test/unit/common/test_event_bus.py`, `tests/core_test/unit/domain/sync_status/sync_progress_tracker_test.py` (ruff I001), and `tests/core_test/unit/domain/strategy/test_engulfing.py:173` (pyright `reportOptionalOperand`)

## Tasks

### Task 02.1: Record BASE_SHA and fix the pre-existing gate failures
- **Goal:** all four gates exit 0 on an unchanged `src/`.
- **Target files and symbols:** the five test files above; `reports/baseline-gates.md`.
- **Steps:**
  1. Create branch `feat/exness-p02-characterization`. Write `BASE_SHA=<output of git rev-parse HEAD>` as the first line of `reports/baseline-gates.md`.
  2. Run `uv run ruff check --fix tests/app_test/unit/market_data/test_quote_app_service.py tests/backtest_test/engine/test_lot_tracker.py tests/core_test/unit/common/test_event_bus.py tests/core_test/unit/domain/sync_status/sync_progress_tracker_test.py`.
  3. In `tests/core_test/unit/domain/strategy/test_engulfing.py`, insert `    assert sig.take_profit_price is not None` as a new line directly before the line `    assert sig.take_profit_price < entry  # TP below entry for a short`.
- **Success criteria:** ruff and pyright are clean.
- **Verify:** `uv run ruff check` exits 0 and `uv run pyright` prints `0 errors`.

### Task 02.2: Metric script with the exact definition
- **Goal:** `scripts/code_metrics.py` reproduces the advice baseline numbers exactly.
- **Target files and symbols:** `scripts/code_metrics.py` with `measure(root: Path) -> dict` and `main(argv=None) -> int`; `tests/scripts/test_code_metrics.py`.
- **Steps:**
  1. Definitions, over every `*.py` under `--root` (default `src/pocketquant`), visiting all `FunctionDef` and `AsyncFunctionDef` nodes via `ast.walk` (nested functions included):
     - `body` = the node body with a leading string-constant docstring statement removed.
     - **tiny**: `len(body) <= 2` AND the name is not a dunder (it does not both start and end with `__`).
     - **pure delegation**: `len(body) == 1`, that statement is a `Return` or an `Expr`, its value (after unwrapping one `Await`) is a `Call`, and the call's `func` is an `ast.Attribute`.
     - **long**: `end_lineno - lineno + 1 > 60`.
  2. Output lines, exactly: `functions_total=<n>`, `tiny_functions=<n>`, `tiny_share=<x.x>%`, `pure_delegations=<n>`, `long_functions=<n>`, then `thresholds tiny_share<=30.0% pure_delegations<=20`.
  3. `--list` also prints `TINY path:line:name`, `DELEGATION path:line:name` and `LONG path:line:name lines=<n>`. `path` is relative to `--root` and uses forward slashes, for example `engine/market_data/sync_runner.py`.
  4. Exit 0 always, unless `--strict` is passed and a threshold is exceeded (then exit 1). When env `GITHUB_ACTIONS=true` and a threshold is exceeded, also print `::warning title=code_metrics::tiny_share=<x>% pure_delegations=<n>`.
  5. The test builds a tmp tree with one tiny function, one delegation (`return self.x.y()`), one dunder and one 61-line function, and asserts the counts 4/2/1/1.
- **Success criteria:** the numbers match the advice baseline on BASE_SHA.
- **Verify:** `uv run python scripts/code_metrics.py` prints exactly `functions_total=794`, `tiny_functions=380`, `tiny_share=47.9%`, `pure_delegations=63` and `long_functions=22`; `uv run pytest tests/scripts/test_code_metrics.py -q` exits 0.

### Task 02.3: Freeze-time test dependency
- **Goal:** time-dependent golden tests are deterministic.
- **Target files and symbols:** `pyproject.toml` `[dependency-groups].dev`, `uv.lock`.
- **Steps:** run `uv add --dev "freezegun>=1.5"`.
- **Success criteria:** freezegun imports.
- **Verify:** `uv run python -c "import freezegun, inspect; assert 'real_asyncio' in inspect.signature(freezegun.freeze_time).parameters"` exits 0.

### Task 02.4: Golden characterization of the scheduled sync jobs
- **Goal:** one golden file pins what the five jobs write for the Binance-backed pipeline, including the current behaviour where `:OKX` symbols fall back to Binance data.
- **Target files and symbols:** `tests/app_test/integration/test_sync_pipeline_characterization.py::test_sync_jobs_golden`; `tests/app_test/integration/golden/sync_jobs.json`.
- **Steps:**
  1. Fixture `jobs_settings` = `settings.model_copy(update={"enable_jobs": True})`.
  2. Monkeypatch these JobScheduler methods (stable API):
     - `JobScheduler.initialize`, `JobScheduler.start` and `JobScheduler.shutdown` → no-ops.
     - `JobScheduler.add_cron_job(self, func, *, job_id, cron_expression=None, hour=None, minute=None, second=None, day_of_week=None, misfire_grace_time=None, **kwargs)` → append `{"func": func, "job_id": job_id, "cron_expression": cron_expression, "hour": hour, "minute": minute, "second": second, "day_of_week": day_of_week, "misfire_grace_time": misfire_grace_time, "kwargs": kwargs}` to a list and return `job_id`.
     - `JobScheduler.add_one_off_job` → record the same way.
  3. Monkeypatch `BinanceClient.fetch_ohlcv` with `fake_fetch(self, symbol, interval, n_bars=1000)`:
     - Record `(symbol.upper(), interval.value, n_bars)`.
     - Return `k = min(n_bars, 600)` ascending closed bars. With `d` = `INTERVAL_SECONDS[interval.value]`, `last = get_bar_start(now, interval) - timedelta(seconds=d)` (using `pocketquant.core.domain.bar.services.bar_builder.get_bar_start`), start of bar i = `last - (k-1-i)*d`.
     - Bar values: `base = (int(start.timestamp()) // 60) % 1000`, `open=1000.0+base`, `high=open+2`, `low=open-1`, `close=open+1`, `volume=1.0+base%7`, `tick_count=1`, `symbol=symbol.upper()`, `interval=interval`.
  4. Inside `freezegun.freeze_time("2026-01-07T04:01:30+00:00", tick=True, real_asyncio=True)`, run:
     - `app = make_test_app(jobs_settings)`, then `async with app.router.lifespan_context(app):`
     - Upsert tracked symbols `BTCUSDT:BINANCE` and `ETHUSDT:OKX` through `TrackedSymbolRepository.upsert(TrackedSymbol(symbol=...))` (resolve the repo with `await app.state.dishka_container.get(TrackedSymbolRepository)`).
     - The lifespan already called `start_background_jobs`, so the recorder holds the five cron registrations. Registration does not depend on tracked symbols.
     - For job ids in the order `sync_1m`, `sync_verify_cascade`, `sync_backfill`, `sync_integrity`, `sync_repair`: take the recorded entry with that `job_id`, resolve it with `apscheduler.util.ref_to_obj(entry["func"])`, and `await fn(**entry["kwargs"])`.
  5. Build the normalized snapshot:
     - `registrations`: the recorded cron entries sorted by `job_id`, without `func` and `kwargs`.
     - `provider_calls`: sorted list of `[symbol, interval, n_bars, count]`.
     - `bars`: for each `(symbol, interval)` in the `bars` collection, sorted, give `count`, `first`, `last` (ISO) and `digest` = sha256 of `"\n".join(f"{dt.isoformat()},{open},{high},{low},{close},{volume},{source}")` sorted by dt.
     - `job_history`: per `job_id`, `status`, `total_inserted`, `total_fetched` and `details` sorted by `(symbol, interval)` with keys `symbol, interval, bars_fetched, bars_inserted, filtered_existing, filtered_misaligned, status`.
     - `sync_status`: per `(symbol, interval)`, `status`, `bar_count`, `consecutive_empty_fetches`, `error_message`.
  6. If env `CHAR_UPDATE=1`, write the snapshot to the golden file (`json.dumps(..., sort_keys=True, indent=2)`). Then assert it equals the golden file content.
  7. Generate the golden on BASE_SHA code with `CHAR_UPDATE=1 uv run pytest tests/app_test/integration/test_sync_pipeline_characterization.py -q`.
- **Success criteria:** the golden file exists and the test passes twice in a row without `CHAR_UPDATE`.
- **Verify:** `uv run pytest tests/app_test/integration/test_sync_pipeline_characterization.py -q` exits 0 on two consecutive runs; `uv run python -c "import json;d=json.load(open('tests/app_test/integration/golden/sync_jobs.json'));assert {r['job_id'] for r in d['registrations']}=={'sync_1m','sync_verify_cascade','sync_backfill','sync_integrity','sync_repair'};assert any(b[0]=='ETHUSDT:OKX' for b in d['provider_calls'])"` exits 0.

### Task 02.5: Golden characterization of the sync-related HTTP routes
- **Goal:** pin the responses of every route the refactor touches.
- **Target files and symbols:** `test_sync_pipeline_characterization.py::test_sync_api_golden`; `golden/sync_api.json`.
- **Steps:**
  1. Use the same frozen time and the same fake fetch. Use `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")` inside the lifespan, as in `tests/app_test/integration/conftest.py:20-27`.
  2. Call in order and record `[status_code, json]`:
     - `POST /api/v1/market-data/sync` with `{"symbol":"BTCUSDT:BINANCE","interval":"5m","n_bars":50,"source":"bulk_sync_api"}`
     - `POST /api/v1/market-data/sync/bulk` with `{"symbols":["BTCUSDT:BINANCE","ETHUSDT:OKX"],"interval":"1h","n_bars":20}`
     - `POST /api/v1/market-data/integrity/check` with `{"symbol":"BTCUSDT:BINANCE","interval":"5m","days_back":1}`
     - `POST /api/v1/market-data/integrity/repair` with the same body
     - `POST /api/v1/market-data/tracked-symbols/BTCUSDT%3ABINANCE/backfill?interval=15m&n=8&mode=auto`
     - `GET /api/v1/market-data/sync-status`
  3. Normalize: delete the keys `last_sync_at` and `misaligned_ids` wherever they appear (replace `misaligned_ids` with its length under `misaligned_ids_len`). Then golden-compare with the same `CHAR_UPDATE` rule.
- **Success criteria:** the golden file exists and the test passes without the update flag.
- **Verify:** `uv run pytest "tests/app_test/integration/test_sync_pipeline_characterization.py::test_sync_api_golden" -q` exits 0.

### Task 02.6: OKX characterization (no OKX tests exist today)
- **Goal:** pin OKX behaviour on surfaces the refactor must not change.
- **Target files and symbols:** `tests/core_test/infra/brokers/test_okx_characterization.py`.
- **Steps:**
  1. `BrokerFactory(EventBus()).create("okx", {"api_key":"k","api_secret":"s","passphrase":"p"})` returns an `OKXBroker` with `name == "okx-demo"`. `create("okx", {})` raises `ValueError`. `create("nope", {})` raises `ValueError`.
  2. `map_order_to_okx_params(OrderAggregate.create(subscription_id="s1", symbol="BTC", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=0.5, price=100.0))` equals a literal dict captured from the current code. Capture it once by printing it in a REPL and paste it as the expected value. Do the same for one LIMIT order.
  3. `OKXBroker._handle_ws_message` with an orders-channel message of state `filled` delivered twice results in exactly one callback, with `OrderResult.status == OrderStatus.FILLED`. A positions-channel message results in zero callbacks. Build the messages as `{"arg":{"channel":"orders"},"data":[{...}]}` with keys `ordId, clOrdId, state, instId, side, accFillSz, avgPx`; capture the resulting `OrderResult` fields from current code and assert them literally.
  4. `map_okx_position_to_domain` and `map_okx_balance_to_domain` on one sample payload each equal literal captured values.
- **Success criteria:** the test passes on BASE_SHA code.
- **Verify:** `uv run pytest tests/core_test/infra/brokers/test_okx_characterization.py -q` exits 0 with at least `5 passed`.

### Task 02.7: Record the gate baseline
- **Goal:** baseline numbers exist for later comparison.
- **Target files and symbols:** `reports/baseline-gates.md`.
- **Steps:**
  1. Append the last line of `just test` (for example `N passed, M skipped in Xs`).
  2. Append the last line of `uv run pytest tests/core_test/infra/binance -q`.
  3. Append the last line of `uv run pytest tests/core_test/infra/brokers/test_okx_characterization.py -q`.
  4. Append the full `uv run python scripts/code_metrics.py` output and `uv run lint-imports | tail -1`.
  5. Commit with `test: pin sync pipeline, sync routes and okx behaviour before refactor`.
- **Success criteria:** the file has six labelled lines after `BASE_SHA`.
- **Verify:** `grep -c "passed\|functions_total\|Contracts:" plans/261009-0858-exness-venue-lean-sync-refactor/reports/baseline-gates.md` prints ≥5.

## Verification (phase gate)
- `just test` exits 0. `uv run ruff check` exits 0. `uv run pyright` prints `0 errors`. `uv run lint-imports` prints `Contracts: 7 kept, 0 broken.`
- `git diff --quiet $BASE_SHA -- src` exits 0 (no production change in this phase).

## Risks
- freezegun interacts badly with the pymongo or asyncio clocks (medium likelihood, medium impact). `real_asyncio=True` and `tick=True` are set. If the tests hang, the Failure Protocol applies.
- Golden tests are flaky across runs (low likelihood, high impact). The Verify step runs them twice, and all collections are sorted.

## Rollback
- Revert the phase commits. Only tests, scripts and the lockfile changed.

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

<!-- FILE: phase-03-sync-policy-runner-binance.md -->
---
phase: 3
title: "SyncPolicy and shared runner with Binance"
status: pending
priority: P1
effort: 5d
dependencies: [2]
---

# Phase 03: SyncPolicy and shared runner with Binance

## Context Links
- Current pipeline:
  - `src/pocketquant/engine/market_data/app_services/sync_jobs.py` (729 LOC: `_sync_by_intervals:130`, `_run_sync:234`, `_run_integrity:285`, `_run_repair:329`, `sync_1m:382`, `_verify_one_symbol:454`, `sync_verify_cascade:511`, `enqueue_missed_catchups:621`, `register_sync_jobs:663`)
  - `cascade_aggregator.py` (`CASCADE_TFS:32`, `tf_seconds:50`, `aggregate_ohlcv:70`, `compute_boundaries:98`, `cascade_for_symbol:140`)
  - `integrity_jobs.py` (`check_integrity:268`, `repair_integrity:311`)
  - `src/pocketquant/engine/market_data/sync_service.py` (`SyncService:33`, `sync_one:48`)
  - `sync_internals/` (`anomaly_log.py`, `bar_alignment.py`, `bar_filters.py`, `provider_fetch.py`, `responses.py`, `__init__.py`)
  - `sync_dtos.py`
- Single-provider wiring today: `src/pocketquant/app/di/infrastructure.py:30` (`get_data_provider` returns `BinanceClient`), `src/pocketquant/app/di/market_data.py:31` (`get_realtime_quote_provider`), `src/pocketquant/app/market_data/app_services/quote_app_service.py:95` (`start`), `ws_subscription_manager.py:165` (`_reconcile`), `src/pocketquant/app/main_extensions.py:187` (`start_quote_feed`), `:204` (`stop_quote_feed`), `src/pocketquant/app/main.py:31` (`set_sync_container` import)
- Other provider consumer: `src/pocketquant/engine/market_data/tracked_symbols_backfill.py:85` (`TrackedSymbolBackfillService.__init__`)
- APScheduler text refs persist in Mongo `apscheduler_jobs`. `add_cron_job` uses `replace_existing=True` (`scheduler.py:237-245`), and job kwargs pass through `**kwargs`.

## Goal
One `SyncPolicy` per provider plus one runner execute `fetch → align → persist → cascade? → integrity → repair`. Binance is policy #1 and reproduces today's behaviour byte-for-byte, as proven by the unchanged Phase 02 golden tests. The job modules, `sync_internals/` and `sync_dtos.py` are deleted.

## Files to Create or Modify
- Create: `src/pocketquant/engine/market_data/sync_policy.py`, `src/pocketquant/engine/market_data/sync_runner.py`, `tests/engine_test/market_data/test_sync_policy.py`
- Modify: `src/pocketquant/engine/market_data/sync_service.py`, `src/pocketquant/engine/market_data/tracked_symbols_backfill.py`, `src/pocketquant/app/routes/integrity.py`, `src/pocketquant/app/routes/market_data_sync.py`, `src/pocketquant/app/main.py`, `src/pocketquant/app/main_extensions.py`, `src/pocketquant/app/di/infrastructure.py`, `src/pocketquant/app/di/market_data.py`, `src/pocketquant/app/market_data/app_services/quote_app_service.py`, `src/pocketquant/app/market_data/app_services/ws_subscription_manager.py`, `src/pocketquant/core/infra/scheduling/scheduler.py` (docstring reference to `sync_jobs.py` only), `src/pocketquant/core/infra/persistence/repositories/job_history_repository.py` (docstring references only)
- Delete: `src/pocketquant/engine/market_data/app_services/sync_jobs.py`, `.../app_services/integrity_jobs.py`, `.../app_services/cascade_aggregator.py`, `src/pocketquant/engine/market_data/sync_internals/` (all 6 files), `src/pocketquant/engine/market_data/sync_dtos.py`
- Modify tests (import paths, constructor and call-site edits only; assertion intent kept):
  - `tests/app_test/integration/app_factory.py`
  - `tests/app_test/integration/test_sync_backfill_gap_fill.py`
  - `tests/app_test/market_data/test_cascade_aggregator.py`
  - `tests/app_test/market_data/test_cascade_aggregator_source.py`
  - `tests/app_test/market_data/test_integrity_jobs_repair_source.py`
  - `tests/app_test/market_data/test_sync_jobs_source_labels.py`
  - `tests/app_test/test_sync_jobs_phase.py`
  - `tests/app_test/unit/handlers/sync/conftest.py`
  - `tests/app_test/unit/handlers/sync/test_bar_filters.py`
  - `tests/app_test/unit/handlers/sync/test_provider_fetch.py`
  - `tests/app_test/unit/handlers/sync/test_no_progress_tracking.py`
  - `tests/app_test/unit/handlers/sync/test_sync_symbol_command_source.py`
  - `tests/app_test/unit/market_data/test_sync_jobs_catchup.py`
  - `tests/app_test/unit/market_data/test_sync_verify_cascade.py`
  - `tests/app_test/unit/market_data/test_quote_app_service.py`
  - `tests/app_test/unit/di/test_di_data_provider.py`
  - `tests/engine_test/market_data/test_sync_service.py`
- MUST NOT modify: `tests/app_test/integration/test_sync_pipeline_characterization.py`, `tests/app_test/integration/golden/*.json`, `tests/core_test/infra/binance/*`, `tests/core_test/infra/brokers/test_okx_characterization.py`, `tests/baseline/*.json`

## Data flow (target)
```
APScheduler ──text ref "…sync_runner:run_sync_job" + kwargs{job}──► run_sync_job(job)
  ├─ deps: SyncPolicies, SyncService, TrackedSymbolRepository, BarRepository, JobHistoryRepository
  ├─ tracked symbols ──policies.group(symbols)──► [(policy, symbols)]
  ├─ sync_1m:      per policy → (skip closed/budget) → SyncService.sync_one(sym, iv, poll_n_bars) → cascade if policy.cascade_intervals
  ├─ backfill:     per policy → history_intervals × policy.backfill_bars(iv)
  ├─ verify:       cascade policies only → policy.bar_source.fetch_ohlcv(5m,12) vs DB
  ├─ integrity:    SyncService.check_integrity (expected grid minus policy.is_closed)
  └─ repair:       SyncService.repair_integrity
HTTP POST /sync → route → SyncService.sync_one → policy.bar_source (by exchange suffix, fallback BINANCE)
WsSubscriptionManager → policies.for_symbol(sym).live_source.subscribe(...) → QuoteAppService.on_quote_update
```

## Tasks

### Task 03.1: `sync_policy.py`
- **Goal:** declarative policy types with Binance's policy equal to today's constants.
- **Target files and symbols:** `src/pocketquant/engine/market_data/sync_policy.py` with `WeeklyWindow`, `SyncPolicy`, `SyncPolicies`, `CASCADE_TFS`, `binance_policy(bar_source, live_source)`; `tests/engine_test/market_data/test_sync_policy.py`.
- **Steps:**
  1. `@dataclass(frozen=True) class WeeklyWindow: start: tuple[int,int,int]; end: tuple[int,int,int]`, where tuples are (weekday Mon=0, hour, minute) in UTC. Add `def contains(self, ts: datetime) -> bool`, which converts ts to minutes-of-week and handles a window that wraps past Sunday.
  2. `@dataclass(frozen=True) class SyncPolicy` with fields, in this order:
     - `exchange: str`, `bar_source: IDataProvider`, `live_source: IRealtimeQuoteProvider`
     - `poll_intervals: tuple[Interval, ...]`, `cascade_intervals: tuple[Interval, ...]`, `history_intervals: tuple[Interval, ...]`
     - `poll_every_minutes: int = 1`, `poll_n_bars: int = 100`, `rate_budget_per_poll: int = 300`
     - `backfill_n_bars: Mapping[Interval, int] = field(default_factory=dict)` (missing key = 5000)
     - `history_depth_days: Mapping[Interval, int] = field(default_factory=dict)` (missing = unbounded)
     - `closed_windows: Mapping[str, tuple[WeeklyWindow, ...]] = field(default_factory=dict)`, keyed by symbol code (missing = 24x7)
  3. Methods:
     - `is_closed(self, symbol: str, ts: datetime) -> bool`: code = `symbol.split(":")[0].upper()`; true if any window for the code contains ts.
     - `backfill_bars(self, interval) -> int`: `n = backfill_n_bars.get(interval, 5000)`; if `interval in history_depth_days`, `n = min(n, history_depth_days[interval] * 86400 // INTERVAL_SECONDS[interval.value])`.
  4. `@dataclass(frozen=True) class SyncPolicies: policies: tuple[SyncPolicy, ...]; fallback: str = "BINANCE"` with:
     - `for_symbol(symbol)`: exchange = `symbol.rsplit(":", 1)[-1].upper()`; return the matching policy, else the policy whose exchange == fallback.
     - `group(symbols) -> list[tuple[SyncPolicy, list[str]]]`: preserves the input order of symbols within each group and the order of `policies`.
  5. `CASCADE_TFS = (Interval.MINUTE_5, Interval.MINUTE_15, Interval.HOUR_1, Interval.HOUR_4, Interval.DAY_1)`.
  6. `binance_policy(bar_source, live_source)` returns `SyncPolicy(exchange="BINANCE", bar_source=bar_source, live_source=live_source, poll_intervals=(Interval.MINUTE_1,), cascade_intervals=CASCADE_TFS, history_intervals=(MINUTE_1, MINUTE_5, MINUTE_15, HOUR_1, HOUR_4, DAY_1, WEEK_1))` with every other field at its default.
  7. Tests cover:
     - `for_symbol("ETHUSDT:OKX")` returns the BINANCE policy (fallback).
     - `group` order.
     - `WeeklyWindow(((4,21,0)),((6,21,5)))` contains Saturday 12:00 and does not contain Monday 00:00.
     - A wrapping window works.
     - `backfill_bars` clamps with a depth of `{Interval.MINUTE_1: 1}` to `1440`.
- **Success criteria:** the module imports only `core.domain` and the stdlib; the tests pass.
- **Verify:** `uv run pytest tests/engine_test/market_data/test_sync_policy.py -q` exits 0.

### Task 03.2: Fold `sync_internals/`, `sync_dtos.py` and integrity into `sync_service.py`
- **Goal:** the per-symbol sync, filters, retry, anomaly log, DTOs and integrity check/repair live in one file, routed by policy.
- **Target files and symbols:** `src/pocketquant/engine/market_data/sync_service.py`:
  - Module functions: `fetch_with_retry`, `filter_new_bars`, `drop_misaligned_bars`, `emit_no_progress` (same names and signatures as today), plus constants `_BACKOFF_SECONDS`, `_TIME_BUDGET_SECONDS`, `_STUCK_STREAK_THRESHOLD`.
  - DTO classes: `SyncSymbolCommand`, `BulkSyncCommand`, `SyncResponse` (same fields and Field metadata).
  - `class SyncService` with:
    - `__init__(self, policies: SyncPolicies, cache: Cache, bar_repository: BarRepository, symbol_repository: SymbolRepository, sync_status_repository: SyncStatusRepository)`
    - `sync_one(self, symbol: str, interval: Interval, n_bars: int, *, source: str, skip_filter: bool = False) -> SyncResponse`
    - `sync_bulk(self, cmd: BulkSyncCommand)`
    - `check_integrity(self, symbol, interval, days_back=7) -> dict`
    - `repair_integrity(self, symbol, interval, *, source, days_back=7) -> dict`
- **Steps:**
  1. Move the bodies verbatim from `sync_internals/*.py`, `sync_dtos.py` and `integrity_jobs.py` (`_group_gaps`, `check_integrity`, `repair_integrity`).
  2. Inline `has_aligned_bar` into `fetch_with_retry` and `build_success` into `sync_one`.
  3. Inline `_persist_bars`, `_get_bar_stats`, `_mark_completed`, `_invalidate_cache` and `_fail` into `sync_one`, keeping the same calls in the same order. `_fail` stays as one private method only if `sync_one` would otherwise exceed 60 lines.
  4. In `sync_one`, replace `self._provider` with `self._policies.for_symbol(symbol).bar_source`.
  5. `check_integrity` keeps its body, but the `expected` grid becomes `{t for t in grid if not policy.is_closed(symbol, t)}` with `policy = self._policies.for_symbol(symbol)` (no-op for Binance). It uses `self._bar_repo`.
  6. `repair_integrity` calls `await self.sync_one(symbol, interval, 5000, source=source, skip_filter=True)` where it called `sync_service.sync_one(SyncSymbolCommand(...))`.
  7. `sync_bulk` calls `self.sync_one(symbol, cmd.interval, cmd.n_bars, source=SOURCE_BULK_SYNC)`.
  8. Keep every log event name unchanged.
  9. Delete `sync_internals/` and `sync_dtos.py`.
- **Success criteria:** no `sync_internals` or `sync_dtos` import remains in `src`, and the file stays readable top-down.
- **Verify:** `git grep -n "sync_internals\|sync_dtos\|integrity_jobs" -- src` exits 1 (no matches).

### Task 03.3: `sync_runner.py`
- **Goal:** one APScheduler entrypoint replaces the five job functions; cascade and verify move in.
- **Target files and symbols:** `src/pocketquant/engine/market_data/sync_runner.py` with:
  - `RUNNER_REF = "pocketquant.engine.market_data.sync_runner:run_sync_job"`
  - `JOB_SCHEDULES` (dict `job_id -> add_cron_job kwargs`, copying the values at `sync_jobs.py:689-721`: `sync_1m` cron `*/1 * * * *` second 2 grace 120; `sync_verify_cascade` cron `0 * * * *` grace 600; `sync_backfill` hour 3 minute 0 grace 3600; `sync_integrity` hour 4 minute 0 grace 3600; `sync_repair` cron `0 */12 * * *` grace 1800)
  - `CATCHUP_TARGETS` (3-tuples `(job_id, RUNNER_REF, max_gap)` with the same job ids and gaps as `sync_jobs.py:72-76`)
  - `set_container`, `run_sync_job(job: str)`
  - `_poll`, `_backfill`, `_verify_cascade`, `_integrity`, `_repair`, `_sync_intervals`
  - `tf_seconds`, `aggregate_ohlcv`, `compute_boundaries`, `cascade_for_symbol(symbol, lookback_minutes, bar_repo, intervals=CASCADE_TFS)`
  - `PRICE_THRESHOLD_PCT`, `VOLUME_THRESHOLD_PCT`, `DIVERGENCE_ALERT_FRACTION`, `compare_bar_fields`, `_verify_one_symbol`
  - `enqueue_missed_catchups`, `register_sync_jobs`
- **Steps:**
  1. `run_sync_job(job)`:
     - Resolve `JobHistoryRepository`, `SyncService`, `TrackedSymbolRepository`, `BarRepository` and `SyncPolicies` from the module container.
     - `doc_id = record_start(job)` (warn on failure, exactly as at `sync_jobs.py:247-250`).
     - Dispatch on `job` to the matching private coroutine. `_poll` and `_backfill` return `(inserted, fetched)`.
     - `record_finish(doc_id, status="completed", duration_ms=..., total_inserted=..., total_fetched=...)`. Pass totals only for `sync_1m` and `sync_backfill`, exactly as today.
     - On an exception: `record_finish(..., status="failed", error=str(exc))` and re-raise.
     - An unknown job raises `ValueError`.
  2. `_sync_intervals(deps, symbols, intervals, n_bars_for, job_name, doc_id, source)` is the body of `_sync_by_intervals` (`sync_jobs.py:130-231`), with `sync_one(symbol, interval, n_bars_for(interval), source=source)` and the same logs and `record_detail` calls. It raises the first exception after the loops.
  3. `_poll`: for each `(policy, symbols)` from `policies.group(tracked)`:
     - Skip the policy when `now.minute % policy.poll_every_minutes != 0`.
     - Drop symbols where `policy.is_closed(sym, now)`, logging `sync.market_closed_skip`.
     - Cap the work to `policy.rate_budget_per_poll` calls; log `sync.rate_budget_exhausted` and truncate.
     - Run `_sync_intervals` with `policy.poll_intervals` and `policy.poll_n_bars`. If it raised, remember the first error and skip the cascade for that policy. Otherwise, when `policy.cascade_intervals` is set, run `cascade_for_symbol(sym, lookback_minutes=100, bar_repo, intervals=policy.cascade_intervals)` for each symbol (logging and the error handling as at `sync_jobs.py:409-430`).
     - At the end, raise the first remembered error.
     - Keep the `name="sync_1m"` log names.
  4. `_backfill`: per policy, `_sync_intervals` with `policy.history_intervals` and `policy.backfill_bars`, `source=SOURCE_REST_BACKFILL`.
  5. `_integrity` and `_repair`: bodies from `sync_jobs.py:298-310` and `:344-361`, iterating per policy over `policy.history_intervals` and calling `sync_service.check_integrity` / `repair_integrity`.
  6. `_verify_cascade`: the body of `sync_verify_cascade` (`sync_jobs.py:533-589`), iterating only policies with non-empty `cascade_intervals`, with `provider=policy.bar_source`.
  7. Move the cascade functions verbatim from `cascade_aggregator.py`. `cascade_for_symbol` loops over its new `intervals` parameter instead of the module `CASCADE_TFS`, and `_TF_EXPECTED_BARS` moves with it.
  8. `enqueue_missed_catchups`: same body, but call `job_scheduler.add_one_off_job(func_ref, job_id=f"{job_id}_catchup", job=job_id)`.
  9. `register_sync_jobs(container, job_scheduler)`: `set_container(container)`; `for job_id, sched in JOB_SCHEDULES.items(): job_scheduler.add_cron_job(RUNNER_REF, job_id=job_id, job=job_id, **sched)`; then the catch-up sweep; log `market_data.registered_sync_jobs` with `job_count=5`.
  10. Every function must be ≤60 lines.
- **Success criteria:** the module compiles; no function is longer than 60 lines.
- **Verify:** `uv run python scripts/code_metrics.py --list | grep -c "^LONG engine/market_data/sync_"` prints `0`.

### Task 03.4: Route policies through DI, WS manager, quote service, backfill service and startup
- **Goal:** every former single-provider consumer resolves through `SyncPolicies`.
- **Target files and symbols:** see the Files list.
- **Steps:**
  1. `app/di/infrastructure.py`: delete `get_data_provider` and its `IDataProvider`/`BinanceClient` imports.
  2. `app/di/market_data.py`:
     - Delete `get_realtime_quote_provider`.
     - Add `@provide(scope=Scope.APP) def get_sync_policies(self, settings: Settings) -> SyncPolicies: return SyncPolicies((binance_policy(BinanceClient(settings=settings), BinanceWebSocketClient()),), fallback="BINANCE")`.
     - Change `get_quote_service` and `get_ws_subscription_manager` to take `policies: SyncPolicies` instead of `provider`.
  3. `QuoteAppService.__init__(self, settings, cache, bar_manager, policies: SyncPolicies)`. `start()` creates `self.ws_tasks = [asyncio.create_task(p.live_source.run_forever()) for p in policies.policies]`. Add `async def stop(self)`, which cancels and awaits each task (5 s timeout, as in `main_extensions.py:205-212`) and then calls `await p.live_source.disconnect()` for each policy.
  4. `WsSubscriptionManager.__init__(self, policies, tracked_symbol_repo, quote_app_service, interval_s=5.0)`. In `_reconcile`, for each `(policy, symbols)` in `policies.group(desired)`, diff against `set(policy.live_source.subscriptions.keys())`. Also unsubscribe keys present in a live source but absent from desired, per policy. Keep the log names.
  5. `main_extensions.start_quote_feed`: set `app.state.ws_tasks = quote_svc.ws_tasks`. `stop_quote_feed`: cancel `subscription_task` as today, then `await (await container.get(QuoteAppService)).stop()`. Remove the `IRealtimeQuoteProvider` import.
  6. `main_extensions.start_background_jobs` and `main.py`: import `register_sync_jobs` / `set_container` from `pocketquant.engine.market_data.sync_runner`.
  7. `TrackedSymbolBackfillService.__init__(self, policies: SyncPolicies, bar_repository)`. In `run`, `policy = self._policies.for_symbol(symbol)`, provider = `policy.bar_source`, and `mode = cmd.resolved_mode() if cmd.interval in policy.cascade_intervals else "direct"`. Import `cascade_for_symbol` and `tf_seconds` from `sync_runner`.
  8. `app/routes/integrity.py`: both routes take only `sync_service: FromDishka[SyncService]` and call `sync_service.check_integrity(symbol, body.interval, body.days_back)` / `sync_service.repair_integrity(symbol, body.interval, source=SOURCE_REST_REPAIR, days_back=body.days_back)`.
  9. `app/routes/market_data_sync.py`:
     - `sync_symbol` returns `await sync_service.sync_one(cmd.symbol, cmd.interval, cmd.n_bars, source=cmd.source)`.
     - `sync_symbol_background` uses `background_tasks.add_task(sync_service.sync_one, cmd.symbol, cmd.interval, cmd.n_bars, source=cmd.source)`.
  10. Replace the textual `sync_jobs.py` references in docstrings of `scheduler.py`, `job_history_repository.py` and `main.py` with `sync_runner.py`.
  11. Delete `sync_jobs.py`, `integrity_jobs.py` and `cascade_aggregator.py`.
- **Success criteria:** no import of the deleted modules remains; the app boots.
- **Verify:** `git grep -n "app_services.sync_jobs\|app_services.cascade_aggregator\|app_services.integrity_jobs\|get_data_provider\|get_realtime_quote_provider" -- src` exits 1; `uv run pytest tests/baseline -q` exits 0.

### Task 03.5: Port the coupled tests (edits limited to imports, constructors and call sites)
- **Goal:** the existing tests keep their assertions against the new API.
- **Target files and symbols:** the 17 test files listed under "Modify tests".
- **Steps (one rule per file group):**
  1. Import swaps. Module `sync_internals.bar_filters`, `sync_internals.provider_fetch` or `sync_internals.anomaly_log` → `pocketquant.engine.market_data.sync_service`. In `test_provider_fetch.py`, replace the module alias `provider_fetch` with `sync_service`. `app_services.cascade_aggregator` / `app_services.sync_jobs` → `pocketquant.engine.market_data.sync_runner`. `app_services.integrity_jobs` → use `SyncService.repair_integrity`.
  2. `unit/handlers/sync/conftest.py`: the module tuple becomes `(sync_service,)` only.
  3. `SyncService(...)` constructions in `test_sync_service.py` and `test_no_progress_tracking.py`: replace `provider=X` with `policies=SyncPolicies((binance_policy(X, MagicMock()),))`. Replace `sync_one(SyncSymbolCommand(symbol=s, interval=i, n_bars=n, source=src, skip_filter=f))` with `sync_one(s, i, n, source=src, skip_filter=f)`.
  4. `test_sync_jobs_source_labels.py`: monkeypatch `sync_runner._container`. The container fake must also return `SyncPolicies((binance_policy(MagicMock(), MagicMock()),))` for `SyncPolicies`. Replace `await sync_jobs.sync_1m()` / `sync_backfill()` with `await sync_runner.run_sync_job("sync_1m")` / `("sync_backfill")`. Assert on `call.kwargs["source"]` of the `sync_one` mock instead of `SyncSymbolCommand.source`.
  5. `test_sync_verify_cascade.py`: replace `sync_verify_cascade()` with `run_sync_job("sync_verify_cascade")`. The fake container returns a `SyncPolicies` whose binance policy `bar_source` is the test's fake provider.
  6. `test_integrity_jobs_repair_source.py`: build a `SyncService` with mocked repos, call `repair_integrity(symbol, interval, source=SOURCE_REST_REPAIR)`, and assert that the `sync_one` mock received `source=SOURCE_REST_REPAIR` and `skip_filter=True`.
  7. `test_quote_app_service.py`: construct with `policies=SyncPolicies((binance_policy(MagicMock(), <the test's provider>),))`.
  8. `test_di_data_provider.py`: assert `MarketDataProvider().get_sync_policies(mock_settings)`:
     - `.for_symbol("BTCUSDT:BINANCE").bar_source` is a `BinanceClient`
     - `.live_source` is a `BinanceWebSocketClient` and `isinstance(..., IRealtimeQuoteProvider)`
     - `.for_symbol("ETHUSDT:OKX")` is the same policy object
  9. `app_factory.py`: change the `set_sync_container` import to `sync_runner`. `test_sync_jobs_phase.py` and `test_sync_jobs_catchup.py`: change the import to `sync_runner` only.
- **Success criteria:** no assertion was removed. The count of `assert` statements per edited file is unchanged or higher.
- **Verify:** run the loop below. It exits 0 only if no edited file lost `assert` statements.

  ```bash
  rc=0
  for f in \
    tests/app_test/integration/test_sync_backfill_gap_fill.py \
    tests/app_test/market_data/test_cascade_aggregator.py \
    tests/app_test/market_data/test_cascade_aggregator_source.py \
    tests/app_test/market_data/test_integrity_jobs_repair_source.py \
    tests/app_test/market_data/test_sync_jobs_source_labels.py \
    tests/app_test/test_sync_jobs_phase.py \
    tests/app_test/unit/handlers/sync/test_bar_filters.py \
    tests/app_test/unit/handlers/sync/test_provider_fetch.py \
    tests/app_test/unit/handlers/sync/test_no_progress_tracking.py \
    tests/app_test/unit/handlers/sync/test_sync_symbol_command_source.py \
    tests/app_test/unit/market_data/test_sync_jobs_catchup.py \
    tests/app_test/unit/market_data/test_sync_verify_cascade.py \
    tests/app_test/unit/market_data/test_quote_app_service.py \
    tests/app_test/unit/di/test_di_data_provider.py \
    tests/engine_test/market_data/test_sync_service.py; do
    a=$(git show "$BASE_SHA:$f" | grep -c '^\s*assert')
    b=$(grep -c '^\s*assert' "$f")
    [ "$b" -ge "$a" ] || { echo "LOST $f $a->$b"; rc=1; }
  done
  exit $rc
  ```

### Task 03.6: Prove equivalence
- **Goal:** the golden and pinned tests pass unchanged.
- **Target files and symbols:** none modified.
- **Steps:** run the commands in Verify.
- **Success criteria:** all green, with the protected files untouched.
- **Verify:**
  - `git diff --quiet $BASE_SHA -- tests/app_test/integration/test_sync_pipeline_characterization.py tests/app_test/integration/golden tests/core_test/infra/binance tests/core_test/infra/brokers/test_okx_characterization.py tests/baseline` exits 0.
  - `uv run pytest tests/app_test/integration/test_sync_pipeline_characterization.py tests/core_test/infra/binance tests/core_test/infra/brokers/test_okx_characterization.py -q` exits 0. The Binance pass count equals the baseline in `baseline-gates.md`.
  - `test ! -d src/pocketquant/engine/market_data/sync_internals` exits 0.

## Verification (phase gate)
- `just test` exits 0. `uv run ruff check` exits 0. `uv run pyright` prints `0 errors`. `uv run lint-imports` prints `0 broken`.
- `uv run python scripts/code_metrics.py`: record its output in `reports/baseline-gates.md` under `## After phase 03`.
- Commit with `refactor(market-data): drive sync jobs from per-provider sync policies`. Ask the user to approve merging and deploying to `master`.
- After the deploy: `gh run list --workflow cicd.yml --branch master --limit 1 --json conclusion -q '.[0].conclusion'` prints `success`. `gh run view $(gh run list --workflow cicd.yml --branch master --limit 1 --json databaseId -q '.[0].databaseId') --log | grep -c "(19/19 passed"` prints ≥1.
- After the deploy: `ssh -i "$KEY" "$HOST" 'docker logs pocketquant-app --since 10m 2>&1 | grep -c "market_data.registered_sync_jobs"'` prints ≥1.

## Risks
- Persisted APScheduler documents still point at `…app_services.sync_jobs:*` (high likelihood, low impact). APScheduler drops unrestorable jobs on load, and `register_sync_jobs` re-adds all five with `replace_existing=True`. The registration log line after the deploy is verified above.
- Behaviour drift in job ordering or totals (medium likelihood, high impact). The golden tests fail if it happens; then the Failure Protocol applies.
- `:OKX` symbols stop syncing (medium likelihood, high impact). Mitigated by the `fallback="BINANCE"` rule and pinned by the golden `provider_calls`.

## Rollback
- Revert the merge commit and redeploy. Persisted new-ref jobs fail to restore under the old code and are dropped and re-registered by the old `register_sync_jobs`, so recovery is self-healing in both directions. No data migration.

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

<!-- FILE: phase-04-lean-consolidation.md -->
---
phase: 4
title: "Lean consolidation: DI, routes, wrappers, contracts"
status: pending
priority: P1
effort: 3d
dependencies: [3]
---

# Phase 04: Lean consolidation: DI, routes, wrappers, contracts

## Context Links
- DI today:
  - `src/pocketquant/app/di/`: `__init__.py`, `backtest_worker.py`, `broker_factory.py`, `container.py`, `core.py`, `execution.py`, `infrastructure.py`, `market_data.py`, `persistence.py`, `services.py` (its comment about "last duplicate registration wins" is at `services.py:6-9`), `trading_services.py`
  - Container entry: `src/pocketquant/app/main.py:8`
- Market-data routes today: `src/pocketquant/app/routes/market_data.py`, `market_data_ohlcv.py`, `market_data_quotes.py`, `market_data_status.py`, `market_data_sync.py`, `integrity.py`, `list_symbols.py`, `tracked_symbols.py`; mounted at `main_extensions.py:366-404`
- Route snapshots that must stay byte-identical: `tests/baseline/openapi_app_snapshot.json`, `tests/baseline/route_inventory_app_snapshot.json`
- Contracts: `pyproject.toml` `[[tool.importlinter.contracts]]` (7 entries; bson is also banned by ruff `TID` at `pyproject.toml` `[tool.ruff.lint.flake8-tidy-imports.banned-api]`)

## Goal
Remove indirection that buys nothing. DI becomes 3 provider modules with strict duplicate detection. Market-data routes collapse into 2 files. Query/Command classes that wrap 0-2 scalars go away. Import-linter drops to 3 contracts. Dead code is deleted. The metric is measured against the user's thresholds, with a stop gate.

## Files to Create or Modify
- DI:
  - Create `src/pocketquant/app/di/adapters.py`.
  - Rewrite `app/di/__init__.py`, `app/di/infrastructure.py`, `app/di/services.py`.
  - Delete `app/di/backtest_worker.py`, `broker_factory.py`, `container.py`, `core.py`, `execution.py`, `market_data.py`, `persistence.py`, `trading_services.py`.
- Routes:
  - Create `src/pocketquant/app/routes/market_data_streams.py`; rewrite `app/routes/market_data.py`.
  - Delete `market_data_ohlcv.py`, `market_data_quotes.py`, `market_data_status.py`, `market_data_sync.py`, `integrity.py`, `list_symbols.py`, `tracked_symbols.py`.
  - Modify `app/main.py`, `app/main_extensions.py`.
- Wrappers:
  - `src/pocketquant/engine/orders_positions_service.py`, `engine/strategy_query_service.py`, `engine/strategy_command_service.py`
  - `engine/market_data/symbols_service.py`, `engine/market_data/quotes_service.py`, `engine/market_data/sync_status_service.py`, `engine/market_data/tracked_symbols_service.py`
  - `backtest/backtest_query_service.py`, `backtest/backtest_command_service.py`
  - `app/routes/strategy.py`, `app/routes/trading_orders_positions.py`, `app/routes/backtest.py`
- Contracts: `pyproject.toml`.
- Dead code and OKX trims: the files named in Tasks 04.6 and 04.7.
- Tests (imports, constructors, call sites only):
  - `tests/app_test/integration/app_factory.py`, `tests/app_test/integration/test_app_standalone_runtime.py`, `tests/app_test/integration/test_reconcile_di_resolution.py`, `tests/app_test/unit/di/test_di_data_provider.py`
  - `tests/engine_test/test_reconcile_restart_resume_integration.py`, `tests/engine_test/test_orders_positions_service.py`, `tests/engine_test/test_strategy_service.py`, `tests/engine_test/test_strategy_handlers_declarative.py`, `tests/engine_test/test_strategy_position_and_trade_handlers.py`
  - `tests/engine_test/market_data/test_quotes_service.py`, `tests/engine_test/market_data/test_tracked_symbols_service.py`
  - `tests/app_test/unit/handlers/status/test_get_sync_status.py`, `tests/app_test/unit/handlers/status/test_get_symbol_sync_status.py`

## Tasks

### Task 04.1: Confirm dishka capabilities
- **Goal:** the DI design relies only on features present in the locked dishka 1.9.1.
- **Target files and symbols:** none.
- **Steps:** run the Verify command.
- **Success criteria:** the imports succeed.
- **Verify:** `uv run python -c "from dishka import STRICT_VALIDATION, from_context, provide_all, make_async_container"` exits 0. If it fails, apply the Failure Protocol; do not substitute another design yourself.

### Task 04.2: DI to three provider modules
- **Goal:** `app/di` holds `__init__.py` plus exactly `infrastructure.py`, `adapters.py` and `services.py`; duplicate provides raise.
- **Target files and symbols:**
  - `InfrastructureProvider`: `settings = from_context(provides=Settings, scope=Scope.APP)`; EventBus `EventBus(max_history=100)`; Database and Cache async generators (bodies from `persistence.py:45-59`); the 11 repositories via `provide_all(..., scope=Scope.APP)`; JobScheduler generator (body from `infrastructure.py:17-27`); `HealthCoordinator(timeout=5.0)`.
  - `AdaptersProvider`: class `BrokerFactory` moved verbatim from `broker_factory.py` without `get_available_types`; `broker_factory = provide(BrokerFactory, scope=Scope.APP)`; `get_sync_policies` moved from `market_data.py`.
  - `ServicesProvider`:
    - Factories with post-init stay as methods: `OrderAppService.load_pending_orders` (`execution.py:34-39`), `PositionAppService.start` (`:42-47`), the StrategyAppService generator (`:50-76`), StrategyReconcileService `interval_s` (`:79-89`), `BacktestDispatchDeps` (`backtest_worker.py:24-37`).
    - Everything else goes in one `provide_all(...)`: SyncService, BarAppService, QuoteAppService, WsSubscriptionManager, RiskCheckHandler, StrategyCommandService, StrategyQueryService, OrderPositionQueryService, BacktestExecutionService, TrackedSymbolService, TrackedSymbolBackfillService, OhlcvService, QuoteQueryService, SyncStatusQueryService, SymbolQueryService, BacktestCommandService, BacktestQueryService, BacktestStatsService.
  - `app/di/__init__.py`: `def create_container(settings: Settings | None = None) -> AsyncContainer: return make_async_container(InfrastructureProvider(), AdaptersProvider(), ServicesProvider(), context={Settings: settings or get_settings()}, validation_settings=STRICT_VALIDATION)`; export the three providers, `BrokerFactory` and `create_container`.
- **Steps:**
  1. Write the three modules and `__init__.py`. Delete the eight old files.
  2. `main.py`: `from pocketquant.app.di import create_container`.
  3. `tests/app_test/integration/app_factory.py`: delete `TestCoreProvider`; set `container = create_container(settings)`.
  4. In the remaining DI tests, change imports to `pocketquant.app.di` or `pocketquant.app.di.adapters`. `test_di_data_provider.py` uses `AdaptersProvider().get_sync_policies(...)`.
  5. If dishka's provide_all auto-wiring cannot resolve a constructor (the error names the class), give that class an explicit `@provide` method that calls the same constructor. Do not change any constructor.
- **Success criteria:** the module count is 3 plus `__init__.py`; the container builds with strict validation.
- **Verify:**
  - `ls src/pocketquant/app/di/*.py | sort | tr '\n' ' '` prints exactly `src/pocketquant/app/di/__init__.py src/pocketquant/app/di/adapters.py src/pocketquant/app/di/infrastructure.py src/pocketquant/app/di/services.py `.
  - `uv run pytest tests/baseline tests/app_test/integration/test_reconcile_di_resolution.py tests/app_test/integration/test_app_standalone_runtime.py -q` exits 0.

### Task 04.3: Market-data routes into two files
- **Goal:** the same routes, names, paths, tags and schemas from two files.
- **Target files and symbols:**
  - `app/routes/market_data.py`:
    - `router = APIRouter(prefix="/market-data", tags=["Market Data"], route_class=DishkaRoute)` holding `sync_symbol`, `sync_symbol_background`, `sync_bulk`, `integrity_check`, `integrity_repair`, `get_ohlcv`, `get_sync_statuses`, `get_symbol_sync_status`, `list_symbols`, plus the models `IntegrityRequest` and `OHLCVResponse`.
    - `tracked_symbols_router = APIRouter(tags=["Tracked Symbols"], route_class=DishkaRoute)` holding the five tracked-symbol routes with their existing `Depends(verify_admin_token)` usage.
  - `app/routes/market_data_streams.py`:
    - `bars_stream_router = APIRouter(prefix="/market-data", tags=["Market Data"], route_class=DishkaRoute)` with `stream_bars` and helper `_bar_payload` (renamed from `market_data_ohlcv._make_payload`).
    - `quotes_router = APIRouter(prefix="/quotes", tags=["Real-time Quotes"], route_class=DishkaRoute)` with `get_latest_quote`, `get_current_bar`, `stream_quote` and helper `_quote_payload`.
- **Steps:**
  1. Move each function body verbatim. Keep the decorator arguments and function names identical.
  2. In `main_extensions.register_routes`, include, in this order:
     - `market_data.router`
     - `market_data.tracked_symbols_router` with `prefix="/market-data"`
     - `market_data_streams.bars_stream_router`
     - `market_data_streams.quotes_router`
     - then the remaining routers unchanged.
  3. Delete the seven old files.
- **Success criteria:** both snapshots are unchanged.
- **Verify:** `git diff --quiet $BASE_SHA -- tests/baseline` exits 0 and `uv run pytest tests/baseline -q` exits 0; `ls src/pocketquant/app/routes/ | grep -c "market_data"` prints `2`.

### Task 04.4: Remove Query/Command classes that wrap 0-2 scalars
- **Goal:** routes pass scalars; Pydantic models remain only for real request bodies and multi-field queries.
- **Target files and symbols (22 classes, as of BASE_SHA):**
  - `orders_positions_service.py`: `GetOrderQuery:19`, `ListOrdersQuery:23`, `GetPositionQuery:27`, `ListPositionsQuery:31`
  - `strategy_query_service.py`: `GetStrategiesQuery:23`, `GetStrategyQuery:28`, `ListSymbolsQuery:32`, `GetStrategyPositionsQuery:36`, `GetStrategyTradesQuery:40`
  - `strategy_command_service.py`: `StartStrategyCommand:29`, `StopStrategyCommand:33`, `RemoveSymbolCommand:48`, `DeleteStrategyCommand:52`
  - `market_data/symbols_service.py`: `ListSymbolsQuery:6`
  - `market_data/quotes_service.py`: `GetLatestQuoteQuery:10`
  - `market_data/sync_status_service.py`: `GetSyncStatusQuery:34`, `GetSymbolSyncStatusQuery:39`
  - `market_data/tracked_symbols_service.py`: `UpdateTrackedSymbolCommand:40`, `RemoveTrackedSymbolCommand:47`, `ListTrackedSymbolsQuery:53`
  - `backtest_query_service.py`: `GetBacktestQuery:24`
  - `backtest_command_service.py`: `SetVerdictCommand:39`
  - Keep: `AddSymbolCommand`, `AddTrackedSymbolCommand`, `BackfillTrackedSymbolCommand`, `RunBacktestCommand`, `ListBacktestsQuery`, `ListTradesQuery`, `GetOHLCVQuery`, `SyncSymbolCommand`, `BulkSyncCommand`.
- **Steps:**
  1. For each removed class, change the service method to take the fields as parameters with the same names and defaults, for example `get_order(self, order_id: str)`, `get_trades(self, subscription_id: str, limit: int = 100)`, `list_all(self)`, `set_verdict(self, run_id: str, verdict: str | None)`, `get_symbol_sync_status(self, symbol: str, interval: str)`. Replace `query.x` / `cmd.x` / `request.x` in the body with `x`.
  2. Update every call site: routes, `app/routes/market_data*.py`, `app/routes/backtest.py`. Then find the test call sites with `git grep -nw <ClassName> -- src tests` and update each.
  3. Delete the class definitions.
- **Success criteria:** none of the 22 names remains in `src` or `tests`; the OpenAPI snapshot is unchanged.
- **Verify:** `git grep -nwE "GetOrderQuery|ListOrdersQuery|GetPositionQuery|ListPositionsQuery|GetStrategiesQuery|GetStrategyQuery|ListSymbolsQuery|GetStrategyPositionsQuery|GetStrategyTradesQuery|StartStrategyCommand|StopStrategyCommand|RemoveSymbolCommand|DeleteStrategyCommand|GetLatestQuoteQuery|GetSyncStatusQuery|GetSymbolSyncStatusQuery|UpdateTrackedSymbolCommand|RemoveTrackedSymbolCommand|ListTrackedSymbolsQuery|GetBacktestQuery|SetVerdictCommand" -- src tests` exits 1; `uv run pytest tests/baseline -q` exits 0.

### Task 04.5: Import-linter to three contracts
- **Goal:** exactly layers, core-domain-free-of-infra and fastapi-only-in-app remain.
- **Target files and symbols:** `pyproject.toml` contracts named "Core imports no inner package", "Engine imports no sibling/upper package", "Backtest imports no upper package" and "No bson/ObjectId usage — UUID7 only".
- **Steps:** delete those four `[[tool.importlinter.contracts]]` tables. The layers contract already forbids upward imports, and ruff `TID` `banned-api` still bans `bson`. Keep the other three tables byte-identical.
- **Success criteria:** three contracts, all kept.
- **Verify:** `uv run lint-imports | tail -1` prints `Contracts: 3 kept, 0 broken.`; `uv run ruff check` exits 0.

### Task 04.6: Delete dead code
- **Goal:** functions with zero references anywhere are gone.
- **Target files and symbols (candidates at BASE_SHA; each must be re-verified):**
  - `backtest/domain/services/performance_calculator.py:183 drawdown_series`
  - `backtest/jobs/backtest_strategy_loader.py:17 resolve_date_range`, `:41 build_backtest_config`, `:65 inject_strategy_into_sandbox`
  - `core/common/messaging/event_bus.py:45 clear_history`
  - `core/common/messaging/event_registry.py:67 get_registered`
  - `core/common/time/simulation.py:38 is_simulation_active`
  - `core/domain/bar/services/bar_builder.py:118 create_for_tick`
  - `core/domain/brokers/value_objects.py:30 is_filled`, `:44 buying_power`
  - `core/domain/order/entities.py:111 partial_fill`
  - `core/domain/position/entities.py:183 cost_basis`
  - `core/domain/position/value_objects.py:14 is_profitable`
  - `core/domain/risk/services/position_sizer.py:89 validate_size`
  - `core/domain/strategy/interfaces.py:89 get_parameter`
  - `core/domain/strategy/value_objects.py:27 is_entry`, `:31 is_exit`, `:91 from_dict`
  - `core/domain/symbol/entities.py:72 deactivate`, `:75 activate`
  - `core/infra/brokers/okx/okx_mapper.py:7 map_okx_order_state`
  - `core/infra/brokers/okx/websocket/okx_message_parser.py:51 get_event_type`, `:55 get_event_code`, `:59 get_event_message`
  - `okx_order_mapper.py:80 get_client_order_id`, `:88 get_symbol`, `:93 get_side`
  - `okx_position_mapper.py:25 is_open`, `:86 get_position_id`, `:90 get_inst_id`, `:94 is_position_closed`
  - `core/infra/persistence/redis.py:118 get_or_set`
  - `core/infra/persistence/repositories/backtest_repository.py:57 get_best_by_metric`
  - `core/infra/scheduling/scheduler.py:324 run_job_now`
  - `engine/app_services/order_app_service.py:170 get_orders_by_strategy`, `:216 get_order_async`, `:222 get_orders_by_strategy_async`
  - `engine/app_services/position_app_service.py:153 get_async`
  - `engine/app_services/strategy_app_service.py:205 get_strategies`
  - `engine/handlers/risk/check_risk/handler.py:81 calculate_max_size`, `:103 get_risk_summary`
  - `engine/market_data/app_services/quote_dto.py:91 to_ohlcv_dict`
  - Never delete: pydantic validators (`_validate_symbol`, `validate_mode`), `OrderAppService.on_order_update` (wired in Phase 08), abstract or Protocol members, `@event_handler` or route functions.
- **Steps:**
  1. For each candidate, run `git grep -nw <name> -- src tests scripts web`. Delete the function only if the output is exactly its own `def` line. Otherwise skip it and write `kept <name>: <first other reference>` in `reports/baseline-gates.md` under `## Dead-code review`.
  2. If deleting leaves a file with no remaining definitions (for example `backtest_strategy_loader.py`), delete the file only if `git grep -n "backtest_strategy_loader" -- src tests scripts` returns nothing.
- **Success criteria:** every deletion was preceded by a zero-reference grep.
- **Verify:** `just test` exits 0 and `uv run pytest tests/core_test/infra/brokers/test_okx_characterization.py -q` exits 0.

### Task 04.7: Inline single-call trivial accessors and attribute-only properties
- **Goal:** trivial wrappers whose name adds nothing are removed, mechanically.
- **Target files and symbols:**
  - `okx_message_parser.py`: `is_event`, `is_data`, `get_channel`, `get_data`, inlined into `OkxMessageParser.parse`.
  - `okx_order_mapper.py`: `is_terminal`, `get_order_id`, `get_state`, inlined into their callers.
  - `PaperBroker.slippage` property plus setter (`paper_broker.py:133-138`), replaced by a public attribute `slippage`.
  - `OKXBroker.trade_api` (`okx_broker.py:73`) and `seen_terminal_orders` (`:77`), replaced by public attributes.
- **Steps:**
  1. Inline a function only if `git grep -nw <name> -- src` shows exactly one call site besides the definition. Replace the call with the function's return expression (for example `message.get("arg", {}).get("channel", "")`).
  2. For a property whose body is exactly `return self._<name>` (or the setter `self._<name> = value`), rename `self._<name>` to `self.<name>` throughout the class and delete the property (and setter). External uses such as `self._broker.slippage = ...` (`backtest_app_service.py:102`) and `self._broker.trade_api` keep working unchanged.
  3. Do not touch the abstract properties of `IBroker`/`IStrategy` (`name`, `is_connected`, `side`, `is_running`).
- **Success criteria:** the OKX and paper characterization still pass.
- **Verify:** `uv run pytest tests/core_test/infra/brokers tests/backtest_test -q` exits 0.

### Task 04.8: Measure the flow-file rule
- **Goal:** evidence that a sync request reads in ≤3 files.
- **Target files and symbols:** `reports/baseline-gates.md` section `## Flow files`.
- **Steps:** record the import chain for `POST /market-data/sync`: `app/routes/market_data.py` → `engine/market_data/sync_service.py` → `engine/market_data/sync_policy.py` (repositories excluded). Do the same for the scheduled poll: `sync_runner.py` → `sync_service.py` → `sync_policy.py`.
- **Success criteria:** both chains list ≤3 project files.
- **Verify:** `grep -c "→" plans/261009-0858-exness-venue-lean-sync-refactor/reports/baseline-gates.md` prints ≥4.

### Task 04.9: Metric gate (stop-and-ask)
- **Goal:** compare against the user's balanced thresholds without gaming them.
- **Target files and symbols:** `reports/baseline-gates.md` section `## After phase 04`.
- **Steps:**
  1. Run `uv run python scripts/code_metrics.py` and record the output.
  2. If `tiny_share<=30.0%` and `pure_delegations<=20`, continue.
  3. Otherwise STOP and ask the user, quoting the numbers and these options (plan.md question 1):
     - (a) Accept the measured values as the soft thresholds in CI and docs.
     - (b) Authorize an extra tranche from `scripts/code_metrics.py --list`. It may only inline private (`_`-prefixed) tiny functions with exactly one call site, and only if the caller stays ≤60 lines.
     - (c) Change the metric definition.
     Do not inline route handlers, ports, properties of ABCs, or serializers on your own initiative.
- **Success criteria:** either the thresholds are met, or the user's choice is recorded.
- **Verify:** `grep -c "tiny_share=" plans/261009-0858-exness-venue-lean-sync-refactor/reports/baseline-gates.md` prints ≥3, and when the thresholds are exceeded, `grep -c "user decision:" plans/261009-0858-exness-venue-lean-sync-refactor/reports/baseline-gates.md` prints ≥1.

## Verification (phase gate)
- `just test` exits 0. `uv run ruff check` exits 0. `uv run pyright` prints `0 errors`. `uv run lint-imports | tail -1` prints `Contracts: 3 kept, 0 broken.`
- `git diff --quiet $BASE_SHA -- tests/baseline tests/core_test/infra/binance tests/app_test/integration/golden` exits 0.
- Commit with `refactor(app): consolidate di, market-data routes and scalar service calls`. Get user approval, then merge and deploy. The CI conclusion is `success` and the log has `(19/19 passed`, using the commands from Phase 03.

## Risks
- Strict validation exposes a hidden duplicate registration (medium likelihood, medium impact). That is the purpose: remove the duplicate and keep the provider the app actually used, as shown by `git show $BASE_SHA:src/pocketquant/app/di/<file>`.
- A route moves and changes the OpenAPI output (low likelihood, high impact). The snapshot test is byte-exact.
- Dead-code grep misses dynamic use (low likelihood, medium impact). The full suite plus golden tests guard it, and `getattr`-style users would show up in grep as a string.

## Rollback
- Revert the merge commit. There is no schema or data change.

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

<!-- FILE: phase-05-coding-standard-rewrite.md -->
---
phase: 5
title: "Coding standard rewrite and CI soft gate"
status: pending
priority: P2
effort: 1d
dependencies: [4]
---

# Phase 05: Coding standard rewrite and CI soft gate

## Context Links
- Current standard: `docs/code-standards.md` (799 lines). Stale or mandating sections: "9. Service Extract-Method Pattern" (`:177`), "Module Size" with the 200-LOC cap and "Current Status" (`:381-390`), "8.5. Command/Query Service Pattern" (`:132`), "Import Contracts" (`:779`), and the anti-pattern example naming `set_sync_container()` (`:612`).
- Binding doc rules: `CLAUDE.md`, section "Writing docs & prose": prose in Vietnamese with English technical terms, AS-IS only, no banners, no changelog. CLAUDE.md line 3 says "(7 contracts)", and the "Routes" rule says "Service methods take Pydantic command/query models".
- CI: `.github/workflows/cicd.yml` job `tests`, step "Check import contracts (layered architecture)".

## Goal
The standard describes the code as it now is and gives rules of thumb instead of mandates. CLAUDE.md is consistent with it. The metric runs in CI as a non-blocking signal.

## Files to Create or Modify
- Rewrite: `docs/code-standards.md`
- Modify: `CLAUDE.md` (the contract count and the Routes rule sentence only)
- Modify: `.github/workflows/cicd.yml`

## Tasks

### Task 05.1: Rewrite `docs/code-standards.md`
- **Goal:** a lean standard in Vietnamese prose with English terms.
- **Target files and symbols:** `docs/code-standards.md`.
- **Steps:**
  1. Keep these sections, edited AS-IS: Clean Architecture dependency direction, Comment Policy (keep unchanged), UUIDv7 primary key rule, Composite Symbol Format, Strategy ID Disambiguation, Async Suspension Points (replace the `set_sync_container` example's module name with `sync_runner`), Datetime Serialization, Configuration & Secrets, Testing, Type Hints, Error Handling.
  2. Replace the following with new sections:
     - `## Khi nào tách hàm`: extract only when the name adds meaning or the code is reused; keep a flow readable in one file where possible, three at most; functions stay ≲60 lines.
     - `## Kích thước file`: about 400 LOC is a soft guide, not a split trigger.
     - `## Bảng hậu tố`: only `Repository`, `Service`, `Event`, `Error`, `Provider` (DI). Existing class names such as `StrategyCommandService` stay; `AppService/CommandService/QueryService` are no longer distinct roles.
     - `## Route và service`: routes call services with scalars; Pydantic models only for real request bodies or multi-field queries.
     - `## Sync policy pattern`: a provider is one adapter package plus one `SyncPolicy` in `engine/market_data/sync_policy.py`; list the fields; one runner, `engine/market_data/sync_runner.py`; fallback exchange `BINANCE`.
     - `## Import contracts`: the 3 contracts, with ruff `TID` for bson.
     - `## Characterization test và golden file`: the `CHAR_UPDATE=1` and `BASELINE_UPDATE=1` flags.
     - `## Code metrics (soft gate)`: the metric definitions from `scripts/code_metrics.py` and the thresholds the user confirmed in Phase 04 Task 04.9.
  3. Delete: "Service Extract-Method Pattern", the 200-LOC rule, "Current Status", every list of current module sizes, "Deprecated Patterns" entries that refer to code that no longer exists, and every `CQRS handler` mention.
- **Success criteria:** no stale claims remain and the new sections exist.
- **Verify:** `grep -cE "Current Status|200 LOC|Extract-Method|Last Updated" docs/code-standards.md` prints `0`; `grep -cE "^## (Khi nào tách hàm|Kích thước file|Bảng hậu tố|Route và service|Sync policy pattern|Import contracts|Code metrics)" docs/code-standards.md` prints `7`.

### Task 05.2: Align CLAUDE.md
- **Goal:** the binding rules match the code.
- **Target files and symbols:** `CLAUDE.md` line 3 and the "Routes" bullet.
- **Steps:**
  1. Replace `(7 contracts)` with `(3 contracts)`.
  2. Replace the sentence `Service methods take Pydantic command/query models and return DTOs.` with `Service methods take scalars, or a Pydantic model when the route has a real request body, and return DTOs.`
- **Success criteria:** both edits are present and nothing else changed.
- **Verify:** `git diff --stat -- CLAUDE.md` shows `1 file changed` with ≤4 lines changed; `grep -c "3 contracts" CLAUDE.md` prints `1`.

### Task 05.3: CI soft gate
- **Goal:** CI prints the metric on every run without blocking.
- **Target files and symbols:** `.github/workflows/cicd.yml`, job `tests`.
- **Steps:** after the step "Check import contracts (layered architecture)", insert:
  ```yaml
      - name: Code metrics (soft gate)
        run: uv run python scripts/code_metrics.py
  ```
- **Success criteria:** the step exists. The script exits 0 without `--strict`.
- **Verify:** `grep -c "scripts/code_metrics.py" .github/workflows/cicd.yml` prints `1`; `uv run python scripts/code_metrics.py; echo $?` ends with `0`.

## Verification (phase gate)
- `just test` exits 0 and `uv run lint-imports | tail -1` prints `Contracts: 3 kept, 0 broken.`
- Commit with `docs(standards): rewrite code standard around rules of thumb and sync policies`. Merge after user approval.

## Risks
- Mixed-language prose violates CLAUDE.md (medium likelihood, low impact). Prose is Vietnamese and code names stay English, as CLAUDE.md requires.

## Rollback
- Revert the commit (docs and CI only).

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

<!-- FILE: phase-06-exness-signer-client.md -->
---
phase: 6
title: "Exness signer, REST client, mappers"
status: pending
priority: P1
effort: 2.5d
dependencies: [1, 5]
---

# Phase 06: Exness signer, REST client, mappers

## Context Links
- Spec header rules: `exness_api.yaml` `info.description` (signing, idempotency, async ACK). Endpoint operationIds: `getCandleHistory`, `placePendingOrder`, `cancelPendingOrder` (DELETE `/orders/{order_id}`), `openPosition` (POST `/positions`), `closePosition` (DELETE `/positions/{position_id}`), `getTradingStateSnapshot`, `getOperationStatus`, `getDealsHistory`, `getAccountDetails`, `getAvailableInstrumentList`, `getInstrumentCondition`, `getLimits`; discovery `GET /v1/trading/access-point?account_id=`.
- Spike results and fixtures: `reports/exness-spike-results.md` (`## Gate`), `tests/core_test/infra/exness/fixtures/`.
- Settings: `src/pocketquant/core/config.py:249` (`Settings`; OKX fields at `:278-282`).
- HTTP style to mirror: `src/pocketquant/core/infra/binance/binance_client.py:42-48` (httpx.AsyncClient).

## Goal
The Exness signing and REST access layer exists with recorded-fixture tests. Nothing is wired into the app yet.

## Files to Create or Modify
- Create: `src/pocketquant/core/infra/exness/__init__.py`, `signer.py`, `client.py`, `mappers.py`
- Create: `tests/core_test/infra/exness/test_signer.py`, `test_client.py`, `test_mappers.py`
- Modify: `src/pocketquant/core/config.py`, `pyproject.toml`, `uv.lock`, `scripts/exness_spike.py`

## Tasks

### Task 06.1: Dependency and settings
- **Goal:** cryptography is a direct dependency, and the Exness settings exist with secret-safe types.
- **Target files and symbols:** `pyproject.toml` `[project].dependencies`; `Settings` fields added after the OKX block:
  - `exness_account_id: str | None = None`
  - `exness_api_key: SecretStr | None = None`
  - `exness_private_key: SecretStr | None = None`
  - `exness_private_key_path: str | None = None`
  - `exness_discovery_url: str = "https://api.exness.com"`
- **Steps:** run `uv add "cryptography>=46"`, then add the fields.
- **Success criteria:** the settings load with no Exness env vars present.
- **Verify:** `uv run python -c "from pocketquant.core.config import Settings;s=Settings(_env_file=None,app_name='a',app_version='0',environment='development',mongodb_url='mongodb://x:1/db',mongodb_database='d',mongodb_min_pool_size=1,mongodb_max_pool_size=2,redis_url='redis://x:1/0',redis_cache_ttl=1,log_level='INFO',log_format='json');assert s.exness_api_key is None"` exits 0.

### Task 06.2: `signer.py`
- **Goal:** a deterministic, tested Ed25519 request signer.
- **Target files and symbols:**
  - `load_private_key(raw: str | None, path: str | None) -> Ed25519PrivateKey`, supporting the format recorded as `key_format` plus PEM.
  - `body_hash(body: bytes) -> str`
  - `sign(private_key, api_key, method, path, body, idempotency_key, timestamp_ms) -> dict[str, str]`, returning the six `EXN-*` headers.
- **Steps:**
  1. Implement exactly as Phase 01 Task 01.2 step 1. `json.dumps(payload, separators=(",", ":"))`, with base64url encoding that has the `=` padding stripped.
  2. Tests:
     - `body_hash(b"") == "47DEQpj8HBSa-_TImW-5JCeuQeRkm5NMpJWZG3hSuFU"`.
     - With the RFC 8032 test key `9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60` (hex seed), decoding `EXN-DATA` gives the expected JSON fields, `EXN-IDEMPOTENCY-KEY == ""` for GET, `EXN-SIGN-VERSION == "1"`, and the signature verifies with the public key.
     - Signing the empty message with that key equals the RFC signature `e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b`.
- **Success criteria:** the tests pass, and the module never logs keys.
- **Verify:** `uv run pytest tests/core_test/infra/exness/test_signer.py -q` exits 0; `git grep -n "logger\.\|print(" -- src/pocketquant/core/infra/exness/signer.py` exits 1.

### Task 06.3: `client.py`
- **Goal:** one signed REST client with access-point resolution, clock offset and a sliding-window limiter fed from `/limits`.
- **Target files and symbols:** `class ExnessClient` with:
  - `__init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None)`, which does no network work.
  - `configured: bool` (true only when account, api key and a key source are all set)
  - `async def start(self)`: resolve the access point, load limits and the instrument list.
  - `async def request(self, method, path, *, query=None, body=None, idempotency_key="")`
  - `instrument_name(code: str) -> str`, a case-insensitive map to the exact Exness name.
  - `async def conditions(name)`, cached per name.
  - `limits` property returning the raw dict, and `max_candles_per_request: int`.
  - Thin call methods: `candles(name, timeframe, from_iso, count)`, `open_position(body, key)`, `close_position(position_id, key)`, `place_order(body, key)`, `cancel_order(order_id, key)`, `snapshot()`, `account()`, `deals(from_iso)`, `operation(operation_id)`.
  - `access_point: str`
  - `async def aclose(self)`.
- **Steps:**
  1. `request` builds `path_with_query` via `urlencode(query)` in the order the keys were inserted, signs it with the timestamp `int(time.time()*1000) + self._offset_ms`, and sends `self._http.request(method, "https://" + access_point + path_with_query, content=body_bytes, headers=...)`.
  2. After each response, update `_offset_ms` from the `Date` header.
  3. Raise `ExnessApiError(status, error_code, message)` on non-2xx. `error_code` comes from the public error model field `error.code`, or `code` when the shape differs; keep whatever the fixture shows.
  4. Limiter: per `api_operation_id`, a deque of timestamps. `acquire(op_id)` sleeps until `len < limit` within `window_seconds`. The global account rate applies to all calls. Each call method passes its operationId constant.
  5. The `operation_id` of mutations is returned from the ACK `{"operation_id","client_request_id","status":"accepted"}`.
  6. Tests use `httpx.MockTransport` that serves the fixtures (`access_point.json`, `limits.json`, `instruments.json`, `conditions_*.json`, `candles_*.json`). Assert that:
     - the request URL path, including the query, equals the signed `path` in the decoded `EXN-DATA`;
     - `instrument_name("XAUUSD")` returns the exact fixture name;
     - the limiter delays the (limit+1)th call when time is patched;
     - a 429 fixture raises `ExnessApiError` with `status == 429`.
- **Success criteria:** the tests pass; every function is ≤60 lines.
- **Verify:** `uv run pytest tests/core_test/infra/exness/test_client.py -q` exits 0; `uv run python scripts/code_metrics.py --list | grep "LONG .*exness"` prints nothing.

### Task 06.4: `mappers.py`
- **Goal:** pure translations live in one module.
- **Target files and symbols:**
  - `INTERVAL_TO_TIMEFRAME: dict[Interval, str]` = `{1m:"M1", 5m:"M5", 15m:"M15", 1h:"H1", 4h:"H4", 1d:"D1", 1w:"W1"}`
  - `candle_to_bar(candle: dict, symbol: str, interval: Interval) -> Bar`: bid OHLC; `volume=float(candle["volume"])`; `tick_count=int(candle["volume"])`; `datetime` parsed from `time` (ISO with offset) to UTC.
  - `tick_to_quote(tick: dict, symbol: str) -> dict`: `{"symbol", "last_price": bid, "bid", "ask", "timestamp": datetime, "volume": None}`
  - `units_to_lots(units, contract_size, step, vmin, vmax, cap) -> float`: `floor(units/contract_size/step)*step`; return 0.0 when that is 0; otherwise clamp to `[vmin, vmax]`, then to `min(cap or vmin, vmax)`.
  - `lots_to_units(lots, contract_size) -> float`
  - `price_str(price, point_digits) -> str`
- **Steps:** implement, and test against the fixtures (`candles_XAUUSD_M1.json` maps to bars whose count equals the fixture length, with ascending datetimes; the first ticks frame maps to a quote). Include a lot-rounding table test with at least 6 cases, including the zero and the cap.
- **Success criteria:** the tests pass; no lot or contract-size logic exists outside `core/infra/exness/`.
- **Verify:** `uv run pytest tests/core_test/infra/exness/test_mappers.py -q` exits 0; `git grep -n "contract_size\|volume_step" -- src/pocketquant/core/domain src/pocketquant/engine src/pocketquant/backtest` exits 1.

### Task 06.5: DRY the spike
- **Goal:** the spike uses the production signer.
- **Target files and symbols:** `scripts/exness_spike.py` `sign_headers`.
- **Steps:** replace its inline signing and key-loading code with calls to `pocketquant.core.infra.exness.signer.sign` and `load_private_key`.
- **Success criteria:** the script still parses and has no mutating call.
- **Verify:** re-run the Verify command from Phase 01 Task 01.2; it exits 0.

## Verification (phase gate)
- `just test` exits 0. `uv run ruff check` exits 0. `uv run pyright` prints `0 errors`. `uv run lint-imports | tail -1` prints `Contracts: 3 kept, 0 broken.`
- Commit with `feat(exness): add signed rest client, signer and mappers`. Merge after user approval. No runtime behaviour changes, because nothing is wired yet.

## Risks
- The signed path does not match because httpx re-encodes the URL (medium likelihood, high impact). The client test asserts that the URL equals the signed path, and the spike already exercised the real server.
- Unknown error-body shape (medium likelihood, low impact). Use the fixture shape; fall back to the raw text in the message.

## Security
- `SecretStr` values are read only inside `ExnessClient.__init__`. No `repr` of settings appears in logs. The fixtures are redacted.

## Rollback
- Revert the commit. The modules are unused by the app.

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

<!-- FILE: phase-07-exness-market-data-policy.md -->
---
phase: 7
title: "Exness market data, quotes, sync policy"
status: pending
priority: P1
effort: 3.5d
dependencies: [6]
---

# Phase 07: Exness market data, quotes, sync policy

## Context Links
- Ports: `src/pocketquant/core/domain/market_data/interfaces.py:18` (`IDataProvider`), `:40` (`IRealtimeQuoteProvider`, 9 members).
- Reconnect shape to reuse: `src/pocketquant/core/infra/binance/binance_websocket_client.py:97-147` (run_forever and backoff) and `okx_reconnection_handler.py:19-20` (circuit breaker: 10 failures → 300 s pause).
- Policy module: `src/pocketquant/engine/market_data/sync_policy.py` (Phase 03). DI: `src/pocketquant/app/di/adapters.py::AdaptersProvider.get_sync_policies` (Phase 04).
- Spike values: `reports/exness-spike-results.md` `## Gate` (`rate_budget_per_poll`, `closed_windows`, `ws_subprotocol_required`, `last_candle_in_progress`).

## Goal
`XAUUSD:EXNESS` bars sync through the shared runner (policy #2, no cascade), and ticks stream to Redis and SSE. Only adapters and one policy are added; no runner or job code changes.

## Files to Create or Modify
- Create: `src/pocketquant/core/infra/exness/websocket.py`, `data_provider.py`, `quote_provider.py`
- Create: `tests/core_test/infra/exness/test_websocket.py`, `test_data_provider.py`, `test_quote_provider.py`
- Modify: `src/pocketquant/engine/market_data/sync_policy.py` (add `exness_policy`, `EXNESS_CLOSED_WINDOWS`), `tests/engine_test/market_data/test_sync_policy.py`, `src/pocketquant/app/di/adapters.py`

## Tasks

### Task 07.1: `websocket.py` (shared stream skeleton)
- **Goal:** one signed WS stream class with reconnect, backoff and a circuit breaker.
- **Target files and symbols:** `class ExnessStream` with:
  - `__init__(self, client: ExnessClient, path: str, on_message: Callable[[dict], Awaitable[None]], on_connect: Callable[[], Awaitable[None]])`
  - `async def send(self, msg: dict)`
  - `async def run_forever(self)`, `async def close(self)`, `is_open() -> bool`
- **Steps:**
  1. Connect with `websockets.connect("wss://" + client.access_point + path, additional_headers=signer headers for GET path, subprotocols=["exness-ws-protocol"] if ws_subprotocol_required else None, ping_interval=20, ping_timeout=10)`. Sign every connect freshly.
  2. After the connection opens, call `on_connect()`; it re-sends the subscriptions.
  3. Backoff: 1 s doubling to 60 s, reset after a connection that lasted more than 60 s. After 10 consecutive failures, log `exness_ws.circuit_breaker_triggered` and sleep 300 s.
  4. HTTP 429 at the handshake counts as a failure. A message carrying `trading_disabled` logs `exness_ws.trading_disabled` and waits 60 s before the next connect.
  5. Do not add a tick-staleness watchdog. Liveness comes from protocol pings, so FX weekends do not cause reconnect loops.
  6. Tests use a local `websockets.serve` server on port 0. The client must receive and dispatch JSON, reconnect after the server closes, call `on_connect` again, and trip the breaker after 10 failed connects (patch `asyncio.sleep`).
- **Success criteria:** the tests pass; each function is ≤60 lines.
- **Verify:** `uv run pytest tests/core_test/infra/exness/test_websocket.py -q` exits 0.

### Task 07.2: `data_provider.py`
- **Goal:** `ExnessDataProvider(IDataProvider)` returns closed bid candles for any `n_bars`.
- **Target files and symbols:** `ExnessDataProvider.__init__(self, client)`, `fetch_ohlcv(symbol, interval, n_bars=1000)`, `search_symbols(query)`, `close()`.
- **Steps:**
  1. `name = client.instrument_name(symbol.split(":")[0])`, `tf = INTERVAL_TO_TIMEFRAME[interval]`.
  2. Page backwards. Start with `from = now ISO`. Request `count = -min(remaining, client.max_candles_per_request)`. The next page uses `from = oldest returned time`. Drop the duplicate boundary candle (`from` is inclusive). Stop when a page returns fewer candles than requested.
  3. Drop any candle with `time + interval > now` (the in-progress candle), as `binance_client.py:75-83` does.
  4. Map with `candle_to_bar(c, symbol.upper(), interval)`. Return the bars ascending.
  5. `search_symbols` returns `[{"symbol": f"{n.upper()}:EXNESS", "name": n}]` for instrument names that contain the query, case-insensitive. `close` calls `client.aclose()`.
  6. Tests use MockTransport with the fixture candles. Cover pagination across 2 pages with `max_candles_per_request` patched to 600, the in-progress drop, and ascending order.
- **Success criteria:** the tests pass.
- **Verify:** `uv run pytest tests/core_test/infra/exness/test_data_provider.py -q` exits 0.

### Task 07.3: `quote_provider.py`
- **Goal:** `ExnessQuoteProvider` satisfies `IRealtimeQuoteProvider` structurally.
- **Target files and symbols:** `ExnessQuoteProvider` with:
  - `last_tick_at`, `connect`, `disconnect`, `subscribe(symbol, callback) -> str`, `unsubscribe(symbol)`, `run_forever`, `is_connected`
  - properties `subscription_count`, `subscriptions`
- **Steps:**
  1. Hold an `ExnessStream` on `/v1/server-events/accounts/{id}/ws/ticks`.
  2. `subscribe` stores `{composite: (exact_name, callback)}`. If the stream is open, send `{"id": f"ticks-{name}", "subscribe": {"event": "ticks", "instruments": [name]}}`.
  3. `on_connect` re-sends one subscribe message listing all instrument names.
  4. `unsubscribe` sends `{"id": ..., "unsubscribe": {"event": "ticks", "instruments": [name]}}`, using the shape recorded in the spike fixture. If the fixture shows no unsubscribe shape, remove the entry locally and re-subscribe the rest on the next connect.
  5. `on_message`: for a frame with `instrument`/`bid`/`ask`, set `last_tick_at = now` and call the callback with `tick_to_quote(frame, composite)`.
  6. Tests:
     - `isinstance(ExnessQuoteProvider(client), IRealtimeQuoteProvider)` is true.
     - Feeding the first `ticks_sample.jsonl` frame calls the callback with `last_price == bid`.
- **Success criteria:** the tests pass.
- **Verify:** `uv run pytest tests/core_test/infra/exness/test_quote_provider.py -q` exits 0.

### Task 07.4: Exness policy and DI wiring
- **Goal:** policy #2 is registered only when Exness is configured.
- **Target files and symbols:**
  - `sync_policy.py`: `EXNESS_CLOSED_WINDOWS: dict[str, tuple[WeeklyWindow, ...]]` (literals copied from `## Gate`, keyed by the uppercased instrument code); `exness_policy(bar_source, live_source, rate_budget_per_poll: int) -> SyncPolicy`
  - `adapters.py`: `@provide(scope=Scope.APP) def get_exness_client(self, settings) -> ExnessClient`; `get_sync_policies(self, settings, exness: ExnessClient)`
- **Steps:**
  1. `exness_policy` returns `SyncPolicy(exchange="EXNESS", ...)` with:
     - `poll_intervals=(MINUTE_1, MINUTE_5, MINUTE_15, HOUR_1, HOUR_4, DAY_1)`, `cascade_intervals=()`, and `history_intervals` = the same six
     - `poll_every_minutes=1`, `poll_n_bars=100`, `rate_budget_per_poll=<arg>`
     - `backfill_n_bars={MINUTE_1:50000, MINUTE_5:20000, MINUTE_15:20000, HOUR_1:20000, HOUR_4:10000, DAY_1:5000}`
     - `history_depth_days={MINUTE_1:365, MINUTE_5:730, MINUTE_15:1095}` (spec depth table)
     - `closed_windows=EXNESS_CLOSED_WINDOWS`
  2. Add the constant `EXNESS_RATE_BUDGET_PER_POLL = <spike value>` next to `EXNESS_CLOSED_WINDOWS`.
  3. `get_sync_policies`:
     - always include `binance_policy(...)`;
     - if `exness.configured`, `await exness.start()` inside `try/except Exception` (make the provider method `async`); on failure log `exness.start_failed` with `error=str(exc)` and leave Exness out, so an Exness outage never blocks app startup or Binance;
     - on success append `exness_policy(ExnessDataProvider(exness), ExnessQuoteProvider(exness), EXNESS_RATE_BUDGET_PER_POLL)`;
     - return `SyncPolicies(tuple(...), fallback="BINANCE")`.
  4. `ExnessClient.aclose` is called on container close. Use a generator provider: `yield client` then `await client.aclose()`.
  5. Tests in `test_sync_policy.py`:
     - `for_symbol("XAUUSD:EXNESS").exchange == "EXNESS"`;
     - the closed window contains Saturday 12:00 UTC for the XAUUSD code;
     - `backfill_bars(MINUTE_1) == 50000`;
     - `for_symbol("BTCUSDT:BINANCE")` is unchanged.
- **Success criteria:** with no Exness env, the container builds exactly as before; with Exness env, two policies exist.
- **Verify:** `uv run pytest tests/engine_test/market_data/test_sync_policy.py tests/baseline tests/app_test/integration/test_sync_pipeline_characterization.py -q` exits 0 (the golden files are unchanged because Exness is unconfigured in tests).

### Task 07.5: Deploy and prove D1 on prod (market hours, stop-and-ask before the push)
- **Goal:** Exness bars and streams work end to end.
- **Target files and symbols:** prod app; `reports/exness-spike-results.md` section `## D1`.
- **Steps:**
  1. Gate, merge and deploy after user approval (CI `success`, `(19/19 passed`).
  2. Add the tracked symbol: `ssh -i "$KEY" "$HOST" 'docker exec pocketquant-app sh -c "curl -s -X POST http://localhost:41921/api/v1/market-data/tracked-symbols -H \"Content-Type: application/json\" -H \"X-Admin-Token: \$ADMIN_TOKEN\" -d \"{\\\"symbol\\\":\\\"XAUUSD:EXNESS\\\"}\""'`. Repeat for `EURUSD:EXNESS` and `BTCUSD:EXNESS`.
  3. Sync: `ssh ... 'docker exec pocketquant-app curl -s -X POST http://localhost:41921/api/v1/market-data/sync -H "Content-Type: application/json" -d "{\"symbol\":\"XAUUSD:EXNESS\",\"interval\":\"1m\",\"n_bars\":1000,\"source\":\"bulk_sync_api\"}"' > /tmp/d1-sync.json`.
  4. SSE (market hours only): `ssh ... 'docker exec pocketquant-app curl -sN --max-time 70 "http://localhost:41921/api/v1/market-data/bars/stream/XAUUSD%3AEXNESS?interval=1m"' | grep -m1 -c '"is_in_progress": true'`, and `ssh ... 'docker exec pocketquant-app curl -sN --max-time 20 http://localhost:41921/api/v1/quotes/stream/XAUUSD%3AEXNESS' | grep -m1 -c '"last_price"'`.
  5. Record the outputs under `## D1`.
- **Success criteria:** D1 holds.
- **Verify:**
  - `uv run python -c "import json;d=json.load(open('/tmp/d1-sync.json'));assert d['status']=='completed' and d['total_bars']>=1000"` exits 0.
  - Both SSE greps print `1`.
  - `ssh ... 'docker logs pocketquant-app --since 15m 2>&1 | grep -c "market_data.sync_1m.symbol_failed"'` prints `0`.

## Verification (phase gate)
- `just test` exits 0. `uv run ruff check` exits 0. `uv run pyright` prints `0 errors`. `uv run lint-imports | tail -1` prints `Contracts: 3 kept, 0 broken.`
- Before Task 07.1, append `PRE_P07_SHA=<git rev-parse HEAD>` to `reports/baseline-gates.md`. At the gate, `git diff --quiet $PRE_P07_SHA -- src/pocketquant/engine/market_data/sync_runner.py src/pocketquant/engine/market_data/sync_service.py` exits 0. Adding Exness needed no runner or service change.

## Risks
- Rate limits are tighter at runtime than in the spike (medium likelihood, medium impact). The client limiter self-paces, the policy budget truncates with a log, and if `sync.rate_budget_exhausted` appears every minute the stop condition for A-v applies.
- The ticks WS rejects when `trading_disabled` (low likelihood, low impact). It is logged and backs off 60 s.
- Weekend FX polling produces no-progress noise (medium likelihood, low impact). Closed windows skip polling; `poll_n_bars=100` refills the 60-minute widening margin automatically after the open.

## Security
- Exness credentials stay in the container env. Curl commands with the admin token expand `$ADMIN_TOKEN` only inside the container.

## Rollback
- Unset `EXNESS_*` in `pocketquant-config` and redeploy; the policy disappears and Binance runs unchanged. To also remove the data, call `DELETE /api/v1/market-data/tracked-symbols/{symbol}` for the three symbols and run, inside Mongo, `db.bars.deleteMany({symbol: /:EXNESS$/})` (user approval required).

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

<!-- FILE: phase-08-exness-broker.md -->
---
phase: 8
title: "Exness broker and async fill wiring"
status: pending
priority: P1
effort: 3.5d
dependencies: [7]
---

# Phase 08: Exness broker and async fill wiring

## Context Links
- Port: `src/pocketquant/core/domain/brokers/interfaces.py:94` (`IBroker`). Value objects: `src/pocketquant/core/domain/brokers/value_objects.py:182` (`OrderResult`), `:210` (`AccountBalance`).
- Fill path today:
  - `src/pocketquant/engine/app_services/order_app_service.py:34` (`submit`); the `else` branch at `:88-96` calls `order.submit()`
  - `:174` (`on_order_update`), which handles only FILLED and CANCELLED and is never subscribed for live brokers today (no `subscribe_order_updates` call in `src/pocketquant/engine` or `src/pocketquant/app`)
- Synthetic-exit pattern to mirror: `src/pocketquant/core/infra/brokers/paper/paper_broker.py:671-718` (publishes `OrderFilledEvent` on the bus).
- Broker selection: `src/pocketquant/engine/app_services/strategy_app_service.py:96` (`load_strategy`), `:409` (`_get_or_create_broker`); subscriptions always build `StrategyConfig` with the default `broker="paper"` (`main_extensions.py:152-157`, `strategy_reconcile_service.py:140-147`).
- Dedupe pattern: `okx_broker.py:59` (`_seen_terminal_orders`).
- Position mapping to mirror: `okx_mapper.py:63` (`map_okx_position_to_domain`).

## Goal
`ExnessBroker` executes market and limit entries at minimum lot with SL attached. It maps async `transaction_event` fills to `OrderResult`, publishes SL/TP closes as `OrderFilledEvent`, and refuses unsafe orders. The engine accepts async fills safely. No live order is placed in this phase.

## Files to Create or Modify
- Create: `src/pocketquant/core/infra/exness/broker.py`, `tests/core_test/infra/exness/test_broker.py`, `tests/engine_test/test_order_app_service_async_fill.py`, `tests/engine_test/test_strategy_live_broker_selection.py`
- Modify: `src/pocketquant/engine/app_services/order_app_service.py`, `src/pocketquant/engine/app_services/strategy_app_service.py`, `src/pocketquant/app/di/adapters.py` (`BrokerFactory`), `src/pocketquant/app/di/services.py` (StrategyAppService factory), `src/pocketquant/core/config.py`

## Tasks

### Task 08.1: Safety settings
- **Goal:** live-risk caps are configuration, and live trading is off by default.
- **Target files and symbols:** `Settings`: `exness_live_trading: bool = False`, `exness_max_lots: float | None = None`, `exness_daily_loss_cap_pct: float | None = None`.
- **Steps:** add the fields after the Phase 06 Exness block.
- **Success criteria:** the defaults are safe.
- **Verify:** no verification needed (covered by the tests in Task 08.3).

### Task 08.2: Engine accepts async fills
- **Goal:** a fill or reject that arrives before or after the REST ACK leaves the order in the right terminal state exactly once.
- **Target files and symbols:** `OrderAppService.submit` (else branch) and `OrderAppService.on_order_update`; `tests/engine_test/test_order_app_service_async_fill.py`.
- **Steps:**
  1. In `submit`'s non-FILLED success branch, call `order.submit(result.broker_order_id)` only when `order.status == OrderStatus.PENDING`, and save the order when its status is already FILLED or REJECTED.
  2. In `on_order_update`:
     - Before `order.fill(...)`, add `if order.status == OrderStatus.PENDING: order.submit(result.broker_order_id)`.
     - Add an `elif result.status == OrderStatus.REJECTED:` branch: `order.reject(result.error_message or "rejected")`, save, pop from `_pending`.
     - Add `logger.info("order_updated_async", order_id=..., status=...)`.
  3. Tests:
     - (a) The callback fires during `broker.submit_order` (before the ACK returns): the order ends FILLED and exactly one `OrderFilledEvent` is published.
     - (b) The callback fires after `submit` returns SUBMITTED: FILLED, one event.
     - (c) An async REJECTED leaves the order rejected and not pending.
     - (d) A PaperBroker immediate fill is unchanged (existing `tests/engine_test/test_order_app_service_immediate_fill.py` passes).
- **Success criteria:** the new and existing order tests pass.
- **Verify:** `uv run pytest tests/engine_test/test_order_app_service_async_fill.py tests/engine_test/test_order_app_service_immediate_fill.py tests/engine_test/test_order_filled_event_routing.py -q` exits 0.

### Task 08.3: `broker.py`
- **Goal:** `ExnessBroker(IBroker)` implements the port with the CFD logic contained inside it.
- **Target files and symbols:** `class ExnessBroker` with:
  - `__init__(self, client, event_bus, cache, order_updates: OrderCallback, max_lots: float | None, daily_loss_cap_pct: float | None)`
  - properties `name -> "exness"` and `is_connected`
  - `connect`, `disconnect`, `submit_order`, `cancel_order`, `get_positions`, `get_balance`, `subscribe_order_updates`, `unsubscribe_order_updates`
  - private `_on_event(msg)`, `_guard(order) -> str | None`
- **Steps:**
  1. `connect`: start an `ExnessStream` on `/v1/server-events/accounts/{id}/ws/events` whose `on_connect` sends `{"id":"tx","subscribe":{"event":"transactions"}}`. Set `self._order_callbacks = [order_updates]`.
  2. `_guard(order)` returns a reject reason or `None`, in this order:
     - `daily_loss_cap_pct is None` → `"exness daily loss cap not configured"`
     - `order.sl_price is None` → `"stop loss required"`
     - a cached position exists for `order.subscription_id` (Redis key `exness:sub:{subscription_id}`) → `"position already open for subscription"`
     - the daily loss reached: `realized = sum(profit+commission)` of deals since UTC midnight from `client.deals(from_iso)`, `unrealized = equity - balance`, and `-(realized + unrealized) >= daily_loss_cap_pct/100 * balance` → `"daily loss cap reached"`
  3. `submit_order`:
     - If `_guard` returns a reason, return `OrderResult(order_id=str(order.id), broker_order_id="", status=REJECTED, error_message=reason)`.
     - `cond = await client.conditions(name)`. `lots = units_to_lots(order.quantity, contract_size, step, vmin, vmax, max_lots)`. If `lots == 0`, return REJECTED `"rounded lot is zero"`.
     - Body: `{"instrument": name, "side": "buy"|"sell", "volume": f"{lots}", "stop_loss_price": price_str(sl, point_digits), "take_profit_price": price_str(tp, point_digits)}`, omitting `take_profit_price` when it is `None`. MARKET goes to `open_position`. LIMIT goes to `place_order` with `{"type": "limit", "price": price_str(order.price, d), ...}`; take the field names from the `NewPendingOrderRequest` schema in the spec.
     - The idempotency key is `str(order.id)`.
     - Store `self._ops[operation_id] = (order_id, subscription_id, symbol, side, contract_size)`.
     - Return `OrderResult(status=SUBMITTED, broker_order_id=operation_id, submitted_at=now, sl_price, tp_price, side)`.
  4. `_on_event`:
     - `transaction_event`: skip if `operation_id` is in `self._seen_terminal`, then add it. Correlate by `client_request_id` or `operation_id`.
       - `status == "success"` with a deal `type == "open"`: build `OrderResult(FILLED, filled_quantity=lots_to_units(deal volume), filled_price=float(deal price), side)`. Write Redis `exness:pos:{position_id}` and `exness:sub:{subscription_id}` with `{subscription_id, symbol, units, side}` and `ttl=2592000`. Notify the callbacks.
       - `status in {"rejected", "failed"}`: notify REJECTED with `error_message=f"{error_code}: {error_message}"`.
       - A deal `type == "close"` for a cached `position_id`: publish `OrderFilledEvent(order_id=generate_id_str(), subscription_id, symbol, side=opposite, filled_quantity=units, filled_price=float(deal price))` on the event bus, then delete both Redis keys.
     - `trading_state_snapshot`: delete Redis entries whose position is not in the snapshot.
     - `hmr_snapshot` / `hmr_update`: `logger.warning("exness.hmr", ...)`.
     - Any other type: `logger.debug`.
  5. `get_positions` reads from `client.snapshot()` and maps to `PositionAggregate` the way `map_okx_position_to_domain` does, with units `= lots_to_units`. `get_balance` returns `AccountBalance(total_equity=equity, available_balance=equity-used_margin, currency=<account currency from client.account()>, margin_used=used_margin, unrealized_pnl=equity-balance)`. `cancel_order(op)` looks up the Exness order id from `self._ops` and calls `client.cancel_order`, returning `False` if it is unknown.
  6. Tests use a fake client and a fake events feed built from the spike `events_first_message.json` plus spec examples (`tradingTransactionEvent`, `sltpTransactionEvent`). Assert:
     - each `_guard` reason;
     - lots are clamped to the min lot when `max_lots` is None;
     - an async FILLED reaches the callback once even when delivered twice;
     - a close deal publishes one `OrderFilledEvent` with the opposite side;
     - the idempotency key equals the order id;
     - no request is sent when `_guard` rejects.
- **Success criteria:** the tests pass; every function is ≤60 lines; lot logic stays in `core/infra/exness`.
- **Verify:** `uv run pytest tests/core_test/infra/exness/test_broker.py -q` exits 0; `uv run python scripts/code_metrics.py --list | grep "LONG .*exness"` prints nothing.

### Task 08.4: Factory and broker selection
- **Goal:** the `exness` broker type exists, and `:EXNESS` subscriptions use it only when `EXNESS_LIVE_TRADING=true`.
- **Target files and symbols:**
  - `BrokerFactory.__init__(self, event_bus, cache: Cache, order_app_service: OrderAppService, exness: ExnessClient, settings: Settings)`; `create("exness", config)`
  - `StrategyAppService.__init__(..., live_broker_by_exchange: dict[str, str] | None = None)`; `load_strategy`
  - the `services.py` StrategyAppService factory
- **Steps:**
  1. In `create("exness", ...)`: if `not exness.configured`, raise `ValueError("Exness broker requires EXNESS_* settings")`. Otherwise return `ExnessBroker(exness, event_bus, cache, order_app_service.on_order_update, settings.exness_max_lots, settings.exness_daily_loss_cap_pct)`.
  2. In `load_strategy`: `broker_type = self._live_brokers.get(config.symbol.rsplit(":", 1)[-1].upper(), config.broker)`, then pass it to `_get_or_create_broker(broker_type)`, then `logger.info("strategy_broker_selected", strategy_id=config.id, symbol=config.symbol, broker=broker.name)`.
  3. The services factory passes `live_broker_by_exchange={"EXNESS": "exness"} if settings.exness_live_trading else {}`.
  4. Tests:
     - With the flag off, an `XAUUSD:EXNESS` strategy gets a `PaperBroker`.
     - With the flag on, it gets `"exness"` from a fake factory.
     - `BTCUSDT:BINANCE` always gets paper.
- **Success criteria:** the tests pass; the OKX characterization is unchanged.
- **Verify:** `uv run pytest tests/engine_test/test_strategy_live_broker_selection.py tests/core_test/infra/brokers/test_okx_characterization.py tests/engine_test/test_reconcile_restart_resume_integration.py -q` exits 0.

## Verification (phase gate)
- `just test` exits 0. `uv run ruff check` exits 0. `uv run pyright` prints `0 errors`. `uv run lint-imports | tail -1` prints `Contracts: 3 kept, 0 broken.`
- `git grep -n "contract_size\|volume_step\|lots" -- src/pocketquant/core/domain` exits 1.
- Commit with `feat(exness): add exness broker with async fills and live-risk guards`. Merge and deploy after user approval. In prod `EXNESS_LIVE_TRADING` is still unset, so no live order is possible.

## Risks
- Duplicate or missed fills (medium likelihood, high impact). Mitigated by idempotency key = order id, the terminal dedupe set, the engine PENDING guard, and snapshot reconciliation on reconnect.
- A server-side SL/TP close is not mirrored after a restart (low likelihood, medium impact). The mapping is in Redis with a 30-day TTL and is reconciled from `trading_state_snapshot`.
- A hedging account opens a second position (medium likelihood, high impact). `_guard` refuses when the subscription already has an open position.
- Live money is used unintentionally (low likelihood, high impact). Off by default; a reject without the loss cap; SL is mandatory; the lot is capped at min lot.

## Security
- The broker logs operation ids and error codes only, never request headers.

## Rollback
- Revert the merge commit. The live flag stays off, so no live state exists yet.

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

<!-- FILE: phase-09-spread-backfill-backtests.md -->
---
phase: 9
title: "Spread parameter, backfill, backtests"
status: pending
priority: P1
effort: 2d
dependencies: [8]
---

# Phase 09: Spread parameter, backfill, backtests

## Context Links
- PaperBroker fills: `src/pocketquant/core/infra/brokers/paper/paper_broker.py:93` (`__init__`), `:436` (`_apply_slippage`), used in `_handle_market` `:199`, `_handle_limit` `:261`, `_fill_pending_on_bar` `:617`, `_fire_synthetic_exit` `:678`.
- Backtest config path:
  - `src/pocketquant/backtest/backtest_command_service.py:22` (`RunBacktestCommand`), `:59-69` (config dict)
  - `src/pocketquant/backtest/workers/backtest_dispatch.py:51`, `:94`
  - `src/pocketquant/backtest/engine/backtest_engine_sandbox.py:113-119`
  - `src/pocketquant/backtest/engine/backtest_app_service.py:102`
  - `src/pocketquant/backtest/engine/result_collector.py:432-442`
  - `src/pocketquant/backtest/models/backtest_config.py:24-34`
- Backtest API: `POST /api/v1/backtest/run` returns `{"request_id"}`. `GET /api/v1/backtest/{run_id}` has a `status` of `started|finished|failed` (`core/domain/backtest/entities.py:33`). `GET /api/v1/backtest/{run_id}/trades` returns `{"items", "next_cursor"}`.

## Goal
CFD backtests pay the spread. Exness M1 and H1 history exists for the three instruments, and both strategies have stored backtests on Exness bars (D3).

## Files to Create or Modify
- Modify: `paper_broker.py`, `backtest_config.py`, `backtest_command_service.py`, `backtest_dispatch.py`, `backtest_engine_sandbox.py`, `backtest_app_service.py`, `result_collector.py`
- Create: `tests/core_test/infra/brokers/test_paper_broker_spread.py`
- Modify (intentional contract change): `tests/baseline/openapi_app_snapshot.json`
- Create: `plans/261009-0858-exness-venue-lean-sync-refactor/reports/exness-backtests.md`

## Tasks

### Task 09.1: Constant spread in PaperBroker
- **Goal:** BUY fills at `price + spread/2` and SELL fills at `price - spread/2`, before slippage. The default of 0 changes nothing.
- **Target files and symbols:** `PaperBroker.__init__(..., spread: float = 0.0)`, `PaperBroker._apply_slippage`.
- **Steps:**
  1. Store `self.spread = spread`.
  2. In `_apply_slippage`, first add `half = self.spread / 2`, then `price = price + half` for BUY or `price - half` for SELL, then apply the existing slippage.
  3. Tests: with `spread=0.4`, a market BUY at close 100 fills at 100.2 and a SELL at 99.8 (slippage 0); a synthetic SL exit SELL fills at `sl - 0.2`; with `spread=0`, fills equal the existing characterization (`paper_broker_fills_characterization_test.py` passes unchanged).
- **Success criteria:** the spread tests pass and the paper characterization is unchanged.
- **Verify:** `uv run pytest tests/core_test/infra/brokers -q` exits 0; `git diff --quiet $BASE_SHA -- tests/core_test/infra/brokers/paper_broker_fills_characterization_test.py` exits 0.

### Task 09.2: Spread in the backtest config path
- **Goal:** `POST /backtest/run` accepts `spread`, and it reaches the broker and the persisted config.
- **Target files and symbols:** the seven sites listed in Context Links.
- **Steps:**
  1. `RunBacktestCommand.spread: float = Field(default=0.0, ge=0, description="Constant bid/ask spread in price units")`.
  2. Add `"spread": cmd.spread` to the config dict.
  3. `BacktestConfig.spread: float = 0.0`, appended after `parameters` (non-default field order stays valid).
  4. `backtest_dispatch`: `spread=payload.get("spread", 0.0)` and pass it to the sandbox.
  5. Sandbox: pass `spread=spread` to `PaperBroker`.
  6. `backtest_app_service`: `self._broker.spread = config.spread` next to the slippage line.
  7. `result_collector` `config_snapshot`: add `"spread": self._config.spread`.
  8. Regenerate the OpenAPI snapshot: `BASELINE_UPDATE=1 uv run pytest tests/baseline/test_openapi_snapshot.py -q`.
- **Success criteria:** the only OpenAPI difference is the new property.
- **Verify:** `uv run python -c "import json,subprocess;old=json.loads(subprocess.check_output(['git','show','HEAD:tests/baseline/openapi_app_snapshot.json']));new=json.load(open('tests/baseline/openapi_app_snapshot.json',encoding='utf-8'));p=new['components']['schemas']['RunBacktestCommand']['properties'];assert 'spread' in p;del p['spread'];assert old==new"` exits 0; `just test` exits 0.

### Task 09.3: Backfill Exness history on prod (stop-and-ask before the merge)
- **Goal:** M1 and H1 history exists for XAUUSD, EURUSD and BTCUSD.
- **Target files and symbols:** prod `bars` collection; the `sync_backfill` job.
- **Steps:**
  1. Merge and deploy Tasks 09.1-09.2 after user approval.
  2. Wait for the 03:00 UTC `sync_backfill` run. Alternatively, the catch-up enqueues it automatically when the last success is older than 25 h.
  3. Query `ssh ... 'docker exec pocketquant-app curl -s "http://localhost:41921/api/v1/market-data/sync-status/XAUUSD%3AEXNESS?interval=1m"'` and the same for `interval=1h`, then for EURUSD and BTCUSD. Record the `bar_count` values in `reports/exness-backtests.md`.
- **Success criteria:** every `1m` `bar_count >= 40000` and every `1h` `bar_count >= 5000`.
- **Verify:** the six recorded `bar_count` values meet these thresholds; `ssh ... 'docker logs pocketquant-app --since 26h 2>&1 | grep -c "market_data.sync_backfill.completed"'` prints ≥1.

### Task 09.4: Backtests on Exness bars (D3)
- **Goal:** both strategies have finished runs with trades.
- **Target files and symbols:** `POST /api/v1/backtest/run`; `reports/exness-backtests.md`.
- **Steps:**
  1. For each instrument code `C` in (XAUUSD, EURUSD, BTCUSD), take `S` = the median spread recorded in `## Gate` of `exness-spike-results.md`. Submit `{"strategy_id":"hitnrun2","symbol":"C:EXNESS","interval":"1m","start_date":<now-30d ISO>,"end_date":<now ISO>,"initial_capital":10000,"slippage_bps":0,"commission_bps":0,"spread":S}` and `{"strategy_id":"engulfing","symbol":"C:EXNESS","interval":"1h","start_date":<now-365d ISO>,...same...}`.
  2. Poll `GET /api/v1/backtest/{run_id}` every 10 s until `status != "started"`.
  3. Record one Markdown row per run in `reports/exness-backtests.md`, exactly in the form `| <strategy> | <symbol> | <status> | <trade_count> | <run_id> |`. `trade_count` is `len(items)` from `GET /api/v1/backtest/{run_id}/trades?limit=50`.
- **Success criteria:** all 6 runs are `finished`, and for each strategy at least one run has `trade_count > 0`.
- **Verify:** all three commands below must pass. Set `R=plans/261009-0858-exness-venue-lean-sync-refactor/reports/exness-backtests.md` first.
  - `grep -cE "^\| (hitnrun2|engulfing) \| [A-Z]+:EXNESS \| finished \|" $R` prints `6`.
  - `grep -cE "^\| hitnrun2 \| [A-Z]+:EXNESS \| finished \| [1-9]" $R` prints ≥1.
  - `grep -cE "^\| engulfing \| [A-Z]+:EXNESS \| finished \| [1-9]" $R` prints ≥1.

## Verification (phase gate)
- `just test` exits 0. `uv run ruff check` exits 0. `uv run pyright` prints `0 errors`. `uv run lint-imports | tail -1` prints `Contracts: 3 kept, 0 broken.`
- Commit with `feat(backtest): add constant spread parameter to paper broker fills`.

## Risks
- The spread makes the backtests unprofitable (expected; informational). Results are recorded honestly and the decision stays with the user. Annualization uses a 365-day year, which overstates FX metrics; this is noted in the report.
- Exness depth or rate limits slow the backfill (medium likelihood, low impact). The limiter paces requests; the next daily run continues.

## Rollback
- Revert the commit, then regenerate the snapshot from the reverted code with `BASELINE_UPDATE=1`. The stored backtest runs stay as records.

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

<!-- FILE: phase-10-live-validation.md -->
---
phase: 10
title: "Live min-lot round trip and week observation"
status: pending
priority: P1
effort: 2d + 1 week market time
dependencies: [9]
---

# Phase 10: Live min-lot round trip and week observation

## Context Links
- Subscription API: `POST /api/v1/strategies/{strategy_code}/subscriptions` with body `{"symbol","interval"}` (`src/pocketquant/app/routes/strategy.py:69`), `POST /api/v1/subscriptions/{sub_id}/start` and `/stop` (`:112`, `:121`, router prefix `/subscriptions` at `:99`).
- Trading state: `GET /api/v1/trading/orders`, `GET /api/v1/trading/positions` (`src/pocketquant/app/routes/trading_orders_positions.py`).
- Log events: `signal_processed`, `order_submitted`, `order_updated_async` (Phase 08), `exness_ws.circuit_breaker_triggered`, `integrity.issues_found`.

## Goal
One minimum-lot live round trip per strategy on Exness, with SL attached, and one week including a weekend close and reopen observed (D2 and the after-one-week metric).

## Files to Create or Modify
- Create: `plans/261009-0858-exness-venue-lean-sync-refactor/reports/live-validation-results.md`
- No code changes.

## Tasks

### Task 10.1: Live gate (stop-and-ask)
- **Goal:** the user's risk cap is in place, and the user explicitly approves live trading.
- **Target files and symbols:** prod env (read-only check); `live-validation-results.md`.
- **Steps:**
  1. Ask the user to set `EXNESS_LIVE_TRADING=true` and `EXNESS_DAILY_LOSS_CAP_PCT=<value>`, and to leave `EXNESS_MAX_LOTS` unset (min lot only), in `pocketquant-config/vps/default/.env`, then redeploy.
  2. Check that the variables are present without printing them: `ssh ... 'docker exec pocketquant-app sh -c "test \"\$EXNESS_LIVE_TRADING\" = true && test -n \"\$EXNESS_DAILY_LOSS_CAP_PCT\" && test -z \"\$EXNESS_MAX_LOTS\" && echo ok"'`.
  3. Ask: "Start live min-lot subscriptions hitnrun2 on XAUUSD:EXNESS 1m and engulfing on XAUUSD:EXNESS 1h?" STOP until the user answers yes. If the user wants a lot size above minimum, STOP (stop condition: a live order would exceed min lot).
- **Success criteria:** the check prints `ok` and the user's "yes" is recorded.
- **Verify:** the ssh command prints `ok`; `grep -c "user approved live" plans/261009-0858-exness-venue-lean-sync-refactor/reports/live-validation-results.md` prints `1`.

### Task 10.2: Start the subscriptions
- **Goal:** both strategies run live on Exness.
- **Target files and symbols:** the subscription API.
- **Steps:**
  1. Create the subscriptions: `ssh ... 'docker exec pocketquant-app sh -c "curl -s -X POST http://localhost:41921/api/v1/strategies/hitnrun2/subscriptions -H \"Content-Type: application/json\" -H \"X-Admin-Token: \$ADMIN_TOKEN\" -d \"{\\\"symbol\\\":\\\"XAUUSD:EXNESS\\\",\\\"interval\\\":\\\"1m\\\"}\""'`. Record the returned `id`. Do the same for `engulfing` with `1h`.
  2. Start each: `POST /api/v1/subscriptions/{id}/start` with the same headers.
  3. Within 30 s the reconcile loop loads both strategies (`reconcile_interval_seconds` is 5 by default).
- **Success criteria:** both subscriptions are running against the Exness broker.
- **Verify:**
  - `ssh ... 'docker exec pocketquant-app curl -s http://localhost:41921/api/v1/subscriptions/' | uv run python -c "import json,sys;s=json.load(sys.stdin);assert sum(1 for x in s if x.get('symbol')=='XAUUSD:EXNESS' and x.get('actual_state')=='running')==2"` exits 0.
  - `ssh ... 'docker logs pocketquant-app --since 5m 2>&1 | grep strategy_broker_selected | grep -c "XAUUSD:EXNESS.*exness"'` prints `2`.

### Task 10.3: Observe the fill and close per strategy (D2)
- **Goal:** each strategy completes one round trip.
- **Target files and symbols:** `live-validation-results.md` with one row per strategy: submit time, ACK `operation_id`, fill time, lot, SL, close reason and time, PnL.
- **Steps:**
  1. Watch `docker logs pocketquant-app --since 1h | grep -E "signal_processed|order_submitted|order_updated_async|exness.hmr"` every hour during market hours.
  2. On the first `order_updated_async status=filled` per subscription, compute the fill latency (fill time minus `order_submitted` time). Check `GET /api/v1/trading/positions` for the position.
  3. Wait for the SL/TP close: the position disappears from Exness `snapshot` and a strategy reset occurs (a new signal is possible).
  4. After both round trips, stop both subscriptions (`POST /api/v1/subscriptions/{id}/stop`).
  5. If any order shows a lot above min or a missing SL in the Exness snapshot, STOP and ask the user (stop condition).
- **Success criteria:** two rows, each with latency ≤10 s, the position seen, and a close recorded.
- **Verify:** `grep -cE "^\| (hitnrun2|engulfing) \| .* \| filled \| [0-9.]+s \| min-lot \| sl=" plans/261009-0858-exness-venue-lean-sync-refactor/reports/live-validation-results.md` prints `2`, and every recorded latency value is ≤10.

### Task 10.4: One-week observation, including a weekend
- **Goal:** the after-one-week success metric holds.
- **Target files and symbols:** `live-validation-results.md` section `## Week`.
- **Steps:**
  1. After seven days that include Friday close through Sunday open, run on the VPS:
     - `docker logs pocketquant-app --since 168h 2>&1 | grep -c exness_ws.circuit_breaker_triggered`
     - `... | grep -c "exness_ws.reconnecting"`
     - `... | grep "integrity.issues_found" | grep -cE "XAUUSD:EXNESS|EURUSD:EXNESS"`
  2. Record the BTCUSD weekend tick count from the Saturday spike run (Phase 01 Task 01.3 step 5) if it is still pending.
- **Success criteria:** zero breaker trips, no FX weekend integrity alarms, and reconnects only with backoff (no more than 1 per 5 minutes on average).
- **Verify:** the breaker count is `0`, the FX integrity count is `0`, and the reconnect count is ≤2016 (7 days × 288); all three are recorded under `## Week`.

## Verification (phase gate)
- `just test` exits 0 (unchanged code).
- `live-validation-results.md` contains the D2 rows and the `## Week` section.

## Risks
- A live loss (certain to be non-zero; impact bounded). Min lot, SL attached, the daily loss cap and a two-trade scope bound it.
- No signal fires during the window (medium likelihood, low impact). Extend the observation; do not change strategy parameters (that is out of scope).

## Security
- All commands run inside the container, and secrets expand there. Nothing is pasted into reports except ids, prices and times.

## Rollback
- Stop the subscriptions. Close any open Exness position from the Exness platform (user). Set `EXNESS_LIVE_TRADING=false` and redeploy.

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

<!-- FILE: phase-11-docs-final-gate.md -->
---
phase: 11
title: "Architecture and deployment docs, final gate"
status: pending
priority: P2
effort: 1d
dependencies: [10]
---

# Phase 11: Architecture and deployment docs, final gate

## Context Links
- `docs/system-architecture.md`:
  - line 3 (summary), `:7` High-Level Architecture, `:255` Layer 4 Adapters, `:455` Where Does X Live?, `:553` Real-Time Streaming, `:563` Known issues, `:604` Dependency Injection, `:702` Configuration, `:710` Known Limitations
- `docs/deployment.md`: env table at `:83-95`.
- `CLAUDE.md`, section "Writing docs & prose" (Vietnamese prose, AS-IS, a Mermaid or ASCII diagram for 2+ interacting parts).

## Goal
The architecture doc shows the Exness adapters, the sync-policy pattern and the MT5 future provider (D7). The deployment doc lists the new env vars. A final full check proves D4-D6.

## Files to Create or Modify
- Modify: `docs/system-architecture.md`, `docs/deployment.md`
- Create: `plans/261009-0858-exness-venue-lean-sync-refactor/reports/final-gate.md`

## Tasks

### Task 11.1: `system-architecture.md`
- **Goal:** the doc describes the system as it now is.
- **Target files and symbols:** the sections listed in Context Links.
- **Steps:**
  1. Summary line and High-Level diagram: add `Exness REST+WS`.
  2. Layer 4: add `core/infra/exness/` with its seven files and one line of purpose each.
  3. Add a `## Sync policy pattern` section with a Mermaid v11 diagram: `SyncPolicies → SyncPolicy(BINANCE | EXNESS) → sync_runner.run_sync_job → SyncService`. Include a field table and the fallback-to-BINANCE rule.
  4. Where Does X Live?: add `sync_policy.py`, `sync_runner.py`, the Exness adapter and the broker.
  5. Real-Time Streaming: add the Exness ticks stream and the events stream (no tick-staleness watchdog; ping liveness). Replace "Binance `@aggTrade` (singleton...)" with a per-policy live source.
  6. DI: describe the three modules and `STRICT_VALIDATION`.
  7. Add a short `## MT5 (future provider, not built)` section: the same three ports; policy sketch: `copy_rates_from` as bar source, `copy_ticks_from` as live source; needs a Windows host or a Wine bridge; out of the current deployment.
  8. Known Limitations: in-memory exness position mapping is backed by Redis TTL 30 d; holidays may produce FX integrity gaps; `is_stuck` badges ignore market hours; OKX live fills are still not subscribed into `OrderAppService`.
  9. Remove any references to `sync_jobs.py`, `cascade_aggregator.py`, `integrity_jobs.py` and `sync_internals`.
- **Success criteria:** D7 holds; no stale module names remain.
- **Verify:** `grep -cE "core/infra/exness|SyncPolicy|MT5" docs/system-architecture.md` prints ≥3; `grep -cE "sync_jobs|cascade_aggregator|integrity_jobs|sync_internals" docs/system-architecture.md` prints `0`; `grep -c '```mermaid' docs/system-architecture.md` is ≥ its value at BASE_SHA + 1.

### Task 11.2: `deployment.md` env table
- **Goal:** operators know the new keys.
- **Target files and symbols:** the env table at `docs/deployment.md:83-95`.
- **Steps:** add rows for `EXNESS_ACCOUNT_ID`, `EXNESS_API_KEY`, `EXNESS_PRIVATE_KEY` / `EXNESS_PRIVATE_KEY_PATH`, `EXNESS_DISCOVERY_URL` (default `https://api.exness.com`), `EXNESS_LIVE_TRADING` (default false), `EXNESS_MAX_LOTS` (unset means min lot), and `EXNESS_DAILY_LOSS_CAP_PCT` (live orders refused while unset). Note that the key is IP-allowlisted to the VPS.
- **Success criteria:** all seven keys appear.
- **Verify:** `grep -cE "EXNESS_(ACCOUNT_ID|API_KEY|PRIVATE_KEY|DISCOVERY_URL|LIVE_TRADING|MAX_LOTS|DAILY_LOSS_CAP_PCT)" docs/deployment.md` prints ≥7.

### Task 11.3: Final gate
- **Goal:** D4-D6 are proven on the final code.
- **Target files and symbols:** `reports/final-gate.md`.
- **Steps:** run each command below and paste its last line into `final-gate.md`:
  - `just test`
  - `uv run ruff check`
  - `uv run pyright`
  - `uv run lint-imports | tail -1`
  - `uv run python scripts/code_metrics.py`
  - `ls src/pocketquant/app/di/*.py`
  - `ls src/pocketquant/app/routes | grep market_data`
  - `test -d src/pocketquant/engine/market_data/sync_internals; echo $?`
  - `uv run pytest tests/core_test/infra/binance -q | tail -1`
  - `git diff --quiet $BASE_SHA -- tests/core_test/infra/binance; echo $?`
  - after the merge, the CI conclusion and the `(19/19 passed` grep
- **Success criteria:**
  - all gates pass;
  - the metric is within the thresholds the user confirmed in Task 04.9;
  - 3 provider modules plus `__init__.py`;
  - 2 market-data route files;
  - `sync_internals` is absent (echo prints `1`);
  - the Binance pass count equals the baseline and the Binance diff echo prints `0`;
  - CI shows `success` and `(19/19 passed`.
- **Verify:** `grep -c "Contracts: 3 kept, 0 broken.\|19/19 passed" plans/261009-0858-exness-venue-lean-sync-refactor/reports/final-gate.md` prints `2`, and every other line in `final-gate.md` matches its listed expectation.

## Verification (phase gate)
- Commit with `docs(architecture): document exness venue, sync policies and mt5 path`. Merge after user approval.

## Risks
- Docs drift into change-narrative ("now", "previously") (medium likelihood, low impact). `grep -ciE "previously|no longer|trước đây" docs/system-architecture.md docs/code-standards.md` must print `0`.

## Rollback
- Revert the docs commit.

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
