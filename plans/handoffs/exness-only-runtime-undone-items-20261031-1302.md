---
handoff-version: 1
generated: 2026-10-31T06:03:00Z
generator: ak:handoff
focus: "hand off every undone item of plan 261028-0652-exness-only-parallel-runtime (closed under D37/D38); re-confirm each item's current state before acting"
workspace: D:/w/_me/algotrading/pocketquant
branch: develop
head: cbb46e18
---

# HANDOFF: undone items of the exness-only parallel runtime plan

## Mission and current status

"hand off every undone item of plan D:/w/_me/algotrading/pocketquant/plans/261028-0652-exness-only-parallel-runtime (closed under D37/D38) to a new Orca Claude tab, which must re-confirm each item's current state before acting"

Outcome wanted: the owner gets a confirmed, current list of what the closed plan left undone, then decides which items to do. Re-confirm every item against the repo and prod before proposing or doing anything.

Done (plan status `completed`):
- Phases 01-09: TradingView/CME removed; money-path fixes; prod runs one image as three compose services `api`, `worker`, `trader` with Mongo leases; rolling deploy with trader handover at a 1m bar boundary; heavy sync jobs resume per symbol after a worker handover; docs updated per `docs/governance/documentation-rules.md`.
- Phase 10 closed early by the owner (D37): 7 counted handover rows PASS (6 same-tag re-rolls), about 19 h of paper.
- Phase 11 stopped after Task 11.3 (D38): live re-armed at 2026-10-31T05:12Z, then disarmed at about 06:00Z. Entries stay paused.

Remaining (undone; each is a candidate, not an order):
1. Owner wants to reset all strategies ("delete all and start fresh"). Not started. Scope not yet chosen: prod data only, or data plus strategy code.
2. Follow-up bug: the SPA Exness strip shows the api's `live_trading` flag, which compose pins off; it reads OFF even when the trader is armed.
3. Follow-up bug: the api-side `BROKER_DISABLED` check in `StrategyCommandService.add_symbol` refuses every exness subscription create on the split runtime (the api's own flag is pinned off). The UI cannot create an exness subscription.
4. Waived Phase 10 checks (D37): 3 more handovers, 14 clean paper days, 2 weekly rows with 7-day job metrics, multi-day memory trend, a Monday-open / post-DST observation.
5. Phase 11 go-live never ran (D38): one strategy live, D12 canary (20 live entries, p95 `t0_t6_ms` ≤ 2000), D33 three live re-rolls, go-live Phase 12 observation, go-live declaration.
6. Never exercised in prod: heavy-job resume after a worker handover cuts a running `sync_backfill` / `sync_integrity` / `sync_repair`.
7. VPS helper gotcha left as is: `/opt/pocketquant/bin/leases.sh` and `deploy/vps/11-verify.sh` run `docker exec -i` and swallow the rest of a script piped into `ssh 'bash -s'`. Only plan text was fixed (`< /dev/null`).
8. Paper subscription `hitnrun2 XAUUSD:EXNESS 1m` (id 01a15754-39ed-73e3-921e-df085eb4a786) is still running in prod; it would go with a strategy reset.

Urgency: none. Live is off and entries are paused.

## Scope and guardrails

- Workspace: `D:/w/_me/algotrading/pocketquant` (branch `develop`), config repo `D:/w/_me/algotrading/pocketquant-config`.
- In scope: re-confirm items 1-8, report the confirmed state to the owner, then do only what the owner approves.
- Out of scope: re-opening the closed plan; arming live trading; pushing `develop:master` without the owner's explicit yes.
- Constraints (owner, standing):
  - Questions to the owner in Vietnamese; code, docs, plans, commits in English.
  - End every response with `mementomori - <yyyy-mm-dd>`.
  - Separate verified fact from inference; never invent a cause.
  - Conventional commits, no AI references, no plan ids in code or commit messages.
  - Read every file in `docs/governance/` before any doc work; docs never copy code-owned values.
  - KISS/DRY; deliver the requested scope, nothing extra.
- Safety boundaries:
  - Back up prod Mongo before any data change (`docs/deployment.md` → Mongo backup and restore).
  - Never remove a tracked symbol: it cascades to market data, subscriptions and backtests.
  - Never print tokens, keys or `.env` values. Credentials live only in `../pocketquant-config/`.
  - `develop` pushes run tests only; every `master` push deploys to prod. Ask before any `master` push.
  - Never commit `.claude/agent-memory/code-reviewer/MEMORY.md` (it is modified locally and is not this work's file).

## Current state

- Branch: `develop`
- HEAD: `cbb46e18` (pushed; equal to `origin/develop` at capture)
- `origin/master`: `ee298e78` (prod image; later `develop` commits are plan/report Markdown only)
- Working tree: dirty, not from this work.
- Changed files: `.claude/agent-memory/code-reviewer/MEMORY.md` (not this work's; leave it).
- Untracked files: `plans/journals/2026-10-28-plan-for-exness-only-data-and-the-api-worker-trader-split.md`, eight `plans/reports/*-261028-*` brainstorm/research reports and the `plans/reports/brainstorm-261028-1159-candidates/` directory (pre-existing; owner has not asked to commit them).
- Intentional local modifications: no (none belong to this handoff).
- Prod state at capture (observed 2026-10-31 ~06:00Z): containers `api`, `worker`, `trader` all `EXNESS_LIVE_TRADING=false`; trader safeguards `"live_trading":false,"entries_paused":true`; 0 `broker=exness` subscriptions; `OOM_OK`.
- Config repo `pocketquant-config`: HEAD `76acb5e` (disarm), pushed.

## Decisions and rationale

- D37 — Phase 10 closed early on current evidence — owner preferred not to wait 14 days — rejected: keep 14 days, shorten to ~5 days — `plan.md` decision table.
- D38 — Plan closed after Task 11.3 — owner will reset strategies, so no strategy can go live under this plan — rejected: run go-live with an existing strategy — `plan.md`.
- Disarm on close — no canary has proven live orders on the split runtime — rejected: keep armed and paused — `reports/re-arm-log.md`.
- Strategy reset deferred — owner answered "Chưa xoá, chỉ đóng plan" — rejected for now: delete prod data only, delete data plus code.
- Keep compose pinning `EXNESS_LIVE_TRADING` off for `api`/`worker` — the api cannot send an order even through a bug — rejected: unpin — `deploy/compose.prod.yml`, `reports/kongming-phase-11-rearm-verify.md`.
- Governance over plan doc steps — `docs/governance/documentation-rules.md` is newer and owner-approved — rejected: copy code-owned values into docs — phase-09 correction note.

## Work performed

- Last session commits on `develop` (latest first): `cbb46e18` plan close + disarm record; `968f6aa2` re-arm record; `6ebdb403` Phase 10 early close; rows and reports before that. Code fixes earlier in the plan: `ab2bb9eb` (Binance WS waits for a subscription), `6142249f` (idempotency index), `d92f88cb` (heavy-job resume).
- Config repo: `e7cc081` armed, `76acb5e` disarmed (`vps/default/.env`, one line each).
- CI runs: `41171394802` (re-arm deploy) and `41174376031` (disarm deploy), both succeeded with 0 verify failures.
- Go-live run 1 closed: `plans/261019-1957-exness-go-live/reports/round-trip.md` has `round_trip: DONE`.
- 0 redactions applied.

## Verification

| Check | Command | Outcome | When |
|---|---|---|---|
| Full test suite | `uv run python -m pytest tests/ -q` | only the expected local red: 4 failed, 4 errors (tzset tests) | 2026-10-30 |
| Handover rows | Phase 10 Task 10.3 facts script | rows 1-7 PASS | 2026-10-30 |
| Disarm per role | `docker inspect` env on api/worker/trader | all `EXNESS_LIVE_TRADING=false` | 2026-10-31 ~06:00Z |
| Trader safeguards | `compose exec -T trader curl -s .../admin/safeguards` | `live_trading:false`, `entries_paused:true` | 2026-10-31 ~06:00Z |
| OOM | `/opt/pocketquant/bin/oom-check.sh <baseline>` | `OOM_OK` | 2026-10-31 ~06:00Z |

Not run:
- Any check on items 2, 3, 6 and 7 beyond code reading: they are follow-ups, not fixed.
- Multi-day memory trend, Monday-open behaviour, 7-day metrics: waived (D37).

## Open risks and blockers

- Type: question. Owner: owner. Impact: the strategy reset scope (prod data only vs data plus code) decides whether a code change and a `master` deploy are needed.
- Type: risk. Owner: unknown. Impact: memory rose 138 MiB over ~19 h (1911 → 2049 MiB used of 3905); not known whether cache or a leak. Kongming read three days of point samples as flat.
- Type: risk. Owner: unknown. Impact: the SPA Exness strip misreports the live flag on the split runtime; the owner may misread the state.
- Type: blocker for any future go-live. Owner: unknown. Impact: the api refuses exness subscription creates (`BROKER_DISABLED`).
- Type: risk. Owner: unknown. Impact: heavy-job resume after a cut has only test and review evidence.

## Exact next actions

1. **First safe step** — read-only: re-confirm items 1-8 of Remaining. Run `git -C D:/w/_me/algotrading/pocketquant status --short`, `git log --oneline -5`, and `git rev-parse origin/master`. Over SSH (key setup in Source pointers), read container env `EXNESS_LIVE_TRADING` per role, trader safeguards, the subscription list, and the OOM check. Grep the code for the strip field (`web/src/components/strategies/exness-strip.tsx`) and the `BROKER_DISABLED` check (`src/pocketquant/engine/strategy/strategy_command_service.py`). Report the confirmed state per item to the owner (Vietnamese), marking any item that changed.
2. Ask the owner (Vietnamese, with a recommendation) which items to do and the strategy-reset scope.
3. For a strategy reset that touches prod data: back up Mongo first, list what will be deleted (subscriptions and their orders, positions, trades, backtests), get an explicit yes, then delete. Never remove tracked symbols.
4. For items 2 and 3 (code fixes): TDD per `docs/code-standards.md`; one `fix(...)` commit each; `develop` CI green; ask before `develop:master`.
5. End each session by removing `.cache/ssh/vps_key`.

## Source pointers

- Plan (closed): `plans/261028-0652-exness-only-parallel-runtime/plan.md` (decisions D36-D38, acceptance criteria, Conventions)
- Phase 10/11 records: `plans/261028-0652-exness-only-parallel-runtime/reports/handover-log.md`, `paper-daily.md`, `machine-limits.md`, `re-arm-log.md`
- Advice: `plans/261028-0652-exness-only-parallel-runtime/reports/kongming-phase-10-checkpoint.md`, `kongming-phase-11-rearm-verify.md`
- Phase 11 Substitutions table (how to run go-live on the split runtime): `plans/261028-0652-exness-only-parallel-runtime/phase-11-re-arm-live-gate.md`
- Go-live plan: `plans/261019-1957-exness-go-live/`
- Runbooks: `docs/deployment.md`; architecture: `docs/system-architecture.md`; rules: `docs/governance/`, `CLAUDE.md`
- Compose pin: `deploy/compose.prod.yml` (api/worker `EXNESS_LIVE_TRADING: "false"`)
- SSH (key and host only from `../pocketquant-config/vps/default/`): `mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key`; `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r')`; prod commands run in `/opt/pocketquant/deploy` as `docker compose -f compose.prod.yml --env-file .env exec -T <api|worker|trader> ...`.
- Git push needs the `camping89` account: `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/<repo>.git" <ref>` (never print the token); `gh` calls take `GH_TOKEN=$(gh auth token --user camping89)`.
- Shell gotchas on this Windows box: multi-line Bash tool commands with nested quotes fail; write a script under `.cache/` and run `bash <file>`. Helpers that use `docker exec -i` need `< /dev/null` inside a piped `bash -s` script.
