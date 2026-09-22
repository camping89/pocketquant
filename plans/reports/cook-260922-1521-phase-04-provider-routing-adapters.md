# Phase 4 completion — Provider Routing Adapters and Settings

Plan: `plans/260921-1436-asset-class-index-futures/`
Phase file: `phase-04-provider-routing-adapters.md`
Date: 2026-09-22
Status: complete. All 8 tasks done; shipped to production and verified on the VPS.

## Outcome

Provider choice is now a function of the symbol's asset class plus optional per-symbol
overrides, resolved behind two routing adapters that implement the same ports their
children do. `SyncService`, `fetch_with_retry`, `WsSubscriptionAppService`,
`QuoteAppService` and `TrackedSymbolBackfillService` were not edited, which is G4.
Binance is the only registered provider, and crypto comes out unchanged.

The phase's own acceptance — "crypto is unchanged through the routing layer" — was met
and proved almost nothing, exactly as Phase 3's report predicted it would. Everything
of value in this phase is in what was added beyond the eight tasks.

## Verification

Phase gate, exit 0 on every command:

| Command | Result |
|---------|--------|
| `uv run pytest tests/ -q` | `782 passed, 1 skipped` (baseline 751) |
| `uv run ruff check src tests scripts` | `All checks passed!` |
| `uv run lint-imports` | `Contracts: 9 kept, 0 broken` |
| `uv run pyright src` | `0 errors` — and now actually checking the port binding |
| `just test-tz` | `782 passed` under UTC, Asia/Ho_Chi_Minh, America/Chicago |
| `cd web && npx tsc --noEmit` | exit 0 |

## The two things the phase was asked to pin anyway

**The nested empty-result loops.** `fetch_with_retry` retries on an empty answer and
the routing adapter walks to the next provider on one. They multiply, and with a
single registered provider nothing that runs today can tell whether the calendar gate
sits above both or between them. The existing calendar-gate suite cannot answer it
either: it mocks `SyncService`, so it stops one layer above the loops.

`tests/app_test/unit/market_data/test_closed_market_skip_precedes_provider_loops.py`
wires the real chain and asserts on the child provider's call count, which is the only
number that reaches a venue. A shut market reaches zero providers, and deleting Phase
3's skip (commit `787f81b`) turns that red — confirmed by deleting it. An open market
whose providers all answer empty costs exactly `attempts x providers`, recorded as an
exact number rather than a bound so Phase 5 reads the price of a second provider
instead of rediscovering it during a halt. A third test pins that the product is a
worst case and not a toll: a primary that answers costs one call.

**The unknown-symbol default.** Task 4 step 2's "use `CRYPTO_SPOT` when the record is
missing" is an ordering invariant wearing a default's clothes, and the failure is
worse than the plan suggests. `_persist_bars` returns early when no bars arrive, so
`SymbolRepository.touch` is never reached. A futures symbol tracked before it is
seeded routes to a crypto venue, receives nothing, never gets a document written, and
repeats forever — with `SymbolLookupHelper` caching the miss for 60s in between. It is
self-reinforcing, not self-correcting.

The assumption now lives in one named constant, `UNSEEDED_SYMBOL_ASSET_CLASS` in
`core/infra/market_data/symbol_provider_resolver.py`, shared by both adapters so there
is exactly one of it, and it emits a one-shot WARNING naming the symbol and the class
it assumed. One-shot because this is a per-minute path and because the ongoing alarm
is already `emit_no_progress`'s job; this line only names the cause the first time.

## What the phase's own Verify steps did not catch

Three of the eight Verify steps could not pass on correct code, and one of them was
concealing a real defect rather than merely being useless. Full detail is in `plan.md`
under Correction 14.

1. **Task 5's Verify calls `issubclass` on a Protocol that forbids it.** The port has
   three non-method members, so CPython raises `TypeError` for every class — including
   the `BinanceWebSocketAdapter` that has been in production for months, which is the
   proof the gate was not measuring the adapter.
2. **What that gate was hiding.** Task 5 step 9 claims a read-only property satisfies
   structural typing. True for runtime `isinstance`, which only checks that a name
   exists; false for pyright, which rejects a property against a member declared as a
   mutable attribute. `pyright src` was green only because Task 7 step 2 said to keep
   the `# type: ignore` comments, and pyright suppresses the whole line — so the one
   place the adapter meets the port type was unchecked. Fixed on the port, by
   declaring `last_tick_at` read-only: every write in the codebase is a provider
   assigning its own attribute, no consumer touches it through the port, and a mutable
   declaration would forbid any provider that derives the value rather than storing
   it. Both ignores removed.
3. **Task 7's Verify grep counts a class definition and two docstrings.** It returns 2
   on correct code. Replaced with one that returns 0 today and 1 when a construction
   is planted in `engine/` — verified by planting one.
4. **Task 8 step 3's URL does not exist.** The quotes router mounts at
   `/api/v1/quotes/latest/{symbol}`, not `/api/v1/market-data/quotes/{symbol}`, which
   returns `{"detail":"Not Found"}`. A manual check rather than an automated gate, so
   it would have wasted a few minutes rather than blocking.

Two expected test counts were also wrong in the harmless direction (Task 3 says 4 and
delivers 5; Task 6 says 10 and delivers 20).

## Mutation results

With one provider registered, every fallback branch is unreachable in production, so
each was confirmed to turn a test red by actually being changed:

| Behaviour removed or inverted | Result |
|---|---|
| Return the primary's empty answer instead of falling through | 1 failed |
| End the walk on an unregistered provider id | 1 failed |
| Drop the unseeded-symbol warning | 2 failed |
| Warn every fetch instead of once per symbol | 1 failed |
| Drop the no-provider warning | 1 failed |
| Ignore overrides / drop `.upper()` / return the stored list (x2) | 1-2 failed each |
| Replace `asyncio.gather` with sequential awaits | 1 failed |
| Swallow `CancelledError` in `run_forever` | 1 failed |
| Break `unsubscribe`'s signature | `pyright src` fails at the DI binding |
| Restore the `# type: ignore` and break it again | pyright goes green — the evidence |
| Revert the port to a mutable attribute | pyright fails, "invariant because it is mutable" |
| Delete Phase 3's closed-market skip | containment test fails |

## The two follow-ups folded in

**`cascade.partial_aggregate` is DEBUG for an unfinished bucket, WARNING for a closed
one.** An open bucket is short because it is still filling, which is arithmetic; a
closed bucket that is short has really lost bars. This removes roughly fourteen
WARNING lines a minute at three symbols. Both directions are mutation-tested.

**`JobHistoryRepository.get_latest_by_job_ids` sorts on `("started_at", "_id")`.** BSON
stores milliseconds, so two runs of a fast job tie and `$first` was free to return
either — the flake seen three times. `_id` is a UUIDv7 string, monotonic within a
millisecond and lexicographically ordered by generation time; that was verified before
being relied on. `get_last_completed_start` has the same untied sort and needs no fix,
because it projects only `started_at` and both sides of a tie return the same value.

The first version of that test passed five times out of five with the fix removed. It
inserted its rows newest-first, so natural order already agreed with the expected
answer. Inserting oldest-first makes the mutation fail five out of five. It is the
phase's own lesson in miniature: a test written against a fix is not automatically a
test of the fix.

## An unstated footgun in Task 1

pydantic-settings does parse `dict[AssetClass, list[str]]` from a JSON environment
string with no custom parser, as Task 1 claims. What it also does is REPLACE the whole
mapping rather than merge into it, so `MARKET_DATA_PROVIDERS={"index_future":[...]}`
leaves crypto with no provider and the sync silently fetches nothing. Documented on the
field, in `README.md` and in `docs/system-architecture.md`, and made audible by the
second one-shot WARNING.

## Commits

```
f7b6e8c feat(market-data): make provider choice a function of asset class
06d2048 feat(market-data): route history and quotes through a provider map
2e0430f test(market-data): pin the closed-market skip above both fetch loops
900b7b4 fix(market-data): log an unfinished cascade bucket at debug
06a9ed7 fix(jobs): decide the latest run when two share a started_at
b2f172d docs(plans): close phase 4 and record what executing it found
```

All six are on `origin/develop`. The port change, the DI ignore removal and the
adapter are deliberately in one commit: split, the intermediate revision fails
`pyright src`. `f7b6e8c` was checked to have no dangling reference to anything later
and to leave the DI on its original Binance bindings.

## Deployment

Actions run `35705061058` green on every job including all three timezone legs.

| Check | Result |
|-------|--------|
| Startup assertion | `runtime.timezone tz=UTC tzlocal=UTC tzname=('UTC','UTC')` |
| Containers | `pocketquant-app` and `-web` healthy on a fresh image |
| Health endpoint | `HTTP 200` |
| Quote feed, `/api/v1/quotes/latest/BTCUSDT:BINANCE` | timestamp 0.5s old |
| `sync_1m`, six consecutive cycles | `synced_count=3, error_count=0, skipped_count=0` every time |
| `job_history` sync_1m run | `total_fetched=300, total_inserted=3`, 3 details, 5.5s |
| `cascade.partial_aggregate` at WARNING | 0 — Phase 3 logged 57 in its first four minutes |
| `market_data.routing.*` warnings | 0 — every tracked symbol is seeded and mapped |
| `no_progress` / `stuck_threshold_crossed` / `misaligned_bars_dropped` / `integrity.issues_found` | zero of each |
| Errors since start | zero `Traceback`, `TypeError`, `AttributeError`, `offset-naive` |

`total_fetched=300, total_inserted=3` with three details is byte-identical to the
pre-deploy baseline recorded at Phase 3's close, and the 5.5s duration sits inside its
4.4-6.1s range. That is the G5 check for this phase: the routing layer is transparent.

The `partial_aggregate` count is the clearest single number here. Phase 3 measured 57
WARNING lines in four minutes on the same three symbols; six minutes after this deploy
there are none, because production runs at `LOG_LEVEL=INFO` and every one of them was
an in-progress bucket now logged at DEBUG. No closed bucket has been short, which is
the case that would still warn.

The quote check is the one that matters most, because it is the only production
exercise of `RoutingRealtimeQuoteAdapter`: a tick arriving means `subscribe` resolved
an owner, the merged `subscriptions` view satisfied `WsSubscriptionAppService`'s
reconcile diff, and the DI binding resolved a Protocol that pyright now actually
checks. Under the old `# type: ignore` a structural mismatch here would have surfaced
as a runtime `AttributeError` on first access rather than at startup.

**Not production-verified, and deliberately so.** Every routing behaviour beyond "the
single registered provider answers" got no production exercise at all, because there
is only one provider and it is the same one as before. The fallback order, the
unseeded warning, the no-provider warning and the realtime owner map have only their
mutation tests until Phase 5 registers TradingView. This is the same shape as Phase
3's closed-market caveat and for the same structural reason.

## Follow-ups, not done and not in Phase 4 scope

- **`asyncio.gather` leaves siblings running if one child's `run_forever` raises.**
  Gather re-raises immediately, `ws_task` becomes `done()`, teardown skips `cancel()`,
  and only the later `provider.disconnect()` stops the others. Unreachable today
  because Binance's loop swallows `Exception` internally. The invariant Phase 5 must
  honour: a child's `run_forever` must never raise except on cancellation. Recorded
  rather than fixed, because `TaskGroup` would kill every child on one failure and
  nothing supervises or restarts `ws_task`.
- **`connect()` fans out in order and lets the first failure abort the rest.**
  Harmless today: nothing in `app/` or `engine/` calls `provider.connect()`, since
  Binance's `run_forever` connects itself.
- **`search_symbols` stays single-provider**, delegating to the first crypto-spot
  provider, because merging two venues' results needs a dedup rule nothing asks for.
- Carried and still untouched: `calendar_id` and `session_date` are write-once on
  cascaded bars and need a backfill migration; the serialization sweep of roughly
  twenty JSON `.isoformat()` emitters proposed for Phase 7; `docs/deployment.md` still
  documents an emergency rollback that could not have worked; `CLAUDE.md` still says
  8 import-linter contracts where there are 9 (Phase 7's docs task owns it).

## Unresolved questions

- **Should the routing adapter fall through on an empty result at all?** It is
  correct for a genuine outage and wrong for a halt, and only the calendar can tell
  them apart — which is why the gate above both loops is load-bearing rather than
  merely tidy. The containment test now measures the cost, but the design question is
  open and belongs to Phase 5, when the fallback provider is an unofficial scraper
  with real rate limits.
- **Nothing registers a second provider, so the routing order itself is unexercised
  in production.** Phase 5's first deploy is the real test of this phase, not this
  one.
