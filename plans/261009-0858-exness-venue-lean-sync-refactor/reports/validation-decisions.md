# Validation and red-team decisions (session 1, 2026-10-10)

These are the user's decisions. They are binding and override the original plan and the advice wherever the two conflict.

## User decisions

1. **The red team is applied in full.**
   - Apply all 15 accepted findings and the Medium mechanical fixes listed under "Red-team findings to apply" below.
   - Findings about live money still apply to the code that gets built, because the broker is still built (decision 3). This covers the lot clamp/fill mismatch, the loss-cap shape, reconciliation, rate priority, the hitnrun2 reject reset, the sizer minimum-lot check and key handling.
   - No live order is placed in this plan.
2. **The metric gate is a ratchet.**
   - Measure the metric after the planned lean refactor (Phase 05) and freeze those numbers as the CI ceiling. CI fails if a later change makes either number worse.
   - Re-measure at the end of the Exness phases with the same ratchet. The new Exness code must not raise the ceiling; inline per-endpoint client wrappers if needed.
   - D4 changes from "≤30% / ≤20" to "≤ the ratcheted ceiling frozen at the end of Phase 05; no regression at the end of the plan".
   - The ≤30% / ≤20 targets are dropped as gates. They may stay in the standard only as an aspiration.
   - Remove the Phase 05 stop-and-ask about the thresholds. Replace it with the ratchet freeze.
3. **The Exness broker is built but kept off. The plan stays on paper now and goes live later.**
   - Build `ExnessBroker` with all the live-money red-team fixes, plus async fill wiring for non-paper brokers, and unit/integration test it with recorded fixtures.
   - Put it behind the global env switch `EXNESS_LIVE_TRADING`, default `false`. When the switch is false, any attempt to create or use an Exness broker is refused with a clear error, and no order request ever reaches Exness.
   - Do not add a per-subscription `broker` field, and do not make any public API or OpenAPI change for broker selection. The selection mechanism is decided in the later go-live plan.
   - Authentication on mutation routes is not built in this plan. It is a written precondition of the future go-live plan.
   - Remove every live order step. That includes the Phase 08 minimum-lot live round trip and the live-week order checks, plus the U3 live risk cap as a precondition for this plan. The `EXNESS_DAILY_LOSS_CAP` and `EXNESS_MAX_LOTS` code paths are still built and tested.
   - Validation in this plan covers:
     - Exness bars synced;
     - quotes streamed;
     - backtests of `hitnrun2` and `engulfing` on Exness bars, with spread modelled;
     - both strategies running on PaperBroker on `:EXNESS` symbols for one market week, including a weekend close/reopen;
     - Exness broker tests green.
   - Rewrite D2 as follows. `ExnessBroker` passes fixture-based tests for:
     - open with SL, rejecting when SL is missing;
     - a clamped quantity normalized before order creation, so that fill → `OrderAppService` → `PositionAppService` opens a position;
     - async fill and reject;
     - reconciliation after a missed fill and after a restart;
     - a daily loss cap computed from the recorded deals fixture.

     With `EXNESS_LIVE_TRADING=false`, the app boots, `BrokerFactory` refuses `exness`, and no Exness order endpoint is ever called. A grep test or mock assertion proves this.
   - Add a section to `plan.md` titled "Out of scope: go-live plan". It lists the preconditions for a later live plan: admin-token auth on mutation routes (fail-closed in prod, with the SPA sending the token), the broker selection mechanism, U3 risk cap, the live minimum-lot round trip, and a live-week observation.
4. **Routing is strictly by the exchange suffix.**
   - Market data for a composite symbol comes only from the provider of its suffix: `XAUUSD:EXNESS` from Exness only, and `XAUUSD:BINANCE` from Binance only.
   - Both can be tracked at the same time, as different series.
   - Do not fall back to another exchange. An unknown suffix logs once and is skipped, never raised in a loop.
   - Implement the lookup with no new router module. `policy_for(symbol)` looks up the `SyncPolicy` by suffix, and the policy carries its data provider and quote provider. Consumers (`SyncService`, quotes, `WsSubscriptionManager`) resolve the provider through the policy.
   - Remove `venue_router.py` and its router classes from the plan. Count file hops honestly against G2.
   - Keep one composite-symbol split helper, reusing what already exists where possible. Do not leave four copies.
5. **`:OKX` market-data symbols are corrected to `:BINANCE`.**
   - Today `:OKX` tracked symbols are silently fetched from Binance. Correct their data identity to `:BINANCE`.
   - OKX stays a broker for execution only and has no data `SyncPolicy`.
   - Add a guarded data-migration task:
     1. Inventory `:OKX` references in prod across tracked symbols, bars, sync status, subscriptions and any other collection that holds a `symbol` field.
     2. Run `mongodump` to back up those collections.
     3. Stop and ask the user, showing counts and any collisions where a `:BINANCE` series already exists.
     4. Migrate by renaming the symbol, or drop duplicates when a `:BINANCE` series already exists, as the user approves.
     5. Verify the counts afterwards.

     It never runs without the backup and the user's approval.
   - After the migration, `:OKX` is treated as an unknown data suffix.

## Red-team findings to apply

The findings are in `red-team-security.md`, `red-team-failure-modes.md`, `red-team-assumptions.md` and `red-team-scope-complexity.md` in this folder.

| # | Finding | Apply as |
|---|---|---|
| 1 | Live trading reachable without auth | Satisfied by decision 3: live is off, there is no selection API, and auth is listed as a go-live precondition. The executor must not add a broker field. |
| 2 | Clamp/fill quantity mismatch | Normalize the quantity before order creation through a broker hook. Add an integration test from clamp to fill to position. `_notify` must be exception-safe and must never kill the stream. |
| 3 | Loss cap reads the wrong deals shape | Record a deals fixture in the spike. `deals_since` follows `next_cursor`/`has_more` and returns `item["deal"]`. Sum only the relevant deal types and exclude `balance` deals. Tests use the recorded fixture. |
| 4 | Key delivery | `EXNESS_PRIVATE_KEY` must be a single-line base64url raw seed. Reject PEM. Drop `EXNESS_PRIVATE_KEY_PATH`. U2 says "committed and pushed to `pocketquant-config` master". Add a pre-deploy guard that fails on `BEGIN` or on a line without `=`. Verify after deploy with a boolean-only `is_configured` check. |
| 5 | Lost fills, orphans, restarts | Use idempotent retry with the same key. Add `client.operation(id)`. Reconcile against the snapshot in both directions. Block signals until the first snapshot. Hold unmapped positions and refuse new orders on that instrument. Register the close path in `_pending_ack`. All of this is tested with fixtures. |
| 6 | Shared rate budget | Reserve priority for order calls. Retry 429 with backoff and `Retry-After`. Run backfill at a rate fraction and never alongside a live broker. Exness sync must not delay Binance `sync_1m` (separate job or time cap). Budget is per operation from `/limits`. |
| 7 | `hitnrun2` silent after a reject | Deliver REJECTED/CANCELLED to the strategy or reset `_open_direction`, and add a test. |
| 8 | Weekend-only calendar | Build `MarketCalendar` from the spike's `trade_sessions` (per weekday, including daily breaks). Add a T1.11 stop condition. The integrity check ignores slots outside sessions. |
| 9 | Sizer can't reach the minimum lot | Add a T1.11 feasibility line. Log a presubmit rejection as `exness.order_rejected_presubmit`. Since live is off this only affects tests and docs, but keep the check. |
| 10 | Lowercase instrument suffixes | Add a case-preserving map from composite code to Exness instrument name, populated from the spike's `instruments.json`. T1.11 records it instead of stopping. |
| 11 | Windows `/tmp` | `code_metrics.py --out <repo-relative path>`, or pipe through stdin. Fix every Verify step that uses `/tmp`. |
| 12 | Week metrics from rotating logs | Persist counters in Mongo (`job_history` details or a small collection), or prove log coverage through container `StartedAt` and the oldest log timestamp. No deploys during the observation week. |
| 13 | Metric not re-measured | Ratchet re-measure at the end of the Exness phases (decision 2). |
| 14 | `venue_router` layer | Replaced by decision 4. |
| 15 | `/api/v1/system/jobs` does not exist | Verify through Mongo `apscheduler_jobs` (no refs to the old module path) and `/{job_id}/runs?limit=1`. |

### Medium mechanical fixes (all applied)

- `client.account()` is undefined. Read the currency from the snapshot, or add `account()` explicitly to the T6.4 contract.
- Spike fixtures must not commit live account state to the PUBLIC repo. Redact monetary fields, `account_name` and ids to placeholders, or synthesize `account.json` and `snapshot.json` from the schema. The secret scan greps the actual secret values inside the container without printing them.
- Validate `EXNESS_API_BASE_URL`: https only, and the host must match the user-confirmed domain recorded in U2. `ws_url` is built from the validated URL. `is_configured` fails closed.
- Validate WS instrument subscriptions against the cached instruments list. Never resend unknown codes.
- Ticks subscribe semantics: the spike tests one-at-a-time subscription and records add-vs-replace. The quote provider sends the full instrument list on change if subscribe replaces.
- Spread model: ask = bid + spread. BUY entries and SHORT exits fill at ask. SHORT SL/TP triggers use bar.high/bar.low + spread. `spread=0` stays byte-identical.
- The spike stays in `scripts/` until feasibility is known. Promote the signer into `src/` in Phase 06, and avoid an extra prod deploy just for fixtures.
- Drop OKX characterization test T2.6, which pins code no phase touches. Reword D6 accordingly. T2.5 covers `BrokerFactory`.
- `code-standards.md` §8 describes only what exists when Phase 05 writes it. Phase 09 revisits §8 with the real add-a-provider touchpoint list.
- A single provider-agnostic deep-backfill path, rather than an Exness-only script, if feasible. Otherwise state the deviation.
- `SyncPolicy`: drop or make load-bearing `live_source` and `rate_budget_per_minute`. Rate limits come from `/limits` at runtime, never hardcoded. Keep one calendar accessor.
- Fix the citations: `core/config.py:98` becomes `:30`, and `paper_broker.py:671` becomes `:678`/`:715`.
- D6: assert `0 failures` from `11-verify.sh`, not a hard-coded 19.
