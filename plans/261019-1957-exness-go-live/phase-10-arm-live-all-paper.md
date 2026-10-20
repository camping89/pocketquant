---
phase: 10
title: "Arm live: entries paused, then deploy C with the flag on; every subscription paper"
status: pending
priority: P1
effort: 1h + CI
dependencies: [9]
---

# Phase 10: Arm live: entries paused, then deploy C with the flag on; every subscription paper

## Context
- User decision 2026-10-20 19:35: arming is deploy C. `EXNESS_LIVE_TRADING=true`, entries paused, the safeguard values set (done in Phase 08). Every subscription stays paper; no `exness` subscription is created here. E2 is not a gate.
- User decision 2026-10-20 20:20: the pause is stored and survives a restart (Phase 05). So this phase pauses first, on the running deploy-B process, and deploy C restarts the app already paused. The check after deploy C is the first prod proof that the stored pause survives a restart.
- With the flag true but no `exness` subscription, no adapter is built (`BrokerFactory.create("exness")` is reached only from `load_strategy` → `_get_or_create_broker`, `engine/strategy/strategy_app_service.py:121,461-479`), so no order can be sent.
- Deep backfill: `scripts/backfill/provider_bars.py:76-78` refuses with exit 3 while the flag is true. In-app sync and `POST /api/v1/market-data/integrity/repair` are not affected (they resync through `SyncService`, `engine/market_data/app_services/integrity_jobs.py:116-130`). Paper subscriptions preload no history. So only history beyond the 5000-bar request cap is blocked while armed. Task 10.3 asks whether any backfill should run first.
- From here on: every planned restart follows the "Restart while live" runbook in `docs/deployment.md`; a local backend against prod Mongo/Redis runs only with `ENABLE_JOBS=false` (plan rule).

## Gates in this phase
[ASK] = stop and ask; state the listed facts; only an explicit yes counts; "no" or "wait" ends the phase with the NOT_YET block. [USER] = the user acts and replies with the stated token. No earlier approval counts.
- [ASK] Task 10.3 deep backfill before arming. [ASK] Task 10.5 flag on and dispatch. [USER] Task 10.5 step 3 only if the agent cannot dispatch.

## Entry gate
Run first. On a miss: edit nothing, spawn no `kongming`, leave the phase pending, and end with:
```
Status: BLOCKED
NOT_YET: <reason>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261019-1957-exness-go-live --from 10 after <UTC time>
```
- `grep -c "^Deploy B:" plans/261019-1957-exness-go-live/reports/ship-log.md` prints `1` and `grep -c "^Break-glass drill:" plans/261019-1957-exness-go-live/reports/ship-log.md` prints `1`.
- `curl -s -o /dev/null -w "%{http_code}" https://pocketquant.xyz/api/v1/admin/safeguards` prints `200`.
- `git status --porcelain -- src web deploy tests scripts docs` prints nothing.
- `grep -c "^Deploy C" plans/261019-1957-exness-go-live/reports/ship-log.md` prints `0` (not armed yet; if it prints `1`, end with `NOT_YET: already armed` and `Resume: ... --from 11 after <now>`).

## Tasks
Code blocks below are indented for Markdown. Before running one, remove only the common leading indentation of the block (keep the Python indentation inside it), so each closing `EOF` starts at column 0. The shell keeps no variables between commands: every command sets `HOST` (and `RUN_ID`) itself. Every `gh` call carries `GH_TOKEN=$(gh auth token --user camping89)`. Never print a token.

### Task 10.1 — SSH setup
- Goal: ssh works.
- Target files and symbols: `.cache/ssh/vps_key` (deleted in Task 10.7).
- Steps: `mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key`.
- Success criteria: ssh works.
- Verify: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" "docker ps --format '{{.Names}}' | grep -c pocketquant-app"` prints `1`.

### Task 10.2 — Facts before arming (read-only)
- Goal: the numbers the two [ASK]s state.
- Target files and symbols: prod app; venue E2 results table.
- Steps:
  1. Run:
     ```bash
     HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r')
     ssh -i .cache/ssh/vps_key "$HOST" 'docker exec -i pocketquant-app python -' <<'EOF'
     import json, urllib.request
     from pymongo import MongoClient
     from pocketquant.core.config import get_settings
     s = get_settings()
     db = MongoClient(str(s.mongodb_url))[s.mongodb_database]
     subs = json.load(urllib.request.urlopen("http://localhost:41921/api/v1/subscriptions/"))
     print("flag", s.exness_live_trading, "subs", len(subs), "paper", sum(x["broker"] == "paper" for x in subs), "exness", sum(x["broker"] == "exness" for x in subs))
     for sym in sorted({x for x in db.bars.distinct("symbol") if x.endswith(":EXNESS")}):
         print(sym, "1m", db.bars.count_documents({"symbol": sym, "interval": "1m"}), "1h", db.bars.count_documents({"symbol": sym, "interval": "1h"}))
     EOF
     ```
  2. Latest E2 row: `grep -E '^\| [0-4]( re-run)? \| 2026' plans/261009-0858-exness-venue-lean-sync-refactor/phase-08-validation-spread-backtests-paper-week.md | tail -1`.
  3. Dispatch auth from `grep "^Deploy A:" plans/261019-1957-exness-go-live/reports/ship-log.md`.
- Success criteria: three facts gathered.
- Verify: step 1 line 1 reads `flag False subs <n> paper <n> exness 0` with both `<n>` equal. Any other value → Failure Protocol.

### Task 10.3 — [ASK] Deep backfill before arming
- Goal: the user decides with the facts, because the backfill is blocked while armed.
- Target files and symbols: `scripts/backfill/provider_bars.py` (existing; run only on request).
- Steps:
  1. Ask: "While EXNESS_LIVE_TRADING is true, the deep backfill script refuses (exit 3); in-app sync and integrity repair keep working. Stored bars: <Task 10.2 lines>. Run any deep backfill before arming? Reply `no backfill`, or give symbol, interval and days for each run."
  2. For each requested run: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" "docker exec pocketquant-app python scripts/backfill/provider_bars.py --symbol <SYM> --interval <tf> --days <n> --rate-fraction 0.5"`; append the printed line to `plans/261019-1957-exness-go-live/reports/ship-log.md`.
- Success criteria: the reply is recorded; requested runs printed `fetched=`.
- Verify: reply `no backfill`, or every run exits 0 and prints a line starting `fetched=` with a value > 0.

### Task 10.4 — Pause entries before arming (no gate)
- Goal: entries are paused, and stored as paused, before the flag goes on.
- Target files and symbols: `POST /api/v1/admin/safeguards/pause` on the running deploy-B process.
- Steps:
  ```bash
  HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r')
  ssh -i .cache/ssh/vps_key "$HOST" 'docker exec -i pocketquant-app sh -s' <<'EOF'
  curl -s -X POST -H "X-Admin-Token: $ADMIN_TOKEN" http://localhost:41921/api/v1/admin/safeguards/pause; echo
  curl -s http://localhost:41921/api/v1/admin/safeguards; echo
  EOF
  ```
- Success criteria: paused.
- Verify: line 2 contains `"live_trading":false` and `"entries_paused":true`.

### Task 10.5 — [ASK] Flag on and redeploy (deploy C)
- Goal: prod runs with `EXNESS_LIVE_TRADING=true`.
- Target files and symbols: `../pocketquant-config/vps/default/.env` key `EXNESS_LIVE_TRADING`; `cicd.yml` dispatch.
- Steps:
  1. Ask: "Arm live trading? Facts: <exness count 0> exness subscriptions, so no adapter is built and no order can be sent; every subscription stays paper (<paper count>); entries are paused now and the pause is stored, so the restart keeps it; the deep backfill refuses while armed; latest E2 row: <line>. Set EXNESS_LIVE_TRADING=true, push pocketquant-config, and redeploy?"
  2. On yes: `F=../pocketquant-config/vps/default/.env; [ -n "$(tail -c1 $F)" ] && echo >> $F; echo 'EXNESS_LIVE_TRADING=true' >> $F; git -C ../pocketquant-config add vps/default/.env && git -C ../pocketquant-config commit -m "feat(env): arm exness live trading" && git -C ../pocketquant-config push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant-config.git" HEAD`; then dispatch: `GH_TOKEN=$(gh auth token --user camping89) gh workflow run cicd.yml --ref master`.
  3. If the dispatch fails, [USER]: "Please run the cicd workflow on master from GitHub (Actions > cicd > Run workflow > master). Reply `dispatched`."
- Success criteria: the run succeeds.
- Verify: `grep -c "^EXNESS_LIVE_TRADING=true" ../pocketquant-config/vps/default/.env` prints `1`; then one command: `sleep 15; RUN_ID=$(GH_TOKEN=$(gh auth token --user camping89) gh run list --branch master --event workflow_dispatch --limit 1 --json databaseId -q '.[0].databaseId'); GH_TOKEN=$(gh auth token --user camping89) gh run watch "$RUN_ID" --exit-status > /dev/null && GH_TOKEN=$(gh auth token --user camping89) gh run view "$RUN_ID" --log | grep "=== Verdict:" | grep -c ", 0 failures)"` prints ≥ 1.

### Task 10.6 — Armed, still paused after the restart, no adapter
- Goal: prove the stored pause survived deploy C, every subscription is paper and no live order path exists yet.
- Target files and symbols: prod app.
- Steps:
  ```bash
  HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r')
  ssh -i .cache/ssh/vps_key "$HOST" 'S=$(docker inspect -f "{{.State.StartedAt}}" pocketquant-app); echo "$S"; docker logs --since "$S" pocketquant-app 2>&1 | grep -c exness.broker_connected; docker exec -i pocketquant-app sh -s' <<'EOF'
  python -c "from pocketquant.core.config import get_settings as g;s=g();print(s.exness_live_trading, s.exness_daily_loss_cap, s.exness_max_lots, s.exness_leverage, s.exness_risk_per_trade, s.admin_token is not None)"
  curl -s http://localhost:41921/api/v1/admin/safeguards; echo
  python -c "import json,urllib.request as u;d=json.load(u.urlopen('http://localhost:41921/api/v1/subscriptions/'));print(len(d), sum(x['broker']=='paper' for x in d))"
  EOF
  ```
- Success criteria: armed, paused after a restart, all paper, no adapter.
- Verify: line 1 is a StartedAt later than the deploy-B StartedAt in the ship log; line 2 is `0`; line 3 is `True 25.0 0.01 1000.0 0.1 True`; line 4 contains `"live_trading":true` and `"entries_paused":true`; line 5 is two equal numbers.

### Task 10.7 — Record, push, remove the key
- Goal: the armed state is on record; no key copy on disk.
- Target files and symbols: `plans/261019-1957-exness-go-live/reports/ship-log.md`; `.cache/ssh/vps_key`.
- Steps: append `Deploy C (armed): <UTC>, app StartedAt <line 1 of Task 10.6>, entries paused across the restart, every subscription paper`; commit `docs(plans): record live trading armed with entries paused`; `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin`; `rm -f .cache/ssh/vps_key`.
- Success criteria: pushed; key removed.
- Verify: `grep -c "^Deploy C (armed):" plans/261019-1957-exness-go-live/reports/ship-log.md` prints `1`; `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `pushed`; `test -f .cache/ssh/vps_key; echo $?` prints `1`.

## Exit rule
Before any `NOT_YET` exit or a stop after Task 10.1, run `rm -f .cache/ssh/vps_key`.

## Risk
- The flag is on with no barrier left against an accidental `exness` subscription except the token (L/M). Entries are paused and stay paused across a restart, so such a subscription would only log rejections; Phase 11 checks for unexpected `exness` subscriptions first.
- The stored pause did not survive deploy C (L/H): Task 10.6 fails on `"entries_paused":true`; no `exness` subscription exists, so nothing trades; Failure Protocol.
- Deep backfill blocked while armed (L/L): Task 10.3 offers it first; afterwards it needs the flag off (rollback step 4 conditions in `plan.md`) and two dispatches [ASK].

## Rollback
Remove `EXNESS_LIVE_TRADING` from `pocketquant-config` and dispatch [ASK]. Safe while no `exness` subscription exists; otherwise follow the "Restart while live" runbook (`docs/deployment.md`) and `plan.md` "Rollback" step 4.

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
