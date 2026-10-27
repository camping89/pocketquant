---
phase: 10
title: "Arm live: entries paused, then deploy C with the flag on; every subscription paper"
status: completed
priority: P1
effort: about 3-4h + CI (backfill)
dependencies: [9]
---

# Phase 10: Arm live: entries paused, then deploy C with the flag on; every subscription paper

## Context
- User decision 2026-10-20 19:35: arming is deploy C. `EXNESS_LIVE_TRADING=true`, entries paused, the safeguard values set (done in Phase 08). Every subscription stays paper; no `exness` subscription is created here. E2 is not a gate.
- User decision 2026-10-20 20:20: the pause is stored and survives a restart (Phase 05). So this phase pauses first, on the running deploy-B process, and deploy C restarts the app already paused. The check after deploy C is the first prod proof that the stored pause survives a restart.
- With the flag true but no `exness` subscription, no adapter is built (`BrokerFactory.create("exness")` is reached only from `load_strategy` → `_get_or_create_broker`, `engine/strategy/strategy_app_service.py:121,461-479`), so no order can be sent.
- Deep backfill: `scripts/backfill/provider_bars.py:76-78` refuses with exit 3 while the flag is true. In-app sync and `POST /api/v1/market-data/integrity/repair` are not affected (they resync through `SyncService`, `engine/market_data/app_services/integrity_jobs.py:116-130`). Paper subscriptions preload no history. So only history beyond the 5000-bar request cap is blocked while armed. Decided 2026-10-21: 1m for the three :EXNESS symbols to the M1 edge; nothing else (Task 10.3). Stored depth on 2026-10-20: 1m reaches back only to 2026-06/07 (about 4.5 months), while 1h reaches 2-3 years and 1d about 7; 1m is the only depth that is one-way once armed.
- From here on: every planned restart follows the "Restart while live" runbook in `docs/deployment.md`; a local backend against prod Mongo/Redis runs only with `ENABLE_JOBS=false` (plan rule).

## Gates in this phase
[ASK] = stop and ask; lead with the recommended reply and its reason, then state the listed facts; only an explicit yes counts; "no" or "wait" ends the phase with the NOT_YET block. [USER] = the user acts and replies with the stated token. No earlier approval counts.
- [ASK] Task 10.5 flag on and dispatch. [USER] Task 10.5 step 3 only if the agent cannot dispatch.

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
- Goal: the numbers Task 10.3 and the Task 10.5 [ASK] use.
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
  2. Latest E2 row: `grep -E '^\| [0-4]( re-run)? \| 2026' plans/archive/261009-0858-exness-venue-lean-sync-refactor/phase-08-validation-spread-backtests-paper-week.md | tail -1`.
  3. Dispatch auth from `grep "^Deploy A:" plans/261019-1957-exness-go-live/reports/ship-log.md`.
- Success criteria: three facts gathered.
- Verify: step 1 line 1 reads `flag False subs <n> paper <n> exness 0` with both `<n>` equal. Any other value → Failure Protocol.

### Task 10.3 — Deep 1m backfill before arming (decided 2026-10-21)
- Goal: 1m history for `XAUUSD:EXNESS`, `EURUSD:EXNESS` and `BTCUSD:EXNESS` reaches back to the Exness M1 history edge before the flag goes on (the script refuses while armed). No other symbol or interval.
- Target files and symbols: `scripts/backfill/provider_bars.py` (existing, unchanged). It requests `days × 1440` 1m bars backwards from now (`n_bars = days × 86400 / interval_seconds`); for FX and metals that reaches about `days × 7/5` calendar days, because weekends have no bars. An Exness error on any page aborts the whole run with nothing inserted (exit 1). Bars are upserted, so re-fetching stored bars is harmless.
- Steps:
  1. Edge probe (read-only, rate 0.2; one call per guess). Run and record its last line as `M1 edge: <days> calendar days` (or `M1 edge: none`) in `plans/261019-1957-exness-go-live/reports/ship-log.md`:
     ```bash
     HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r')
     ssh -i .cache/ssh/vps_key "$HOST" 'docker exec -i pocketquant-app python -' <<'EOF'
     import asyncio
     from datetime import UTC, datetime, timedelta
     from pocketquant.core.config import get_settings
     from pocketquant.core.domain.shared.enums import Interval
     from pocketquant.core.infra.exness.exness_client import ExnessApiError, ExnessClient
     from pocketquant.core.infra.exness.exness_mappers import INTERVAL_TO_EXNESS, instrument_name
     async def main():
         c = ExnessClient(get_settings().model_copy(update={"exness_rate_fraction": 0.2}))
         try:
             for days in (360, 330, 300, 270, 240, 210, 180):
                 frm = (datetime.now(UTC) - timedelta(days=days)).isoformat()
                 try:
                     body = await c.call("getCandleHistory", params={"instrument": instrument_name("XAUUSD:EXNESS"), "timeframe": INTERVAL_TO_EXNESS[Interval("1m")], "price_type": "bid", "from": frm, "count": -10})
                 except ExnessApiError as exc:
                     print(days, exc.code)
                     continue
                 if body.get("candles"):
                     print("M1 edge:", days)
                     return
                 print(days, "empty")
             print("M1 edge: none")
         finally:
             await c.close()
     asyncio.run(main())
     EOF
     ```
  2. Runs, one at a time, each started with the harness's background-run facility (wait for its exit before the next; the earlier 90-day run took 12-13 min, so expect about 45-60 min per symbol [I]). With `E` = the edge in days: XAUUSD and EURUSD use `--days $(( (E - 15) * 5 / 7 ))`; BTCUSD trades every day, so it uses `--days $(( E - 15 ))`. For each `<SYM>` in `XAUUSD:EXNESS EURUSD:EXNESS BTCUSD:EXNESS`: `E=<edge>; HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" "docker exec pocketquant-app python scripts/backfill/provider_bars.py --symbol <SYM> --interval 1m --days <n> --rate-fraction 0.5"; echo "exit=$?"`. `M1 edge: none` → skip the runs.
  3. Append one ship-log line per symbol: exit 0 → `backfill <SYM> 1m days <n>: <the printed fetched=... total_bars=... line>`; exit 1 → `backfill <SYM> 1m failed: <printed code>` and continue with the next symbol (the data is optional for live; arming proceeds); skipped → `backfill <SYM> 1m skipped: edge under 180 days`. Exit 3 means the flag is already on → Failure Protocol.
- Success criteria: the edge is recorded; each symbol has one backfill line; no run exited 3.
- Verify: `grep -c "^M1 edge:" plans/261019-1957-exness-go-live/reports/ship-log.md` prints `1` and `grep -cE "^backfill (XAUUSD|EURUSD|BTCUSD):EXNESS 1m " plans/261019-1957-exness-go-live/reports/ship-log.md` prints `3`.

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
  1. Ask: "Recommended: yes. Arm live trading? Facts: <exness count 0> exness subscriptions, so no adapter is built and no order can be sent; every subscription stays paper (<paper count>); entries are paused now and the pause is stored, so the restart keeps it; the deep backfill refuses while armed (Task 10.3 ran the decided 1m backfill: <its ship-log lines>); latest E2 row: <line>. Set EXNESS_LIVE_TRADING=true, push pocketquant-config, and redeploy?"
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
- A backfill page past the history edge aborts that run with nothing inserted (M/L): the probe sizes each run 15 days inside the edge; a failed run is recorded and arming proceeds.
- Deep backfill blocked while armed (L/L): Task 10.3 runs the decided 1m backfill first; afterwards it needs the flag off (rollback step 4 conditions in `plan.md`) and two dispatches [ASK].

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
