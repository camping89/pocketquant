# Phase 07 checkpoint: go/no-go for Phase 08

Reviewed 2026-10-29 on `develop` @ 4ba15de2 (origin/develop e646b3b5, origin/master e646b3b5).

## TL;DR

**GO, after one housekeeping commit.** Phase 07 evidence satisfies every Phase 08 entry-gate line except line 1, which misses today for a reason unrelated to Phase 07: `docs/governance/` is untracked and `CLAUDE.md` has an uncommitted diff (the docs purge started 2026-10-29). Phase 08's text needs only line-number corrections in `compose.prod.yml` and `10-deploy.sh`; no symbol, lease name, event name or script reference is stale. The Binance HTTP 400 predates Phase 07 and is harmless; fix it in Phase 09, not Phase 08.

## Q1. Entry gate against Phase 07 evidence

| Line | State | Evidence |
|---|---|---|
| 1 clean tree | **MISS** | `git status --porcelain -- ... docs` prints `?? docs/governance/` (fact, run today). `CLAUDE.md:7` already points at it, uncommitted. |
| 2 `Result: PASS` | met | `deploy-a-roles-and-leases.md:106`, count 1. |
| 3 lease module on master | met | `git cat-file -e origin/master:...lease_repository.py` printed `deploy-a-on-master`. |
| 4 `oom_baseline=` | met | count 1 in `machine-baseline.md`. |
| 5-6 Docker, VPS | not run here | Report: `probes_left=0`, one `pocketquant-app`; the gate re-checks. |

Action before the gate: commit `docs/governance/` and `CLAUDE.md` on `develop` (`.md`-only, no CI). If the owner considers the purge unfinished, stash them instead; do not leave them in the tree. Note that HEAD is one docs commit ahead of `origin/develop`; Task 8.6 step 3 pushes it, nothing else needed.

Phase 07 facts Phase 08 depends on, all verified: lease names `worker`/`trader` (`roles.py:139,234`); `/health` `role`/`lease`/`lease_renewed_age_s` (`main_extensions.py:352-368`); owner `hostname:pid` (`main.py:50`); every event in Context line 27 exists in `roles.py` and `strategy_app_service.py:460,505,575`; `app_roles` default `api` (`config.py:64`); lease doc fields `name/owner/expires_at/renewed_at/released_at` match `leases.sh` (`lease_repository.py:32-46`); `$lte` changes no Phase 08 text. No `start_jobs`, `recover_orphan_backtests` or `ENABLE_JOBS` remains in the phase file. Rehearsal seam: `PaperBrokerAdapter` inherits the `inflight_count` property from `broker_port.py:26-27` and the engine reads it as a property (`strategy_app_service.py:493`), so the `sitecustomize` patch is shape-correct; the seed script's imports and types resolve. `11-verify.sh`, `cicd.yml`, `nginx.conf` and `web/Dockerfile` line citations still hold.

### Corrections (2026-10-29)

Line drift from 2efcc067 (Phase 07 edited `compose.prod.yml` and `10-deploy.sh` after the Context was verified at 453e8e90):

- Context line 16: `verified on develop @ 453e8e90` -> `@ 4ba15de2`.
- Context line 18: `app` `:53-91` -> `:53-92` (comment `:53-55`, service `:56-92`); `container_name: pocketquant-app` `:60` -> `:58`; Vietnamese comments `:113-114` -> `:114-115`; networks comment `:164` -> `:165`; backend network declared `:167` -> `:168`.
- Context line 20: `wait_health` `:54-70` -> `:54-71`; `wait_health pocketquant-app 41921 240` `:72` -> `:73`; prune `:75` -> `:76`.
- Task 8.1 target line 66: `:53-57` -> `:53-55`; `:113-114` -> `:114-115`; `:164` -> `:165`. Step 2 `(:53-91)` -> `(:53-92)`; step 4 `:113-114` -> `:114-115`; step 5 `:164` -> `:165`.
- Task 8.3 target line 130: `:43-78` -> `:43-79` (file is 79 lines).

## Q2. Binance HTTP 400

Fact (code): `QuoteAppService.start()` creates the `run_forever` task (`quote_app_service.py:102`) before `start_quote_feed` creates the subscription task (`main_extensions.py:209`). `run_forever` connects at once; with no subscriptions `_build_url` returns the placeholder `wss://stream.binance.com:9443/ws/` (`binance_websocket_adapter.py:174-175`). Subscriptions arrive only from `WsSubscriptionAppService._reconcile`, which first awaits Mongo (`ws_subscription_app_service.py:70,86`).
Fact (tested today): Binance answers that placeholder URL with HTTP 400 and accepts `/ws/btcusdt@aggTrade`.
Fact: the pre-Phase-07 `main_extensions.py` (d10c1c3d) created the tasks in the same order.
Inference (high): the 400 is the first connect racing the first reconcile, it predates Phase 07, and the standby -> quote feed -> lease order is not the cause. No pre-Phase-07 prod log survives to make this a fact.

Impact: one ERROR line per trader start, ticks start about 1 s later, inside standby. After Task 8.4 the new `[error` pattern turns it into a WARN in `11-verify.sh` (`:178-182`), never a FAIL; Phase 10 counts only `Error notifying listener`.

Recommendation: **follow up in Phase 09** (a Python change in Phase 08 would break its "no Python changed" premise, Task 8.5 note and Task 8.6 step 1). Fix shape: `run_forever` waits until `_subscriptions` is non-empty before the first `connect()`; delete the placeholder branch.

## Assumptions

- The docs purge files are safe to commit as-is (medium); the owner decides.
- Prod has Binance tracked symbols, so the 1 s delay never matters (high).

Status: DONE_WITH_CONCERNS
Summary: GO for Phase 08 once `docs/governance/` and `CLAUDE.md` are committed; apply the line-number corrections above. The Binance 400 is a pre-existing connect-before-subscribe race, harmless, scheduled for Phase 09.
