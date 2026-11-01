---
phase: 17
title: "Observe; one-week 1d comparison; prod STF delete; close"
status: pending
priority: P1
effort: "days of observation + 0.5d"
dependencies: [16]
---

# Phase 17: Observe; one-week 1d comparison; prod STF delete; close

<!-- Red team 2026-11-01: #15 -->
No open issue. AGNOSTIC is the plan.md Conventions check "Strategy-agnostic UI".

## Goal

Paper proves the stop entry, the strategy EXIT, manual close and manual cancel on prod; the cascaded 1d bars equal fresh Exness bars for one week; the STF and orphan prod data are deleted by exact id lists with the owner's yes; the plan is closed.

## Context

- Inputs from earlier phases: `manual_action` and the last manual action outcome on subscription documents (Phase 11, D7), order documents with `sl_price` (Phase 09), `GET /api/v1/subscriptions/{id}/snapshot` with the admin token (Phase 11, D8), `d1_deployed_at=` in `reports/phase-03-*.md`, `paper_sub_id=` and `paper_started_at=` in `reports/phase-16-*.md`.
- A7, A9: observations carry order or trade ids; the drawer shows changing readings (`DRAWER OK`). A missing observation exits `NOT_YET` and resumes every 12 h.
- <!-- Red team 2026-11-01: #14 --> Exit reason: Phase 09 does not persist a reason on the trade. `Trade` has no reason field (`src/pocketquant/core/domain/trading/value_objects.py:85-122`); the reason reaches the paper order events and the INFO log `strategy.position_close_sent` (subscription_id, reason, closed) (phase-09 Task 09.4). So obs-2 keeps the inference rule (an exit inside the SL with no TP, not a manual close) and records a matching `reason=strategy_exit` log line as extra evidence when the trader log still holds it.
- <!-- Red team 2026-11-01: #3 --> Manual close price: the trader applies a queued close only once the paper broker holds a current price for the symbol (plan.md Design verdict "Manual action"); a close filled at the stored entry price would mean that rule failed, so obs-3 requires `exit != entry`.
- <!-- Red team 2026-11-01: #14 --> Live ring entries: the warm-up replay fills the ring before the first live write, so obs-5 counts only entries whose `bar_start` is after `paper_started_at`.
- <!-- Red team 2026-11-01: #7 --> D7: every attempt clears `manual_action` and records `accepted` or `rejected:<code>`; obs-3 and obs-4 require `accepted`. With the setup still holding, Triple Screen re-places its stop on the next entry bar after a manual cancel; that is expected.
- Synthesis D11 (`reports/kongming-261101-1630-debate-synthesis.md`; plan.md owner decisions stop at D9) and design verdict "1d comparison": <!-- Consistency sweep 2026-11-01 --> the cascade overwrites the stored REST bar (`src/pocketquant/core/infra/persistence/repositories/bar_repository.py:42-98`), so compare stored 1d bars with bars fetched fresh by `ExnessAdapter.fetch_ohlcv` (`src/pocketquant/core/infra/exness/exness_adapter.py:28-66`; op `getCandleHistory` is not an order op, so the live flag does not block it). `ExnessClient(settings)` exposes `is_configured` and `close()` (`src/pocketquant/core/infra/exness/exness_client.py:172-186,364`). The comparison waits for 7 full UTC days after the day of `d1_deployed_at` (at least `d1_deployed_at` + 7 days).
- C12, D5, R8: no backup; exact `_id` lists; orphans (positions, orders, trades linked to no subscription) listed separately with their own yes; children first; assert each `deleted_count`; re-list to zero; never touch `tracked_symbols`, `bars`, `sync_status`, `job_history`; never call `TrackedSymbolService.remove` (it cascades by symbol, `src/pocketquant/engine/market_data/tracked_symbols_service.py:93-139`). Links: positions and orders by `subscription_id`, trades by `run_id` = subscription id plus `strategy_code`, backtest orders and trades by `run_id` and `strategy_code` (`reports/scout-web-docs-ops.md`, Collections table). Prod before the plan: 4 STF subscriptions, 2 open BTCUSDT:BINANCE positions, 234 positions, 259 orders, 215 trades, 21 backtest runs (`reports/debate-evidence-packet.md`).
- Synthesis D12: the delete runs last, after the observations, unless the owner says delete now. <!-- Consistency sweep 2026-11-01 -->
- Docs line test: `docs/governance/documentation-rules.md:9-25,46-52`. Plan close: `ak plan update <id> --status completed` rewrites `plan.md` front matter (`ak plan update --help`); the plan id is `pocketquant/261101-0843` (`ak plan list --json`).

**Ops lines.** KEY, SSH, PRODPY, HEADER, ADMINGET, PRODPY-ARG and the key cleanup are those of `phase-15-release-d2.md` and `phase-16-backtests-and-paper-start.md` (Context, Ops lines). UPLOAD `<local>`: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cat > /tmp/ids.json' < <local> && ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env cp /tmp/ids.json api:/tmp/ids.json'`. R = `plans/261101-0843-stf-to-mtf-foundation/reports`.

## Entry gate

1. Conventions EG (1)-(3); the previous report is `reports/phase-16-*.md`.
2. `grep -c "^paper_sub_id=" plans/261101-0843-stf-to-mtf-foundation/reports/phase-16-*.md` prints `1`.
3. AGNOSTIC prints `0`.

On a miss (here or any `NOT_YET` below), run `rm -f .cache/ssh/vps_key`, edit nothing else and end with exactly:
```
Status: BLOCKED
NOT_YET: <reason>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261101-0843-stf-to-mtf-foundation --from 17 after <UTC time>
```

## Files

- Create: `plans/261101-0843-stf-to-mtf-foundation/reports/stf-delete-ids.json`, `plans/261101-0843-stf-to-mtf-foundation/reports/stf-delete-relist.json`, the phase report. Modify: `plans/261101-0843-stf-to-mtf-foundation/plan.md` front matter through `ak plan update` only; a doc under `docs/` only if Task 17.8 finds a stale name.
- Prod writes: the owner's manual close and cancel (paper); the delete in Task 17.6.

## Tasks

### Task 17.1 — Paper observations obs-1..obs-6 (resumable)

**Goal:** every capability is seen working on prod with an id.

**Target files and symbols:** prod `subscriptions`, `orders`, `positions`, `trades` of `<paper_sub_id>`; the snapshot route.

**Steps:**
1. KEY. STATUS = PRODPY-ARG `<paper_sub_id> <paper_started_at>` with HEADER, ADMINGET plus:
```python
import sys
from datetime import UTC, datetime
SID = sys.argv[1]
SINCE = datetime.fromisoformat(sys.argv[2].replace("Z", "+00:00"))
sub = db.subscriptions.find_one({"_id": SID})
manual = {k: sub[k] for k in sub if "manual" in k}
print(f"state={sub['desired_state']}/{sub['actual_state']} manual_action={sub.get('manual_action')} manual={json.dumps(manual, default=str, sort_keys=True)}")
for o in db.orders.find({"subscription_id": SID}).sort("created_at", -1).limit(20):
    print(f"order id={o['_id']} type={o['order_type']} side={o['side']} status={o['status']} stop={o.get('stop_price')} sl={o.get('sl_price')} updated={o['updated_at'].isoformat()}")
for p in db.positions.find({"subscription_id": SID, "is_closed": False}):
    print(f"open_position id={p['_id']} side={p['side']} qty={p['quantity']} sl={p.get('sl_price')}")
for t in db.trades.find({"run_id": SID}).sort("exit_time", -1).limit(20):
    print(f"trade id={t['_id']} dir={t['direction']} entry={t['entry_price']} exit={t['exit_price']} sl={t.get('sl_price')} tp={t.get('tp_price')} exit_time={t['exit_time'].isoformat()}")
ring = admin_get(f"/subscriptions/{SID}/snapshot")
live = [e for e in ring if datetime.fromisoformat(str(e["bar_start"]).replace("Z", "+00:00")).replace(tzinfo=UTC) > SINCE]
print(f"ring entries={len(ring)} live_entries={len(live)} live_distinct_bar_start={len({e['bar_start'] for e in live})} live_distinct_readings={len({json.dumps(e.get('readings'), sort_keys=True) for e in live})}")
```
   EXITLOG = SSH `cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env logs --since <paper_started_at> trader 2>&1` piped locally to `sed 's/\x1b\[[0-9;]*m//g' | grep "strategy.position_close_sent" | grep "subscription_id=<paper_sub_id>" | grep "reason=strategy_exit"`.
2. Record each item once, as its own report line, only when not yet recorded:
   - `obs-1 PASS order=<id>`: an `order` line with `type=stop_market status=filled`.
   - `obs-2 PASS trade=<id>`: a `trade` line with `tp=None` and (`dir=LONG` and `exit` > `sl`, or `dir=SHORT` and `exit` < `sl`) whose `exit_time` is not within 120 s after obs-3's `requested_at` (an SL exit fills at or beyond the SL; a manual close is excluded by time). <!-- Red team 2026-11-01: #14 --> Run EXITLOG and append any line whose time is within 120 s of that `exit_time` as `obs-2 log=<line>` (extra evidence; the inference rule decides).
   - <!-- Red team 2026-11-01: #3, #7 --> `obs-3 PASS trade=<id>`: when an `open_position` line exists, [USER] ask the owner (Vietnamese intent) to press Close at market in the drawer on `https://pocketquant.xyz/strategies`, confirm, and reply `CLOSED`; record `obs-3 requested_at=<UTC>` at the reply; within 30 s run STATUS; pass when no `open_position` line remains, `manual_action=None`, the `manual=` value contains `accepted`, and the newest trade's `exit_time` is at most 120 s before `requested_at` or later and its `exit` differs from its `entry` (a close at the entry price means the broker had no current price).
   - <!-- Red team 2026-11-01: #7 --> `obs-4 PASS order=<id>`: when an `order` line has `type=stop_market` and `status=submitted` or `pending`, [USER] ask the owner to press Cancel pending, confirm, and reply `CANCELLED`; within 30 s run STATUS; pass when that order shows `status=cancelled`, `manual_action=None` and the `manual=` value contains `accepted`.
   - <!-- Red team 2026-11-01: #14 --> `obs-5 PASS`: `live_distinct_bar_start>=2` and `live_distinct_readings>=2` on the `ring` line (live entries only).
   - `obs-6 PASS`: [USER] the owner opens the drawer of the paper subscription, checks readings, decision, pending or position, recent decisions, orders and trades, and the interval switcher, and replies `DRAWER OK`.
3. While any of obs-1..obs-6 is missing, end with `NOT_YET: waiting for <missing items>` and a resume time of now + 12 h (the next run re-reads STATUS). <!-- Consistency sweep 2026-11-01 --> Synthesis D12 escape hatch: only if the owner says on their own to delete now, [ASK] (intent) "skip <missing items> and go to the comparison and the delete?" `Recommended: no`, reason: A7 stays unproven; on an explicit yes record `obs-<n> SKIPPED by owner` for each missing item. An action the owner took that does not show the pass state within 30 s is a failed Verify, with one exception: <!-- Red team 2026-11-01: #3 --> while `manual_action` still shows the action (queued because the trader has no current price, D6), re-run STATUS every 5 min for up to 1 h before calling it failed. Ask for obs-3 and obs-4 only while the XAUUSD market is open.

**Success criteria:** six PASS lines (or owner-approved skips).

**Verify:** `grep -c -E "^obs-[1-6] (PASS|SKIPPED by owner)" plans/261101-0843-stf-to-mtf-foundation/reports/phase-17-observe-compare-delete.md` prints `6`.

### Task 17.2 — One-week 1d comparison against fresh Exness bars

**Goal:** A6: stored cascaded 1d bars equal the vendor's 1d bars for 7 days, with no REST repair.

**Target files and symbols:** prod `bars` (1d), `ExnessAdapter.fetch_ohlcv`.

**Steps:**
1. Copy `d1_deployed_at=` from `R/phase-03-*.md`. If now is before the next UTC midnight after it plus 7 days, end with `NOT_YET: 1d comparison window not complete` and that time.
2. PRODPY with HEADER plus (replace `<D1_ISO>`):
```python
import asyncio
from datetime import UTC, datetime, timedelta
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.exness.exness_adapter import ExnessAdapter
from pocketquant.core.infra.exness.exness_client import ExnessClient
D1 = datetime.fromisoformat("<D1_ISO>".replace("Z", "+00:00"))
FIRST = (D1 + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
LAST = FIRST + timedelta(days=7)
syms = sorted(d["symbol"] for d in db.tracked_symbols.find({"symbol": {"$regex": ":EXNESS$"}}, {"symbol": 1}))
def same(a, b, tol):
    return abs(a - b) <= tol * max(1.0, abs(b))
async def main():
    client = ExnessClient(s)
    assert client.is_configured
    adapter = ExnessAdapter(client)
    n_bars = max(12, (datetime.now(UTC) - FIRST).days + 2)
    mismatches, per_sym = 0, {}
    try:
        for sym in syms:
            vendor = {b.datetime.replace(tzinfo=UTC): b for b in await adapter.fetch_ohlcv(sym, Interval.DAY_1, n_bars=n_bars)}
            stored = {b["datetime"].replace(tzinfo=UTC): b for b in db.bars.find({"symbol": sym, "interval": "1d", "datetime": {"$gte": FIRST, "$lt": LAST}})}
            days = sorted(d for d in set(vendor) | set(stored) if FIRST <= d < LAST)
            per_sym[sym] = len(days)
            for d in days:
                v, st = vendor.get(d), stored.get(d)
                ok = (v is not None and st is not None and st.get("source") == "cascade"
                      and all(same(st[k], getattr(v, k), 1e-9) for k in ("open", "high", "low", "close"))
                      and same(st["volume"], v.volume, 1e-4))
                mismatches += 0 if ok else 1
                print(sym, d.date(), "equal" if ok else "diff", "source=" + str(st.get("source") if st else None))
    finally:
        await client.close()
    repair = db.bars.count_documents({"interval": "1d", "source": "rest_repair", "created_at": {"$gt": D1}})
    print(f"min_days={min(per_sym.values()) if per_sym else 0}")
    print(f"mismatches={mismatches} repair_1d={repair}")
asyncio.run(main())
```
3. Copy the output into the report. A `diff` row or `repair_1d` above 0: [ASK] (intent) "the 1d cascade differs from Exness on <rows>; continue to the delete with A6 failed?" `Recommended: no`, reason: the advice stop rule; the owner decides on reverting the cascade (Phase 03 rollback). A non-yes ends with `NOT_YET`.

**Success criteria:** `mismatches=0 repair_1d=0` and every symbol has at least 5 compared days.

**Verify:** the output's last two lines are `min_days=<n>` with `n >= 5` and exactly `mismatches=0 repair_1d=0`.

### Task 17.3 — Exact delete lists (read-only)

**Goal:** the exact `_id` sets to delete are saved, STF and orphans apart, with guard counts.

**Target files and symbols:** prod `subscriptions`, `positions`, `orders`, `trades`, `backtest_runs`, `backtest_orders`, `backtest_trades`; `R/stf-delete-ids.json`.

**Steps:**
1. LIST = PRODPY-ARG `<paper_sub_id>` with HEADER plus, stdout redirected locally to the given file:
```python
import json
import sys
PAPER = sys.argv[1]
STF = ["hitnrun2", "engulfing", "engulfing_pullback30_touch"]
def ids(coll, q):
    return sorted(d["_id"] for d in db[coll].find(q, {"_id": 1}))
S = ids("subscriptions", {"strategy_code": {"$in": STF}})
R = ids("backtest_runs", {"strategy_code": {"$in": STF}})
assert PAPER not in S
by_run = {"$or": [{"run_id": {"$in": R}}, {"strategy_code": {"$in": STF}}]}
stf = {
    "backtest_orders": ids("backtest_orders", by_run), "backtest_trades": ids("backtest_trades", by_run),
    "backtest_runs": R, "trades": ids("trades", {"$or": [{"run_id": {"$in": S}}, {"strategy_code": {"$in": STF}}]}),
    "orders": ids("orders", {"subscription_id": {"$in": S}}), "positions": ids("positions", {"subscription_id": {"$in": S}}),
    "subscriptions": S,
}
ALL = list(db.subscriptions.distinct("_id"))
orphans = {c: [i for i in ids(c, {key: {"$nin": ALL}}) if i not in set(stf[c])]
           for c, key in (("positions", "subscription_id"), ("orders", "subscription_id"), ("trades", "run_id"))}
open_ids = set(stf["positions"]) | set(orphans["positions"])
open_total = db.positions.count_documents({"_id": {"$in": list(open_ids)}, "is_closed": False})
paper = db.subscriptions.find_one({"_id": PAPER}) or {}
guard = {c: db[c].count_documents({}) for c in ("tracked_symbols", "sync_status", "bars", "job_history")}
print(json.dumps({"stf": stf, "orphans": orphans, "open_positions_total": open_total,
                  "paper_state": f"{paper.get('desired_state')}/{paper.get('actual_state')}", "guard": guard}, sort_keys=True))
```
2. Run LIST with `> R/stf-delete-ids.json`. Summary: `uv run python -c "import json; d=json.load(open('plans/261101-0843-stf-to-mtf-foundation/reports/stf-delete-ids.json')); print(' '.join(f'{c}={len(v)}' for c, v in d['stf'].items())); print('orphans ' + ' '.join(f'{c}={len(v)}' for c, v in d['orphans'].items())); print('open_positions_total=' + str(d['open_positions_total']), 'paper=' + d['paper_state'])"`; copy the three lines into the report.

**Success criteria:** 4 STF subscriptions; 2 open positions across both lists; the paper subscription is not listed and is running.

**Verify:** the summary's first line contains `subscriptions=4` and its last line starts with `open_positions_total=` followed by a number from 0 to 2 (an STF paper position may have closed on its SL or TP since the 2026-11-01 count) and ends with `paper=running/running`. <!-- Consistency sweep 2026-11-01 -->

### Task 17.4 — [ASK] delete the STF list

**Goal:** an explicit yes for the STF ids.

**Target files and symbols:** none.

**Steps:**
1. Ask in Vietnamese (intent): "Delete these STF documents permanently, with no backup: <the STF summary line>, the 4 subscription ids, the 2 open position ids; full lists in `reports/stf-delete-ids.json`. Tracked symbols, bars, sync status and job history are not touched." `Recommended: yes`, reason: C12 and the paper run is observed. Record the reply as `stf_delete=yes` or end with `NOT_YET`.

**Success criteria:** `stf_delete=yes` recorded.

**Verify:** `grep -c "^stf_delete=yes$" plans/261101-0843-stf-to-mtf-foundation/reports/phase-17-observe-compare-delete.md` prints `1`.

### Task 17.5 — [ASK] delete the orphans, separately

**Goal:** the owner decides on the orphan ids on their own.

**Target files and symbols:** none.

**Steps:**
1. Skip with `orphans=none` when every orphan list is empty. Otherwise ask in Vietnamese (intent): "Also delete <orphans summary line>: positions, orders and trades linked to no subscription (ids in the same file)?" `Recommended: yes`, reason: D5; only STF strategies ever ran live. Record `orphans=approved` on an explicit yes, else `orphans=declined`.

**Success criteria:** one `orphans=` line.

**Verify:** `grep -c -E "^orphans=(approved|declined|none)$" plans/261101-0843-stf-to-mtf-foundation/reports/phase-17-observe-compare-delete.md` prints `1`.

### Task 17.6 — Delete children first and assert every count

**Goal:** exactly the listed documents are gone; guarded collections are untouched.

**Target files and symbols:** the seven collections of Task 17.3.

**Steps:**
1. Skip when the report already holds a `mismatch=` line (resume rule). UPLOAD `R/stf-delete-ids.json`. PRODPY-ARG `<1 if orphans=approved else 0>` with HEADER plus:
```python
import json
import sys
data = json.load(open("/tmp/ids.json"))
with_orphans = sys.argv[1] == "1"
GUARD = ("tracked_symbols", "sync_status", "bars", "job_history")
before = {c: db[c].count_documents({}) for c in GUARD}
mismatch = 0
for coll in ("backtest_orders", "backtest_trades", "backtest_runs", "trades", "orders", "positions", "subscriptions"):
    parts = [("stf", data["stf"][coll])]
    if with_orphans and coll in data["orphans"]:
        parts.append(("orphans", data["orphans"][coll]))
    for kind, ids in parts:
        deleted = db[coll].delete_many({"_id": {"$in": ids}}).deleted_count if ids else 0
        mismatch += 0 if deleted == len(ids) else 1
        print(f"{kind} {coll} listed={len(ids)} deleted={deleted}")
after = {c: db[c].count_documents({}) for c in GUARD}
ok = before["tracked_symbols"] == after["tracked_symbols"] and before["sync_status"] == after["sync_status"] \
    and after["bars"] >= before["bars"] and after["job_history"] >= before["job_history"]
print(f"guard_ok={int(ok)} before={before} after={after}")
print(f"mismatch={mismatch}")
```

**Success criteria:** every `listed` equals `deleted`; guarded counts unchanged (bars and job history may only grow).

**Verify:** the output's last two lines start with `guard_ok=1` and equal `mismatch=0`.

### Task 17.7 — Re-list to zero

**Goal:** A11: no STF or approved orphan document remains; the paper subscription still runs.

**Target files and symbols:** `R/stf-delete-relist.json`.

**Steps:**
1. Run LIST with `> R/stf-delete-relist.json`, then `uv run python -c "import json; d=json.load(open('plans/261101-0843-stf-to-mtf-foundation/reports/stf-delete-relist.json')); print('stf_total=' + str(sum(len(v) for v in d['stf'].values())), 'orphans_total=' + str(sum(len(v) for v in d['orphans'].values())), 'paper=' + d['paper_state'])"`. `rm -f .cache/ssh/vps_key`.

**Success criteria:** zero STF documents; zero orphans when approved; paper running.

**Verify:** the printed line is `stf_total=0 orphans_total=0 paper=running/running` (with `orphans=declined`, `orphans_total` equals the Task 17.3 orphan count instead of `0`).

### Task 17.8 — Docs line test and plan close

**Goal:** every doc this plan touched passes the line test checks; the plan is closed.

**Target files and symbols:** docs changed since `e4a998b8`; `plan.md` front matter.

**Steps:**
1. Stale words: `git grep -n -i -E "hitnrun2|engulfing_pullback|engulfing_strategy|dedup_triple|SL/TP only|One take-profit per entry|swing-pivot" -- docs README.md CLAUDE.md | wc -l` prints `0`.
2. Names exist and length holds:
```bash
for f in $(git diff --name-only e4a998b8..HEAD -- docs README.md CLAUDE.md); do
  test -f "$f" || continue
  [ "$(wc -l < "$f")" -le 800 ] || echo "long $f"
  grep -o '`[^` ]*/[^` ]*`' "$f" | tr -d '`' | sort -u | while read -r tok; do
    p="${tok%%::*}"; p="${p%%:[0-9]*}"; sym=""; [ "$tok" != "${tok#*::}" ] && sym="${tok#*::}"
    case "$p" in http*|/*|*'{'*|*'<'*|*'*'*) continue;; esac
    q="$p"; [ -e "$q" ] || q="src/pocketquant/$p"
    if [ ! -e "$q" ]; then echo "missing $f $tok"; elif [ -n "$sym" ] && ! git grep -q -w "$sym" -- "$q"; then echo "missing $f $tok"; fi
  done
done > .cache/doc-check.txt; wc -l < .cache/doc-check.txt
```
   It prints `0`; otherwise fix each listed line in its doc (rule 5, stale: fix now), commit `docs: fix stale names in the architecture docs`, push, and re-run.
3. Write the acceptance table A1-A13 into the report, each row with its evidence line (report path and line).
4. `ak plan --help`, then `ak plan update pocketquant/261101-0843 --status completed --no-interactive` and `ak plan status plans/261101-0843-stf-to-mtf-foundation`.
5. Write `Result: PASS` as the report's last line; `git add plans/261101-0843-stf-to-mtf-foundation` and commit `docs(plans): close the multi-timeframe foundation plan`; push `develop` (Markdown only, no CI).

**Success criteria:** both checks print `0`; `plan.md` says `status: completed`; HEAD is pushed.

**Verify:** `wc -l < .cache/doc-check.txt; grep -c "^status: completed$" plans/261101-0843-stf-to-mtf-foundation/plan.md; test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `0`, `1`, `pushed`.

## Rollback

Observations and the comparison are read-only (the owner's paper close and cancel are normal paper actions). The delete is irreversible by owner decision (C12, no backup); the exact lists in `R/stf-delete-ids.json` record what was removed. A 1d mismatch is handled by the owner through the Phase 03 rollback. The plan close is undone with `ak plan update pocketquant/261101-0843 --status in-progress`.

## Report

`reports/phase-17-observe-compare-delete.md`: entry-gate outputs; the six `obs-` lines with ids and `obs-3 requested_at=`; the comparison output; the three summary lines; `stf_delete=yes`; `orphans=`; the delete output; the re-list line; both doc-check counts; the A1-A13 table; the `ak plan status` line; then `Result: PASS`.

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
