---
phase: 1
title: "Post-DST session and integrity check"
status: pending
priority: P2
effort: 1 check
dependencies: []
---

# Phase 01: Post-DST session and integrity check

## Goal
Prove on prod that the Exness XAUUSD and EURUSD sessions moved one hour later in UTC after US DST ended on 2026-11-01, and that the calendar adapter still matches the stored bars.

## Entry gate
Run on or after Mon 2026-11-02 03:00Z (10:00 Bangkok), after the first post-DST Sunday reopen (EUR 22:05Z, XAU 23:01:30Z on 2026-11-01). Before then, change nothing and report `NOT_YET`.

## Context
- Source: plan `archive/261009-0858-exness-venue-lean-sync-refactor`, Phase 08, T8.7 row 4 and the C5 description. The commands below are copied from there; C1, C2 and C5 were tested in prod on 2026-10-19 and C3 on 2026-10-20.
- Paper subscription ids started in that plan's T8.6: hitnrun2 XAUUSD 1m `01a15754-39ed-73e3-921e-df085eb4a786`, engulfing EURUSD 1h `01a15754-3ab5-7258-b46b-ad98e1f3471f`. Both were stopped on 2026-10-26 (that plan's T8.8), so C2 is expected to print `running 0`.
- `SINCE` for C1: the last "checked at" in that plan's T8.7 results table.

## Commands
- **Setup (every check, repo root):** the key file has CRLF line endings, so use a normalized copy.
  ```bash
  mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key
  KEY=.cache/ssh/vps_key; HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r')
  ```
- **Checks:**
  - **C1 log counters** since the previous row's check time. Prints `S= F= CB= RC= RL=`. If `S` is later than `SINCE`, the counters start at the restart; if `F` is later than both, logs rotated. Record either case; neither is a failure.
    ```bash
    SINCE=<previous row's "checked at", UTC ISO>
    ssh -i "$KEY" "$HOST" "SINCE=$SINCE sh -s" <<'EOF'
    L=$(docker logs --timestamps --since "$SINCE" pocketquant-app 2>&1)
    echo "S=$(docker inspect -f '{{.State.StartedAt}}' pocketquant-app) F=$(echo "$L" | head -1 | cut -d' ' -f1) CB=$(echo "$L" | grep -c exness_ws.circuit_breaker_open) RC=$(echo "$L" | grep -c exness_ws.reconnecting) RL=$(echo "$L" | grep -c exness.rate_limited_retry)"
    EOF
    ```
  - **C2 integrity, `sync_1m` and subscriptions.** `CHECKS` is a space-separated list of `SYMBOL/INTERVAL/DAYS_BACK`.
    ```bash
    CHECKS='<per row>'; WINDOW=<24h|7d>; IDS='<id1> <id2>'
    ssh -i "$KEY" "$HOST" "CHECKS='$CHECKS' WINDOW=$WINDOW IDS='$IDS' sh -s" <<'EOF'
    q() { docker exec pocketquant-app curl -s "$@"; }
    py() { docker exec -i pocketquant-app python -c "$1"; }
    for c in $CHECKS; do
      set -- $(echo "$c" | tr / ' ')
      q -X POST http://localhost:41921/api/v1/market-data/integrity/check -H 'Content-Type: application/json' -d "{\"symbol\":\"$1\",\"interval\":\"$2\",\"days_back\":$3}" \
        | py "import json,sys;d=json.load(sys.stdin);print('$1 $2 $3d missing', d['missing_count'], 'misaligned', d['misaligned_count'], d['gap_ranges'][:5])"
    done
    q "http://localhost:41921/api/v1/system/jobs/sync_1m/stats?window=$WINDOW" | py "import json,sys;d=json.load(sys.stdin);print('sync_1m p95_ms', d['p95_ms'], d['by_status'])"
    q http://localhost:41921/api/v1/subscriptions/ | py "import json,sys;ids=set('$IDS'.split());print('running', sum(1 for s in json.load(sys.stdin) if s['id'] in ids and s['actual_state']=='running'))"
    EOF
    ```
  - **C3 integrity with a venue check.** Runs the integrity check for each `CHECKS` item, then reads each `gap_ranges` entry forward from Exness (`getCandleHistory`, positive `count` reads forward from `from` inclusive; candle field `time`). A range is venue-empty when no candle has `time <= range_end`. Prints `PASS` when `misaligned 0` and every range is venue-empty. C3 replaces C2's integrity loop, so run C2 with `CHECKS=''`. Start C3 at UTC second 20 or later: `sync_1m` fires at second 2 and takes up to about 15 s, so an earlier check can see the just-closed minute as missing. `check()` sends `X-Admin-Token` from the app settings (tested in prod 2026-10-23).
    ```bash
    CHECKS='<per row>'
    ssh -i "$KEY" "$HOST" "CHECKS='$CHECKS' docker exec -i -e CHECKS pocketquant-app python -" <<'EOF'
    import asyncio, json, os, urllib.request, datetime as d
    from pocketquant.core.config import get_settings
    from pocketquant.core.infra.exness.exness_client import ExnessClient
    TF = {"1m": "M1", "5m": "M5", "15m": "M15", "1h": "H1", "4h": "H4", "1d": "D1"}
    SEC = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
    TOKEN = get_settings().admin_token.get_secret_value()  # admin auth guards every POST since the go-live deploy
    def check(sym, iv, days):
        req = urllib.request.Request("http://localhost:41921/api/v1/market-data/integrity/check",
            data=json.dumps({"symbol": sym, "interval": iv, "days_back": days}).encode(),
            headers={"Content-Type": "application/json", "X-Admin-Token": TOKEN})
        return json.load(urllib.request.urlopen(req))
    async def main():
        c = ExnessClient(get_settings())
        try:
            for item in os.environ["CHECKS"].split():
                sym, iv, days = item.split("/")
                r = check(sym, iv, int(days))
                out = []
                for start, end in r["gap_ranges"]:
                    s, e = d.datetime.fromisoformat(start), d.datetime.fromisoformat(end)
                    n = min(1000, int((e - s).total_seconds() // SEC[iv]) + 1)
                    body = await c.call("getCandleHistory", params={"instrument": sym.split(":")[0],
                        "timeframe": TF[iv], "price_type": "bid", "from": s.isoformat(), "count": n})
                    have = [k["time"] for k in body.get("candles", []) if d.datetime.fromisoformat(k["time"]) <= e]
                    out.append((start[:16], end[:16], "venue_empty" if not have else "VENUE_HAS " + str(have[:3])))
                ok = r["misaligned_count"] == 0 and all(o[2] == "venue_empty" for o in out)
                print(sym, iv, days + "d", "missing", r["missing_count"], "misaligned", r["misaligned_count"],
                      "PASS" if ok else "FAIL", out[:8])
        finally:
            await c.close()
    asyncio.run(main())
    EOF
    ```
  - **C5 sessions.** Compares the live `trade_sessions` with the calendar constants as merged UTC open segments. The constants were recorded under EDT and the adapter holds them in `America/New_York`, so from 2026-11-01 the expectation is the constants shifted +1 h (checked against `ExnessSessionCalendarAdapter.is_open` for the weeks of 2026-10-19 and 2026-11-02: unshifted matches before DST, +1 h matches after, unshifted fails after). Prints `<shift> <bool>`; it must print `0 True` before 2026-11-01 and `3600 True` from then on.
    ```bash
    ssh -i "$KEY" "$HOST" 'docker exec -i pocketquant-app python -' <<'EOF'
    import asyncio
    import datetime as d
    from pocketquant.core.config import get_settings
    from pocketquant.core.infra.exness.exness_client import ExnessClient
    from pocketquant.core.infra.calendars.exness_session_calendar_adapter import _EURUSD_SESSIONS, _XAUUSD_SESSIONS, _shifted, _week_offset
    def spans(sessions, shift):  # merged open [start, end) seconds from Monday 00:00 UTC
        pieces = sorted(p for s in sessions if s["trade_mode"] == "enabled"
                        for p in _shifted(_week_offset(s["week_start_time"]), _week_offset(s["week_end_time"]) + 1, shift))
        merged = []
        for a, b in pieces:
            if merged and a <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b))
            else:
                merged.append((a, b))
        return merged
    async def main():
        c = ExnessClient(get_settings())
        try:
            return [(await c.conditions(n))["trade_sessions"] for n in ("XAUUSD", "EURUSD")]
        finally:
            await c.close()
    shift = 3600 if d.datetime.now(d.UTC).date() >= d.date(2026, 11, 1) else 0  # EDT-recorded constants move 1 h later under EST
    live = asyncio.run(main())
    print(shift, [spans(t, 0) for t in live] == [spans(c, shift) for c in (_XAUUSD_SESSIONS, _EURUSD_SESSIONS)])
    EOF
    ```

## Tasks
### T1.1 Run the check
- **Steps:**
  1. Run the setup, then C5.
  2. Run C1 with `SINCE` as above.
  3. Run C3 with `CHECKS='XAUUSD:EXNESS/1m/2 EURUSD:EXNESS/1m/2 XAUUSD:EXNESS/1h/7 EURUSD:EXNESS/1h/7'`, starting at UTC second 20 or later.
  4. Run C2 with `CHECKS=''`, `WINDOW=7d` and `IDS='01a15754-39ed-73e3-921e-df085eb4a786 01a15754-3ab5-7258-b46b-ad98e1f3471f'`.
  5. Write one row into the results table below.
- **Pass:**
  1. C5 prints `3600 True`.
  2. `misaligned 0` and `PASS` on every C3 line. On a `FAIL` whose only `VENUE_HAS` range ends within 2 minutes of the check, re-run C3 once after 60 s; a `PASS` then passes. Otherwise run `POST /api/v1/market-data/integrity/repair` once for that symbol and interval and re-run C3; still `FAIL` fails the check.
  3. `sync_1m p95_ms < 60000` and `CB=0`.
  4. `running 2` only if the paper subscriptions are still running; otherwise record the count.
  5. Recorded only: `missing` counts, the venue-empty ranges, `RC`, `RL` and `by_status`.
- **Verify:** The results table has one `PASS` row dated 2026-11-02 or later.

## Results
| Checked at (UTC) | `S` (StartedAt) | `F` | CB | RC | RL | Integrity missing/misaligned | `sync_1m` p95 ms (by_status) | Running | C5 | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|

## Stop-and-ask
- C5 prints `False`, or C5 prints `0` as the shift on or after 2026-11-01.
- A C3 line still fails after the repair.
- Any step that would place a live order or change code.

## Security
Read-only: no credentials are printed, and no order endpoint is called. Delete `.cache/ssh/vps_key` when done.
