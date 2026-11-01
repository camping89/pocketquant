---
phase: 15
title: "D-2 release: prod migration, index drop, deploy, post-checks"
status: pending
priority: P1
effort: 0.5d
dependencies: [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
---

# Phase 15: D-2 release: prod migration, index drop, deploy, post-checks

<!-- Red team 2026-11-01: #15 -->
No open issue. plan.md Design verdict "Prod migration" settles the empty-object write (`{"$literal": {}}`) and drops the backtest-run migration. AGNOSTIC is the plan.md Conventions check "Strategy-agnostic UI".

## Goal

Prod runs the multi-timeframe code: the four legacy subscriptions carry the new fields, the old unique index is gone, the release is deployed with live trading still off in the trader, and the post-checks pass.

## Context

- Design verdict "Prod migration": before the `develop:master` push, one idempotent script adds `intervals`, `intervals_key` and `parameters` to legacy subscriptions (keeps `interval`) and drops `ix_subscriptions_dedup_triple`. <!-- Red team 2026-11-01: #13 --> It re-runs before every push attempt, also on a resume, because a rollback window can create old-shape subscriptions and the old code recreates the old index at startup. Why before the push: the old index on `(strategy_code, symbol, interval)` (`src/pocketquant/core/infra/persistence/repositories/subscription_repository.py:79-83`) gives every new document a null `interval` key, so two Triple Screen subscriptions on one symbol would collide. No compatibility or index-drop code in `src`.
- <!-- Red team 2026-11-01: #15 --> Legacy backtest runs are not migrated: all 21 are STF, `BacktestResult.from_mongo` tolerates their shape (`src/pocketquant/core/domain/backtest/entities.py:78-100`), and Phase 17 deletes them.
- Old code tolerates the added fields: `Subscription.from_mongo` reads named keys only (`src/pocketquant/core/domain/subscription/entities.py:52-70`). <!-- Red team 2026-11-01: #13 --> The old code writes no `intervals_key`, so the new unique index `ix_subscriptions_dedup_intervals` would treat every old-code document as null and refuse a second interval for one `(strategy_code, symbol)` (DuplicateKeyError maps to 409, `subscription_repository.py:19-27`). The rollback therefore deletes new-shape subscriptions, drops `ix_subscriptions_dedup_intervals`, then re-rolls the old image (R7).
- <!-- Red team 2026-11-01: #13 --> Live flag: compose pins `EXNESS_LIVE_TRADING: "false"` for api and worker only (`deploy/compose.prod.yml:83,99`); the trader service has no pin (`:109-114`, comment `:75` "Only the trader may trade live") and reads the flag from the deploy `.env`. The order fence reads `settings.exness_live_trading` in the trader process (`src/pocketquant/core/infra/exness/exness_client.py:231`; setting `src/pocketquant/core/config.py:70`). So the live-off check runs inside the `trader` container (LIVECHK below), never through PRODPY, which runs in `api`.
- Owner decisions: D1, D2 and D6-D9 shipped by Phases 04-13 (reconcile reload and manual action, CI web job, no expiry for queued manual actions, close and cancel outside the live fence, admin-token reads, no freshness column); D3-D5 (backtest sets, paper settings, orphan delete) run in Phases 16-17. <!-- Consistency sweep 2026-11-01 -->
- Log events: `reconcile.failed` (`src/pocketquant/engine/live/strategy_reconcile_app_service.py:73`), `reconcile.unknown_template` logged once per subscription (`self._reported` holds the sub id, `:121-130`), so the 4 legacy subscriptions give `4`. <!-- Consistency sweep 2026-11-01 -->
- Deploy: `master` push runs tests, builds, deploys with `deploy/vps/10-deploy.sh` and `11-verify.sh` (`.github/workflows/cicd.yml:192-247`); images are tagged `sha-<7 chars>` (`:83,129`); manual re-roll `IMAGE_TAG=sha-<short> bash deploy/vps/10-deploy.sh` (`deploy/vps/10-deploy.sh:9`).

**Ops lines (from plan.md Ops recipe).** KEY: `mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key`. SSH `<cmd>`: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" '<cmd>'`. PRODPY: write the script to `.cache/f.py`, then run plan.md's PRODPY command. Every script starts with the HEADER `from pymongo import MongoClient` / `from pocketquant.core.config import get_settings` / `s = get_settings()` / `db = MongoClient(str(s.mongodb_url))[s.mongodb_database]` and prints no secret. <!-- Red team 2026-11-01: D8 --> ADMINGET: lines added after HEADER when a script reads a D8-guarded route (the subscription list, snapshot, orders, positions, trades): `import json` / `import urllib.request` / `def admin_get(path):` / `    req = urllib.request.Request("http://localhost:41921/api/v1" + path, headers={"X-Admin-Token": s.admin_token.get_secret_value()})` / `    return json.load(urllib.request.urlopen(req))`. <!-- Red team 2026-11-01: #13 --> LIVECHK: write `.cache/live.py` with the two lines `from pocketquant.core.config import get_settings` / `print("trader_live=" + str(get_settings().exness_live_trading))`, then `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cat > /tmp/live.py' < .cache/live.py && ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env cp /tmp/live.py trader:/tmp/live.py && docker compose -f compose.prod.yml --env-file .env exec -T trader python /tmp/live.py'` (PRODPY, but in `trader`). MIGRATE: the Task 15.4 script. End of phase and before any `NOT_YET` exit: `rm -f .cache/ssh/vps_key`.

## Entry gate

1. Conventions EG (1)-(3); the previous report is `reports/phase-14-*.md`.
2. `for n in 03 04 05 06 07 08 09 10 11 12 13 14; do tail -1 plans/261101-0843-stf-to-mtf-foundation/reports/phase-$n-*.md; done | grep -c "^Result: PASS$"` prints `12`.
3. `git fetch -q origin && git log --oneline origin/master..origin/develop | wc -l` prints a number `>= 1`.
4. `uv run python -c "import re,glob,datetime as d; t=re.search(r'd1_deployed_at=(\S+)', open(glob.glob('plans/261101-0843-stf-to-mtf-foundation/reports/phase-03-*.md')[0]).read()).group(1); a=d.datetime.fromisoformat(t.replace('Z','+00:00')); m=(a+d.timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0); print('midnight_passed=' + ('yes' if d.datetime.now(d.UTC)>=m else 'no'))"` prints `midnight_passed=yes`.
5. KEY, then PRODPY with HEADER plus: `subs = list(db.subscriptions.find({}, {"desired_state": 1, "actual_state": 1, "broker": 1}))` / `print(f"subs={len(subs)} stopped={sum(1 for d in subs if d.get('desired_state') == 'stopped' and d.get('actual_state') == 'stopped')} exness={sum(1 for d in subs if d.get('broker') == 'exness')}")` prints `subs=4 stopped=4 exness=0`.
6. AGNOSTIC (plan.md Conventions) prints `0`.
7. <!-- Red team 2026-11-01: #13 --> LIVECHK prints exactly `trader_live=False`.

On a miss, run `rm -f .cache/ssh/vps_key`, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261101-0843-stf-to-mtf-foundation --from 15 after <UTC time>
```

## Files

- Create, Modify, Delete in the repo: none (the phase report only).
- Prod writes: Task 15.4 (migration and index drop, re-run before every push attempt) and Task 15.5 (release push).

## Tasks

### Task 15.1 — D-1 day check (read-only)

**Goal:** the 1d cascade has written every closed Exness day since D-1, on time, with no REST repair.

**Target files and symbols:** prod `bars`, `tracked_symbols`.

**Steps:**
1. Copy `d1_deployed_at=<ISO>` from `reports/phase-03-*.md`. PRODPY with HEADER plus (replace `<D1_ISO>` before upload):
```python
from datetime import UTC, datetime, timedelta
D1 = datetime.fromisoformat("<D1_ISO>".replace("Z", "+00:00"))
syms = sorted(d["symbol"] for d in db.tracked_symbols.find({"symbol": {"$regex": ":EXNESS$"}}, {"symbol": 1}))
first_day = (D1 + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
days = non_cascade = late = 0
for sym in syms:
    for b in db.bars.find({"symbol": sym, "interval": "1d", "datetime": {"$gte": first_day, "$lt": today}}):
        days += 1
        start = b["datetime"].replace(tzinfo=UTC)
        if b.get("source") != "cascade":
            non_cascade += 1
            print("non_cascade", sym, start.date(), b.get("source"))
        ua = b.get("updated_at")
        if ua is None or ua.replace(tzinfo=UTC) >= start + timedelta(days=1, minutes=1):
            late += 1
            print("late", sym, start.date(), ua)
repair_1d = db.bars.count_documents({"interval": "1d", "source": "rest_repair", "created_at": {"$gt": D1}})
print(f"symbols={len(syms)} days={days} non_cascade={non_cascade} late={late} repair_1d={repair_1d}")
```
2. Any non-zero of `non_cascade`, `late`, `repair_1d`, or `days=0`: [ASK] (intent) "the 1d cascade check found <line>; release anyway?" `Recommended: no`, reason: the one-week comparison would start from a broken cascade. A non-yes ends with `NOT_YET`.

**Success criteria:** the last line ends `non_cascade=0 late=0 repair_1d=0` with `days` above 0.

**Verify:** the PRODPY output's last line matches `^symbols=[1-9][0-9]* days=[1-9][0-9]* non_cascade=0 late=0 repair_1d=0$`.

### Task 15.2 — Pre-release state and `free -m` before

**Goal:** the counts the migration must match, the rollback tag and the memory baseline are recorded.

**Target files and symbols:** prod `subscriptions`; `origin/master`.

**Steps:**
1. PRODPY with HEADER plus:
```python
print(f"subs_legacy={db.subscriptions.count_documents({'intervals': {'$exists': False}})}")
print("indexes=" + ",".join(sorted(db.subscriptions.index_information())))
```
2. Record `prev_master=$(git rev-parse --short=7 origin/master)` and SSH `free -m` (the `Mem:` line) as `free_before`.

**Success criteria:** `subs_legacy=4`, `indexes=` contains `ix_subscriptions_dedup_triple`; the report holds `prev_master=<sha7>` and `free_before`.

**Verify:** the PRODPY output contains the line `subs_legacy=4`, and its `indexes=` line contains `ix_subscriptions_dedup_triple`.

### Task 15.3 — [ASK] release

**Goal:** the owner approves the two prod writes and the release.

**Target files and symbols:** none.

**Steps:**
1. Ask in Vietnamese (intent): "Release the multi-timeframe foundation to prod? It ships: STF code removed, subscriptions with `intervals` and `parameters` plus edit, higher-timeframe context from Mongo, stop entry and strategy EXIT in paper, Exness close and cancel (outside the live fence) and pending stops (behind it, live off in the trader: `trader_live=False`), snapshot ring and manual close/cancel with recorded outcomes, admin-token reads, the generic subscription and backtest UI, Triple Screen. Prod writes: (1) add `intervals`, `intervals_key`, `parameters` to the 4 stopped legacy subscriptions, keeping `interval`, and drop `ix_subscriptions_dedup_triple` (re-run before every push attempt; it is idempotent); (2) push `develop:master` (`<git log --oneline origin/master..origin/develop | wc -l>` commits). Rollback: delete new-shape subscriptions, drop `ix_subscriptions_dedup_intervals`, then re-roll `sha-<prev_master>`." Lead with `Recommended: yes`, reason: every phase passed, live trading is off in the trader and all 4 subscriptions are stopped.
2. Only an explicit yes continues; record the reply.

**Success criteria:** the report holds the owner's yes.

**Verify:** no verification needed (Task 15.4 runs only after the recorded yes).

### Task 15.4 — Prod migration and index drop (MIGRATE, idempotent)

<!-- Red team 2026-11-01: #13, #15 -->
**Goal:** every subscription carries the new fields and the old unique index is gone, immediately before each push attempt.

**Target files and symbols:** prod `subscriptions`, index `ix_subscriptions_dedup_triple`.

**Steps:**
1. Always run it, also on a resume and after a rollback (it only touches documents that lack `intervals` and drops the index only when present). PRODPY with HEADER plus:
```python
subs = db.subscriptions.update_many(
    {"intervals": {"$exists": False}},
    [{"$set": {"intervals": ["$interval"], "intervals_key": "$interval", "parameters": {"$literal": {}}}}],
)
if "ix_subscriptions_dedup_triple" in db.subscriptions.index_information():
    db.subscriptions.drop_index("ix_subscriptions_dedup_triple")
missing = db.subscriptions.count_documents({"$or": [{"intervals": {"$exists": False}}, {"intervals_key": {"$exists": False}}, {"parameters": {"$exists": False}}]})
print(f"subs_modified={subs.modified_count} missing={missing}")
print("indexes=" + ",".join(sorted(db.subscriptions.index_information())))
```
2. Append both lines to the report with the UTC time of the run (one block per run).

**Success criteria:** `missing=0`; the index list has no `ix_subscriptions_dedup_triple`; the first run shows `subs_modified=4`.

**Verify:** the output's first line matches `^subs_modified=[0-9]+ missing=0$` and its `indexes=` line does not contain `dedup_triple`.

### Task 15.5 — Release push and master run

**Goal:** `master` equals `develop` and the master pipeline (tests, build, deploy, verify) succeeds.

**Target files and symbols:** `origin/master`.

**Steps:**
1. <!-- Red team 2026-11-01: #13 --> Right before every push attempt (the first one included, even straight after Task 15.4), run MIGRATE again and append its block; its Verify must pass. Run LIVECHK; it must print `trader_live=False`.
2. Record `d2_pushed_at=<UTC ISO now>`.
3. `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop:master && git fetch origin`; then `test "$(git rev-parse origin/master)" = "$(git rev-parse origin/develop)" && echo released` prints `released`.
4. `sleep 15`, then poll `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch master --limit 1 --json headSha,status,conclusion` every 60 s until `status` is `completed`.

**Success criteria:** the master run concludes `success` on the released sha.

**Verify:** `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch master --limit 1 --json headSha,status,conclusion -q '.[0] | "\(.status) \(.conclusion) \(.headSha)"'` prints `completed success <sha>` with `<sha>` equal to `git rev-parse origin/develop`.

### Task 15.6 — Post-deploy checks and `free -m` after

**Goal:** the new code runs on prod with the new index, reads the legacy documents, serves the defaults, guards the reads, keeps live off in the new trader and logs no reconcile failure.

**Target files and symbols:** prod `subscriptions` indexes; api routes; trader container; trader log.

**Steps:**
1. PRODPY with HEADER, ADMINGET plus:
```python
import urllib.error
print("indexes=" + ",".join(sorted(db.subscriptions.index_information())))
p = json.load(urllib.request.urlopen("http://localhost:41921/api/v1/strategies/triple_screen")).get("parameters") or {}
print(f"params={len(p)} entry_type={p.get('entry_type')} exit_mode={p.get('exit_mode')}")
rows = admin_get("/subscriptions/")
print(f"rows={len(rows)} one_interval={sum(1 for r in rows if isinstance(r.get('intervals'), list) and len(r['intervals']) == 1)}")
try:
    urllib.request.urlopen("http://localhost:41921/api/v1/subscriptions/")
    print("read_without_token=200")
except urllib.error.HTTPError as e:
    print(f"read_without_token={e.code}")
```
2. <!-- Red team 2026-11-01: #13 --> LIVECHK against the new trader container.
3. SSH `cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env logs --since <d2_pushed_at> trader 2>&1` piped locally to `sed 's/\x1b\[[0-9;]*m//g' > .cache/trader.log`; then `grep -c "reconcile.failed" .cache/trader.log; grep -c "reconcile.unknown_template" .cache/trader.log`.
4. SSH `free -m` as `free_after`. `rm -f .cache/ssh/vps_key`.

**Success criteria:** `indexes=` contains `ix_subscriptions_dedup_intervals` and not `ix_subscriptions_dedup_triple`; `params=8 entry_type=market exit_mode=sl_tp`; `rows=4 one_interval=4`; `read_without_token=401`; `trader_live=False`; the grep counts are `0` and `4`.

**Verify:** the PRODPY output has `params=8 entry_type=market exit_mode=sl_tp`, `rows=4 one_interval=4`, `read_without_token=401` and an `indexes=` line containing `ix_subscriptions_dedup_intervals` but not `dedup_triple`; LIVECHK prints `trader_live=False`; the two `grep -c` commands print `0` then `4`.

## Rollback

<!-- Red team 2026-11-01: #13 -->
Each step is an [ASK]. (1) PRODPY with HEADER plus `print([d["_id"] for d in db.subscriptions.find({"$expr": {"$ne": ["$intervals_key", "$interval"]}})])`; after the owner's yes, in one PRODPY script delete exactly those ids with `db.subscriptions.delete_many({"_id": {"$in": [<ids>]}})`, print `deleted_count`, then drop `ix_subscriptions_dedup_intervals` when `index_information()` lists it and print the index list (the old code writes no `intervals_key`, so the new unique index would refuse its second interval per strategy and symbol; the old code recreates its own index at startup). (2) SSH `cd /opt/pocketquant && IMAGE_TAG=sha-<prev_master> bash deploy/vps/10-deploy.sh`. The added fields stay; the old code ignores them. Record `free -m` after a rollback. A later roll-forward starts again at Task 15.4, which migrates any document the old code wrote meanwhile and drops the recreated old index.

## Report

`reports/phase-15-release-d2.md`: entry-gate outputs (LIVECHK included); the Task 15.1 line; `subs_legacy=`, `prev_master=`, `free_before` and `free_after` (`Mem:` lines); the owner's yes; every MIGRATE run with its time; each LIVECHK line; `d2_pushed_at=` and the master run id and sha; the post-check output and both grep counts; then `Result: PASS`.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same failure evidence to the user. Never continue by self-reasoning.
