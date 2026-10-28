# Debate evidence packet: Exness-only data, `api`/`worker`/`trader` split, zero-downtime trader handover

Working dir: `D:/w/_me/algotrading/pocketquant` (git repo, branch `develop`, HEAD 453e8e90). Timezone Asia/Bangkok; all times in plans are UTC. Plan dir: `plans/261028-0652-exness-only-parallel-runtime/`.

## Binding inputs (read in this order)

1. `plans/reports/brainstorm-261028-1159-parallel-exness-only-runtime.md`: the accepted contract (outcome §1, constraints §2, non-goals §3, acceptance §4, trade-offs §5, better approaches §6, recommended direction and phase sketch §7, unknowns §8), the verifier corrections appendix (12 items) and the owner decisions D11-D24. **The owner decisions override the body where they conflict.**
2. `plans/reports/brainstorm-261028-1159-evidence-packet.md`: owner decisions D1-D10 and the code facts behind them.
3. `plans/reports/kongming-261028-1020-parallel-exness-only-reanalysis.md`, `plans/reports/code-reviewer-261028-0915-live-path-parallel-safety.md` (C1-C3, H1-H3, M1-M3 findings), `plans/reports/explore-261028-0915-tradingview-removal-impact.md` (TV/CME removal surface), `plans/reports/kongming-261028-0848-event-loop-concurrency-review.md`, `plans/reports/brainstormer-261028-0915-parallel-process-topology.md`, `plans/reports/researcher-261028-0920-exness-index-cfd-equivalents.md`.
4. `CLAUDE.md` (repo rules), `docs/system-architecture.md`, `docs/deployment.md`, `docs/code-standards.md`, `deploy/compose.prod.yml`, `web/nginx.conf`, `.github/workflows/cicd.yml`, `justfile`.
5. `plans/261028-0652-exness-only-parallel-runtime/reports/researcher-261028-1400-compose-rolling-deploy.md`: compose rolling swap recipe, nginx re-resolve (today's static `proxy_pass` at `web/nginx.conf:26` breaks under a swap), `container_name: pocketquant-app` must go, uvicorn SIGTERM/graceful-shutdown facts, scripts using the fixed container name, and the one-time `app` → `api`/`worker`/`trader` cutover.

## Decision summary (authoritative list; details in the report)

- D1/D4: delete TradingView, the CME calendar, `ES1!/NQ1!/YM1!:TRADINGVIEW`, subscription `01a178ef` and their data.
- D2: live 1m included; a 1m entry reaches Exness within ~2 s of bar end.
- D3: Binance stays data + paper. Exness is the only live venue.
- D5/D6: one 8 vCPU / 16 GB host; full `api`/`worker`/`trader` split from one image in this delivery.
- D7/D8: zero-downtime deploys; no missed bar or order; new trader warms up in standby, takes the lease at a bar boundary; 1-2 s handover gap allowed.
- D9: strategy state rebuilt from stored bars + venue position; no new state store.
- D10: stale or gapped bars refuse entries, exits/SL always run, one WARNING per skip (1m >10 s, 15m >60 s, 1h >120 s late).
- D11: delete the Exness `closePosition` branch; live positions close only by venue SL/TP.
- D12: before re-arming live, a live minimum-lot canary: first 20 entries, T0→T6 p95 ≤ 2 s.
- D13: paper balance rebuilt at takeover from initial balance + realized P&L in stored trades.
- D15/D24: spike two ticks WS sessions on ONE key/account first, before handover code; fallback if they interfere is a second Exness account (not a second key). The plan picks F1-A (hot standby with tick overlap) or a fallback from the spike result.
- D16: rewrite the `CLAUDE.md` rule "When a change needs more code than the code it replaces, stop and ask" into a plain KISS rule; net line counts are not a stop gate. Also rewrite "Single uvicorn worker only" to "one lease-holding trader and one lease-holding worker".
- D17: the second-trader / two-WS probe may run any time; `EXNESS_LIVE_TRADING` is off, so no real trade is at risk.
- D18: orphan backtest sweep uses a heartbeat (running backtests refresh a timestamp; sweep fails only stale ones).
- D19: 429 gate stays at 72 `exness.rate_limited_retry` per 7 days, 0 terminal `exness.rate_limited` on order ops.
- D20: gap threshold 60 s trading time; timer-close grace 0.5 s; check VPS NTP sync before enabling timer close.
- D21: more than 2 live 1m subscriptions expected: do not hold the bar lock across `openPosition`; opens on one boundary must not add to N × call latency.
- D22/D23: Exness API does not support indices (Help Center, consistent with verified 404s). **Phase 4 (US indices) is dropped from this delivery.** Indices acceptance row and open questions 1 and 7 are out.
- Plan location: a NEW plan dir (this one). The final "re-arm live" step points to re-running phases 11-12 of `plans/261019-1957-exness-go-live/` (do not copy them) plus the D12 canary.

## Verifier corrections the plan must apply (from the report appendix)

`stop_grace_period` ~120 s with lease TTL 30 s / renew 10 s; build and warm strategies in standby (hitnrun2 needs 481 1m bars); define the Redis-seed gap case using `last_update`; synchronous loss-cap fallback costs ~2 s on the first entry after a close (say so); heartbeat orphan sweep (D18); pause route returns an error when the store write fails; move `web` `depends_on` and the nginx upstream from `app` to `api`; second-trader test is the two-WS spike (D17); update the ES memory note when TV removal lands; `main.py:472-475` does not exist (quote feed at `main.py:65`, sweeps at `main_extensions.py:132-172`).

## Exness facts from the public OpenAPI spec (`.cache/exness-docs/exness_api.yaml`, downloaded 2026-10-28)

- REST limits are per account across the AP cluster (`global_account_rate` measured 10/s; 2/s for candles, deals, orders, snapshot, limits, instrument list). WebSocket limits are per account per server node: `max_active_connections` measured 10, connection-rate bucket, 50 inbound msgs/s, 25 subscribe ops/s, strikes threshold 10 (a subscribe to a non-existent instrument is a strike).
- Idempotency: same key + same payload returns the original `operation_id` without re-executing; same key + different payload is rejected; retention "limited time" (unpublished). Key length 5-128, `[A-Za-z0-9._~-]`.
- Mutating trading calls return an ACK with `operation_id`; the final result arrives on the events stream or via `GET .../operations/{operation_id}`.
- WS streams have no replay; after reconnect, resubscribe and reconcile from snapshot.

## Repo conventions the plan must follow

- Branch model: all work on `develop`; a `develop` push runs CI tests only; a `develop:master` fast-forward push deploys prod (ask before any master push). Push recipe and gh token handling: `plans/261019-1957-exness-go-live/plan.md` "Ops recipe" section; reuse it, do not reinvent.
- Tests: `just test` needs Docker Desktop; expected local Windows red is exactly `4 failed, 4 errors` in `tests/core_test/unit/common/test_utc_runtime_guard.py` and `tests/core_test/infra/scheduling/test_cron_trigger_timezone.py`. CI runs `lint-imports` (8 contracts), the code-metrics ratchet (flexible: raise the ceiling in its own commit rather than pad code) and pytest.
- `CLAUDE.md` limits: a flow reads in ≤3 files, ≤2 hops to I/O, new class/flag/config key needs a second real caller today, delete dead code in the same change, logs follow the frequency rule, English only in code/docs/plans.
- Symbol delete through the API cascades market data, subscriptions and backtests.
- Runner: `eve-cook-plan` executes `phase-NN-*.md` in strict numeric order; file order = execution order.

## Handover contract (`--advice`)

The plan will be executed by a weaker model. Every phase decomposes into tasks with Goal, Target files and symbols, Steps, Success criteria, and a Verify field that is a mechanical comparison (exact command + exact expected result) or an explicit `no verification needed`. Every phase file contains the literal Failure Protocol block (stop, spawn `kongming` with task id, steps, command, full output, failed pass condition; if `kongming` cannot be spawned, stop and report to the user).

## Owner decisions during planning (2026-10-28)

| # | Topic | Decision |
|---|---|---|
| D25 | Host size | Verified 2026-10-28 by SSH: the prod VPS has **2 vCPU and 3 GB RAM**, Docker Compose v5.1.1, Engine 29.3.0, NTP synchronized. D5's 8 vCPU / 16 GB host does not exist yet. The owner chooses to run this delivery on the current machine and upgrade later, and wants to **see and measure the current machine's limits** (CPU, memory, loop lag, OOM risk during the two-trader overlap). The verification phase must report them. |
| D26 | Stale budgets beyond D10 | Proportional: 5m 30 s, 4h 300 s, 1d and 1w 600 s (1m 10 s, 15m 60 s, 1h 120 s stay as D10). |
| D27 | `web` gap per deploy | Accepted: `web` keeps being recreated with a few seconds of SPA gap; trading is unaffected. The handover probe targets the API path through `web` only between web recreations, or is measured against `api` directly; `web` is excluded from the zero-failure probe criterion. |
| D28 | TradingView `rg` gate | Exclude dated records: `docs/journals/**` and `plans/**` are not edited and not checked. |
| — | Code facts all three candidates verified | Only 6 import-linter contracts remain after TV removal (two exist only for the deleted libraries, `pyproject.toml:141-176`). `/api/health` does not exist (`/health` at `main_extensions.py:372`, nginx proxies `/api/` only). |
| D29 | Handover deploy count | Same-tag re-rolls (`IMAGE_TAG=<current> bash deploy/vps/10-deploy.sh`) count as handover deploys; at least 5 of the 10 are re-rolls and carry the zero-failure web probe. |
| D30 | Opposite-side entries on paper | Rejected in the risk check, the same as live (D11). Exits are SL/TP only on paper and live. |
| D31 | D25 machine-limit gate | Record only. Measure and report every D25 metric; the only stop condition is an OOM line (`dmesg` OOM / oom-kill). Low available memory, swap use and trader loop lag ≥ 0.5 s are reported, not stops. |
| D32 | Mongo backup before the TradingView cascade delete | No backup. Delete directly per D4 (explicit owner decision; it overrides the standing "back up before data changes" rule for this one delete). |
