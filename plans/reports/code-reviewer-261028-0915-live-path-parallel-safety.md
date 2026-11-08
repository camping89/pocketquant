---
title: "Live-trading hot path: what breaks when the app goes parallel"
date: 2026-10-28
status: advisory, no code changed
scope: read-only review of develop @ 453e8e90
related: plans/reports/kongming-261028-0848-event-loop-concurrency-review.md, plans/reports/debug-261023-0045-daily-0400-integrity-event-loop-stall.md
---

# Live-trading hot path under parallelism

Labels: **[F]** = I verified it in code at the cited line. **[I]** = my inference, not
measured. **[U]** = unknown, needs a check. Findings are ranked by risk to real money once
Exness live trading is on. Today `EXNESS_LIVE_TRADING` is off and every subscription is
paper. Some findings below already apply to a single process; they are marked "today".

## TL;DR

- The live path is correct today only because of four implicit single-process guarantees:
  1. one process owns all subscriptions, brokers and the scheduler;
  2. one global bar lock runs all bar handling, and every order from it, one at a time;
  3. the entry pause is held in one object in memory;
  4. handlers on the in-process bus run in a fixed order.
- Nothing enforces any of them. They are kept by a comment in the Dockerfile/compose and by CLAUDE.md.
- Splitting the hot path across processes would break all four. Splitting the batch jobs
  off breaks none of them, as long as the worker never starts the trading runtime. That is
  the only safe parallel shape I see:
  - **one trader process**, holding a lease, owns the quote feed, bar building, strategies,
    brokers, reconcile and the pause flag;
  - **one or more worker processes** run sync, integrity, repair and backtests and never
    touch a broker.
- Three gaps hurt real money even in one process (H1-H3): an entry still in flight is
  invisible to the duplicate-entry checks; nothing stops a strategy acting on a stale bar;
  a gap in the bar feed is never detected.

## 1. Hot path as built [F]

```
WS frame (Binance aggTrade / Exness tick / TV poll)
 -> adapter callback, awaited inline          binance_websocket_adapter.py:177-208, exness_quote_adapter.py:124-135
 -> QuoteAppService.on_quote_update           quote_app_service.py:40-92 (Redis SET, then add_tick)
 -> BarAppService.add_tick under ONE lock      bar_app_service.py:79,90-92 (all symbols, all 7 intervals)
    bar closes only when a tick of a later bucket arrives   bar_app_service.py:117-132
 -> EventBus.publish(BarCompletedEvent), sequential awaits  event_bus.py:26-42, bar_app_service.py:162
    1st: StrategyAppService._on_bar_completed  strategy_app_service.py:241-270
    last: PaperBrokerAdapter._on_bar_completed (SL/TP)      paper_broker_adapter.py:141-146, 523-562
 -> _process_signal: get_balance, risk check, sizing, normalize_quantity   strategy_app_service.py:323-376
 -> OrderAppService.submit: save, then broker.submit_order  order_app_service.py:37-135
 -> Exness: snapshot gate, loss cap (deals HTTP), conditions, openPosition(idempotency_key=order.id)
                                               exness_broker_adapter.py:199-243, 317-370
 -> fill on events stream or status poll -> on_order_update -> OrderFilledEvent
    -> PositionAppService mirror row + strategy.on_order_filled    position_app_service.py:61-128
```

All of that, from the WS read to the venue ACK, runs inside one `await` chain while
`BarAppService._lock` is held [F: bar_app_service.py:90-92 -> 162]. Ticks for every symbol
wait until the order call returns.

## 2. Invariants that rely on one process / one loop

| # | Invariant | Where [F] | What enforces it |
|---|-----------|-----------|------------------|
| I1 | Exactly one process runs strategies, brokers and reconcile | `main.py:472-475`. `bootstrap_live_instances` and `start_quote_feed` run regardless of `enable_jobs` (`main_extensions.py:161-172,185-199`) | Only the comments in `deploy/Dockerfile:62` and `deploy/compose.prod.yml:62-63`, plus CLAUDE.md. No lease, no lock |
| I2 | Exactly one APScheduler uses the Mongo jobstore | `scheduler.py:54-75` | Nothing. The docstring (`scheduler.py:3-5,54-56`) says sharing across processes is safe ("first to update next_run_time wins"). The APScheduler 3.x FAQ says the opposite: "Sharing a persistent job store among two or more processes will lead to incorrect scheduler behavior" (jobs run twice or are skipped) |
| I3 | The entry pause is one object in memory, read on every open | `exness_safeguards.py:10-31`. Loaded once at boot (`di/adapters.py:50-58`). The route flips the in-memory flag, then stores it (`routes/safeguards.py:102-108`). Read at `exness_broker_adapter.py:246` | The single process. The stored value is re-read only at the next boot |
| I4 | All bar handling, and so every order, runs one at a time | One global `asyncio.Lock` (`bar_app_service.py:79,90`). The order is submitted inside the handler (`strategy_app_service.py:258-261,380`) | The lock. This is also why `_loss_cap_reason` (`exness_broker_adapter.py:222,265-275`) and the exposure check (`risk_check.py:32-46`) cannot race each other today |
| I5 | Bus handlers run in subscription order: strategy first, paper SL/TP last | `strategy_app_service.py:75-81`, `paper_broker_adapter.py:141-146` | List order inside one `EventBus` instance |
| I6 | The paper "fresh position" filter compares two timestamps taken from one clock | `paper_broker_adapter.py:538` (`p.opened_at >= event.occurred_at`) | Same process, same clock |
| I7 | One venue adapter per account, one events stream, one in-memory `_positions` / `_inflight` map | `strategy_app_service.py:421-442` (venue broker pooled per type), `exness_broker_adapter.py:111-127` | The single process |
| I8 | Paper broker state (balance, positions) lives only in memory. Boot deletes the open mirror rows of paper subscriptions | `paper_broker_adapter.py:111`, `position_app_service.py:36-53`, `di/services.py:121-132` | The single process |
| I9 | One Exness request pacer per account; order ops jump the queue | `exness_client.py:59-60,147-177,288-312`. One APP-scoped client is shared by candles, the ticks WS and orders (`di/adapters.py:82-127`) | The single process. Exness limits are cluster-wide (`exness_client.py:302`) |
| I10 | Boot sweeps assume nothing else is running | `recover_orphan_backtests` marks every `started` run failed (`main_extensions.py:132-141`); `recover_orphan_jobs` (`:144-158`) | The "single uvicorn worker" assumption written in the docstrings |
| I11 | Each symbol has exactly one realtime feed, so ticks are not counted twice | `routing_realtime_quote_adapter.py:298-322` | Per process only. A second process opens a second feed and builds its own bars |

## 3. Findings, ranked by real-money risk

### Critical (blocks any split of the trading runtime)

**C1. The entry pause does not cross a process boundary.** [F] for the mechanism, [I] for the outcome.
- Mechanism: the pause is a field on a per-process dataclass. It is loaded once at boot
  (`di/adapters.py:58`) and read from memory on every open (`exness_broker_adapter.py:246`).
- Outcome: if the API runs in one process and the Exness broker in another,
  `POST /admin/safeguards/pause` flips only the API's copy and writes Mongo. The broker
  process keeps opening positions until it restarts. The kill switch would look like it
  worked: the route returns `entries_paused: true`.
- Fix: the broker reads the stored flag before each open, and **fails closed**: if the read
  fails, the open is refused. Alternatively, only the trader process serves
  `/admin/safeguards`. One `find_one` per open costs well under the order's own HTTP time [I].

**C2. Nothing stops a second trading runtime: two broker sessions on one account and duplicate orders.** [F] for each step, [I] for the combined outcome.
- Any second copy of the app pointed at the prod Mongo does all of the following:
  - runs `bootstrap_live_instances` without condition (`main.py:472`);
  - opens its own quote feeds and builds its own bars (`main.py:474`);
  - with `enable_jobs=true`, starts every subscription (`main_extensions.py:236-237`).
- Each process then evaluates the same bar and submits its own order. Each order has a fresh
  uuid7 as its idempotency key (`OrderAggregate.create` at `strategy_app_service.py:401`,
  key at `exness_broker_adapter.py:327-333`), so the venue cannot merge the two.
- The adapters then talk across each other through the shared account events stream:
  - Process B sees A's fill as an unknown request (`exness_broker_adapter.py:506-511`). That
    blocks B's further opens on that instrument, which is fail-safe, but only after the
    duplicate has already gone out.
  - A snapshot rebuild in B can adopt A's position from its repo row
    (`exness_broker_adapter.py:448-459`). Both processes then react to its close: each
    publishes `OrderFilledEvent` and `TradeClosedEvent`.
  - The result is duplicate `trades` rows: `trade_id=generate_id()` and nothing dedups on the
    venue position or deal id (`live_trade_collector.py:57-81`, `trade_repository.py:21-45`).
  - It also produces duplicate or overwritten `positions` rows: there is no unique index on
    the open position per subscription (`position_repository.py:99-103`), and `save` replaces
    the whole document, so the last writer wins (`:56-58`).
- Even a "harmless" second process with jobs off does damage at boot:
  - it deletes the open mirror rows of the live process's paper subscriptions
    (`position_app_service.py:46-47`, run from `di/services.py:121-132`);
  - it marks every running backtest failed (`main_extensions.py:132-141`).
- Fix: a **trader lease**. One Mongo doc `{_id: "trader", owner, lease_until}`, taken with
  `find_one_and_update` on start and renewed every few seconds.
  - Every hot-path start must hold it: bootstrap, quote feed, reconcile, broker connect.
  - Every boot sweep must hold it: paper-row delete, orphan sweeps, migrations.
  - On losing the lease, the process stops its strategies and refuses opens.
  - A per-subscription owner field is not needed while there is a single trader process [I].

**C3. If two schedulers share the jobstore, `sync_repair` / `sync_1m` can run twice or be skipped.** [F] APScheduler FAQ, [I] for impact.
- This one does not touch orders directly.
- Two `sync_repair` runs on the same range would both delete and re-insert bars
  (`integrity_jobs.py:144`, per the kongming report).
- The scheduler docstring invites this exact split. It must be corrected before anyone
  builds a worker on the strength of it.
- Fix: exactly one scheduler. Put it in the worker and drop it from the trader, or the
  reverse. Never both.

### High (apply to one process today; parallel bar delivery makes them worse)

**H1. An entry that is in flight is invisible to every duplicate-entry check.** [F] for each check.
- Exness `_held_for` looks only at filled positions (`exness_broker_adapter.py:202-204,307-315`).
- `_presubmit_reason` never asks whether this subscription already has an `_inflight` open
  (`:245-263`).
- `EngulfingStrategyService` sets `_open_direction` only on the fill (`engulfing_strategy_service.py:13-15,96-98,135-147`).
- `RiskCheckHandler` passes when the position is `None`, which it stays until the fill
  (`risk_check.py:32-33`).
- The idempotency key covers retries of one HTTP request (`exness_client.py:315-330`), not
  two signals for one bar.
- Today the window is narrow, because the bar lock holds the next bar until the ACK [F: I4].
  A second entry needs the fill to arrive after the next bar of that subscription. That only
  happens when the stream misses the fill and the status poll is still running: 15 s wait,
  then up to 4 polls 15 s apart (`exness_broker_adapter.py:58-59,372-395`) [I].
- With parallel or duplicated bar delivery (C2, or per-symbol workers), the window becomes
  the whole ACK-to-fill time [I].
- Fix:
  - (a) In the adapter, reject an open while any `_inflight` entry with `kind == "open"`
    belongs to the same subscription.
  - (b) Make the client request id deterministic: `uuid5(subscription_id, bar_start, direction)`.
    A replayed or duplicated signal then carries the same key.
  - [U] Whether Exness deduplicates on `EXN-IDEMPOTENCY-KEY`, and for how long, is not
    recorded in the repo. Verify on the demo account before relying on (b).

**H2. No guard against acting on a stale bar; a bar closes only when the next tick arrives.** [F] for the code, [I] for the session-gap case.
- A bucket closes on the first tick of a later bucket (`bar_app_service.py:117-132`). There is no timer.
- `BarCompletedEvent` carries `bar_start` and `occurred_at`, the time it was published (`bar/events.py`, `shared/events.py:10`).
- The strategy uses `event.close` as the current price for sizing, for the fallback SL and for `order.price` (`strategy_app_service.py:261,351-364,378,401-410`).
- Nothing compares `now` with the bar end.
- Consequences:
  - During the 25-49 min `sync_repair` stall (kongming report), a live entry can go out up
    to 49 min after its bar closed. It would be sized and stopped on prices that old [I].
  - On a session close (FX weekend, CME daily break), the last bar closes on the next
    session's first tick. A Friday 1h EURUSD bar would trigger an entry on Monday's open,
    with a SL based on Friday's prices. Depending on the gap, the venue may reject the stop
    or fill it at once [I].
  - Paper fills at `order.price`, i.e. the stale close (`paper_broker_adapter.py:205`).
    Paper P&L therefore hides latency cost entirely [F]. This matters when paper results
    are used to justify going live.
- Fix: in `_on_bar_completed`, compute `age = now - bar_end` and refuse **entries** (never
  exits) when `age` is over a per-interval budget (section 5). Log `strategy.bar_stale_skipped`
  with the age. Also record the age on every signal.

**H3. A gap in the bar feed is never detected; a cut-short bar is published as complete.** [F] for the code, [I]/[U] for the trigger.
- `BarBuilderDomainService.add_tick` silently drops ticks outside the bucket (`bar_builder_domain_service.py:91-92`).
- Strategies never check that bars are consecutive. Engulfing compares whatever `_prev_bar` holds (`engulfing_strategy_service.py:100-105`).
- If a feed drops for N minutes, the bar open before the drop closes on the first tick
  after it, holding only its pre-drop ticks, and the N missing buckets are never published.
  Binance aggTrade and Exness ticks are not replayed on reconnect.
- [U] Whether the 25-49 min stalls already cause such drops: during a stall the client
  cannot answer keepalive pings (`binance_websocket_adapter.py:62-63` ping 20 s / timeout
  10 s, websockets 16.0). Check the prod logs for `binance_ws` / `exness_ws.connection_failed`
  reconnects between 00:00-00:50 and 12:00-12:50 UTC.
- The docstring promises "at-least-once" delivery (`bar_app_service.py:54,149`). In fact
  delivery is at most once: the bar in progress is lost on restart, and buckets are lost on
  a feed gap. The promise is wrong, and a refactor may build on it.
- Fix:
  - Keep `last_bar_start` per subscription in `StrategyAppService`. When the new
    `bar_start` is not the calendar successor of the last one, skip entries on that bar
    and log `strategy.bar_gap`.
  - `(symbol, interval, bar_start)` is the natural sequence and dedup key. If bars ever
    cross a process boundary, carry it and drop duplicates on it.

### Medium

**M1. The calls before an order wait in the same pacer queue as candle backfills; a second process doubles the request rate.** [F] for the code, [I] for the outcome.
- Only `openPosition`, `closePosition` and `getOperationStatus` have priority (`exness_client.py:60`).
- Before every open, the hot path makes four calls, and none has priority:
  - `getTradingStateSnapshot`, for `get_balance` (`exness_broker_adapter.py:656-669`);
  - `getAccountDetails`;
  - `getDealsHistory`, for the loss cap (`:277-305`);
  - `conditions`.
- Once TradingView is gone, every repair or backfill page (`exness_adapter.py:58`) shares
  that queue. A `sync_repair` backlog would then delay the balance and loss-cap calls
  before each entry [I].
- A separate worker with its own `ExnessClient` would have its own pacer against a limit
  that is cluster-wide.
- A 429 on an order call is not retried (`exness_client.py:303-305`). It rejects the open
  and closes the snapshot gate until the next reconcile (`exness_broker_adapter.py:337-339`).
- Fix:
  - Give the pre-order reads priority, or cache balance and loss cap for a few seconds.
  - Give the worker a separate API key, or a fixed share of the limit
    (`exness_rate_fraction`) that adds up with the trader's to at most 1.0.
  - [U] Whether Exness counts limits per key or per account.

**M2. Removing the global bar lock removes serialization that the loss cap and exposure checks rely on.** [F] for I4, [I] for the race.
- Kongming item 3 proposes per-symbol locks, or moving the order call out of the lock, for latency.
- If that happens, two opens can pass `_loss_cap_reason` concurrently (a check, then a
  separate send).
- `max_lots` is a per-order cap, not an account cap (`exness_broker_adapter.py:188-197`).
- Fix: put an account-level `asyncio.Lock` around the open path in the adapter, from the
  presubmit checks to registering the in-flight request (`_inflight[rid]` set). This keeps
  correctness while the bar lock stops covering HTTP.

**M3. Strategy state is not restored from the venue position after a restart or stop/start; an opposite entry becomes a close.** [F] for each step, [I] for the chain.
- `on_start` clears `_open_direction` (`engulfing_strategy_service.py:74-79`, `hitnrun2_strategy_service.py:68-73`).
- The Exness position survives and is re-mapped from the snapshot.
- An opposite-side order whose quantity equals the held units is treated as an exit (`exness_broker_adapter.py:205-214`).
- Without `max_lots`, every order is clamped to the minimum lot (`exness_mappers.py:86-93`),
  so the quantities match by construction.
- So after a restart, an opposite engulfing **entry** closes the held position. The strategy
  then takes the SELL fill as its entry and records `_open_direction = SHORT` while the
  account is flat (`engulfing_strategy_service.py:143-147`). From then on it never trades.
- Fix:
  - On start, seed the strategy's open direction from the position mirror
    (`PositionAppService.get(sub_id)`).
  - In the adapter, accept a close only when the order is marked as an exit. Signals have
    `Direction.EXIT`, but it is rejected today (`risk_check.py:29-30`), so add an explicit
    `reduce_only` flag on the order. Do not infer an exit from the side alone.

**M4. Paper SL/TP order and the "fresh" filter depend on one in-process bus (I5, I6).** [F] Paper money only.
- If bar events ever travel through Redis Streams or similar, strategy-before-broker
  ordering and the same-clock comparison both stop holding.
- Keep the paper broker in the trader process.

**M5. Orders in flight at a crash are restored into `OrderAppService._pending` but not into the adapter's `_inflight`.** [F] for the code, [I] for the outcome.
- `load_pending_orders` (`di/services.py:119`) restores them into `_pending`; the adapter's `_inflight` starts empty.
- Their outcome lands in `unknown_request_fill` (`exness_broker_adapter.py:506-511`), and
  since no mirror row exists, the snapshot cannot map the position. The instrument stays
  blocked until a human steps in.
- This fails safe, but block-until-human should be a documented runbook state.

### Low

- `_seen_terminal` grows without bound (`exness_broker_adapter.py:120,570`). Trim after the snapshot.
- `flush_all_bars` is dead code. If wired into shutdown, it would publish bars still in
  progress as completed ones that strategies trade on (`bar_app_service.py:270-289`). Delete it.
- The doc comment at `scheduler.py:3-5,54-56` is wrong (C3). Fix it now. It is the most
  likely source of a bad "just run two of them" decision.

## 4. Guards: what exists, what is missing

| Guard | State | Evidence |
|-------|-------|----------|
| Idempotency key on order HTTP calls | **Exists, narrow**: covers transport retries of one request. Key = random `order.id` | `exness_client.py:315-330`, `exness_broker_adapter.py:327-333` |
| Deterministic client id per (subscription, bar, direction) | Missing | H1 |
| Single in-flight open per subscription | Missing | H1 |
| One position per subscription, same side | Exists (adapter rejects) | `exness_broker_adapter.py:206-207` |
| Venue-side SL on every open | **Exists**: the main mitigation for loop stalls | `exness_broker_adapter.py:220-221,239-242` |
| Opens gated until the venue snapshot is reconciled; unknown fills block the instrument | Exists | `exness_broker_adapter.py:256-262,333-342,506-511,642-647` |
| Terminal outcome delivered once per request | Exists | `_seen_terminal`, `exness_broker_adapter.py:489-491,568-576` |
| Daily loss cap from venue deals | Exists, but its check-then-send only stays atomic while I4 holds | `exness_broker_adapter.py:265-288` |
| Entry pause, durable | Exists for a single process; **breaks across processes** | C1 |
| Single owner per subscription / trader lease / heartbeat | Missing. Kept by convention only | C2 |
| Single scheduler | Missing, and the docstring wrongly says sharing is fine | C3 |
| Bar sequence number / gap detection | Missing. `(symbol, interval, bar_start)` is enough as the key | H3 |
| Stale-bar entry guard | Missing | H2 |
| One realtime feed per symbol | Exists (per process) | `routing_realtime_quote_adapter.py:298-322` |
| Late-tick rejection | Exists (drops silently) | `bar_builder_domain_service.py:91-92` |
| Dedup for trade rows / one open position row per subscription | Missing (random `trade_id`; no unique index) | C2 |
| Event-loop lag probe | Missing (proposed by kongming) | — |

## 5. Latency budget

**Where to measure.** None of these timestamps is logged together today. The only existing
pieces are `exness.order_submitted` and `ack_to_fill_ms` (`exness_broker_adapter.py:353-360,564-565`).
Emit one structured line per signal (`live.signal_latency`, keyed by subscription_id + bar_start) with:

| Point | Meaning | Source |
|-------|---------|--------|
| T0 bar_end | `calendar` successor of `bar_start` | computed |
| T1 closing-tick venue time | first tick of the next bucket (activity lag = T1-T0) | `tick.timestamp` |
| T2 tick received | network + loop lag (T2-T1) | wall clock at adapter |
| T3 event published | bar-lock wait (T3-T2) | `BarCompletedEvent.occurred_at` |
| T4 signal returned | strategy compute | after `on_bar_completed` |
| T5 pre-order checks done | balance, loss cap, conditions (T5-T4; M1) | before `openPosition` |
| T6 venue ACK | order sent (T6-T5) | `exness.order_submitted` |
| T7 fill | `ack_to_fill_ms` (exists) | `exness.order_filled` |

Add the event-loop lag probe from the kongming report next to it. When the probe shows lag,
it explains a T3-T2 spike.

**Targets** [I]: these are recommendations, not measurements. The aim is to keep entry
latency a small fraction of the bar and well below typical SL distance.

| Interval | p95 T0->T6 target | Hard stale-entry guard (refuse entry beyond) |
|----------|-------------------|-----------------------------------------------|
| 1m | <= 2 s | 10 s |
| 15m | <= 5 s | 60 s |
| 1h | <= 10 s | 120 s |

Notes:
- T1-T0 depends on market activity. FX majors and BTC tick many times a second [I]. ES via
  TradingView polling adds up to one poll interval (`tradingview_quote_adapter.py:157-224`;
  60 s per kongming). So a TV-fed symbol cannot meet any 1m budget, and even 15m is
  borderline. This is another reason to take quotes from the execution venue.
- Today's 25-49 min stalls break every row by 2-3 orders of magnitude. The calendar fix
  (kongming option A) comes before any parallelism work. The stale guard (H2) is the safety
  net while that fix is pending.

## 6. Recommended order

1. Correct the `scheduler.py` docstring (C3). Write down the "one trader process" rule as a
   checked invariant, not a comment.
2. Stale-bar entry guard + bar-gap guard + latency line (H2, H3, section 5). This is small,
   lives in `StrategyAppService._on_bar_completed`, and works in one process today.
3. One in-flight open per subscription + an account-level open lock in the Exness adapter
   (H1a, M2). Restore strategy direction from the mirror on start, and an explicit
   reduce-only exit (M3).
4. Make the entry pause read the store on each open and fail closed (C1). Do this before any
   process split.
5. Trader lease (C2). Then, and only then, move the scheduler and batch jobs into a worker
   that never starts the quote feed, bootstrap, reconcile, brokers or the boot sweeps. That
   split needs `main.py` lifespan to branch on a role, because today those steps ignore
   `enable_jobs`.
6. Deterministic client request id (H1b), after verifying how Exness treats a repeated
   idempotency key.

## Unresolved questions

- [U] Does Exness deduplicate repeated `EXN-IDEMPOTENCY-KEY` values, and for how long?
- [U] Are Exness rate limits counted per API key or per account? This decides whether a worker can have its own budget.
- [U] Do the 00:00/12:00 UTC stalls already drop the Binance or Exness WS? Check the reconnect logs (H3).
- [U] Does Exness allow two concurrent events or ticks WS sessions per account? It matters during a lease handover.
