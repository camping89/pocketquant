The contract below holds all of D1-D10. I found two places where the packet's proposals do not meet D2/D8 as written: 1m latency and the trader handover. Labels: **[F]** verified (file:line or report), **[I]** my inference, **[U]** unknown.

## 1. Outcome
- One 8 vCPU host runs three compose services from one image: `api`, `worker`, `trader`.
- TradingView and the CME calendar are gone. Market data is Exness only, plus Binance for paper.
- Deploys roll. `api` and `worker` restart with no gap. The `trader` hands over at a 1m boundary with no missed bar and no missed order.
- The live path is safe for 1m Exness entries before `EXNESS_LIVE_TRADING` goes back on. The pause works across processes, no second open can go out while one is in flight, stale or gapped bars refuse entries, and state is rebuilt after a restart.
- `US500/USTEC/US30` are onboarded only once Exness serves data for them.

## 2. Constraints
- D1-D10 and the CLAUDE.md limits apply.
- The CLAUDE.md "Single uvicorn worker" rule gets rewritten, not ignored. New text: one process per role; `worker` and `trader` are singletons guarded by a Mongo lease.
- The global bar lock stays [F `bar_app_service.py:79,90`]. It is what keeps the loss-cap check-then-send atomic today (M2). Removing it later requires an account-level open lock.
- Mongo stays standalone: no change streams, no new Redis features [F brainstormer §2].
- Migrations must be expand-only. During a roll, old and new code run against the same Mongo [I].
- Every phase's PR states its net line count. CLAUDE.md says "more code than replaced → ask". TV removal lands first so the total stays net-negative [I].

## 3. Non-goals
- Free-threaded 3.14t, `--workers N`, a process pool, symbol sharding, Redis Streams, a shared pacer.
- Moving backtests to the worker.
- H1b deterministic request ids. They wait for Exness to state the idempotency window.
- Zero loss on a crash, as opposed to a deploy. A crash still costs up to the lease TTL plus boot time.
- Live Binance.
- Replaying missed bars into strategies.

## 4. Acceptance criteria
Prod numbers are judged over 7 consecutive days unless stated.

**Stalls**
- `/health` reports `role`, `lease` (active/standby) and `event_loop_lag_max_s`. Max lag: trader < 0.5 s, api/worker < 1 s, every hour including 00/03/04/12Z.
- `job_history` p95: `sync_repair` < 120 s, `sync_integrity` < 10 s, `sync_1m` < 5 s. Today they are 1,609 / 419 / 9.3 s [F packet].
- 0 "Error notifying listener" lines, against 72 today [F].
- WS reconnects in the 00h/12h hours are no higher than in other hours.

**Parallelism and single owner**
- A forced second `worker` or `trader` start logs `lease.held_by_other` and starts nothing.
- No duplicate `(job_id, scheduled_run_time)` in `job_history`.
- `db.leases.countDocuments()` == 2.
- `APP_ROLES=api` (remote-db profile) logs no `quote_feed.started` and no `strategy_loaded`.
- Trader lag stays < 0.5 s during a 1-year 1m backtest.

**TradingView removal**
- `rg -i "tradingview|pandas_market_calendars|cme_globex"` over src, web/src, tests, scripts, docs, README, pyproject and uv.lock → 0 hits.
- Mongo: `bars`, `tracked_symbols`, `symbols`, `subscriptions`, `backtest_runs` matching `{symbol: /:TRADINGVIEW$/}` → 0. `01a178ef` is absent. Field names are assumed [U].
- CI green, including the 8 import-linter contracts.

**Exness indices**
- Gate: on the prod account, `getCandleHistory(US500, M1)` returns 200.
- Until the gate passes, `EXNESS_INSTRUMENTS` holds no index names. A CI test guards this, because a mapped name takes a WS strike on every reconnect [F researcher §8].
- After onboarding:
  - 0 `MARKET_INSTRUMENT_NOT_FOUND` frames.
  - `sync_integrity` shows 0 missing bars inside `EXNESS_US_INDEX` sessions.
  - Calendar tests pass for 2026-10-30 (DST) and 2026-11-02 (standard time).

**Live-path safety (CI tests plus prod logs)**

| Item | What must hold |
|---|---|
| C1 | A pause written by `api` → the trader's next open is rejected `entries_paused`. A failed Mongo read → the open is rejected (fail closed). `Safeguards.entries_paused` and the route's dual write are deleted. |
| C2 | Without the lease, a trader never runs bootstrap, feeds, broker connect or boot sweeps. Test: fake repo, assert zero calls. |
| H1 | A second open for a subscription while one is in `_inflight` → rejected `open_in_flight`. |
| H2 / D10 | A bar older than 10 s / 60 s / 120 s (1m / 15m / 1h) → the entry is skipped with one `strategy.entry_skipped_stale` WARNING. SL/exit still runs. A bar closes on a timer at bar_end + 300 ms, not only on the next tick. |
| H3 | A WS reconnect inside a bucket, a builder started mid-bucket without a covering seed, or a non-successor bar → `strategy.entry_skipped_gap`. The "at-least-once" docstring is corrected. |
| M1 | The pre-order path makes exactly 1 REST call (`openPosition`). Fake-client call count == 1. |
| M2 | Two concurrent signals cannot both pass the loss cap. |
| M3 | Restart with an open position: the direction is restored, and an opposite entry that is not `reduce_only` is rejected, not turned into a close. |

**1m latency**
- One `live.signal_latency` line per signal, with T0-T6 [reviewer §5].
- Paper: p95(T5 − T0) ≤ 1.0 s.
- Exness: p95(T6 − T0) ≤ 2.0 s over the first 20 demo or min-lot entries.

**Zero-downtime deploys**
- Drill: 5 deploys in market hours, with 1m/15m/1h paper subscriptions running.
  - Each handover logs one INFO `trader.handover_completed {handover_at, gap_ms}`, with `gap_ms` ≤ 2000.
  - The old trader's last handled bar_end == `handover_at`. The new trader's first == `handover_at` + 1m.
  - 0 `exness.unknown_request_fill`, 0 `exness.position_unmapped`.
- 1 req/s through Cloudflare to `/api/health` → 0 non-2xx during deploy.
- Exactly one `sync_1m` row per minute across the deploy.
- If in-flight orders are unresolved after 30 s: `trader.handover_aborted` WARNING, the old trader keeps the lease, and the deploy script exits non-zero.

## 5. Trade-offs

**Fork 1: trader handover (D8)**

| | A. Short tick overlap (recommended) | B. No overlap, venue seed | C. Stop-start |
|---|---|---|---|
| How | New trader in standby: loads strategies, warms up from stored bars, sends no orders and opens no events WS. It subscribes ticks about 10 s before boundary T. The old trader handles bars ending ≤ T, drains `_inflight`, then CAS-transfers the lease. The new one opens the events WS, gets a snapshot, and seeds the buckets that straddle T from stored 1m/cascade bars (in Mongo by about T+15 s, since `sync_1m` runs at second 2 [F `sync_jobs.py:707`]). | New trader connects only after the transfer. It seeds open buckets from REST candles including the in-progress one. | Restart and accept a partial first bar. |
| Assumption it depends on most | Exness tolerates two ticks WS sessions on one account for about 10 s [U]. The spike says up to 10 WS per account [F kongming §3.3]. | Adapters can return the open candle. Exness drops it today [F explore §3]; Binance is unverified. | — |
| Fails first when | Exness kicks or strikes the old session → bar T incomplete → one refused entry | The takeover seed gets a 429 or pacing delay past the bucket end | Always: it misses a bar |
| Worst case | One missed bar per deploy, visible in the drill | A refused entry on a higher interval, plus a new adapter parameter | Violates D8. Rejected. |

**Fork 2: 1m pre-order latency (D2)**
- Facts that set the budget:
  - Pre-order REST calls today: snapshot, deals pages, `openPosition` [F `exness_broker_adapter.py:222,299,657`]. `getAccountDetails` and `conditions` are cached [F `:658`, `exness_client.py:373`].
  - Pacer spacing at fraction 0.6 is 1.0 s [F `:120,355`].
  - The bar closes only on a later tick [F `bar_app_service.py:120`]. XAUUSD gave 55 ticks in 45 s [F researcher §0]. That puts the closing-tick wait alone at a p95 near 2.5 s [I].
- A (recommended): a background refresher fetches snapshot and deals every 10 s, plus right away on any close fill. The hot path reads the cache and fails closed if it is older than 30 s. Add the bar-close timer.
  - Depends on: equity and losses moving little within 10 s.
  - Fails when: an SL hits and an entry follows before the refresh lands.
  - Worst case: one trade past the cap.
- B: an event-sourced loss cap built from stream deals.
  - Depends on: no lost events.
  - Worst case: an undercount that lasts until the next reconcile, which is worse than A.
- C: give the reads pacer priority. This fails by construction: 3 calls × 1.0 s is already more than 2 s.

**Fork 3: Exness rate budget across processes**
- A (recommended): static `exness_rate_fraction` per role [F `config.py:118`]: trader 0.6, worker 0.3, api 0.05. Move `sync_1m` from second 2 to second 20, out of the order window.
  - Depends on: limits counted per account.
  - Fails when: a cluster 429 lands below the limit [F `exness_client.py:304`], and a 429 on `openPosition` is never retried [F `:305`].
  - Worst case: a missed order, logged.
- B: route all Exness REST through the trader. This is new infrastructure on the order path. Rejected.
- C: a separate API key for the worker. Depends on limits being per key [U]. The probe evidence shows a second consumer on the account disturbs prod anyway [F kongming §0].

## 6. Better approaches
None. The recommended direction is the requested one:
- D8's warm-up / lease-at-boundary / old-exits sequence is implementable with the existing seed hook [F `bar_app_service.py:114,180`] and the existing snapshot gate [F `exness_broker_adapter.py:256`].
- The bar-close timer and the pre-order cache are what make D2 and D10 reachable. They do not replace any decision.

## 7. Recommended direction and phases

**Phase 1 — TradingView first (D1, D4)**
1. Run the existing symbol delete on `ES1!/NQ1!/YM1!` in prod. It cascades bars, subscriptions including `01a178ef`, and backtests [F memory]. The owner's D1 overrides the "never stop/delete `01a178ef`" note in memory.
2. Then deploy the code deletion: the explore §1 list, the CME adapter, `pandas_market_calendars`, `scripts/seed_index_futures.py`, the web branches.
3. Ride-alongs: the skip-listener fix, the `scheduler.py` docstring (C3), the loop-lag probe, `python:3.14-slim`, and deleting `flush_all_bars`.
4. This removes the stall's root cause [F kongming §1]. Deploy outside 00, 03, 04 and 12Z.

**Phase 2 — Live-path guards, still in one process**
- C1 read-through.
- H1a.
- D10 stale and gap guards, using a feed-connection epoch per bucket. Not silence: EURUSD has normal night gaps [I].
- The bar-close timer.
- D9 warm-up: replay the last N stored bars with signals discarded. Then restore direction from the position mirror (M3), with explicit `reduce_only`.
- Paper positions rebuilt from mirror rows. This deletes the boot-time paper-row delete [F `position_app_service.py:46-47`].
- The pre-order refresher and `live.signal_latency`.

**Phase 3 — Split and rolling deploys (D5-D8)**
- `APP_ROLES` replaces `enable_jobs`, which is deleted.
- One lease helper with two callers. Boot sweeps run only after the role's lease is held. The api backtest sweep must not fail the other replica's runs.
- Compose:
  - Drop `container_name` so the scale-then-stop roll works.
  - nginx uses the Docker resolver for `api`.
  - `10-deploy.sh` rolls `api` → `worker` → `trader`. The trader rolls with the Fork 1A handover.
- Rate fractions, `sync_1m` moved to second 20.
- Rewrite the CLAUDE.md rule and the architecture docs.
- Move to the 8 vCPU host.

**Phase 4 — Gated on index data returning 200**
- `EXNESS_US_INDEX` calendar, built from live `trade_sessions`, standard-time table after 2026-11-01. Close-only minutes count as closed for entries.
- Three `EXNESS_INSTRUMENTS` entries, `ContractSpec`s, M1 backfill.

**Before live trading is re-armed:** Phases 2 and 3 done, 7 green days on the section 4 metrics, the 5-deploy drill passed, and the Exness latency check on demo or min lot.

**Deleted:** the TradingView/CME surface, `enable_jobs`, the in-memory pause, the paper-row boot delete, `flush_all_bars`, the REST calls on the hot path, the `app` service, and the "single uvicorn worker" rule text.

## 8. Unknowns and open questions
1. **Blocking (Phase 4):** Exness returns 404 for indices data on this account [F researcher]. The app showing the symbols does not prove API data access [F researcher §8].
2. **Blocking (Phase 3, Fork 1A):** can two ticks WS sessions run on one account without a kick or a strike? Test in an owner-approved window. If they cannot, fall back to 1B.
3. **Blocking (live re-arm):** VPS-to-Exness `openPosition` round trip, and whether a demo account exists for the latency check.
4. **Not blocking:** are limits per key or per account? What is the `EXN-IDEMPOTENCY-KEY` window, which would decide whether one 429 retry is safe?
5. **Not blocking:** should paper balance persist across restarts? Today it lives in memory only [F reviewer I8].
6. **Not blocking:** does cloudflared re-resolve `web` if `web` also rolls? Web restarts are outside D8 as written [I].
7. **Not blocking:** the US500 tick rate. The bar-close timer bounds it either way.
