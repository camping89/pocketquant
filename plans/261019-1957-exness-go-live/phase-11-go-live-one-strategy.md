---
phase: 11
title: "Take one strategy live (re-runnable)"
status: pending
priority: P1
effort: ~1h attention, days of calendar
dependencies: [10]
---

# Phase 11: Take one strategy live (re-runnable)

## Context
- User decision 2026-10-20 19:35: ONE strategy the user picks goes live per run of this phase. Its paper subscription is deleted [ASK], its `exness` subscription is created [ASK] while entries are paused, the first paused rejection proves sizing and the pause gate at zero money, then Resume [ASK]. The round trip is the strategy's first natural trade (D3 = A). A second strategy goes live only by re-running this phase alone: `/eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261019-1957-exness-go-live --from 11 --to 11` (the runner supports `--to`, `~/.claude/skills/eve-cook-plan/SKILL.md:18,37`).
- User decision 2026-10-20 20:20: the pause is stored and survives a restart (Phase 05). A restart still resets strategy warmup and the open direction.
- User decision 2026-10-21 00:21: the agent recommends the strategy from the Task 11.2 preflight and the user confirms it and the balance at the 11.3 [ASK]. Each run is a single-order run: after Resume, entries are paused again as soon as the first `exness` position opens (Task 11.9 step 0, Task 11.1 step 4); pause needs no gate and exits are never gated. The trade closes by the strategy's own SL/TP (set at signal time and held at the venue, `exness_broker_adapter.py:239-240`) or its exit rule. D3 = A stays: no hand-placed order and no hand-set TP/SL (no manual order route exists).
- User decision 2026-10-21 00:43: the unwatched single-order risk is accepted (see Risk); there is no in-app "pause after first fill". The Task 11.9 step 0 watch runs about 4 h. Task 11.12 recommends `keep on` when the round trip was clean, else `pause`.
- The unique index on `(strategy_code, symbol, interval)` (`core/infra/persistence/repositories/subscription_repository.py:102-106`) forces the paper subscription off the triple first. `remove_symbol` deletes only the subscription document; its orders, positions and trades stay (`engine/strategy/strategy_command_service.py:99-107`); the DELETE route returns 204 whatever happens (`app/routes/strategy.py:141-147`). Deleting a validation subscription makes E2's `running 2` read 1 from then on (accepted: E2 is optional).
- Zero-money proof: `normalize_quantity` runs before `submit_order` (`engine/strategy/strategy_app_service.py:405-415`); a size below the lot grid never creates an order and logs `order_quantity_below_broker_minimum` with `strategy_id=<subscription id>` (`:407-409`); a zero size logs `zero_position_size` (`:401-404`). While paused, `_presubmit_reason` rejects first and logs `exness.order_rejected_presubmit reason=entries_paused subscription_id=<id>` (Phase 05). The `orders` document stores no rejection reason, so the proof reads that log line. An order that reached the venue logs `exness.order_submitted` or `exness.order_rejected` with `order_id` = the `orders._id` (`exness_broker_adapter.py:316,330,342-349`). `below_min_lot` carries no subscription id; every `exness` subscription is live, so it is counted unscoped.
- hitnrun2 re-arms on rejection (`core/domain/strategy/services/hitnrun2_strategy_service.py:130-132`) and re-signals each 1m bar while its condition holds: expect one paused rejection per bar (bounded). Warmup after a create or a restart: hitnrun2 XAUUSD 1m about 8 open-market hours (`:92-93`), engulfing EURUSD 1h about 21 open hours.
- Sizing at 250 USD (Phase 05): risk leg `0.10 × free / |entry − sl|`; one 0.01 lot = `0.01 × contract_size` units (XAUUSD 1 oz, EURUSD 1000). The SL is set once at signal time (`hitnrun2_strategy_service.py:151`, `engulfing_strategy_service.py:170`).
- Cap: realized-only, checked at open (`core/infra/brokers/exness/exness_broker_adapter.py:255-277`). Worst day ≈ 25 + 25 × open positions before gaps. Deal history is clamped to the API window (`_deals`, `:279-294`; `ExnessClient.deals_window_days`, `exness_client.py:370-372`).
- Scripts that call Exness run in a second process with their own pacer; they use `get_settings().model_copy(update={"exness_rate_fraction": 0.2})` (`core/config.py:124`; precedent `scripts/backfill/provider_bars.py:80`) so the live app keeps most of the account rate.
- The pause is global: pausing here also pauses entries of any strategy already live until Resume. Phase 12 does not run while this phase has an open run. Every planned restart follows the "Restart while live" runbook (`docs/deployment.md`); a local backend against prod Mongo/Redis runs only with `ENABLE_JOBS=false` (plan rule).

## State record (read and written by every run)
`plans/261019-1957-exness-go-live/reports/round-trip.md` holds one section per live run, appended in this order:
```
## Live run <n>: <strategy_code> <symbol> <interval>
- chosen_at: <UTC>; preflight: <the Task 11.2 line of this candidate>
- paper_sub_id: <id>
- baseline: balance <x> at <UTC ISO>
- paper_deleted: <UTC>
- exness_create_requested: <UTC>
- exness_sub_id: <id>, created <UTC ISO>, app StartedAt <value>
- zero_money_proof: <UTC>, paused_rejections <n>, below_minimum 0, submitted 0, other 0
- resumed_at: <UTC ISO>, app StartedAt <value>
- round_trip: DONE <UTC>
```
The current run is the last `## Live run` section without a `round_trip: DONE` line. Its last key line decides the next task: no current run → 11.2; `paper_sub_id` → 11.4; `baseline` → 11.5; `paper_deleted` or `exness_create_requested` → 11.6; `exness_sub_id` → 11.7; `zero_money_proof` → 11.8; `resumed_at` → 11.9. Note lines (`restart seen`, `proof_window`, `proof_check`, `paused after first entry`, `AC6`, `pause while open`, `after round trip`) are not keys. Tasks before the chosen one are skipped.

## Gates in this phase
[ASK] = stop and ask; lead with the recommended reply and its reason, then state the listed facts; only an explicit yes counts; "no" or "wait" ends the phase with the NOT_YET block. [USER] = the user acts and replies with the stated token. No earlier approval counts.
- [ASK] 11.3 which strategy. [ASK] 11.5 delete the paper subscription. [ASK] 11.6 create and start the `exness` subscription. [ASK] 11.8 Resume (a single-order run; the pause after the first entry needs no gate). [USER] 11.10 `sl seen`. [ASK] 11.11 only on a void AC6. [ASK] 11.12 D4.
- Calendar waits end the worker with `NOT_YET` (11.7, 11.9). They are not failures: no `kongming`.

## Entry gate
Run first. On a miss: edit nothing, spawn no `kongming`, leave the phase pending, and end with:
```
Status: BLOCKED
NOT_YET: <reason>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261019-1957-exness-go-live --from 11 --to 11 after <UTC time>
```
- `grep -c "^Deploy C (armed):" plans/261019-1957-exness-go-live/reports/ship-log.md` prints `1` (else `NOT_YET: live trading is not armed; run --from 10`).
- `git status --porcelain -- src web deploy tests scripts docs` prints nothing.

## Tasks
Code blocks below are indented for Markdown. Before running one, remove only the common leading indentation of the block (keep the Python indentation inside it), so each closing `EOF` starts at column 0. The shell keeps no variables between commands: every command sets `HOST` itself. `<GET safeguards>` means `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" "docker exec pocketquant-app curl -s http://localhost:41921/api/v1/admin/safeguards"`. An admin call is `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'docker exec -i pocketquant-app sh -s'` with a heredoc on stdin holding `curl -s -X POST -H "X-Admin-Token: $ADMIN_TOKEN" http://localhost:41921/api/v1/<path>` (the token stays in the container).

### Task 11.1 — SSH setup, state and pause check
- Goal: the worker knows the current state; entries are paused whenever a run is not yet resumed or its first live position has opened.
- Target files and symbols: `.cache/ssh/vps_key` (deleted at every exit); `plans/261019-1957-exness-go-live/reports/round-trip.md`; prod app.
- Steps:
  1. `mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key`.
  2. Read the current run (State record). Read `docker inspect -f '{{.State.StartedAt}}' pocketquant-app` over SSH and `<GET safeguards>`.
  3. A current run without `resumed_at`, or with a `paused after first entry` line, means intended paused. If `entries_paused` is false then: pause now (admin call) and append `- restart seen: StartedAt <value>, found unpaused, re-paused <UTC>` (the pause is stored, so someone resumed it or the store failed; Task 11.7 counts any order sent meanwhile).
  4. If the current run has `resumed_at` and no `paused after first entry` line: run the Task 11.9 step 0 command once with `TRIES=1`. `first_entry <opened_at>` → admin call `pause` now and append `- paused after first entry: <UTC>, position opened <opened_at>`; continue.
  5. If the current run has `resumed_at` and StartedAt differs from the last StartedAt recorded in the section: `GET /api/v1/subscriptions/<exness_sub_id>/positions`. Non-empty → stop and report (an unplanned restart while an `exness` position is open). Empty → append `- restart seen: StartedAt <value>` and continue.
- Success criteria: the next task is known.
- Verify: `<GET safeguards>` contains `"live_trading":true`, and after step 3 or a step 4 pause contains `"entries_paused":true`.

### Task 11.2 — Preflight per candidate (read-only)
- Goal: stop distances and margin for every strategy that could go live.
- Target files and symbols: prod Mongo `trades`, `bars`; Exness snapshot and conditions.
- Steps: run only when there is no current run; keep the output:
  ```bash
  HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r')
  ssh -i .cache/ssh/vps_key "$HOST" 'docker exec -i pocketquant-app python -' <<'EOF'
  import asyncio, json, statistics, urllib.request
  from decimal import Decimal
  from pymongo import AsyncMongoClient
  from pocketquant.core.config import get_settings
  from pocketquant.core.infra.exness.exness_client import ExnessClient
  async def main():
      s = get_settings()
      db = AsyncMongoClient(str(s.mongodb_url))[s.mongodb_database]
      subs = json.load(urllib.request.urlopen("http://localhost:41921/api/v1/subscriptions/"))
      live = {(x["strategy_code"], x["symbol"], x["interval"]) for x in subs if x["broker"] == "exness"}
      c = ExnessClient(s.model_copy(update={"exness_rate_fraction": 0.2}))
      try:
          st = (await c.call("getTradingStateSnapshot"))["account_state"]
          free = float(st["equity"]) - float(st["used_margin"])
          print("balance", st["balance"], "equity", st["equity"], "free", round(free, 2), "live", len(live))
          for x in subs:
              key = (x["strategy_code"], x["symbol"], x["interval"])
              if x["broker"] != "paper" or x["actual_state"] != "running" or not x["symbol"].endswith(":EXNESS") or key in live:
                  continue
              cond = await c.conditions(x["symbol"].split(":")[0])
              units = 0.01 * float(cond["contract_size"])
              bar = await db.bars.find_one({"symbol": x["symbol"], "interval": "1m"}, sort=[("datetime", -1)])
              margin, limit = units * bar["close"] / 1000, 0.10 * free / units
              d = [abs(t["entry_price"] - t["sl_price"]) async for t in db.trades.find({"run_id": x["id"], "sl_price": {"$ne": None}})]
              ok = Decimal(cond["volume_min"]) == Decimal("0.01") and free >= margin + 25
              print(x["id"], *key, "stops", len(d), "median", statistics.median(d) if d else None, "max", max(d) if d else None,
                    "limit", round(limit, 5), "above", sum(v > limit for v in d), "margin", round(margin, 2),
                    "margin_percent", cond.get("margin_percent"), "margin_ok", ok)
      finally:
          await c.close()
  asyncio.run(main())
  EOF
  ```
- Success criteria: one line per candidate.
- Verify: the first line starts with `balance`.

### Task 11.3 — [ASK] Which strategy goes live
- Goal: the agent recommends one candidate; the user confirms it (or picks another, or not now).
- Target files and symbols: `plans/261019-1957-exness-go-live/reports/round-trip.md`.
- Steps:
  1. Offer only candidates with `margin_ok True`. If none, stop and report the Task 11.2 output. Recommend by this rule: zero above-limit stops, then the lowest median stop; on a tie hitnrun2 XAUUSD 1m (1m signals shorten the proof and the round-trip wait; warmup about 8 h versus about 21 h).
  2. Ask: "Recommended: <code symbol interval> (<why: zero above-limit stops / lowest median stop / 1m signals>). Candidates: <one line each: code symbol interval, stops count/median/max, above-limit count, margin>. Balance <x> USD (must be ≤ 250; confirm). Already live: <n>. Facts: the pause is global, so entries of any live strategy stay paused until you approve Resume; deleting the paper subscription ends its E2 `running` count (latest E2 row: <`grep -E '^\| [0-4]( re-run)? \| 2026' plans/archive/261009-0858-exness-venue-lean-sync-refactor/phase-08-validation-spread-backtests-paper-week.md | tail -1`>); warmup after create: hitnrun2 about 8 open-market hours, engulfing about 21; a candidate with above-limit stops will see those entries rejected below the minimum lot, which stops this phase. This is a single-order run: entries pause again once the first position opens, and its SL/TP come from the strategy's rule, not from hand-chosen levels. Reply `yes`, another subscription id, or `not now`."
  3. `not now` → end with `NOT_YET: the user deferred go-live`, resume time = now.
  4. Otherwise (`yes` = the recommended candidate) append the section header, the `chosen_at` line (with the candidate's Task 11.2 line) and `paper_sub_id`.
- Success criteria: a new section.
- Verify: `grep -c "^## Live run" plans/261019-1957-exness-go-live/reports/round-trip.md` increased by 1, and the user confirmed balance ≤ 250.

### Task 11.4 — Pause and baseline (no gate)
- Goal: entries paused; balance baseline recorded.
- Target files and symbols: safeguards; Exness snapshot.
- Steps:
  1. Admin call `pause`.
  2. Snapshot (Task 11.8 re-runs this read-only):
     ```bash
     HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r')
     ssh -i .cache/ssh/vps_key "$HOST" 'docker exec -i pocketquant-app python -' <<'EOF'
     import asyncio
     from datetime import UTC, datetime
     from pocketquant.core.config import get_settings
     from pocketquant.core.infra.exness.exness_client import ExnessClient
     async def main():
         c = ExnessClient(get_settings().model_copy(update={"exness_rate_fraction": 0.2}))
         try:
             st = (await c.call("getTradingStateSnapshot"))["account_state"]
             print("balance", float(st["balance"]), "free", round(float(st["equity"]) - float(st["used_margin"]), 2), "at", datetime.now(UTC).isoformat())
         finally:
             await c.close()
     asyncio.run(main())
     EOF
     ```
  3. Append `- baseline: balance <x> at <ISO>`.
- Success criteria: paused; baseline line.
- Verify: `<GET safeguards>` contains `"entries_paused":true`; `grep -c "baseline: balance" plans/261019-1957-exness-go-live/reports/round-trip.md` increased by 1.

### Task 11.5 — [ASK] Delete the paper subscription
- Goal: the triple is free.
- Target files and symbols: `POST /api/v1/subscriptions/{id}/stop`, `DELETE /api/v1/subscriptions/{id}`.
- Steps:
  1. If `paper_sub_id` no longer appears in `GET /api/v1/subscriptions/` (an interrupted earlier run deleted it), append `- paper_deleted: <UTC>` and go to Task 11.6 without asking.
  2. Facts: its id and triple; `GET /api/v1/subscriptions/<id>/positions` item count; "its orders, positions and trades rows stay". Ask: "Recommended: yes (the unique triple index requires it before the exness create). Stop and delete paper subscription <id> (<triple>)?"
  3. On yes: admin calls `POST .../<id>/stop`; poll `GET /api/v1/subscriptions/` every 5 s, at most 12 times, until its `actual_state` is not `running`; then `curl -s -o /dev/null -w "%{http_code}" -X DELETE -H "X-Admin-Token: $ADMIN_TOKEN" http://localhost:41921/api/v1/subscriptions/<id>`.
  4. Append `- paper_deleted: <UTC>`.
- Success criteria: the id is gone.
- Verify: the id no longer appears in `GET /api/v1/subscriptions/`.

### Task 11.6 — [ASK] Create and start the `exness` subscription
- Goal: one `exness` subscription runs with entries paused; one adapter in the process.
- Target files and symbols: `POST /api/v1/strategies/{strategy_code}/subscriptions`, `POST /api/v1/subscriptions/{id}/start`.
- Steps:
  1. Re-run case (the section has `exness_create_requested`): look up `GET /api/v1/subscriptions/` for the triple with `"broker":"exness"`. Found → adopt its id; `POST .../<id>/start` if its `desired_state` is not `running` (the earlier [ASK] covered create and start); go to step 4. Not found → continue at step 2.
  2. Facts: `<GET safeguards>` (`live_trading` true, `entries_paused` true); the triple; the number of `exness` subscriptions in GET now; "no order can go out while paused; the first paused signal is the zero-money proof". Ask: "Recommended: yes (entries are paused, so no order can go out). Create and start the Exness subscription for <triple>?"
  3. On yes: append `- exness_create_requested: <UTC>` first; then admin calls `curl -s -X POST -H "X-Admin-Token: $ADMIN_TOKEN" -H 'Content-Type: application/json' -d '{"symbol":"<symbol>","interval":"<interval>","broker":"exness"}' http://localhost:41921/api/v1/strategies/<strategy_code>/subscriptions` (note the returned `id`), then `POST .../subscriptions/<id>/start`.
  4. Wait 30 s. Append `- exness_sub_id: <id>, created <ISO of the create, or now when adopted>, app StartedAt <value>`.
- Success criteria: running, paused, one adapter.
- Verify: GET shows the id with `"broker":"exness"` and `"actual_state":"running"`; `<GET safeguards>` contains `"entries_paused":true`; over SSH `docker logs --since <StartedAt> pocketquant-app 2>&1 | grep -c exness.broker_connected` prints `1` (or `0` when another `exness` subscription existed before and its line rotated out), and `docker logs --since <created> pocketquant-app 2>&1 | grep -c exness.broker_connected` prints `1` when no other `exness` subscription existed before, else `0`.

### Task 11.7 — Zero-money proof (calendar wait)
- Goal: AC7 for this strategy.
- Target files and symbols: app logs; Mongo `orders`.
- Steps:
  1. Window start `W` = `created` on the `exness_sub_id` line, or the newest `proof_window` line. If the current StartedAt differs from the StartedAt on that line, the proof is void: append `- proof_window: from <StartedAt ISO>, app StartedAt <value>` and end with `NOT_YET: restart reset warmup for <code>`, resume after now + 8 h (hitnrun2) or now + 24 h (other).
  2. Counts (fill `<id>` and `<W>`):
     ```bash
     HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r')
     ssh -i .cache/ssh/vps_key "$HOST" 'bash -s' <<'EOF'
     ID=<id>; W=<W>
     L=$(docker logs --since "$W" pocketquant-app 2>&1)
     echo "paused_rejections $(echo "$L" | grep "$ID" | grep order_rejected_presubmit | grep -c entries_paused)"
     echo "below_minimum $(echo "$L" | grep "$ID" | grep -cE 'order_quantity_below_broker_minimum|zero_position_size') $(echo "$L" | grep -c below_min_lot)"
     OUT=$(docker exec pocketquant-app python -c "from datetime import datetime; from pymongo import MongoClient; from pocketquant.core.config import get_settings as g; s=g(); db=MongoClient(str(s.mongodb_url))[s.mongodb_database]; q={'subscription_id': '$ID', 'created_at': {'\$gte': datetime.fromisoformat('$W')}}; print('other', db.orders.count_documents({**q, 'status': {'\$ne': 'rejected'}})); [print(o['_id']) for o in db.orders.find(q, {'_id': 1})]")
     echo "$OUT" | head -1
     OIDS=$(echo "$OUT" | tail -n +2)
     if [ -n "$OIDS" ]; then echo "submitted $(echo "$L" | grep -E 'exness\.order_(submitted|rejected[^_])' | grep -cF "$OIDS")"; else echo "submitted 0"; fi
     EOF
     ```
  3. Decide: `other` > 0 or `submitted` > 0 → stop and report (an order left the pause gate). Any `below_minimum` number > 0 → stop and report (sizing does not reach the lot grid). `paused_rejections` = 0 → append `- proof_check: <UTC>, paused_rejections 0, below_minimum 0 0, submitted 0, other 0` and end with `NOT_YET: no paused entry signal yet for <code>`, resume after now + 8 h (hitnrun2) or now + 24 h (other). `paused_rejections` ≥ 1 → append `- zero_money_proof: <UTC>, paused_rejections <n>, below_minimum 0, submitted 0, other 0`.
- Success criteria: proof line, or a recorded `NOT_YET` exit.
- Verify: proof case: `paused_rejections` ≥ 1, `below_minimum 0 0`, `other 0`, `submitted 0`.

### Task 11.8 — [ASK] Resume entries
- Goal: real-money entries are allowed.
- Target files and symbols: `POST /api/v1/admin/safeguards/resume`.
- Steps:
  1. Facts: the proof line; hours since create; current free margin from re-running the Task 11.4 step 2 snippet (read-only, append nothing) against `margin` in the `chosen_at` preflight; other live strategies that Resume also unpauses; worst day ≈ 25 + 25 × open positions USD; "the SPA row shows LIVE; Pause in the strip stops new entries at any time and stays on across a restart"; "this is a single-order run: entries are paused again as soon as the first position opens while the watch runs (about 4 h); after an unwatched window, more trades can open one at a time under the 25 USD daily cap (accepted 2026-10-21 00:43); the trade then closes by the strategy's SL/TP (hitnrun2: SL ≤ 1% from entry, TP ≥ 2%; engulfing: SL at the pattern extreme ± 0.1%, TP ≥ 1R) or its exit rule; you can press Pause in the SPA at any time". Ask: "Recommended: yes (the zero-money proof passed). Resume real-money entries now for one order?"
  2. `wait` → end with `NOT_YET: the user deferred Resume`, resume after the time the user names (default now + 4 h).
  3. On yes: admin call `POST .../resume`; append `- resumed_at: <ISO>, app StartedAt <value>`.
- Success criteria: unpaused.
- Verify: `<GET safeguards>` contains `"entries_paused":false`.

### Task 11.9 — First natural round trip (calendar wait)
- Goal: one closed live trade exists, with no stop condition; entries are paused again once the first position opens (single-order run).
- Target files and symbols: app logs; Mongo `positions` (`subscription_id`, `opened_at`; open and closed rows); Mongo `trades` (`run_id` = subscription id, `engine/live/live_trade_collector.py:58-63`).
- Steps:
  0. Single-order watch, only if the section has no `paused after first entry` line. Start this with the harness's background-run facility (up to about 4 h) and wait for its exit; it checks every 60 s for a position of the `exness` subscription opened since `resumed_at`, open or already closed:
     ```bash
     HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r')
     ssh -i .cache/ssh/vps_key "$HOST" 'bash -s' <<'EOF'
     ID=<exness_sub_id>; R=<resumed_at ISO>; TRIES=240
     for i in $(seq "$TRIES"); do
       P=$(docker exec pocketquant-app python -c "from datetime import datetime; from pymongo import MongoClient; from pocketquant.core.config import get_settings as g; s=g(); db=MongoClient(str(s.mongodb_url))[s.mongodb_database]; p=db.positions.find_one({'subscription_id': '$ID', 'opened_at': {'\$gte': datetime.fromisoformat('$R')}}, sort=[('opened_at', 1)]); print(p['opened_at'].isoformat() if p else '')")
       if [ -n "$P" ]; then echo "first_entry $P"; exit 0; fi
       [ "$i" -lt "$TRIES" ] && sleep 60
     done
     echo "no_entry $(date -u +%FT%TZ)"
     EOF
     ```
     `first_entry <opened_at>` → admin call `pause` (no gate), check `<GET safeguards>` shows `"entries_paused":true`, append `- paused after first entry: <UTC>, position opened <opened_at>`, then continue at step 1. `no_entry` → continue at step 1 (it ends with the `NOT_YET` exit of step 3 as before).
  1. Logs since `resumed_at` (`R`), scoped to the live ids:
     ```bash
     HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r')
     ssh -i .cache/ssh/vps_key "$HOST" 'bash -s' <<'EOF'
     R=<resumed_at ISO>
     IDS=$(docker exec pocketquant-app python -c "import json,urllib.request as u;[print(x['id']) for x in json.load(u.urlopen('http://localhost:41921/api/v1/subscriptions/')) if x['broker']=='exness']")
     L=$(docker logs --since "$R" pocketquant-app 2>&1)
     echo "stop_events $(echo "$L" | grep -cE 'exness\.(position_unmapped|unknown_request_fill|operation_unresolved|position_missing_close_deal|event_handler_failed)')"
     echo "below_min $(echo "$L" | grep -c below_min_lot) $(echo "$L" | grep order_quantity_below_broker_minimum | grep -cF "$IDS")"
     echo "order_rejected $(echo "$L" | grep -cE 'exness\.order_rejected[^_]')"
     EOF
     ```
  2. First trade: `db.trades.find_one({"run_id": "<id>", "entry_time": {"$gte": <R>}}, sort=[("exit_time", 1)])` (snippet style of Task 11.7); print its `entry_order_id`, `exit_order_id`, `entry_time`, `exit_time`, `quantity`, `pnl`, `commission`, `sl_price`, or `None`.
  3. Any count in step 1 > 0 → stop and report. Step 2 `None` → end with `NOT_YET: no closed live trade yet for <code>`, resume after now + 24 h. More trades after the first are allowed (they can open only while no worker watches; see Risk).
- Success criteria: the first trade is known.
- Verify: after a step 0 `first_entry`, `grep -c "paused after first entry" plans/261019-1957-exness-go-live/reports/round-trip.md` increased by 1; step 1 prints `stop_events 0`, `below_min 0 0`, `order_rejected 0`; step 2 prints a trade.

### Task 11.10 — Per-trade checks and [USER] SL
- Goal: the first trade's entry and exit are recorded once each.
- Target files and symbols: Mongo `orders`, `positions`, `trades`.
- Steps:
  1. For the first trade `T`: `trades` count with `entry_order_id == T.entry_order_id`; `orders` with `_id` in `{T.entry_order_id, T.exit_order_id}` (`status`, `quantity`); the first `positions` row with `subscription_id == <id>` and `opened_at ≥ R`, sorted by `opened_at` (`sl_price`, `is_closed`).
  2. Ask: "In the Exness app history, does the closed <instrument> position opened at <T.entry_time> show a stop loss of <T.sl_price>? Reply `sl seen` or `no sl`."
- Success criteria: one of each, SL confirmed.
- Verify: the duplicate count is `1`; both orders are `filled` and each quantity equals `0.01 × contract_size`; the position has `sl_price` not None and `is_closed` true; `T.pnl` and `T.commission` are not None; the reply equals `sl seen` (`no sl` → stop and report).

### Task 11.11 — Commission check (AC6) and pause-while-open record
- Goal: the cap's arithmetic is safe against the real deals.
- Target files and symbols: Exness `getDealsHistory`, snapshot.
- Steps:
  1. Run (fill the baseline values):
     ```bash
     HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r')
     ssh -i .cache/ssh/vps_key "$HOST" 'docker exec -i pocketquant-app python -' <<'EOF'
     import asyncio
     from datetime import UTC, datetime, timedelta
     from pocketquant.core.config import get_settings
     from pocketquant.core.infra.exness.exness_client import ExnessClient
     BASE_AT, BASE_BAL = datetime.fromisoformat("<baseline ISO>"), <baseline balance>
     PNL = {"close", "swap_fee", "admin_fee", "dividend"}
     async def main():
         c = ExnessClient(get_settings().model_copy(update={"exness_rate_fraction": 0.2}))
         try:
             bal = float((await c.call("getTradingStateSnapshot"))["account_state"]["balance"])
             floor = datetime.now(UTC) - timedelta(days=await c.deals_window_days())
             params, P, C, nb, nc = {"from": max(BASE_AT, floor).isoformat(), "limit": 200}, 0.0, 0.0, 0, 0
             while True:
                 body = await c.call("getDealsHistory", params=params)
                 for it in body.get("items", []):
                     d = it["deal"]; k = d.get("type")
                     nb += k == "balance"; nc += k == "close"
                     if k != "balance":
                         P += float(d["profit"]["amount"]) if k in PNL and d.get("profit") else 0.0
                         C += abs(float(d.get("commission") or 0))
                 if not body.get("has_more") or not body.get("next_cursor"):
                     break
                 params = {"cursor": body["next_cursor"], "limit": 200}
             print(f"delta {bal - BASE_BAL:.2f} P {P:.2f} C {C:.2f} code {P - C:.2f} balance_deals {nb} close_deals {nc} clamped {floor > BASE_AT}")
         finally:
             await c.close()
     asyncio.run(main())
     EOF
     ```
  2. `balance_deals` > 0 or `clamped True` → [ASK]: "Recommended: <`accept` (only the deal history window is clamped) | `stop` (a deposit or withdrawal is in the window and needs an explanation first)>. AC6 is void for this run (<a deposit or withdrawal is in the window | the baseline is older than the deal history window>). Reply `accept` (without AC6) or `stop`." Use `accept` as the recommendation only when `clamped True` and `balance_deals 0`; otherwise `stop`. Accept → append `- AC6: void (<reason>), accepted <UTC>` and go to step 4. Stop → stop and report.
  3. `delta < code − 0.01` → stop and report (the cap under-counts losses). `delta > code + 0.01` → record `AC6 over-count: follow-up adapter fix` (safe; the cap trips early).
  4. Pause-while-open (record only): `docker logs --since <R> pocketquant-app 2>&1 | grep -E "exness.safeguards.entries_(paused|resumed)"` timestamps against the first position's `opened_at`/`closed_at`; record `pause while open: yes|no`.
  5. Append the step 1 line and the step 3-4 notes to the section.
- Success criteria: AC6 recorded, or accepted as void.
- Verify: the step 1 line has `balance_deals 0`, `clamped False` and `delta ≥ code − 0.01`, or the section has an `AC6: void` line.

### Task 11.12 — [ASK] D4 and close the run
- Goal: the user sets the post-round-trip state; the run is done.
- Target files and symbols: safeguards; `plans/261019-1957-exness-go-live/reports/round-trip.md`; `.cache/ssh/vps_key`.
- Steps:
  1. The round trip is clean when Tasks 11.9-11.11 passed (no stop event, `sl seen`) and the section has an AC6 line or an accepted `AC6: void` line. Ask: "Recommended: <`keep on` (clean round trip; Phase 12 then observes real trading under the 25 USD daily cap) | `pause` (<what was not clean>)>. Round trip for <code> is recorded (AC6 <line>); entries are now <GET safeguards entries_paused> (paused since the first entry). `keep on` resumes entries and starts the five-day observation of a trading system; `pause` keeps entries paused, and Phase 12 rows then record a paused system (`new_trades 0`). Reply `keep on` or `pause`."
  2. `pause` → if not paused, admin call `pause`; `<GET safeguards>` shows true. Phase 12 rows then expect paused. `keep on` → if paused, admin call `resume`; `<GET safeguards>` shows `"entries_paused":false`.
  3. Append `- after round trip: <keep on|paused>` and `- round_trip: DONE <UTC>`. Commit `docs(plans): record a live round trip`; `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin` (never print the token); `rm -f .cache/ssh/vps_key`.
- Success criteria: the section is closed.
- Verify: `grep -c "round_trip: DONE" plans/261019-1957-exness-go-live/reports/round-trip.md` increased by 1; `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `pushed`.

## Exit rule
Before any `NOT_YET` exit or a stop after Task 11.1, run `rm -f .cache/ssh/vps_key`. Every 11.7 `NOT_YET` exit first appends its counts (`proof_check` or `proof_window`), so log rotation cannot erase them.

## Risk
- No signal for days (H/L): `NOT_YET` exits; the user re-runs `--from 11 --to 11`.
- Gap or slippage through the SL (M/M): 0.01 lot; the cap stops new opens after 25 USD realized; one max-risk stop can reach it alone.
- A restart during the proof wait (M/L): the pause holds (stored); warmup restarts, so Task 11.7 voids the proof and restarts the window.
- A restart while positioned (L/M): the strategy state is lost; Task 11.1 stops and reports.
- Margin rejection (`TRADING_RULE_INSUFFICIENT_MARGIN` → CANCELLED) (M/L): Task 11.2 checks margin.
- Script calls compete with the app for the account rate (L/M): every script runs at rate fraction 0.2.
- More than one order in a single-order run (M/L): the watch pauses only while a worker runs (step 0 watches about 4 h; Task 11.1 step 4 checks at each re-run). When the watch ends with `no_entry`, entries stay on until the next run (up to 24 h later), so a first trade can open and close unwatched and more can follow; each is 0.01 lot with a venue SL. Bound: one open position at a time per subscription (`submit_order` opens only when the subscription holds no position, `core/infra/brokers/exness/exness_broker_adapter.py:200-205`), and the 25 USD daily loss cap rejects an open once realized PnL for the UTC day is at or below -25 USD (`:261-263`). Worst case is about 50 USD per UTC day, about 100 USD if an unwatched window straddles midnight UTC, plus gap slippage (audit Q1). Accepted by the user 2026-10-21 00:43; no in-app feature.

## Rollback
Softest first (`plan.md` "Rollback"): Pause; Pause over SSH; stop the subscription; close in the Exness app; flag off only with a flat account and after deleting every `exness` subscription. Planned restarts follow the "Restart while live" runbook (`docs/deployment.md`). To return a strategy to paper: pause, stop its `exness` subscription, confirm the account is flat (`GET /api/v1/subscriptions/<id>/positions` empty and no open position in the Exness app), then delete it [ASK], then create a paper subscription on the triple [ASK]. The venue adapter stays connected (Phase 02), so a later run reuses it.

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
