<!-- FILE: plan.md -->
---
title: "Exness venue + lean sync-policy refactor"
description: "Spike Exness, refactor the market-data sync into per-provider SyncPolicy + one runner (Binance first), add Exness REST/WS adapters, validate, document."
status: pending
priority: P1
effort: 32d
branch: master
tags: [exness, market-data, sync, refactor, broker, code-standards]
blockedBy: []
blocks: []
created: 2026-10-09
---

# Exness venue + lean sync-policy refactor

## Overview
Add Exness as a third live venue behind the existing ports (`IDataProvider`, `IRealtimeQuoteProvider`, `IBroker`) after a balanced refactor: one `SyncPolicy` per provider consumed by one shared runner, three DI modules, two market-data route files, three import-linter contracts and a rewritten `docs/code-standards.md`. Binance, OKX, PaperBroker, `hitnrun2`, `engulfing` stay. MT5 is documented only; no MCP; no deployment-topology change. Source: advice report `D:/w/_me/algotrading/plans/reports/advise-261008-1148-exness-api-replacement.md` (sections 2, 5, 9).

## Goals
- G1: Exness is a usable live venue alongside Binance/OKX (data, quotes, orders, positions).
- G2: a provider = one adapter package + one policy object; any flow readable in ≤3 files.
- G3: a standard the code actually follows, enforced by ruff, 3 import-linter contracts and a soft metric gate.

## Phases
| # | Phase | Effort | Depends on |
|---|-------|--------|------------|
| 01 | [Exness read-only spike and baseline gate](./phase-01-exness-read-only-spike.md) | 2d | user preconditions |
| 02 | [Characterization tests and metric gate](./phase-02-characterization-tests-and-metrics.md) | 2d | 01 |
| 03 | [Consolidate DI, routes, wrappers and contracts](./phase-03-consolidate-di-routes-and-contracts.md) | 3d | 02 |
| 04 | [Sync policy and shared runner (Binance)](./phase-04-sync-policy-and-shared-runner.md) | 5d | 03 |
| 05 | [Lean code standard and burn-down](./phase-05-lean-code-standard-and-burn-down.md) | 2d | 04 |
| 06 | [Exness signer, client and streams](./phase-06-exness-signer-client-and-streams.md) | 4d | 01, 05 |
| 07 | [Exness market data and sync policy](./phase-07-exness-market-data-and-sync-policy.md) | 3d | 06 |
| 08 | [Exness broker and live order flow](./phase-08-exness-broker-and-live-order-flow.md) | 5d | 07 |
| 09 | [Validation: spread, backtests, live round trip](./phase-09-validation-spread-backtests-live.md) | 5d + 1 weekend | 08, risk cap |
| 10 | [Architecture, deployment and MT5 docs; final gate](./phase-10-architecture-deployment-docs.md) | 1d | 09 |

## Dependencies
- Strictly sequential (each phase edits files the next one reads). One branch per phase, merged to `master` only on user approval (a push to `master` deploys prod via `.github/workflows/cicd.yml`).
- Exness phases (06-09) need the phase-01 fixtures and `reports/exness-spike-summary.json`.

## User preconditions (the executor gates on these, never performs them)
1. Developer Portal link followed from Exness Personal Area resolves to `exness-api.com` (gate: phase 01).
2. Scoped API key (one account, IP allowlist incl. the VPS and the machine that runs the spike) stored in `pocketquant-config` and local `.env` as `EXNESS_ACCOUNT_ID`, `EXNESS_API_KEY`, `EXNESS_PRIVATE_KEY` (or `EXNESS_PRIVATE_KEY_PATH`) (gate: phases 01, 07).
3. Live-test risk cap set: minimum lot, SL always attached, daily loss cap % (gate: phase 09).
4. Docker running locally (tests use testcontainers); `../pocketquant-config` checked out for prod verification.
Never print, log or commit key material.

## Success criteria (D1-D7, measurable)
- D1 `POST /api/v1/market-data/sync` `{"symbol":"XAUUSD:EXNESS","interval":"1m","n_bars":1000,"source":"bulk_sync_api"}` (real body: composite symbol, `source` required) → `status=="completed"`, `total_bars >= 1000`; `GET /api/v1/market-data/bars/stream/XAUUSD%3AEXNESS?interval=1m` emits `"is_in_progress": true` within 60 s in market hours; `GET /api/v1/quotes/stream/XAUUSD%3AEXNESS` emits a payload.
- D2 One min-lot live order per strategy reaches `FILLED` via the events WS within 10 s of ACK and appears in `GET /api/v1/trading/positions`.
- D3 `hitnrun2` and `engulfing` backtests on Exness bars persist to `backtest_runs` with non-empty trades; `PaperBroker` has `spread`.
- D4 `engine/market_data/sync_internals/` absent; `app/di` holds `__init__.py` + 3 modules; market-data routes in 2 files; `scripts/code_metrics.py` reports `tiny_share<=30`, `pure_delegation<=20`.
- D5 `docs/code-standards.md` rewritten, no stale status claims; `uv run lint-imports` → 3 contracts kept, 0 broken.
- D6 Binance/OKX tests green; `just test`, `uv run ruff check`, `uv run pyright`, `uv run lint-imports` green; CI deploy green with `11-verify.sh` verdict `0 failures`.
- D7 `docs/system-architecture.md` shows Exness adapters, sync-policy pattern, MT5 future provider.
- After one live week: reconnects logged with backoff, zero `exness_stream.circuit_open`, no FX weekend integrity alarms.

## Metric baseline note
The interview script behind "48% / 63" was not saved. Phase 02 commits `scripts/code_metrics.py` with explicit definitions; at commit `29f2f67` it reports `functions=614 tiny=205 tiny_share=33.4 pure_delegation=24`. Thresholds stay as confirmed (≤30, ≤20). See unresolved questions in the planner report.

<!-- FILE: phase-01-exness-read-only-spike.md -->
---
phase: 1
title: "Exness read-only spike and baseline gate"
status: pending
priority: P1
effort: 2d
dependencies: []
---

# Phase 01: Exness read-only spike and baseline gate

## Goal
Settle assumptions A-i..A-v with real Exness responses, record the rate budget, and capture fixtures for adapter tests, without touching `src/`. Record a green baseline gate.

## Context Links
- Spec: `https://www.exness-api.com/exness_api.yaml` (v1.0.2). Signing: `EXN-DATA` = base64url (no `=`) of JSON `{api_key, idempotency_key, timestamp, sign_version, method, path, body_hash}`; `EXN-SIGN` = Ed25519 over the decoded bytes; `body_hash` = base64url SHA-256 of body (empty body → `47DEQpj8HBSa-_TImW-5JCeuQeRkm5NMpJWZG3hSuFU`); GET sends `EXN-IDEMPOTENCY-KEY` empty.
- Host discovery: `GET https://api.exness.com/v1/trading/access-point?account_id={id}` → `{"access_point": "<host>", "account_id": n}`. WS: `wss://<host>` + path, subprotocol `exness-ws-protocol`, signed GET headers in the upgrade request (portal code examples).
- Endpoints used: `/v1/configuration/accounts/{id}/limits`, `/instruments`, `/instruments/{i}/conditions`, `/v1/market-data/accounts/{id}/candles` (`instrument`, `timeframe`, `from`, `count` (negative = backwards), `price_type=bid`), WS `/v1/server-events/accounts/{id}/ws/ticks`.

## Files to Create or Modify
- Create: `scripts/exness_spike.py`, `tests/core_test/infra/exness/fixtures/*.json`, `docs/journals/2026-10-09-exness-api-spike.md` (date = day of the run), `plans/261009-0858-exness-venue-lean-sync-refactor/reports/gate-baseline.txt`, `plans/261009-0858-exness-venue-lean-sync-refactor/reports/exness-spike-summary.json`.
- Modify: `pyproject.toml`, `uv.lock` (add `cryptography`), `scripts/README.md`.

## Tasks

### T1.1 User precondition gate
- Goal: confirmed portal domain and credentials present without exposing them.
- Target: local `.env`, `.gitignore:56` (`.env`).
- Steps:
  1. Ask the user: "Confirm (a) the Developer Portal link from Exness Personal Area resolves to exness-api.com, (b) a scoped API key exists whose IP allowlist includes this machine and the VPS, (c) EXNESS_ACCOUNT_ID, EXNESS_API_KEY and EXNESS_PRIVATE_KEY (or EXNESS_PRIVATE_KEY_PATH) are in the local .env." Wait for an explicit yes to all three.
  2. **Stop and ask** if the user reports the portal link does not resolve to `exness-api.com`; do nothing else in this plan.
- Success criteria: user said yes to (a), (b), (c).
- Verify: `git check-ignore -q .env; echo $?` prints `0`; `grep -c '^EXNESS_ACCOUNT_ID=.' .env` prints `1`; `grep -c '^EXNESS_API_KEY=.' .env` prints `1`; `grep -cE '^EXNESS_PRIVATE_KEY(_PATH)?=.' .env` prints `1` or more. Never `cat` the file.

### T1.2 Baseline gate
- Goal: prove the suite is green before any change.
- Target: `.venv`, `justfile:40-41` (`test`), `pyproject.toml` tool config.
- Steps:
  1. `git checkout master && git pull --ff-only && git checkout -b feat/exness-spike`.
  2. `uv sync`; `docker info > /dev/null` (Docker must be running).
  3. Run `just test 2>&1 | tail -3`, `uv run ruff check`, `uv run pyright 2>&1 | tail -1`, `uv run lint-imports 2>&1 | tail -3` and append each output to `plans/261009-0858-exness-venue-lean-sync-refactor/reports/gate-baseline.txt`.
- Success criteria: all four commands exit 0; baseline pass count recorded.
- Verify: `grep -c "passed" plans/261009-0858-exness-venue-lean-sync-refactor/reports/gate-baseline.txt` ≥ 1; file contains `0 errors` and `7 kept, 0 broken`; none of the four commands returned non-zero.

### T1.3 Add the Ed25519 dependency
- Goal: `cryptography` is a direct dependency (it is already in `uv.lock` transitively at 46.0.4).
- Target: `pyproject.toml` `[project].dependencies`.
- Steps: `uv add "cryptography>=46.0"`.
- Success criteria: dependency line present; import works.
- Verify: `grep -c '"cryptography>=46.0"' pyproject.toml` prints `1`; `uv run python -c "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey"` exits 0.

### T1.4 Write `scripts/exness_spike.py` (read-only)
- Goal: one script that signs requests, discovers the host, reads limits/instruments/conditions/candles, holds the ticks WS, writes scrubbed fixtures and a summary.
- Target: new `scripts/exness_spike.py`. Only GET requests and the ticks WS; no trading endpoints.
- Steps:
  1. Read env (never print): `EXNESS_ACCOUNT_ID`, `EXNESS_API_KEY`, `EXNESS_PRIVATE_KEY` or file at `EXNESS_PRIVATE_KEY_PATH`, `EXNESS_BASE_URL` (default `https://api.exness.com`), `EXNESS_WS_BASE_URL` (default `wss://<access_point>`), `EXNESS_INSTRUMENT_SUFFIX` (default empty). Load `.env` by parsing `KEY=VALUE` lines yourself if the vars are not in `os.environ`.
  2. Key loading: strip; replace literal `\n` with newline; if it starts with `-----BEGIN` use `serialization.load_pem_private_key(..., password=None)`; else if 64 hex chars use `bytes.fromhex`; else base64 (standard or urlsafe, pad `=`); if decoded length is 64 keep the first 32 bytes; build `Ed25519PrivateKey.from_private_bytes(seed)`. Error messages must not contain key text. Record `key_format` (`pem`|`hex`|`base64`) in the summary.
  3. Signing — use exactly this function (it moves into `src` in phase 06):
     ```python
     def _b64url(data: bytes) -> str:
         return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

     def sign_headers(*, api_key, private_key, method, path_with_query, body, idempotency_key, timestamp_ms):
         payload = {
             "api_key": api_key,
             "idempotency_key": idempotency_key,
             "timestamp": timestamp_ms,
             "sign_version": 1,
             "method": method.upper(),
             "path": path_with_query,
             "body_hash": _b64url(hashlib.sha256(body).digest()),
         }
         data = json.dumps(payload, separators=(",", ":")).encode()
         return {
             "EXN-API-KEY": api_key,
             "EXN-IDEMPOTENCY-KEY": idempotency_key,
             "EXN-TIMESTAMP": str(timestamp_ms),
             "EXN-SIGN-VERSION": "1",
             "EXN-DATA": _b64url(data),
             "EXN-SIGN": _b64url(private_key.sign(data)),
         }
     ```
     Build `path_with_query` with `urllib.parse.urlencode(params)` once and send that exact string (`httpx.AsyncClient.get(base + path_with_query, headers=...)`). Clock offset: from the first response's `Date` header (`email.utils.parsedate_to_datetime`), `offset_ms = server - local`; every later timestamp = local ms + offset.
  4. Calls in order, saving each JSON body: access point (save only `{"access_point_host_suffix": host.split(".",1)[1]}`), `limits`, `instruments`, `conditions` for `XAUUSD`, `EURUSD`, `BTCUSD` (+ suffix), candles: `XAUUSD` M1 `from=<now UTC ISO>` `count=-1000` (paginate backwards by `max_candles_per_request` if smaller); `XAUUSD`, `EURUSD`, `BTCUSD` H4 and D1 `count=-30`; M1 for each instrument from last Friday 18:00 UTC `count=+N` up to Monday 02:00 UTC (paginate) for the weekend-gap analysis. Try candles against the access-point host first, then `EXNESS_BASE_URL`; record which host answered.
  5. Ticks WS: `websockets.connect(ws_base + path, subprotocols=["exness-ws-protocol"], additional_headers=sign_headers(... method="GET", path_with_query=path, body=b"", idempotency_key="" ...), ping_interval=20, ping_timeout=20)`; send `{"id":"ticks-1","subscribe":{"event":"ticks","instruments":[...3 names...]}}`; read for `--ticks-seconds` (default 600); keep the first 20 raw frames; count frames per instrument; compute median inter-arrival ms.
  6. Scrub before writing: replace the account id string everywhere with `123456`; drop any key named `balance`, `equity`, `used_margin`, `api_key`. Write fixtures to `tests/core_test/infra/exness/fixtures/`: `limits.json`, `instruments.json`, `conditions_xauusd.json`, `conditions_eurusd.json`, `conditions_btcusd.json`, `candles_xauusd_m1.json`, `candles_xauusd_h4.json`, `candles_xauusd_d1.json`, `candles_weekend_m1_<instrument>.json`, `ticks_frames.json`.
  7. Write `plans/261009-0858-exness-venue-lean-sync-refactor/reports/exness-spike-summary.json` with keys: `key_format`, `clock_offset_ms`, `candles_host` (`access_point`|`base`), `global_rate` (`limit`, `window_seconds`), `candle_rate` (rate of `api_operation_id == "getCandleHistory"`), `open_position_rate` (`openPosition`), `max_candles_per_request`, `history_range_days`, `instrument_names` (the 3 names), `conditions` (per instrument: `contract_size`, `volume_min`, `volume_max`, `volume_step`, `point_digits`, `exec_mode`, `trade_mode`, `trade_sessions`), `m1_count`, `last_candle_in_progress` (last `time` ≥ floor(now,1m)), `negative_count_includes_from`, `h4_aligned_utc`, `d1_aligned_utc` (every `time` on the UTC 4h / 00:00 grid), `weekend_gaps` (per instrument: list of `[start,end]` M1 gaps > 5 min), `ws_handshake_ok`, `ticks_per_instrument`, `tick_median_ms`, `tick_frame_shape` (sorted keys of the first tick frame).
  8. Print only the summary JSON. Never print headers, key, or env.
- Success criteria: script lints clean and never calls a non-GET endpoint.
- Verify: `uv run ruff check scripts/exness_spike.py` exits 0; `grep -cE '\.(post|put|patch|delete)\(' scripts/exness_spike.py` prints `0`.

### T1.5 Run the spike
- Goal: real numbers and fixtures.
- Steps: `uv run python scripts/exness_spike.py --ticks-seconds 600` during FX market hours on the allowlisted machine.
- Success criteria: exit 0; summary + fixtures exist; no secret in any written file.
- Verify: `ls tests/core_test/infra/exness/fixtures/ | wc -l` ≥ 10; `test -s plans/261009-0858-exness-venue-lean-sync-refactor/reports/exness-spike-summary.json && echo ok` prints `ok`; `grep -rIl -- "$(grep '^EXNESS_API_KEY=' .env | cut -d= -f2-)" tests scripts docs plans | wc -l` prints `0`; `grep -rIl -- "$(grep '^EXNESS_ACCOUNT_ID=' .env | cut -d= -f2-)" tests docs plans | wc -l` prints `0`.

### T1.6 Feasibility decision for policy A-v
- Goal: confirm "WS ticks live + REST native candles each minute, no cascade" fits the limits.
- Steps: from the summary compute `peak_calls_per_min = 3 instruments × 6 timeframes = 18` (00:00 UTC, when M1..D1 all close) and `budget_per_min = min(candle_rate.limit, global_rate.limit) × 60 / window_seconds`.
- Success criteria (all true): `peak_calls_per_min ≤ 0.5 × budget_per_min`; `max_candles_per_request ≥ 100`; `h4_aligned_utc` and `d1_aligned_utc` true; `ws_handshake_ok` true and every instrument `ticks_per_instrument ≥ 1`; `trade_sessions` non-empty for XAUUSD and EURUSD.
- **Stop and ask** if any criterion is false (Exness limits/behaviour make policy A-v infeasible). Report the failing values.
- Verify: write the five checks with values and PASS/FAIL into the journal (T1.7); every line reads `PASS`.

### T1.7 Journal note and scripts index
- Goal: numbers recorded for later phases.
- Target: `docs/journals/2026-10-09-exness-api-spike.md` (use the run date), `scripts/README.md`.
- Steps: write the journal in Vietnamese prose (English technical terms), containing the T1.6 table, instrument names, `EXNESS_INSTRUMENT_SUFFIX` value to use, candle host, tick cadence, key format, weekend gaps. Add one bullet for `exness_spike.py` to `scripts/README.md` ("read-only, ghi fixtures").
- Verify: `grep -c "PASS" docs/journals/2026-10-*-exness-api-spike.md` ≥ 5; `grep -c "exness_spike.py" scripts/README.md` prints `1`.

### T1.8 Commit and ship
- Steps: `git add scripts/exness_spike.py scripts/README.md tests/core_test/infra/exness/fixtures docs/journals pyproject.toml uv.lock` then `git commit -m "chore(scripts): add read-only Exness API spike with recorded fixtures"`. Ask the user to approve merge+push; on yes: `git checkout master && git merge --ff-only feat/exness-spike && git push origin master`; `RUN_ID=$(gh run list --branch master --limit 1 --json databaseId -q '.[0].databaseId'); gh run watch "$RUN_ID" --exit-status`.
- Verify: `gh run watch` exits 0; `gh run view "$RUN_ID" --log | grep -m1 "=== Verdict:"` contains `0 failures`.

## Risks
| Risk | L×I | Mitigation |
|------|-----|------------|
| Key leaks into fixtures/logs | M×H | scrub step + T1.5 grep checks; summary-only stdout |
| IP allowlist excludes dev machine | M×M | T1.1 asks explicitly; else run on an allowlisted host |
| Limits make A-v infeasible | L×H | T1.6 stop-and-ask before any adapter code |

## Security
Read-only endpoints only. Secrets come from env only. `.env` stays ignored.

## Rollback
`git revert` the spike commit and push (CI redeploys). Nothing in `src/` changed.

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

<!-- FILE: phase-02-characterization-tests-and-metrics.md -->
---
phase: 2
title: "Characterization tests and metric gate"
status: pending
priority: P1
effort: 2d
dependencies: [1]
---

# Phase 02: Characterization tests and metric gate

## Goal
Pin today's sync behaviour through surfaces that survive the refactor (registered APScheduler jobs, HTTP responses, `BrokerFactory`), and commit the metric script plus a soft CI step. No production code changes.

## Context Links
- Jobs today: `src/pocketquant/engine/market_data/app_services/sync_jobs.py:663` `register_sync_jobs` (5 cron jobs `sync_1m`, `sync_verify_cascade`, `sync_backfill`, `sync_integrity`, `sync_repair`), `:54` `SYNC_INTERVALS`, `:382` `sync_1m` (1m × 100 bars + cascade), `:609` `sync_backfill` (5000 bars × 7 intervals).
- Test app: `tests/app_test/integration/app_factory.py:66` `make_test_app(settings)`; `settings` fixture `tests/app_test/conftest.py:16` (`enable_jobs=False`).
- Snapshot convention: `tests/baseline/test_openapi_snapshot.py` (`BASELINE_UPDATE=1` rewrites).

## Files to Create or Modify
- Create: `scripts/code_metrics.py`, `tests/scripts/test_code_metrics.py`, `tests/app_test/integration/test_sync_pipeline_characterization.py`, `tests/app_test/integration/sync_pipeline_snapshot.json`, `tests/engine_test/test_broker_factory_characterization.py`.
- Modify: `.github/workflows/cicd.yml`, `scripts/README.md`.

## Tasks

### T2.1 Create `scripts/code_metrics.py`
- Goal: reproducible function-shape metrics.
- Steps: `git checkout -b refactor/characterization` from `master`. Create the file with exactly this content:
  ```python
  """Function-shape metrics for the lean code standard (soft CI gate).

  Counted functions exclude declarations: stub bodies (docstring, ``...``, ``pass``),
  @property / .setter, @abstractmethod, dunder methods and route handlers.
  tiny: a counted function whose body holds at most 2 statements, counted
  recursively (leading docstring and nested defs excluded).
  pure delegation: any non-route function whose only statement returns or evaluates
  one (optionally awaited) call on an attribute, passing only its own parameters.
  """

  from __future__ import annotations

  import argparse
  import ast
  import sys
  from pathlib import Path

  ROUTE_VERBS = {"get", "post", "put", "delete", "patch"}
  FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


  def _is_docstring(stmt: ast.stmt) -> bool:
      return (
          isinstance(stmt, ast.Expr)
          and isinstance(stmt.value, ast.Constant)
          and isinstance(stmt.value.value, str)
      )


  def _is_route(fn: FunctionNode) -> bool:
      return any(
          ast.unparse(d).split("(")[0].rsplit(".", 1)[-1] in ROUTE_VERBS for d in fn.decorator_list
      )


  def _is_declaration(fn: FunctionNode) -> bool:
      stub = all(
          _is_docstring(s)
          or isinstance(s, ast.Pass)
          or (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and s.value.value is ...)
          for s in fn.body
      )
      decorators = [ast.unparse(d) for d in fn.decorator_list]
      marked = any(
          d.endswith("property") or d.endswith(".setter") or "abstractmethod" in d
          for d in decorators
      )
      dunder = fn.name.startswith("__") and fn.name.endswith("__")
      return stub or marked or dunder or _is_route(fn)


  def _statement_count(fn: FunctionNode) -> int:
      count = 0
      for stmt in fn.body:
          if _is_docstring(stmt):
              continue
          for node in ast.walk(stmt):
              if isinstance(node, ast.stmt) and not isinstance(
                  node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
              ):
                  count += 1
      return count


  def _is_pure_delegation(fn: FunctionNode) -> bool:
      body = [s for s in fn.body if not _is_docstring(s)]
      if len(body) != 1 or not isinstance(body[0], (ast.Return, ast.Expr)) or _is_route(fn):
          return False
      value = body[0].value
      if isinstance(value, ast.Await):
          value = value.value
      if not isinstance(value, ast.Call) or not isinstance(value.func, ast.Attribute):
          return False
      if "super()" in ast.unparse(value.func):
          return False
      params = {a.arg for a in [*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs]}
      params -= {"self", "cls"}
      args = [*value.args, *(k.value for k in value.keywords)]
      return all(isinstance(a, ast.Name) and a.id in params for a in args)


  def measure(root: Path) -> dict[str, list[str]]:
      found: dict[str, list[str]] = {"counted": [], "tiny": [], "delegation": []}
      for path in sorted(root.rglob("*.py")):
          tree = ast.parse(path.read_text(encoding="utf-8"))
          for node in ast.walk(tree):
              if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                  continue
              where = f"{path.relative_to(root).as_posix()}:{node.lineno} {node.name}"
              if _is_pure_delegation(node):
                  found["delegation"].append(where)
              if _is_declaration(node):
                  continue
              found["counted"].append(where)
              if _statement_count(node) <= 2:
                  found["tiny"].append(where)
      return found


  def main() -> int:
      parser = argparse.ArgumentParser()
      parser.add_argument("--root", default="src/pocketquant")
      parser.add_argument("--max-tiny-share", type=float, default=30.0)
      parser.add_argument("--max-delegation", type=int, default=20)
      parser.add_argument("--list", choices=["tiny", "delegation"])
      args = parser.parse_args()
      found = measure(Path(args.root))
      share = round(100 * len(found["tiny"]) / max(len(found["counted"]), 1), 1)
      if args.list:
          print("\n".join(found[args.list]))
      print(f"functions={len(found['counted'])}")
      print(f"tiny={len(found['tiny'])}")
      print(f"tiny_share={share}")
      print(f"pure_delegation={len(found['delegation'])}")
      ok = share <= args.max_tiny_share and len(found["delegation"]) <= args.max_delegation
      print(f"status={'PASS' if ok else 'FAIL'}")
      return 0 if ok else 1


  if __name__ == "__main__":
      sys.exit(main())
  ```
- Success criteria: baseline reproduced on unchanged `src/`.
- Verify: `uv run python scripts/code_metrics.py` prints `functions=614`, `tiny=205`, `tiny_share=33.4`, `pure_delegation=24`, `status=FAIL` and exits `1`. If numbers differ, Failure Protocol (do not edit the script to match).

### T2.2 Unit test for the metric script
- Target: `tests/scripts/test_code_metrics.py` (imports `from scripts.code_metrics import measure`, as `tests/scripts/test_audit_bar_quality.py:18` does).
- Steps: write a test that writes this source to `tmp_path / "pkg" / "m.py"`, calls `measure(tmp_path / "pkg")` and asserts `len(found["counted"]) == 4`, `len(found["tiny"]) == 3`, `len(found["delegation"]) == 2` (verified against the script: `forward`, `helper`, `fwd` are tiny; `forward`, `fwd` are delegations; `p` and `route` are not counted):
  ```python
  class A:
      @property
      def p(self):
          return 1
      def forward(self, x):
          return self.dep.call(x)
      def helper(self):
          y = 1
          return y
      def big(self, x):
          a = x + 1
          b = a * 2
          return a + b
  @router.get("/x")
  async def route(svc):
      return await svc.list()
  def fwd(svc, q):
      return svc.find(q)
  ```
- Verify: `.venv/Scripts/python.exe -m pytest tests/scripts/test_code_metrics.py -q` exits 0.

### T2.3 Soft CI step
- Target: `.github/workflows/cicd.yml` job `tests`, after step `Check import contracts (layered architecture)`.
- Steps: insert
  ```yaml
        - name: Code shape metrics (soft gate)
          continue-on-error: true
          run: uv run python scripts/code_metrics.py
  ```
  Add a bullet for `code_metrics.py` to `scripts/README.md`.
- Verify: `grep -n "continue-on-error: true" .github/workflows/cicd.yml` prints one line directly under the new step name; `grep -c "code_metrics.py" scripts/README.md` prints `1`.

### T2.4 Sync pipeline characterization (jobs)
- Goal: observable job behaviour pinned in a JSON snapshot that must stay byte-identical through phases 03-05.
- Target: `tests/app_test/integration/test_sync_pipeline_characterization.py`, snapshot `tests/app_test/integration/sync_pipeline_snapshot.json`.
- Steps:
  1. Fake provider: `monkeypatch.setattr(BinanceClient, "fetch_ohlcv", fake)` (`pocketquant.core.infra.binance.binance_client.BinanceClient`). `fake(self, symbol, interval, n_bars=1000)` appends `[symbol, interval.value, n_bars]` to a module list `CALLS` and returns `min(n_bars, 50)` closed bars: open times `floor(now, interval) - k*interval` for `k = 50..1`, prices `100+k`, `volume=1.0`, `Bar(symbol=symbol.upper(), interval=interval, datetime=..., open=..., high=...+1, low=...-1, close=..., volume=1.0)`. Use `INTERVAL_SECONDS` from `pocketquant.core.domain.shared.value_objects`; for `1w` use Monday 00:00 UTC weekly steps.
  2. Fixture `jobs_app`: `s = settings.model_copy(update={"enable_jobs": True})`; `app = make_test_app(s)`; `async with app.router.lifespan_context(app):` get `container = app.state.dishka_container`, `scheduler = await container.get(JobScheduler)`, call `scheduler._scheduler.pause()`, clear collections with `await (await container.get(Repo))._collection().delete_many({})` for `BarRepository`, `JobHistoryRepository`, `TrackedSymbolRepository`, `SyncStatusRepository`; upsert `TrackedSymbol(symbol="BTCUSDT:BINANCE", seeded_from="test")`; `CALLS.clear()`; yield `(container, scheduler)`.
  3. Helper `run(job_id)`: `job = scheduler._scheduler.get_job(job_id)`; `CALLS.clear()`; `await job.func(*job.args, **job.kwargs)`; return `list(CALLS)`.
  4. Build one observation dict:
     - `"jobs"`: `{job.id: {"trigger": str(job.trigger), "misfire_grace_time": job.misfire_grace_time} for job in scheduler._scheduler.get_jobs() if not job.id.endswith("_catchup")}`.
     - For each of `sync_1m`, `sync_backfill`, `sync_verify_cascade`, `sync_integrity`, `sync_repair` (run in that order, clearing the four collections and re-seeding the tracked symbol before each): `"calls"` = returned list; `"history"` = `{k: v for k, v in (await history_repo.get_latest_by_job_ids([job_id]))[job_id].items() if k in ("status", "total_inserted", "total_fetched")}`.
     - After `sync_1m` also: `"bars_1m"` = `await bar_repo.count("BTCUSDT:BINANCE", Interval.MINUTE_1)`, `"cascade_written"` = sorted interval values in `5m,15m,1h,4h,1d` whose count > 0, `"bars_1w"` = count for `1w`.
  5. Compare `json.dumps(obs, sort_keys=True, indent=2) + "\n"` with the snapshot file; if `os.environ.get("BASELINE_UPDATE") == "1"` write it first (same pattern as `tests/baseline/test_openapi_snapshot.py`).
  6. Generate once: `BASELINE_UPDATE=1 .venv/Scripts/python.exe -m pytest tests/app_test/integration/test_sync_pipeline_characterization.py -q`, then inspect the JSON: `sync_1m.calls == [["BTCUSDT:BINANCE","1m",100]]`, `sync_backfill.calls` has 7 entries with `5000`, `sync_verify_cascade.calls == [["BTCUSDT:BINANCE","5m",12]]`.
- Success criteria: snapshot committed; second run without the env var passes.
- Verify: `.venv/Scripts/python.exe -m pytest tests/app_test/integration/test_sync_pipeline_characterization.py -q` exits 0 (without `BASELINE_UPDATE`); `grep -c '"sync_1m"' tests/app_test/integration/sync_pipeline_snapshot.json` ≥ 1.

### T2.5 Sync route characterization
- Target: same test file, using the `app_client` fixture (`tests/app_test/integration/conftest.py:21`).
- Steps: with the same fake, `POST /api/v1/market-data/sync` body `{"symbol":"BTCUSDT:BINANCE","interval":"1m","n_bars":10,"source":"bulk_sync_api"}`; store in the snapshot under `"route_sync"` the response JSON minus `last_bar_at`, plus `"last_bar_at_is_str": isinstance(...)`; regenerate with `BASELINE_UPDATE=1` once.
- Verify: test passes without the env var; snapshot `route_sync.status == "completed"` and `bars_synced == 10`.

### T2.6 BrokerFactory characterization (pins the OKX/paper construction path the DI move touches)
- Target: `tests/engine_test/test_broker_factory_characterization.py`; class today at `src/pocketquant/app/di/broker_factory.py:7`.
- Steps: import via `from pocketquant.app.di.broker_factory import BrokerFactory` (the only line phase 03 changes). Assert: `create("paper", {})` → `PaperBroker` with `.name == "paper"` and `.slippage == 0.001`; `create("okx", {"api_key":"k","api_secret":"s","passphrase":"p"})` → `OKXBroker` with `.name == "okx-demo"` (do not call `connect`); `create("okx", {})` raises `ValueError`; `create("x", {})` raises `ValueError`.
- Verify: `.venv/Scripts/python.exe -m pytest tests/engine_test/test_broker_factory_characterization.py -q` exits 0.

### T2.7 Gate, commit, ship
- Steps: run the gate (below); commit `test: pin sync pipeline and broker factory behaviour; add code metrics script`; ask user to approve merge+push; on yes merge `--ff-only` into `master`, push, watch run.
- Gate: `just test` exit 0; `uv run ruff check` exit 0; `uv run pyright` output contains `0 errors`; `uv run lint-imports` contains `7 kept, 0 broken`.
- Verify: all gate conditions met; `gh run watch "$RUN_ID" --exit-status` exit 0; verdict line contains `0 failures`.

## Risks
| Risk | L×I | Mitigation |
|------|-----|------------|
| Scheduler fires during the test | M×M | `pause()` right after lifespan start; `CALLS.clear()` before each run |
| Snapshot captures time-dependent data | M×M | only call lists, counts and status keys are recorded |

## Rollback
Tests and scripts only; `git revert` the commit.

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

<!-- FILE: phase-03-consolidate-di-routes-and-contracts.md -->
---
phase: 3
title: "Consolidate DI, routes, wrappers and contracts"
status: pending
priority: P1
effort: 3d
dependencies: [2]
---

# Phase 03: Consolidate DI, routes, wrappers and contracts

## Goal
Mechanical, behaviour-neutral consolidation: `app/di` = `__init__.py` + 3 modules; market-data routes = 2 files; Query/Command classes wrapping 0-2 scalars removed from routes/services; import-linter = 3 contracts. OpenAPI and route-inventory snapshots unchanged except removed internal schema components.

## Context Links
- DI today: 10 files in `src/pocketquant/app/di/` (`__init__.py`, `backtest_worker.py`, `broker_factory.py`, `container.py`, `core.py`, `execution.py`, `infrastructure.py`, `market_data.py`, `persistence.py`, `services.py`, `trading_services.py`); `create_container` at `container.py:28`; main imports it at `app/main.py:8`.
- Routes today: `app/routes/market_data.py:9` aggregates `market_data_sync.py`, `integrity.py`, `market_data_ohlcv.py`, `market_data_status.py`, `list_symbols.py`; `tracked_symbols.py` and `market_data_quotes.py` mounted in `app/main_extensions.py:353-390`.
- Contracts: `pyproject.toml` `[[tool.importlinter.contracts]]` × 7; `bson` is also banned by ruff `TID` (`pyproject.toml` `banned-api`).

## Files to Create or Modify
- Rewrite: `src/pocketquant/app/di/__init__.py`, `src/pocketquant/app/di/infrastructure.py`, `src/pocketquant/app/di/services.py`. Create: `src/pocketquant/app/di/adapters.py`.
- Delete: `app/di/backtest_worker.py`, `broker_factory.py`, `container.py`, `core.py`, `execution.py`, `market_data.py`, `persistence.py`, `trading_services.py`.
- Rewrite: `src/pocketquant/app/routes/market_data.py`. Create: `src/pocketquant/app/routes/market_data_streams.py`. Delete: `market_data_sync.py`, `integrity.py`, `market_data_ohlcv.py`, `market_data_status.py`, `list_symbols.py`, `market_data_quotes.py`, `tracked_symbols.py`.
- Modify: `src/pocketquant/app/main.py`, `src/pocketquant/app/main_extensions.py`, `src/pocketquant/app/routes/strategy.py`, `src/pocketquant/app/routes/trading_orders_positions.py`, `src/pocketquant/app/routes/backtest.py`, `src/pocketquant/engine/orders_positions_service.py`, `src/pocketquant/engine/strategy_command_service.py`, `src/pocketquant/engine/strategy_query_service.py`, `src/pocketquant/engine/market_data/{quotes_service,symbols_service,sync_status_service,tracked_symbols_service}.py`, `src/pocketquant/backtest/backtest_query_service.py`, `pyproject.toml`.
- Tests to update: `tests/app_test/integration/app_factory.py`, `tests/app_test/integration/test_app_standalone_runtime.py`, `tests/app_test/integration/test_reconcile_di_resolution.py`, `tests/app_test/unit/di/test_di_data_provider.py`, `tests/engine_test/test_reconcile_restart_resume_integration.py`, `tests/engine_test/test_broker_factory_characterization.py`, `tests/engine_test/test_orders_positions_service.py`, `tests/engine_test/test_strategy_service.py`, `tests/engine_test/test_strategy_handlers_declarative.py`, `tests/engine_test/test_strategy_position_and_trade_handlers.py`, `tests/engine_test/market_data/test_quotes_service.py`, `tests/engine_test/market_data/test_tracked_symbols_service.py`, `tests/app_test/unit/handlers/status/test_get_sync_status.py`, `tests/app_test/unit/handlers/status/test_get_symbol_sync_status.py`.

## Tasks

### T3.1 Three DI modules
- Goal: every provided type registered exactly once across three providers.
- Steps:
  1. `git checkout -b refactor/consolidate-di-routes` from `master`.
  2. `infrastructure.py` → `class InfrastructureProvider(Provider)` with `__init__(self, settings: Settings | None = None)` calling `super().__init__()` and storing it; `get_settings()` returns the stored settings when not `None`, else `pocketquant.core.config.get_settings()`; `get_event_bus()` → `EventBus(max_history=100)`; move verbatim from `persistence.py` the `get_database`/`get_cache` async generators and the 11 repository `provide(...)` attributes; move verbatim from today's `infrastructure.py` `get_job_scheduler`; `get_health_coordinator` → `HealthCoordinator(timeout=5.0)`.
  3. `adapters.py` → move class `BrokerFactory` verbatim from `broker_factory.py` but delete its unused `get_available_types` (no caller in `src` or `tests`); `class AdapterProvider(Provider)` with `get_data_provider(settings) -> IDataProvider` (`BinanceClient(settings=settings)`), `get_realtime_quote_provider() -> IRealtimeQuoteProvider` (`BinanceWebSocketClient()`, keep the existing `# type: ignore[return-value]` comment), `broker_factory = provide(BrokerFactory, scope=Scope.APP)`.
  4. `services.py` → `class ServiceProvider(Provider)` holding everything from `execution.py`, `market_data.py`, `backtest_worker.py`, `trading_services.py` and today's `services.py`. Replace a factory with `provide(Class, scope=Scope.APP)` only for `BacktestDispatchDeps` (dataclass, `backtest/workers/backtest_dispatch.py:36`), `BacktestExecutionService` (`backtest/backtest_execution_service.py:22`) and `QuoteAppService`; keep the other factories' bodies verbatim (`BarAppService` has an untyped-default `intervals` param; `WsSubscriptionManager` uses a forward-ref annotation).
  5. `__init__.py` → export `InfrastructureProvider`, `AdapterProvider`, `ServiceProvider`, and `def create_container(settings: Settings | None = None) -> AsyncContainer: return make_async_container(InfrastructureProvider(settings), AdapterProvider(), ServiceProvider())`. Short module docstring stating "one type, one provider".
  6. Delete the 8 old modules. `app/main.py:8` → `from pocketquant.app.di import create_container`.
  7. Tests: `app_factory.py` builds `make_async_container(InfrastructureProvider(settings), AdapterProvider(), ServiceProvider())` and drops `TestCoreProvider`; same replacement in `test_app_standalone_runtime.py:20-63` and `test_reconcile_di_resolution.py:13-40`; `test_di_data_provider.py` imports `AdapterProvider` and calls `AdapterProvider().get_data_provider(mock_settings)` / `.get_realtime_quote_provider()`; `test_reconcile_restart_resume_integration.py:21` and `test_broker_factory_characterization.py` import `BrokerFactory` from `pocketquant.app.di.adapters`.
- Success criteria: app boots with the 3 providers; no duplicate provision.
- Verify: `ls src/pocketquant/app/di/*.py | wc -l` prints `4`; `grep -rn "app.di.container\|app.di.broker_factory\|app.di.execution\|app.di.market_data\|app.di.persistence\|app.di.core\|app.di.trading_services\|app.di.backtest_worker" src tests | wc -l` prints `0`; `.venv/Scripts/python.exe -m pytest tests/baseline tests/app_test/integration/test_lifespan_boot.py tests/app_test/integration/test_reconcile_di_resolution.py tests/app_test/unit/di tests/engine_test/test_broker_factory_characterization.py -q` exits 0.

### T3.2 Drop scalar Query/Command wrappers
- Goal: services take scalars; request-body models stay.
- Target classes to delete (file:line) and new signatures:
  - `engine/orders_positions_service.py:19-31` `GetOrderQuery`, `ListOrdersQuery`, `GetPositionQuery`, `ListPositionsQuery` → `get_order(order_id: str)`, `list_orders()`, `get_position(strategy_id: str)`, `list_positions()`.
  - `engine/strategy_command_service.py:29-52` `StartStrategyCommand`, `StopStrategyCommand`, `RemoveSymbolCommand`, `DeleteStrategyCommand` → `start(subscription_id)`, `stop(subscription_id)`, `remove_symbol(sub_id)`, `delete_strategy(strategy_id)`. Keep `AddSymbolCommand` (3 fields).
  - `engine/strategy_query_service.py:23-40` `GetStrategiesQuery`, `GetStrategyQuery`, `ListSymbolsQuery`, `GetStrategyPositionsQuery`, `GetStrategyTradesQuery` → `get_all()`, `get_one(strategy_code)`, `list_symbols(strategy_code: str | None)`, `get_positions(subscription_id)`, `get_trades(subscription_id, limit)`.
  - `engine/market_data/quotes_service.py:10` `GetLatestQuoteQuery` → `get_latest(symbol)`; `symbols_service.py:6` `ListSymbolsQuery` → `list_symbols()`; `sync_status_service.py:34,39` → `get_sync_status()`, `get_symbol_sync_status(symbol, interval)`; `tracked_symbols_service.py:40,47,53` `UpdateTrackedSymbolCommand`, `RemoveTrackedSymbolCommand`, `ListTrackedSymbolsQuery` → `update(symbol)`, `remove(symbol)`, `list_all()` (keep `AddTrackedSymbolCommand`: it is a request body).
  - `backtest/backtest_query_service.py:24` `GetBacktestQuery` → `get_result(run_id)`. Keep `SetVerdictCommand`, `RunBacktestCommand`, `ListBacktestsQuery`, `ListTradesQuery`, `GetOHLCVQuery`, `SyncSymbolCommand`, `BulkSyncCommand`, `BackfillTrackedSymbolCommand`, `AddSymbolCommand`.
- Steps: for each class: delete it, change the service method to the scalar signature (body reads the scalar instead of `query.x`), update every caller in `app/routes/*.py`, update the listed tests to call the new signature.
- Success criteria: no remaining reference to deleted classes.
- Verify: `grep -rnwE "GetOrderQuery|ListOrdersQuery|GetPositionQuery|ListPositionsQuery|StartStrategyCommand|StopStrategyCommand|RemoveSymbolCommand|DeleteStrategyCommand|GetStrategiesQuery|GetStrategyQuery|GetStrategyPositionsQuery|GetStrategyTradesQuery|GetLatestQuoteQuery|ListSymbolsQuery|GetSyncStatusQuery|GetSymbolSyncStatusQuery|UpdateTrackedSymbolCommand|RemoveTrackedSymbolCommand|ListTrackedSymbolsQuery|GetBacktestQuery" src tests | wc -l` prints `0`; `.venv/Scripts/python.exe -m pytest tests/engine_test tests/app_test/unit -q` exits 0.

### T3.3 Market-data routes into two files
- Goal: same paths, names, methods, tags; two files.
- Steps:
  1. `app/routes/market_data.py`: `router = APIRouter(prefix="/market-data", tags=["Market Data"], route_class=DishkaRoute)` holding handlers moved verbatim (same function names) from `market_data_sync.py` (`sync_symbol`, `sync_symbol_background`, `sync_bulk`), `integrity.py` (`IntegrityRequest`, `integrity_check`, `integrity_repair`), `market_data_status.py` (`get_sync_statuses`, `get_symbol_sync_status`), `list_symbols.py` (`list_symbols`); plus `tracked_symbols_router = APIRouter(prefix="/market-data", tags=["Tracked Symbols"], route_class=DishkaRoute)` with the 5 handlers from `tracked_symbols.py` (keep `Depends(verify_admin_token)` — auth, not service injection).
  2. `app/routes/market_data_streams.py`: `ohlcv_router = APIRouter(prefix="/market-data", tags=["Market Data"], route_class=DishkaRoute)` with `OHLCVResponse`, `get_ohlcv`, `stream_bars`; `quote_router = APIRouter(prefix="/quotes", tags=["Real-time Quotes"], route_class=DishkaRoute)` with `get_latest_quote`, `get_current_bar`, `stream_quote`. One module helper `_sse(generator) -> StreamingResponse` with the shared headers dict replaces the two duplicated `StreamingResponse(...)` blocks; rename payload helpers `_bar_payload`, `_quote_payload`.
  3. `main_extensions.register_routes` (`app/main_extensions.py:353`): import `router`, `tracked_symbols_router` from `market_data` and `ohlcv_router`, `quote_router` from `market_data_streams`; include all four on `api` (remove the old `prefix="/market-data"` argument for tracked symbols since the router now carries it).
  4. Delete the 7 old route files.
- Success criteria: snapshots unchanged.
- Verify: `ls src/pocketquant/app/routes/market_data*.py | wc -l` prints `2`; `ls src/pocketquant/app/routes/{integrity,list_symbols,tracked_symbols}.py 2>/dev/null | wc -l` prints `0`; `.venv/Scripts/python.exe -m pytest tests/baseline/test_route_inventory.py tests/baseline/test_openapi_snapshot.py -q` exits 0 with no snapshot regeneration (the removed wrapper classes never appear in the OpenAPI schema: `grep -cE "GetOrderQuery|ListSymbolsQuery|GetBacktestQuery" tests/baseline/openapi_app_snapshot.json` prints `0` today); `git diff --quiet tests/baseline/; echo $?` prints `0`.

### T3.4 Three import-linter contracts
- Target: `pyproject.toml` `[tool.importlinter]`.
- Steps: keep only contracts `Layered architecture — app top tier`, `Core domain stays free of infra adapters`, `fastapi only in app` (with its comment). Delete `Core imports no inner package`, `Engine imports no sibling/upper package`, `Backtest imports no upper package` (implied by the layers contract) and `No bson/ObjectId usage — UUID7 only` (ruff `TID` banned-api already rejects `bson`).
- Verify: `uv run lint-imports` output contains `3 kept, 0 broken`; `grep -c "^\[\[tool.importlinter.contracts\]\]" pyproject.toml` prints `3`; `grep -c '"bson".msg' pyproject.toml` prints `1`.

### T3.5 Gate, commit, ship
- Steps: gate; characterization must pass unchanged: `.venv/Scripts/python.exe -m pytest tests/app_test/integration/test_sync_pipeline_characterization.py -q` with no snapshot edit (`git diff --quiet tests/app_test/integration/sync_pipeline_snapshot.json`). Commits: `refactor(di): merge providers into infrastructure, adapters and services`, `refactor(api): drop scalar query and command wrappers`, `refactor(api): consolidate market-data routes into two modules`, `build: reduce import-linter to three contracts`. Ask approval; merge `--ff-only`; push; watch run.
- Gate: `just test` exit 0 (no test file was deleted in this phase, so the passed count must be ≥ the count in `gate-baseline.txt`); `uv run ruff check` exit 0; `uv run pyright` contains `0 errors`; `uv run lint-imports` contains `3 kept, 0 broken`.
- Verify: gate met; `git diff --quiet tests/app_test/integration/sync_pipeline_snapshot.json; echo $?` prints `0`; CI watch exit 0; verdict contains `0 failures`.

## Risks
| Risk | L×I | Mitigation |
|------|-----|------------|
| Duplicate/missing DI registration | M×H | boot + reconcile DI tests in T3.1 Verify |
| Route schema drift breaks SPA | L×H | route-inventory snapshot must stay unchanged; OpenAPI diff filter |
| Tests depending on old provider split | M×M | enumerated test list above |

## Rollback
Revert the phase merge commit(s) and push; or pin the previous image tag per `docs/deployment.md` "Rollback".

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

<!-- FILE: phase-04-sync-policy-and-shared-runner.md -->
---
phase: 4
title: "Sync policy and shared runner (Binance)"
status: pending
priority: P1
effort: 5d
dependencies: [3]
---

# Phase 04: Sync policy and shared runner (Binance)

## Goal
Replace the job modules and `sync_internals/` with one `SyncPolicy` per provider and one runner. Binance's policy reproduces today exactly (WS aggTrade live, REST 1m each minute, cascade 5m..1d, 1w via REST); the phase-02 snapshot stays byte-identical.

## Data flow
`APScheduler cron → sync_runner.run_job(name) → for tracked symbol: SyncPolicies.for_symbol → SyncService.sync_one (fetch → filter → align → persist → status) → cascade_for_symbol if policy.cascade_intervals → job_history`. Live: `QuoteAppService → RoutedQuoteProvider → policy.quote_provider`. Readable in `sync_runner.py`, `sync_service.py`, `cascade_aggregator.py`.

## Context Links
- `sync_jobs.py:54,70,72,86,91,115,130,234,285,329,382,454,511,609-617,621,663`; `integrity_jobs.py:18,33,76`; `sync_service.py:33-181`; `sync_internals/*.py` (5 files); `sync_dtos.py`; `tracked_symbols_backfill.py:31-182`; `app/main.py:31-51` (`set_sync_container` before any await); `app/main_extensions.py:168-183` (`start_background_jobs`).
- Persisted jobs: `MongoDBJobStore` (`core/infra/scheduling/scheduler.py`) stores text refs; jobs whose ref no longer imports are dropped by APScheduler on load, and `register_sync_jobs` re-adds the 5 ids with `replace_existing=True`. Job ids stay identical so `/system/jobs` and `job_history` continue.

## Files to Create or Modify
- Create: `src/pocketquant/core/domain/market_data/sessions.py`, `src/pocketquant/engine/market_data/sync_policy.py`, `src/pocketquant/engine/market_data/sync_runner.py`, `tests/engine_test/market_data/test_sync_policy.py`, `tests/core_test/unit/domain/test_market_sessions.py`.
- Modify: `src/pocketquant/engine/market_data/sync_service.py`, `src/pocketquant/engine/market_data/tracked_symbols_backfill.py`, `src/pocketquant/app/di/adapters.py`, `src/pocketquant/app/routes/market_data.py`, `src/pocketquant/app/main.py`, `src/pocketquant/app/main_extensions.py`, `src/pocketquant/core/infra/scheduling/scheduler.py` (docstring reference only).
- Delete: `src/pocketquant/engine/market_data/app_services/sync_jobs.py`, `.../app_services/integrity_jobs.py`, `src/pocketquant/engine/market_data/sync_internals/` (all 6 files), `src/pocketquant/engine/market_data/sync_dtos.py`.
- Tests to update (import path/constructor only, assertions unchanged): `tests/app_test/test_sync_jobs_phase.py`, `tests/app_test/market_data/test_sync_jobs_source_labels.py`, `tests/app_test/market_data/test_integrity_jobs_repair_source.py`, `tests/app_test/unit/market_data/test_sync_jobs_catchup.py`, `tests/app_test/unit/market_data/test_sync_verify_cascade.py`, `tests/app_test/unit/handlers/sync/conftest.py`, `.../test_bar_filters.py`, `.../test_provider_fetch.py`, `.../test_no_progress_tracking.py`, `tests/engine_test/market_data/test_sync_service.py`, `tests/app_test/integration/test_sync_backfill_gap_fill.py`, `tests/app_test/integration/app_factory.py`, `tests/app_test/unit/di/test_di_data_provider.py`.

## Tasks

### T4.1 Market sessions value object
- Target: new `core/domain/market_data/sessions.py`.
- Steps: `git checkout -b refactor/sync-policy-runner`. Create:
  ```python
  from dataclasses import dataclass
  from datetime import UTC, datetime

  WEEK_MINUTES = 7 * 24 * 60


  def minute_of_week(ts: datetime) -> int:
      ts = ts.astimezone(UTC) if ts.tzinfo else ts.replace(tzinfo=UTC)
      return ts.weekday() * 1440 + ts.hour * 60 + ts.minute


  @dataclass(frozen=True)
  class MarketCalendar:
      """Weekly UTC open windows as [start, end) minute-of-week (Monday 00:00 = 0).

      A window with start > end wraps over the week boundary. No windows = always open.
      """

      open_windows: tuple[tuple[int, int], ...] = ()

      def is_open_between(self, start: datetime, end: datetime) -> bool:
          if not self.open_windows:
              return True
          length = int((end - start).total_seconds() // 60)
          if length >= WEEK_MINUTES:
              return True
          lo = minute_of_week(start)
          hi = lo + max(length, 1)
          for a, b in self.open_windows:
              for sa, sb in ([(a, b)] if a < b else [(a, WEEK_MINUTES), (0, b)]):
                  if any(sa + s < hi and lo < sb + s for s in (0, WEEK_MINUTES)):
                      return True
          return False


  ALWAYS_OPEN = MarketCalendar()
  ```
  Test `tests/core_test/unit/domain/test_market_sessions.py`: always-open; window Mon 00:00-Fri 21:00 (`(0, 4*1440+1260)`) closed on Saturday 12:00 for 1 minute, open Friday 20:59; wrap window `(6*1440+1320, 4*1440+1260)` open Sunday 22:30, closed Saturday; a 1d bar starting Sunday 00:00 overlaps the wrap window.
- Verify: `.venv/Scripts/python.exe -m pytest tests/core_test/unit/domain/test_market_sessions.py tests/core_test/unit/domain/test_domain_purity.py -q` exits 0.

### T4.2 `SyncPolicy`, `SyncPolicies`, `RoutedQuoteProvider`
- Target: new `engine/market_data/sync_policy.py`.
- Steps: create
  ```python
  @dataclass(frozen=True)
  class SyncPolicy:
      exchange: str                                  # composite suffix, e.g. "BINANCE"
      provider: IDataProvider                        # authoritative bar source
      quote_provider: IRealtimeQuoteProvider         # live source
      poll_intervals: tuple[Interval, ...]           # fetched by sync_1m when their bar just closed
      cascade_intervals: tuple[Interval, ...]        # () = no cascade
      sync_intervals: tuple[Interval, ...]           # backfill / integrity / repair set
      calendar_for: Callable[[str], Awaitable[MarketCalendar]]
      poll_every_minutes: int = 1
      poll_bars: int = 100
      backfill_bars: int = 5000
      max_requests_per_minute: int | None = None     # rate budget, checked by the runner
      history_days: Mapping[Interval, int] = field(default_factory=dict)  # {} = unbounded
  ```
  plus `async def always_open(symbol: str) -> MarketCalendar` (returns `ALWAYS_OPEN`), `def exchange_of(symbol: str) -> str` (`symbol.upper().rsplit(":", 1)[-1]`), `class SyncPolicies` (`__init__(self, policies: Iterable[SyncPolicy])` keyed by `exchange`; `for_symbol(symbol) -> SyncPolicy` raising `ValueError(f"No sync policy for exchange {exchange}")`; `__iter__`), and `class RoutedQuoteProvider` implementing all 9 `IRealtimeQuoteProvider` members (`core/domain/market_data/interfaces.py:40`) by routing `subscribe`/`unsubscribe` through `policies.for_symbol(symbol).quote_provider`, `connect`/`disconnect` over every distinct quote provider, `run_forever` = `asyncio.gather(*(p.run_forever() for p in providers))`, `last_tick_at` = max of children (property), `subscriptions` = merged dict (property), `subscription_count` = its length, `is_connected` = all children connected.
  In `app/di/adapters.py` add now `def binance_policy(provider: IDataProvider, quote_provider: IRealtimeQuoteProvider) -> SyncPolicy` returning `exchange="BINANCE"`, `poll_intervals=(Interval.MINUTE_1,)`, `cascade_intervals=(MINUTE_5, MINUTE_15, HOUR_1, HOUR_4, DAY_1)`, `sync_intervals=(MINUTE_1, MINUTE_5, MINUTE_15, HOUR_1, HOUR_4, DAY_1, WEEK_1)` (same as `sync_jobs.py:54` `SYNC_INTERVALS`), `calendar_for=always_open`, defaults otherwise (it is used by tests from T4.3 on).
  Test `tests/engine_test/market_data/test_sync_policy.py`: `for_symbol("btcusdt:binance")` returns the BINANCE policy; unknown exchange raises `ValueError`; router subscribes only on the matching child (two `MagicMock`/`AsyncMock` children); `isinstance(router, IRealtimeQuoteProvider)` is true.
- Verify: `.venv/Scripts/python.exe -m pytest tests/engine_test/market_data/test_sync_policy.py -q` exits 0.

### T4.3 Fold `sync_internals` and DTOs into `sync_service.py`
- Steps:
  1. Move into `sync_service.py` as module-level functions with unchanged names/bodies: `fetch_with_retry` (+ `_BACKOFF_SECONDS`, `_TIME_BUDGET_SECONDS`, inline `has_aligned_bar` as a generator expression), `filter_new_bars`, `drop_misaligned_bars`, `emit_no_progress` (+ `_STUCK_STREAK_THRESHOLD`); move `SyncSymbolCommand`, `BulkSyncCommand`, `SyncResponse` from `sync_dtos.py`; inline `build_success` into `sync_one`'s return. Keep `__all__`.
  2. Constructor: replace `provider: IDataProvider` with `policies: SyncPolicies`. In `sync_one`, inside the existing `try`, resolve `policy = self._policies.for_symbol(symbol)` and use `policy.provider`; clamp `n_bars` to `policy.history_days[interval] * 86400 // INTERVAL_SECONDS[interval]` when the interval is in `history_days`.
  3. Delete `sync_internals/` and `sync_dtos.py`.
  4. Tests: in `tests/app_test/unit/handlers/sync/conftest.py:25` the loop becomes `for module in (sync_service,):` (drop the three `sync_internals` imports); `test_bar_filters.py`, `test_provider_fetch.py`, `test_sync_backfill_gap_fill.py` import from `pocketquant.engine.market_data.sync_service`; in `test_provider_fetch.py:18,56,194` replace the module object `provider_fetch` with `sync_service` (`patch.object(sync_service.asyncio, "sleep", ...)`, `patch.object(sync_service.time, "monotonic", ...)`); the two `SyncService(provider=provider, ...)` constructions (`test_no_progress_tracking.py:78`, `test_sync_service.py:84`) become `SyncService(policies=SyncPolicies([binance_policy(provider, MagicMock())]), ...)` (`binance_policy` from T4.5).
- Verify: `test -d src/pocketquant/engine/market_data/sync_internals; echo $?` prints `1`; `grep -rn "sync_internals\|sync_dtos" src tests | wc -l` prints `0`; `.venv/Scripts/python.exe -m pytest tests/app_test/unit/handlers/sync tests/engine_test/market_data/test_sync_service.py -q` exits 0.

### T4.4 Shared runner `sync_runner.py`
- Goal: one module replaces `sync_jobs.py` + `integrity_jobs.py`; functions ≤ ~60 lines.
- Steps: create `engine/market_data/sync_runner.py` with:
  1. `_MODULE = "pocketquant.engine.market_data.sync_runner"`; `CATCHUP_TARGETS = [("sync_backfill", f"{_MODULE}:run_job", 86400 + 3600), ("sync_integrity", f"{_MODULE}:run_job", 86400 + 3600), ("sync_repair", f"{_MODULE}:run_job", 43200 + 1800)]`; `PRICE_THRESHOLD_PCT`, `VOLUME_THRESHOLD_PCT`, `DIVERGENCE_ALERT_FRACTION` copied; `_container` + `set_container` copied.
  2. `@asynccontextmanager async def _job_run(history_repo, name)` → `record_start` (warn on failure), yields a mutable `dict` for totals, `record_finish(status="completed", duration_ms=..., **totals)` on success, `record_finish(status="failed", error=str(exc))` + re-raise on failure. This replaces the 5 copied start/finish blocks.
  3. `async def run_job(name: str) -> None`: resolve `JobHistoryRepository`, `TrackedSymbolRepository`, `BarRepository`, `SyncService`, `SyncPolicies` from `_container`; `async with _job_run(...) as totals:` dispatch via a dict `{"sync_1m": _poll, "sync_backfill": _backfill, "sync_verify_cascade": _verify_cascade, "sync_integrity": _integrity, "sync_repair": _repair}`.
  4. `_sync_symbol_intervals(...)`: body of `_sync_by_intervals` (`sync_jobs.py:130`) per (symbol, intervals) with the same `record_detail` calls, same log names `market_data.{job}.started/completed/symbol_failed`, re-raising the first error after the loop.
  5. `_poll`: for each tracked symbol: `policy = policies.for_symbol(sym)` (unknown exchange → `logger.warning("sync_policy.unknown_exchange", symbol=sym)` and skip); skip if `minute % policy.poll_every_minutes`; `calendar = await policy.calendar_for(sym)`, skip when `not calendar.is_open_between(now_minute - 2min, now_minute)`; intervals = those in `policy.poll_intervals` with `int(now_minute.timestamp()) % INTERVAL_SECONDS[iv] == 0`; sync them with `n_bars=policy.poll_bars`, `source=SOURCE_REST_SYNC_1M`; if `policy.cascade_intervals`: `cascade_for_symbol(sym, lookback_minutes=policy.poll_bars, bar_repo=bar_repo)` with the same error log `sync_1m.cascade_failed`; log `sync_1m.cascade_summary` as today. Log `sync_policy.rate_budget_exceeded` (warning) when planned calls for a policy exceed `max_requests_per_minute`.
  6. `_backfill`: per symbol `policy.sync_intervals`, `n_bars=policy.backfill_bars`, `source=SOURCE_REST_BACKFILL`.
  7. `_verify_one_symbol` (copied unchanged) and `_verify_cascade`: only for symbols whose policy has `cascade_intervals`, using `policy.provider`; same log events.
  8. `check_integrity(symbol, interval, bar_repo, days_back=7, calendar=ALWAYS_OPEN)` and `repair_integrity(..., *, source, days_back=7, calendar=ALWAYS_OPEN)` copied from `integrity_jobs.py` with one change: `expected = {t for t in grid if calendar.is_open_between(t, t + step)}`; `_integrity`/`_repair` iterate `policy.sync_intervals` and pass `await policy.calendar_for(sym)`.
  9. `enqueue_missed_catchups` copied; it calls `job_scheduler.add_one_off_job(func_ref, job_id=f"{job_id}_catchup", name=job_id)`.
  10. `register_sync_jobs` copied; every `add_cron_job` uses `f"{_MODULE}:run_job"` and passes `name=<job id>` (same `job_id`, cron, `second=2`, `misfire_grace_time` values as `sync_jobs.py:663-`); keep the explanatory comments that state why (grace times, +2 s).
  11. Delete `app_services/sync_jobs.py` and `app_services/integrity_jobs.py`. `app/main.py:31` imports `set_container as set_sync_container` from `sync_runner`; `main_extensions.start_background_jobs` imports `register_sync_jobs` from `sync_runner`; routes `integrity_check`/`integrity_repair` import from `sync_runner`, inject `FromDishka[SyncPolicies]` and pass `calendar=await policies.for_symbol(symbol).calendar_for(symbol)`. Update the `scheduler.py` docstring reference to `sync_runner.py`.
  12. Tests: replace imports of `...app_services.sync_jobs` / `...app_services.integrity_jobs` with `pocketquant.engine.market_data.sync_runner` in the files listed above; in `test_sync_jobs_source_labels.py` monkeypatch `sync_runner._container` with a mapping that also contains `SyncPolicies: SyncPolicies([binance_policy(MagicMock(), MagicMock())])`, call `await sync_runner.run_job("sync_1m")` / `run_job("sync_backfill")`, monkeypatch `sync_runner.cascade_for_symbol`; `app_factory.py:41` imports `set_container` from `sync_runner`.
- Verify: `ls src/pocketquant/engine/market_data/app_services/sync_jobs.py src/pocketquant/engine/market_data/app_services/integrity_jobs.py 2>/dev/null | wc -l` prints `0`; `grep -rn "app_services.sync_jobs\|app_services.integrity_jobs" src tests | wc -l` prints `0`; `.venv/Scripts/python.exe -m pytest tests/app_test/unit tests/app_test/market_data tests/app_test/test_sync_jobs_phase.py -q` exits 0 (the DI graph is completed in T4.5; full app tests run there).

### T4.5 Binance policy and DI
- Target: `app/di/adapters.py`, `engine/market_data/tracked_symbols_backfill.py`.
- Steps:
  1. `binance_policy` already exists (T4.2).
  2. `AdapterProvider`: replace `get_data_provider`/`get_realtime_quote_provider` with `get_binance_client(settings) -> BinanceClient`, `binance_ws = provide(BinanceWebSocketClient, scope=Scope.APP)`, `get_sync_policies(binance_client: BinanceClient, binance_ws: BinanceWebSocketClient) -> SyncPolicies` (`SyncPolicies([binance_policy(binance_client, binance_ws)])`), `quote_router = provide(RoutedQuoteProvider, provides=IRealtimeQuoteProvider, scope=Scope.APP)`.
  3. `TrackedSymbolBackfillService.__init__(self, policies: SyncPolicies, bar_repository: BarRepository)`; in `run`: `policy = self._policies.for_symbol(cmd.symbol)`; mode = `cmd.mode` unless `"auto"`, where auto = `"cascade"` if `cmd.interval in policy.cascade_intervals` else `"direct"`; a requested `"cascade"` with empty `policy.cascade_intervals` becomes `"direct"`; use `policy.provider`. Delete `_CASCADE_DEFAULT_TFS` and `resolved_mode`.
  4. `test_di_data_provider.py`: assert `AdapterProvider().get_sync_policies(BinanceClient(settings=mock_settings), BinanceWebSocketClient()).for_symbol("BTCUSDT:BINANCE").provider` is a `BinanceClient` and the policy's `cascade_intervals` has 5 entries.
- Verify: `.venv/Scripts/python.exe -m pytest tests/app_test tests/engine_test tests/baseline -q` exits 0.

### T4.6 Characterization proof, prod precheck, gate, ship
- Steps:
  1. `.venv/Scripts/python.exe -m pytest tests/app_test/integration/test_sync_pipeline_characterization.py -q` and `git diff --quiet tests/app_test/integration/sync_pipeline_snapshot.json` — the trigger strings must not change. If only `"jobs"` trigger/misfire entries differ, Failure Protocol (do not regenerate).
  2. Prod precheck (read-only): `HOST="$(cat ../pocketquant-config/vps/default/host)"; KEY="../pocketquant-config/vps/default/id_rsa"; ssh -i "$KEY" "$HOST" "docker exec pocketquant-app curl -s http://localhost:41921/api/v1/market-data/tracked-symbols"`; every `symbol` must end with `:BINANCE`. **Stop and ask** if any does not (it would now be skipped instead of silently synced from Binance).
  3. Gate; commit `refactor(market-data): drive sync jobs from per-provider sync policies`; ask approval; merge; push; watch run. After deploy: `ssh ... "docker logs pocketquant-app --since 10m 2>&1 | grep -c 'market_data.sync_1m.completed'"` ≥ 5 (one per minute).
- Gate: `just test` exit 0; `uv run ruff check` exit 0; `uv run pyright` contains `0 errors`; `uv run lint-imports` contains `3 kept, 0 broken`.
- Verify: all of the above; verdict contains `0 failures`.

## Risks
| Risk | L×I | Mitigation |
|------|-----|------------|
| Binance behaviour drift | M×H | phase-02 snapshot byte-identical; ported tests keep assertions |
| Old persisted job refs | L×M | same job ids + `replace_existing`; APScheduler drops unrestorable refs (one error log on first boot) |
| Non-BINANCE tracked symbols in prod | L×M | T4.6 precheck stop-and-ask |
| Circular import sync_policy ↔ interfaces | L×L | `sync_policy.py` imports only `core` |

## Rollback
Revert the merge and push; the old job refs come back via `register_sync_jobs` of the reverted code (same ids, `replace_existing`).

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

<!-- FILE: phase-05-lean-code-standard-and-burn-down.md -->
---
phase: 5
title: "Lean code standard and burn-down"
status: pending
priority: P2
effort: 2d
dependencies: [4]
---

# Phase 05: Lean code standard and burn-down

## Goal
Rewrite `docs/code-standards.md` into the standard the code follows, remove dead/alias functions found by the metric script, and record the metric after the refactor.

## Context Links
- Stale claims: `docs/code-standards.md:381-392` ("Keep individual files under 200 LOC", "Current Status ... quote_aggregator.py"), `:177` ("Service Extract-Method Pattern"), `:132` ("Command/Query Service Pattern"), `:95` (provider order naming deleted modules), `:608-616` (`register_sync_jobs`), `:722` (`sync_jobs`).
- Docs rules: `CLAUDE.md` "Writing docs & prose" (Vietnamese prose, English technical terms, AS-IS, no banners, no changelog).

## Files to Create or Modify
- Rewrite: `docs/code-standards.md`. Modify: `CLAUDE.md` (contract count "7 contracts" → "3 contracts"), `docs/README.md` only if it describes code-standards sections.
- Burn-down (delete, callers updated): `core/common/messaging/event_bus.py:45` `clear_history`; `core/common/messaging/event_registry.py:67` `get_registered`; `engine/app_services/order_app_service.py:170` `get_orders_by_strategy`, `:222` `get_orders_by_strategy_async`; `engine/app_services/strategy_app_service.py:205` `get_strategies`; `core/common/time/simulation.py:38` `is_simulation_active`; `backtest/engine/backtest_engine_sandbox.py:92` `get_available_types`; `engine/market_data/app_services/quote_dto.py:57-59` property `key`; `core/domain/backtest/entities.py:69` and `core/domain/backtest/value_objects.py:316` `to_dict` aliases (callers `app/routes/backtest.py:78,195` call `to_mongo()`).

## Tasks

### T5.1 Rewrite `docs/code-standards.md`
- Steps: `git checkout -b docs/lean-code-standard`. Replace the file. Required sections (Vietnamese prose): Dependency direction (`core ◁ engine ◁ backtest ◁ app`, 3 import-linter contracts by name); Khi nào extract helper (only when the name adds meaning or the code is reused; one flow readable in one file where possible, ≤3 files); Kích thước (functions ≲60 lines; file ~400 LOC soft guidance, not a split trigger); Suffix table trimmed to `Repository`, `Service`, `Event`, `Error`, `Provider` (DI) — `AppService/CommandService/QueryService` are not distinct roles; Routes (`FromDishka[...]` + `DishkaRoute`, scalars passed directly, Pydantic models only for real request bodies); DI (3 modules `infrastructure.py`, `adapters.py`, `services.py`, one type one provider); Sync policy pattern (fields of `SyncPolicy`, runner flow, "a new provider = adapter package + one policy"); Ports stay (`IDataProvider`, `IRealtimeQuoteProvider`, `IBroker`, `IStrategy`); CFD/venue specifics live only in adapters; Primary keys UUIDv7; Async suspension points (keep the existing section's content, update `sync_jobs` names to `sync_runner`); Comment policy (keep existing content); Testing (characterization before refactor, testcontainers); Code quality tools (ruff, pyright, lint-imports, `scripts/code_metrics.py` soft gate with its definitions and thresholds 30% / 20). No "Current Status", no dates, no history.
- Verify: `grep -cE "Current Status|200 LOC|Extract-Method|sync_jobs|sync_internals|CoreProvider|PersistenceProvider" docs/code-standards.md` prints `0`; `grep -c "SyncPolicy" docs/code-standards.md` ≥ 1; `grep -c "code_metrics.py" docs/code-standards.md` ≥ 1; `grep -c "7 contracts" CLAUDE.md` prints `0`.

### T5.2 Burn-down of dead and alias functions
- Steps:
  1. `uv run python scripts/code_metrics.py > /tmp/metrics-before.txt; true`.
  2. For each target listed above: `grep -rnw <name> src tests` first; delete only if the only hits are the definition and (for `to_dict`) the two route callers `app/routes/backtest.py:78,195`, which switch to `to_mongo()`. If any other caller exists, leave that function and name it in the commit body.
  3. `uv run python scripts/code_metrics.py > /tmp/metrics-after.txt; true`.
- Verify: `grep tiny= /tmp/metrics-after.txt` value is lower than in `/tmp/metrics-before.txt`; `grep pure_delegation= /tmp/metrics-after.txt` value is lower than before; `.venv/Scripts/python.exe -m pytest tests/backtest_test tests/engine_test tests/core_test/unit tests/app_test/integration/test_backtest_orders_api.py -q` exits 0.

### T5.3 Record the metric and gate
- Steps: run `uv run python scripts/code_metrics.py` and append its output to `plans/261009-0858-exness-venue-lean-sync-refactor/reports/gate-baseline.txt` under a line `after-refactor`. Gate; commits `docs: rewrite code standards around the lean sync-policy design`, `refactor: remove unused and alias accessors`; ask approval; merge; push; watch.
- Gate: `just test` exit 0; `uv run ruff check` exit 0; `uv run pyright` contains `0 errors`; `uv run lint-imports` contains `3 kept, 0 broken`.
- Verify: gate met; `grep -c "after-refactor" plans/261009-0858-exness-venue-lean-sync-refactor/reports/gate-baseline.txt` prints `1`; verdict `0 failures`. (Thresholds are judged in phase 10; Exness code changes the ratio.)

## Risks
| Risk | L×I | Mitigation |
|------|-----|------------|
| Inlining to game the metric | M×M | only listed dead/alias functions; no other inlining in this phase |
| Doc drifts from code | M×M | Verify greps; phase 10 re-checks |

## Rollback
Revert the docs and burn-down commits.

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

<!-- FILE: phase-06-exness-signer-client-and-streams.md -->
---
phase: 6
title: "Exness signer, client and streams"
status: pending
priority: P1
effort: 4d
dependencies: [1, 5]
---

# Phase 06: Exness signer, client and streams

## Goal
Transport layer for Exness inside `core/infra/exness/`: Ed25519 signer, REST client with host discovery, clock offset and rate windows, and one reconnecting signed WebSocket stream. Fixture-tested; nothing wired into DI yet.

## Context Links
- Phase-01 summary `plans/.../reports/exness-spike-summary.json` (`key_format`, `candles_host`, rates, `max_candles_per_request`), fixtures `tests/core_test/infra/exness/fixtures/`.
- Limits schema: `limits.rest.global_account_rate.{limit,window_seconds}`, `limits.rest.methods[].{api_operation_id,rate_limit,limits.max_candles_per_request}`.
- Reconnect shape to mirror: `core/infra/brokers/okx/websocket/okx_reconnection_handler.py:16-20` (1 s doubling to 30 s, circuit 10 failures → 300 s pause).
- `websockets` 16 (`additional_headers=`, `subprotocols=`).

## Files to Create or Modify
- Create: `src/pocketquant/core/infra/exness/__init__.py`, `signer.py`, `client.py`, `websocket.py`; tests `tests/core_test/infra/exness/__init__.py`, `test_exness_signer.py`, `test_exness_client.py`, `test_exness_stream.py`.
- Modify: `src/pocketquant/core/config.py` (settings), `scripts/exness_spike.py` (import the signer), `.env.example` if present (`ls .env.example`; if absent, skip).

## Tasks

### T6.1 Settings
- Target: `core/config.py` class `Settings` after the OKX block (`:58-62`).
- Steps: `git checkout -b feat/exness-transport`. Add `exness_account_id: str | None = None`, `exness_api_key: SecretStr | None = None`, `exness_private_key: SecretStr | None = None`, `exness_private_key_path: str | None = None`, `exness_base_url: str = "https://api.exness.com"`, `exness_ws_base_url: str | None = None`, `exness_instrument_suffix: str = ""` (value from the phase-01 journal), `exness_force_min_lot: bool = True`, `exness_daily_loss_cap_pct: float = 0.01`, `exness_deviation_points: int = 50`.
- Verify: `uv run python -c "from pocketquant.core.config import Settings; f=Settings.model_fields; assert all(k in f for k in ['exness_account_id','exness_api_key','exness_private_key','exness_private_key_path','exness_base_url','exness_ws_base_url','exness_instrument_suffix','exness_force_min_lot','exness_daily_loss_cap_pct','exness_deviation_points'])"` exits 0.

### T6.2 `signer.py`
- Steps: move `_b64url` and `sign_headers` from `scripts/exness_spike.py` (T1.4 code, add type hints) plus `load_private_key(raw: str) -> Ed25519PrivateKey` (T1.4 step 2 rules) into `core/infra/exness/signer.py`. `scripts/exness_spike.py` imports them from here and deletes its copies.
- Tests: empty-body `body_hash` equals `47DEQpj8HBSa-_TImW-5JCeuQeRkm5NMpJWZG3hSuFU`; decoded `EXN-DATA` keys equal the 7 spec keys; signature verifies with `private_key.public_key().verify(...)`; `load_private_key` accepts PEM, 64-hex, base64 forms of a generated key and its error message never contains the input.
- Verify: `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_exness_signer.py -q` exits 0; `grep -c "def sign_headers" scripts/exness_spike.py` prints `0`.

### T6.3 `client.py`
- Goal: `ExnessClient(settings, transport: httpx.AsyncBaseTransport | None = None)`.
- Steps: implement:
  - `is_configured` (property): account id, api key and a private key source all set.
  - `_request(method, path, *, params=None, body=None, idempotency_key="", use_access_point=True) -> dict`: build `path_with_query` once with `urlencode`, sign with `sign_headers` using `timestamp_ms = now_ms + self._clock_offset_ms`, send to the access-point host (`https://{access_point}`) or `settings.exness_base_url`; update `_clock_offset_ms` from the `Date` header on every response; acquire the global and per-operation rate windows before sending; raise `ExnessApiError(status, code)` on non-2xx with `error.code` from the body (never include headers in the message).
  - `_access_point()`: cached `GET /v1/trading/access-point?account_id=...` against `exness_base_url`.
  - Rate windows: small class `_RateWindow(limit, window_seconds)` with `async acquire()` (deque of monotonic timestamps; sleep until the oldest leaves the window). Built lazily from `limits()` for the global rate and `getCandleHistory`, `openPosition`.
  - Public: `limits()` (cached), `max_candles_per_request()`, `instrument_conditions(instrument)` (cached 6 h), `candles(instrument, timeframe, *, from_: datetime, count: int, price_type="bid") -> list[dict]` (host per `candles_host` from the spike summary: access point unless the journal says base), `snapshot()`, `open_position(body: dict, idempotency_key: str) -> dict`, `operation_status(operation_id)`, `ws_url(path)` (`settings.exness_ws_base_url` or `wss://{access_point}`, plus path), `signed_ws_headers(path)`, `close()` (closes httpx and clears the cached access point).
- Tests (`httpx.MockTransport` serving phase-01 fixtures): candles call signs `path` equal to the exact requested path+query; access point requested once; `limits()` cached; a 429 raises `ExnessApiError` with code; `max_candles_per_request()` returns the fixture value.
- Verify: `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_exness_client.py -q` exits 0.

### T6.4 `websocket.py`
- Goal: `ExnessStream(client, path, on_message, name)` reused by quotes (ticks) and broker (events).
- Steps: `run_forever()`: loop while running: `websockets.connect(client.ws_url(path), subprotocols=["exness-ws-protocol"], additional_headers=client.signed_ws_headers(path), ping_interval=20, ping_timeout=20, close_timeout=5)`; on open reset failures, re-send every remembered subscribe message; for each frame `json.loads` and `await on_message(frame)` (log and continue on callback errors); on close/error log `exness_stream.disconnected` with `name`, sleep backoff (1 s doubling to 30 s); after 10 consecutive failures log `exness_stream.circuit_open` and sleep 300 s. `send(msg)` sends when open; `remember(key, msg)` / `forget(key)` keep subscribe messages for replay; `close()`; `last_message_at`; `is_connected()`. No tick-staleness watchdog (markets close on weekends; liveness comes from WS ping/pong).
- Tests: with a fake `connect` (monkeypatch `pocketquant.core.infra.exness.websocket.websockets.connect` to an async context returning a fake socket yielding fixture frames then raising `ConnectionClosed`): remembered messages are re-sent after reconnect; backoff delays recorded via patched `asyncio.sleep` equal `[1, 2, 4]` for three failures.
- Verify: `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_exness_stream.py -q` exits 0.

### T6.5 Gate and commit
- Steps: gate; commit `feat(exness): add signed REST client and WebSocket stream`. Ship (merge+push) only on user approval; the code is not wired, so this deploy is behaviour-neutral.
- Gate: `just test` exit 0; `uv run ruff check` exit 0; `uv run pyright` contains `0 errors`; `uv run lint-imports` contains `3 kept, 0 broken`.
- Verify: gate met; `grep -rn "print(" src/pocketquant/core/infra/exness | wc -l` prints `0`; `grep -rniE "logger\.[a-z]+\(.*(api_key|private_key|EXN-SIGN)" src/pocketquant/core/infra/exness | wc -l` prints `0`.

## Security
Key material only via `Settings` `SecretStr` (`.get_secret_value()` at signing time). Never log headers, payloads with `api_key`, or settings objects.

## Risks
| Risk | L×I | Mitigation |
|------|-----|------------|
| Query re-encoding breaks signatures | M×H | sign and send the same pre-encoded string; T6.3 test asserts signed path |
| Clock skew > 3 s | M×M | offset from `Date` on each response |
| Handshake differs from portal example | M×H | phase-01 `ws_handshake_ok` proved it |

## Rollback
Revert the commit; nothing references the package yet.

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
effort: 3d
dependencies: [6]
---

# Phase 07: Exness market data and sync policy

## Goal
`XAUUSD:EXNESS`-style symbols sync bid candles and stream bid/ask ticks through the existing ports, driven by policy #2 (WS ticks live, REST native M1/M5/M15/H1/H4/D1, no cascade, session calendar). Delivers D1.

## Context Links
- Ports: `core/domain/market_data/interfaces.py:18` (`IDataProvider`), `:40` (`IRealtimeQuoteProvider`, 9 members). Quote dict keys consumed by `app/market_data/app_services/quote_app_service.py:34-80` (`symbol`, `timestamp`, `last_price`, `bid`, `ask`, `volume`, ...).
- In-progress candle handling to mirror: `core/infra/binance/binance_client.py:75-85`.
- Spike facts: `exness-spike-summary.json` (`instrument_names`, `negative_count_includes_from`, `last_candle_in_progress`, `tick_frame_shape`, `trade_sessions`).

## Files to Create or Modify
- Create: `src/pocketquant/core/infra/exness/mappers.py`, `data_provider.py`, `quote_provider.py`; tests `tests/core_test/infra/exness/test_exness_mappers.py`, `test_exness_data_provider.py`, `test_exness_quote_provider.py`.
- Modify: `src/pocketquant/app/di/adapters.py`.

## Tasks

### T7.1 `mappers.py` (market-data part)
- Steps: `git checkout -b feat/exness-market-data`. Add: `INTERVAL_TO_EXNESS = {MINUTE_1:"M1", MINUTE_5:"M5", MINUTE_15:"M15", HOUR_1:"H1", HOUR_4:"H4", DAY_1:"D1", WEEK_1:"W1"}`; `instrument_for(symbol, suffix) -> str` (`code + suffix` from `CODE:EXNESS`); `candle_to_bar(candle, symbol, interval) -> Bar` (`datetime` = parsed `time`, OHLC floats, `volume=float(candle["volume"])` — tick volume per A-iii); `tick_to_quote(frame, symbol) -> dict` with `last_price=bid`, `bid`, `ask`, `timestamp` parsed, `volume=1.0` (one tick), other keys `None` (shape from `ticks_frames.json`); `sessions_to_calendar(trade_sessions) -> MarketCalendar` parsing `"Mon, 10:00:00"` (days Mon..Sun → 0..6) for sessions whose `trade_mode != "trading_disabled"`, end exclusive (`(sec+1)//60` when seconds = 59 else `sec//60`), empty/invalid → `ALWAYS_OPEN`.
- Tests use the phase-01 fixtures: every `candles_xauusd_m1.json` candle maps to a `Bar` with `symbol=="XAUUSD:EXNESS"`; first frame of `ticks_frames.json` maps to a dict with `last_price == bid`; XAUUSD conditions' sessions produce a calendar that is closed during each `weekend_gaps` window from the summary and open one hour before it.
- Verify: `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_exness_mappers.py -q` exits 0.

### T7.2 `data_provider.py`
- Steps: `ExnessDataProvider(IDataProvider)` with `__init__(client, settings)`; `fetch_ohlcv(symbol, interval, n_bars)`: `cutoff = floor(now, interval)`; page backwards with `from_=cursor` (start `cutoff`), `count=-min(remaining, await client.max_candles_per_request())`, `price_type="bid"`; keep candles with open time `< cutoff`; next cursor = earliest returned time; stop on empty page or short page; de-duplicate by time; return the last `n_bars` ascending. `search_symbols` returns `[]`. `close()` is a docstring-only body ("the shared client is closed by the DI container"). `calendar_for(symbol)` → `sessions_to_calendar((await client.instrument_conditions(instrument)).get("trade_sessions", []))`.
- Tests (MockTransport + fixtures): 1000 bars returned ascending, none `>= cutoff`; pagination with `max_candles_per_request=300` issues 4 calls and returns 1000 unique bars; `calendar_for` returns a non-`ALWAYS_OPEN` calendar for XAUUSD.
- Verify: `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_exness_data_provider.py -q` exits 0.

### T7.3 `quote_provider.py`
- Steps: `ExnessQuoteProvider` implementing the 9 protocol members over one `ExnessStream(client, f"/v1/server-events/accounts/{account_id}/ws/ticks", self._on_frame, "ticks")`. `subscribe(symbol, callback)` stores `{composite: (instrument, callback)}`, remembers and sends `{"id": f"ticks-{instrument}", "subscribe": {"event": "ticks", "instruments": [instrument]}}`, returns the composite key; `unsubscribe` forgets and sends the matching `"unsubscribe"` message. `_on_frame`: tick frames → `tick_to_quote` → callback, set `last_tick_at`; error frames (`trading disabled`, `MARKET_*`) → `logger.warning("exness_ticks.unavailable", ...)` and continue (no raise).
- Tests: subscribe sends the exact message; fixture frame reaches the callback with `symbol=="XAUUSD:EXNESS"`; an error frame logs and does not raise; `isinstance(provider, IRealtimeQuoteProvider)`.
- Verify: `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_exness_quote_provider.py -q` exits 0.

### T7.4 Exness policy and DI
- Target: `app/di/adapters.py`.
- Steps: add `def exness_policy(provider: ExnessDataProvider, quote_provider: ExnessQuoteProvider, max_requests_per_minute: int) -> SyncPolicy` with `exchange="EXNESS"`, `poll_intervals=(MINUTE_1, MINUTE_5, MINUTE_15, HOUR_1, HOUR_4, DAY_1)`, `cascade_intervals=()`, `sync_intervals=` same six, `calendar_for=provider.calendar_for`, `history_days={MINUTE_1: 365, MINUTE_5: 730, MINUTE_15: 1095}`, `max_requests_per_minute` = half of the T1.6 `budget_per_min`, as a module constant with a one-line comment: measured from `/limits` during the spike; the runner only warns on it, `ExnessClient` rate windows enforce the live values (boot must not depend on Exness being reachable). `AdapterProvider`: `get_exness_client(settings)` as an async generator that yields `ExnessClient(settings)` and awaits `close()` on shutdown; `get_exness_data_provider`, `get_exness_quote_provider`; `get_sync_policies` appends the Exness policy only when `client.is_configured`.
- Verify: `.venv/Scripts/python.exe -m pytest tests/app_test/unit/di -q` exits 0 after adding a test: with empty Exness settings `SyncPolicies` has only BINANCE; with dummy values (no network) it has BINANCE and EXNESS.

### T7.5 Gate, ship, D1 on prod
- Steps:
  1. Gate; characterization snapshot unchanged (`git diff --quiet tests/app_test/integration/sync_pipeline_snapshot.json`). Commit `feat(exness): add market-data and quote adapters with Exness sync policy`.
  2. **Gate on user precondition 2**: ask the user to confirm `EXNESS_*` values are in `pocketquant-config/vps/default/.env` and pushed. Then ask approval; merge; push; watch run.
  3. On prod (pattern `docs/deployment.md` "Verify"): with `ADMIN` = admin token from `pocketquant-config` env (never echo it): `POST /api/v1/market-data/tracked-symbols` `{"symbol":"XAUUSD:EXNESS"}`, same for `EURUSD:EXNESS`, `BTCUSD:EXNESS` (header `X-Admin-Token`). Then `POST /api/v1/market-data/sync` `{"symbol":"XAUUSD:EXNESS","interval":"1m","n_bars":1000,"source":"bulk_sync_api"}`.
- Gate: `just test` exit 0; `uv run ruff check` exit 0; `uv run pyright` contains `0 errors`; `uv run lint-imports` contains `3 kept, 0 broken`.
- Verify (market hours): sync response `status == "completed"` and `total_bars >= 1000`; `ssh -i "$KEY" "$HOST" "docker exec pocketquant-app timeout 70 curl -sN 'http://localhost:41921/api/v1/market-data/bars/stream/XAUUSD%3AEXNESS?interval=1m'" | grep -m1 -c '"is_in_progress": true'` prints `1`; same with `/api/v1/quotes/stream/XAUUSD%3AEXNESS` and `grep -m1 -c '"bid"'` prints `1`; after 10 minutes `docker logs pocketquant-app --since 10m | grep -c "sync_policy.rate_budget_exceeded"` prints `0`; verdict `0 failures`. Finally ask the user to open the SPA chart for `XAUUSD:EXNESS` and confirm it updates (D1 visual).

## Risks
| Risk | L×I | Mitigation |
|------|-----|------------|
| In-progress candle persisted | M×H | cutoff filter + `drop_misaligned_bars` |
| Weekend no-progress noise | M×M | runner skips closed sessions (`calendar_for`) |
| Higher-TF poll waste | L×L | only intervals whose bar just closed are fetched |

## Rollback
Delete the Exness tracked symbols (`DELETE /api/v1/market-data/tracked-symbols/{symbol}`), then revert the merge; or unset `EXNESS_*` in prod env (policy is not registered without credentials).

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

<!-- FILE: phase-08-exness-broker-and-live-order-flow.md -->
---
phase: 8
title: "Exness broker and live order flow"
status: pending
priority: P1
effort: 5d
dependencies: [7]
---

# Phase 08: Exness broker and live order flow

## Goal
`ExnessBroker(IBroker)` with lot conversion, mandatory SL, min-lot and daily-loss guards, async ACK → fill over the events WS, and venue SL/TP closes reported as fills. Subscriptions can choose broker `exness`. No live order is placed in this phase.

## Data flow
`StrategyAppService._process_signal → OrderAppService.submit → ExnessBroker.submit_order` (POST positions, `EXN-IDEMPOTENCY-KEY = order.id`) → `OrderResult(SUBMITTED, broker_order_id=operation_id)` → events WS `transaction_event` with `client_request_id == order.id` → `OrderResult(FILLED)` → `OrderAppService.on_order_update` → `OrderFilledEvent` → `PositionAppService` + strategy. Venue SL/TP close (`deals[].type == "close"`) → broker publishes `OrderFilledEvent` (opposite side) on the `EventBus`, as `PaperBroker._fire_synthetic_exit` does (`core/infra/brokers/paper/paper_broker.py:671`).

## Context Links
- Gap today: nothing subscribes `OrderAppService.on_order_update` (`engine/app_services/order_app_service.py:174`) to a live broker; subscriptions always load with `broker="paper"` (`engine/app_services/strategy_reconcile_service.py:140-146`, `app/main_extensions.py:132-140`; `StrategyConfig.broker` default `core/domain/strategy/value_objects.py:84`).
- `StrategyAppService._get_or_create_broker` `engine/app_services/strategy_app_service.py:409`.
- Dedupe pattern: `OKXBroker._seen_terminal_orders` (`core/infra/brokers/okx/okx_broker.py:59,358-362`).
- Spec: `OpenPositionRequest` (`instrument`, `side`, `volume`, `price` for `exec_mode=instant`, `deviation`, `stop_loss_price`, `take_profit_price`), `AckResponse` (`operation_id`, `client_request_id`), `transaction_event` (`status` success/rejected/failed, `error_code`, `payload.deals[]` `type` open/close, `position_id`, `price`, `volume`), `trading_state_snapshot`, `hmr_snapshot`/`hmr_update`.

## Files to Create or Modify
- Create: `src/pocketquant/core/infra/exness/broker.py`; tests `tests/core_test/infra/exness/test_exness_broker.py`, `tests/engine_test/test_async_fill_wiring.py`.
- Modify: `core/infra/exness/mappers.py` (trading part), `core/domain/brokers/interfaces.py` (`IBroker`), `engine/app_services/strategy_app_service.py`, `engine/app_services/order_app_service.py`, `core/domain/subscription/entities.py`, `engine/strategy_command_service.py`, `engine/app_services/strategy_reconcile_service.py`, `app/main_extensions.py`, `app/routes/strategy.py`, `app/di/adapters.py`, `tests/baseline/openapi_app_snapshot.json` (regenerated), `tests/core_test/unit/domain/subscription/test_subscription_entity.py`.

## Tasks

### T8.1 Trading mappers
- Steps: `git checkout -b feat/exness-broker`. In `mappers.py` add `lots_for_quantity(quantity, conditions, force_min_lot) -> Decimal | None` (`Decimal` math: `force_min_lot` → `volume_min`; else `quantity / contract_size` rounded down to `volume_step` from `volume_min`, clamped to `volume_max`; below `volume_min` → `None`), `format_price(price, point_digits) -> str`, `open_position_body(order, instrument, lots, conditions, deviation_points) -> dict` (`side` buy/sell, `volume` str, `stop_loss_price`/`take_profit_price` formatted, `price`+`deviation` only when `exec_mode == "instant"`), `fills_from_transaction(event) -> list[dict]` returning per deal `{deal_id, position_id, type, side, volume, price}`.
- Tests: XAUUSD conditions fixture: `force_min_lot=True` → `volume_min`; quantity giving 0.0349 lots with step 0.01 → `0.03`; below min → `None`; prices rounded to `point_digits`.
- Verify: `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_exness_mappers.py -q` exits 0.

### T8.2 `IBroker.reports_fills_async` and engine wiring
- Steps:
  1. `IBroker` (`core/domain/brokers/interfaces.py:12`): add class attribute `reports_fills_async: bool = False` (PaperBroker/OKX unchanged).
  2. `StrategyAppService._get_or_create_broker`: after `self._broker_factory.create(...)`, if `broker.reports_fills_async`: `await broker.subscribe_order_updates(self._order_app_service.on_order_update)`.
  3. `OrderAppService.on_order_update`: add branch `elif result.status == OrderStatus.REJECTED:` → `order.reject(result.error_message or "Order rejected")`, save, pop from `_pending`.
  4. Test `tests/engine_test/test_async_fill_wiring.py`: a fake broker with `reports_fills_async = True` returning SUBMITTED then invoking the callback with FILLED → order persisted `FILLED`, one `OrderFilledEvent` published; REJECTED path rejects; a `PaperBroker` is not subscribed (`_order_callbacks` empty).
- Verify: `.venv/Scripts/python.exe -m pytest tests/engine_test -q` exits 0.

### T8.3 `broker.py`
- Steps: `ExnessBroker(IBroker)`: `name="exness"`, `reports_fills_async=True`; `__init__(client, settings, event_bus)`. 
  - `connect()`: start `ExnessStream(client, f"/v1/server-events/accounts/{id}/ws/events", self._on_event, "events")` task; remember+send `{"id":"tx-1","subscribe":{"event":"transactions"}}`.
  - `submit_order(order)`: guards return `OrderResult(REJECTED, error_message=...)` without calling the API: not `MARKET` ("only market orders"), `order.sl_price is None` ("stop loss required"), lots `None` ("below volume_min"), daily loss reached (`snapshot()` equity vs first equity seen this UTC day ≥ `exness_daily_loss_cap_pct`). Else `ack = await client.open_position(body, idempotency_key=str(order.id))`; store `self._pending[str(order.id)] = (order, contract_size, ack_time)`; lazily send an `hmr` subscribe for the instrument; return `OrderResult(order_id, broker_order_id=ack["operation_id"], status=SUBMITTED, submitted_at, side, sl_price, tp_price)`; log `exness.order_ack`.
  - `_on_event(frame)`: `transaction_event` with `client_request_id` in `_pending`: status success + an `open` deal → `OrderResult(FILLED, filled_quantity=volume*contract_size, filled_price=price, side)`, remember `position_id → (subscription_id, symbol, side, contract_size)`, log `exness.order_filled` with `latency_ms`; status rejected/failed → `OrderResult(REJECTED, error_message=error_code)`; deliver via callbacks. `close` deals whose `position_id` is known → publish `OrderFilledEvent(order_id=generate_id_str(), subscription_id, symbol, side=opposite, filled_quantity, filled_price)` on the event bus and forget the position; unknown position → `logger.warning("exness.unmapped_close", position_id=...)`. Dedupe by `deal_id` set. `trading_state_snapshot` → if `_pending` non-empty log `exness.reconnect_pending_orders` (warning). `hmr_snapshot`/`hmr_update` → `logger.warning("exness.hmr_event", ...)`.
  - `cancel_order` → log and return `False` (market-only). `get_balance()` from `snapshot()["account_state"]` (`total_equity=equity`, `available_balance=equity-used_margin`, `margin_used`). `get_positions()` maps snapshot positions to `PositionAggregate.open(...)` with the stored subscription id or `"exness:unmapped"`. `subscribe_order_updates`/`unsubscribe_order_updates` manage a callback list. `disconnect()` closes the stream.
- Tests (fixtures + fake client + fake stream): guards reject without HTTP; ACK → SUBMITTED with `broker_order_id`; fill frame → FILLED with `filled_quantity = lots × contract_size`; duplicate frame ignored; close deal → one `OrderFilledEvent` with opposite side; rejected frame → REJECTED.
- Verify: `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_exness_broker.py -q` exits 0.

### T8.4 Broker choice on subscriptions and factory entry
- Steps:
  1. `Subscription` (`core/domain/subscription/entities.py:33`): add `broker: str = "paper"` last; `to_mongo` writes it; `from_mongo` reads `doc.get("broker", "paper")`.
  2. `AddSymbolCommand` gains `broker: str = "paper"`; `add_symbol` validates `broker in ("paper", "okx", "exness")` (else `ValidationError` 400 via existing exception types in `core/common/exceptions.py`), stores it, returns `"broker"` in the dict.
  3. `CreateSubscriptionBody` (`app/routes/strategy.py:32`) gains `broker: Literal["paper", "okx", "exness"] = "paper"` passed through.
  4. Reconcile `_ensure_instances` (`strategy_reconcile_service.py:140`) and `rehydrate_strategies_from_subscriptions` (`main_extensions.py:132`) pass `broker=sub.broker` into `StrategyConfig`.
  5. `BrokerFactory` (`app/di/adapters.py`): constructor `(event_bus: EventBus, settings: Settings, exness_client: ExnessClient)`; `create("exness", config)` → `ExnessBroker(exness_client, settings, event_bus)` or `ValueError("Exness broker requires EXNESS_ACCOUNT_ID, EXNESS_API_KEY and EXNESS_PRIVATE_KEY")` when `not exness_client.is_configured`. Update `test_broker_factory_characterization.py` construction only (paper/OKX assertions unchanged) and add an `exness` not-configured case.
  6. Regenerate OpenAPI snapshot: `BASELINE_UPDATE=1 .venv/Scripts/python.exe -m pytest tests/baseline/test_openapi_snapshot.py -q`.
- Verify: `git diff tests/baseline/openapi_app_snapshot.json | grep '^+' | grep -c '"broker"'` ≥ 1; `git diff tests/baseline/route_inventory_app_snapshot.json | wc -l` prints `0`; `.venv/Scripts/python.exe -m pytest tests/core_test/unit/domain/subscription tests/engine_test tests/app_test/integration/test_strategy_subscriptions_api.py tests/baseline -q` exits 0.

### T8.5 Gate and ship (no live order)
- Steps: gate; commits `feat(exness): add broker with lot conversion and async fill mapping`, `feat(trading): let subscriptions choose their broker`; ask approval; merge; push; watch run.
- Gate: `just test` exit 0; `uv run ruff check` exit 0; `uv run pyright` contains `0 errors`; `uv run lint-imports` contains `3 kept, 0 broken`.
- Verify: gate met; `grep -rn "from pocketquant.core.infra" src/pocketquant/core/domain | wc -l` prints `0`; `git diff master -- src/pocketquant/core/domain | grep '^+' | grep -ciE "contract_size|volume_step|volume_min|spread|lots?\b"` prints `0` (CFD logic stays in the adapter); verdict `0 failures`.

## Risks
| Risk | L×I | Mitigation |
|------|-----|------------|
| Fill arrives before ACK returns | M×H | correlation by `client_request_id == order.id`; `on_order_update` waits on the same lock as `submit` |
| Venue close after restart unmapped | M×M | `exness.unmapped_close` warning; do not restart during a live test (phase 09) |
| Oversized live order | L×H | `exness_force_min_lot=True` default, SL mandatory, daily cap |
| OKX behaviour change | L×M | `reports_fills_async` defaults `False`; OKX untouched |

## Security
Idempotency key = order UUIDv7 (36 chars, allowed set). Never log request bodies with credentials; responses logged only by ids.

## Rollback
Revert merge; existing subscriptions without `broker` read as `paper`. Docs written by `to_mongo` with `broker` are ignored by the reverted `from_mongo`.

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

<!-- FILE: phase-09-validation-spread-backtests-live.md -->
---
phase: 9
title: "Validation: spread, backtests, live round trip"
status: pending
priority: P1
effort: 5d + 1 weekend
dependencies: [8]
---

# Phase 09: Validation: spread, backtests, live round trip

## Goal
Honest re-validation: PaperBroker `spread`, Exness backtests of both strategies, one minimum-lot live round trip per strategy with SL, and one observed weekend close/reopen. Delivers D2, D3.

## Context Links
- Fill price today: `PaperBroker._apply_slippage` `core/infra/brokers/paper/paper_broker.py:436`; slippage set per run at `backtest/engine/backtest_app_service.py:102`; config chain `backtest/backtest_command_service.py:22-70` → `backtest/workers/backtest_dispatch.py:43` → `backtest/models/backtest_config.py:9` → `backtest/engine/result_collector.py:430-441`.
- Routes: `POST /api/v1/backtest/run`, `GET /api/v1/backtest/{run_id}`, `GET /api/v1/backtest/{run_id}/trades`; `POST /api/v1/strategies/{code}/subscriptions`; `POST /api/v1/subscriptions/{id}/start|stop`; `GET /api/v1/trading/orders|positions`.

## Files to Create or Modify
- Modify: `core/infra/brokers/paper/paper_broker.py`, `backtest/models/backtest_config.py`, `backtest/backtest_command_service.py`, `backtest/workers/backtest_dispatch.py`, `backtest/engine/backtest_app_service.py`, `backtest/engine/result_collector.py`, `tests/baseline/openapi_app_snapshot.json` (regenerated). Create: `tests/core_test/infra/brokers/test_paper_broker_spread.py`, `docs/journals/<date>-exness-live-validation.md`.

## Tasks

### T9.1 `spread` in PaperBroker and the backtest config chain
- Steps: `git checkout -b feat/paper-spread`. `PaperBroker.__init__(..., spread: float = 0.0)` + `spread` property/setter; `_apply_slippage`: BUY `(price + spread/2) * (1 + slippage)`, SELL `(price - spread/2) * (1 - slippage)`. `BacktestConfig.spread: float = 0.0` (absolute price units); `RunBacktestCommand.spread: float = Field(default=0.0, ge=0)`; config dict key `"spread"`; `_config_from_dict` reads `payload.get("spread", 0.0)`; `BacktestAppService` sets `self._broker.spread = config.spread` next to slippage; `result_collector` config snapshot includes `"spread"`. Regenerate OpenAPI snapshot with `BASELINE_UPDATE=1`.
- Tests: spread 0 leaves every existing paper-broker test green; spread 0.4 with slippage 0: market BUY at 100 fills 100.2, SELL fills 99.8; SL exit of a long fills at `sl - 0.2`.
- Verify: `.venv/Scripts/python.exe -m pytest tests/core_test/infra/brokers tests/backtest_test -q` exits 0; `git diff tests/baseline/openapi_app_snapshot.json | grep '^+' | grep -c '"spread"'` ≥ 1.

### T9.2 Gate and ship spread
- Gate: `just test` exit 0; `uv run ruff check` exit 0; `uv run pyright` contains `0 errors`; `uv run lint-imports` contains `3 kept, 0 broken`.
- Steps: commit `feat(backtest): model a constant bid-ask spread in PaperBroker`; ask approval; merge; push; watch.
- Verify: gate met; verdict `0 failures`.

### T9.3 Backfill and backtests on Exness bars
- Steps (prod, via ssh+curl as in phase 07): `POST /api/v1/market-data/sync` with `n_bars: 5000` for each of `XAUUSD`, `EURUSD`, `BTCUSD` `:EXNESS` × `1m` and `1h` (`source: "bulk_sync_api"`). Spread per instrument = typical spread from the phase-01 tick fixture (median `ask - bid`), recorded in the validation journal. Run `POST /api/v1/backtest/run` for `hitnrun2` on `XAUUSD:EXNESS` `1m` and `engulfing` on `XAUUSD:EXNESS` `1h`, `start_date`/`end_date` spanning the synced range, `spread` set, `slippage_bps: 0`, `commission_bps: 0`. Poll `GET /api/v1/backtest/{run_id}` until status is not `started`.
- Success criteria: both runs persisted with non-empty trades.
- **Stop and ask** if a run completes with zero trades (do not change strategy parameters or date ranges on your own).
- Verify: `GET /api/v1/backtest/{run_id}` status `completed` for both; `GET /api/v1/backtest/{run_id}/trades` returns ≥ 1 item for both.

### T9.4 Live round trip per strategy (minimum lot, SL attached)
- Steps:
  1. **Gate on user precondition 3**: ask the user to confirm the risk cap (minimum lot, SL always, daily loss cap %) and that prod env has `EXNESS_FORCE_MIN_LOT=true` and `EXNESS_DAILY_LOSS_CAP_PCT=<value>`. Wait for explicit yes.
  2. Check prod settings without printing secrets: `ssh ... "docker exec pocketquant-app python -c \"from pocketquant.core.config import get_settings as g; s=g(); print(s.exness_force_min_lot, s.exness_daily_loss_cap_pct)\""` prints `True <cap>`.
  3. **Stop and ask** if any planned order would exceed minimum lot or run without SL (guards make this impossible; if the check in step 2 prints `False`, stop).
  4. Create subscriptions: `POST /api/v1/strategies/hitnrun2/subscriptions` `{"symbol":"XAUUSD:EXNESS","interval":"1m","broker":"exness"}` and `POST /api/v1/strategies/engulfing/subscriptions` `{"symbol":"XAUUSD:EXNESS","interval":"1h","broker":"exness"}`; response has `"broker":"exness"`. Start both. Do not restart the app while a position is open.
  5. When each strategy has had one entry filled and then closed by SL/TP, stop its subscription (`POST /api/v1/subscriptions/{id}/stop`).
- Success criteria: per strategy one order `FILLED` and one position visible, closed later by venue SL/TP.
- Verify: `docker logs pocketquant-app | grep exness.order_filled` shows one line per strategy with `latency_ms` ≤ 10000; `GET /api/v1/trading/orders` contains each order with `status` `filled`; during the open period `GET /api/v1/trading/positions` lists it; after close `docker logs ... | grep -c exness.unmapped_close` prints `0`; user confirms the SPA showed the position.

### T9.5 One week live observation incl. a weekend
- Steps: keep the Exness symbols tracked through one Friday close and Sunday reopen.
- Verify (after the week): `docker logs pocketquant-app --since 168h | grep -c exness_stream.circuit_open` prints `0`; `grep -c '"integrity.issues_found".*EXNESS'` over the same window for `XAUUSD`/`EURUSD` prints `0`; `grep -c "market_data.sync.stuck_threshold_crossed.*EXNESS"` prints `0`; `exness_stream.disconnected` lines, if any, are followed by reconnect within 30 s. Record results in `docs/journals/<date>-exness-live-validation.md` (Vietnamese prose).

## Risks
| Risk | L×I | Mitigation |
|------|-----|------------|
| Real money loss | M×H | min lot, SL required, daily cap, user gate, attended run |
| Spread-free optimism | H×M | T9.1 before T9.3 |
| Swap not modelled for multi-day `engulfing` | M×L | noted in journal (advice trade-off) |

## Rollback
Stop subscriptions; close any open position from the Exness terminal; revert T9.1 merge if needed (spread defaults to 0).

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

<!-- FILE: phase-10-architecture-deployment-docs.md -->
---
phase: 10
title: "Architecture, deployment and MT5 docs; final gate"
status: pending
priority: P2
effort: 1d
dependencies: [9]
---

# Phase 10: Architecture, deployment and MT5 docs; final gate

## Goal
Docs describe the system as it is (D7), deployment lists the Exness env vars, MT5 is a documented future provider; the final D4/D5/D6 checks run.

## Context Links
- `docs/system-architecture.md` sections "Layer 4: Adapters" (:255), "Where Does X Live?" (:455, `app/di/` row :472, sync registration row :483), "Real-Time Streaming" (:553), "Dependency Injection (Dishka)" (:604-606), "Known Limitations" (:710).
- `docs/deployment.md` env table (:83-94). `README.md` canonical routes. `CLAUDE.md` Layout line (contract count).

## Files to Create or Modify
- Modify: `docs/system-architecture.md`, `docs/deployment.md`, `README.md` (only if it lists modules/routes that changed), `docs/README.md` (only if its index names changed files).

## Tasks

### T10.1 Architecture doc
- Steps: `git checkout -b docs/exness-architecture`. Vietnamese prose, AS-IS. Add/update: Exness adapter package (`core/infra/exness/` 7 modules and their port), a Mermaid diagram of the sync-policy flow (`APScheduler → sync_runner → SyncPolicies → SyncService → provider`; live `RoutedQuoteProvider → quote providers`), the policy table (BINANCE vs EXNESS fields), live order flow (ACK → events WS → fill; venue SL/TP close), DI = 3 providers, "MT5 (future provider, not built)": same three ports, policy sketch (`copy_rates_from` as bar source, `copy_ticks_from` as live source, Windows host or Wine bridge), deployment impact. Known limitations: venue close after restart unmapped; operation recovery by logs only; swap not modelled.
- Verify: `grep -c "core/infra/exness" docs/system-architecture.md` ≥ 1; `grep -c "SyncPolicy" docs/system-architecture.md` ≥ 1; `grep -c "MT5" docs/system-architecture.md` ≥ 1; `grep -cE "6 providers|sync_jobs|sync_internals" docs/system-architecture.md` prints `0`.

### T10.2 Deployment doc
- Steps: add rows for `EXNESS_ACCOUNT_ID`, `EXNESS_API_KEY`, `EXNESS_PRIVATE_KEY` / `EXNESS_PRIVATE_KEY_PATH`, `EXNESS_INSTRUMENT_SUFFIX`, `EXNESS_FORCE_MIN_LOT`, `EXNESS_DAILY_LOSS_CAP_PCT` (Req: No, purpose "Exness live venue") to the env table; one line that the key's IP allowlist must include the VPS.
- Verify: `grep -c "EXNESS_" docs/deployment.md` ≥ 6.

### T10.3 Final D4/D5/D6 gate
- Steps: run `uv run python scripts/code_metrics.py`.
- Success criteria: `tiny_share<=30`, `pure_delegation<=20`, `status=PASS`.
- **Stop and ask** if `status=FAIL`: report the numbers and `--list tiny`/`--list delegation` output, and offer (A) consolidate the OKX websocket helper modules (`core/infra/brokers/okx/websocket/okx_message_parser.py`, `okx_order_mapper.py`, `okx_position_mapper.py`, ~16 tiny accessors) behind new characterization tests, or (B) accept the measured values as the soft-gate thresholds. Do not inline other code to move the numbers.
- Verify: `uv run python scripts/code_metrics.py` exits 0; `test -d src/pocketquant/engine/market_data/sync_internals; echo $?` prints `1`; `ls src/pocketquant/app/di/*.py | wc -l` prints `4`; `ls src/pocketquant/app/routes/market_data*.py | wc -l` prints `2`; `uv run lint-imports` contains `3 kept, 0 broken`; `just test` exit 0; `uv run ruff check` exit 0; `uv run pyright` contains `0 errors`; `.venv/Scripts/python.exe -m pytest tests/core_test/infra/binance tests/engine_test/test_broker_factory_characterization.py tests/app_test/integration/test_sync_pipeline_characterization.py -q` exits 0.

### T10.4 Commit and ship
- Steps: commit `docs: describe Exness adapters, sync policies and MT5 path`; ask approval; merge; push (docs-only pushes are ignored by CI `paths-ignore`, so no deploy).
- Verify: `git log -1 --format=%s` equals the message; `git status --porcelain | wc -l` prints `0`.

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
