# Planner report: Exness go-live plan extension

Date: 2026-10-20. Plan: `plans/261019-1957-exness-go-live/` (one plan dir, renumbered so file order = execution order). No code edits, no commit, no push. The renames were done with `git mv` and are staged.

## Result
The plan now has ten phases in runner order:

| # | File | Change |
|---|---|---|
| 01 | `phase-01-admin-token-auth.md` | Cross-references only: the deploy is now Phase 07, and the tunnel (Phase 08) closes D5 |
| 02 | `phase-02-subscription-broker-selection.md` | Conditional step 7 dropped (D1 resolved by 04); steps renumbered; the paper delete now happens in Phase 09 |
| 03 | `phase-03-access-point-re-resolve.md` | Unchanged |
| 04 | `phase-04-backend-safeguards-and-sizing.md` | New. `Safeguards` dataclass at `Scope.APP`; adapter reads it; `entries_paused` checked first in `_presubmit_reason`; admin GET/pause/resume routes; `RiskConfig.leverage`; exness-only `RiskConfig` in reconcile; 1m `unexpected_count`/`unexpected_ranges` |
| 05 | `phase-05-spa-mode-pause-and-hints.md` | New. Badge, pill, strip, `moneyHint`, LIVE Start confirm, Delete in the footer, `.btn-danger`, 8 dead files deleted |
| 06 | `phase-06-cloudflare-tunnel.md` | New. **[USER]** creates the tunnel and `tunnel-test` and pastes `TUNNEL_TOKEN`; agent adds `cloudflared` and keeps `web` `ports:` |
| 07 | `phase-07-ship-with-live-off.md` (was 04) | New env keys and values; safeguards GET check; tunnel round 2 verification at the master push |
| 08 | `phase-08-tunnel-cutover.md` | New. **[USER]** moves DNS to the tunnel; agent drops the port, fixes `11-verify.sh`, removes `WEB_PORT`, and verifies `:80` refused and https 200 |
| 09 | `phase-09-live-round-trip.md` (was 05) | Stop-distance pre-check (≤ 25 USD/oz), margin check, pause-while-open check, D4 = Pause |
| 10 | `phase-10-observation-dst-go-live.md` (was 06) | Observation row extended; Pause offered as the soft weekend option |

`plan.md` changes:
- the E1 line is fixed: it is merged (508093a, cad00b9, 65ddc39), and only Phase 04 edits the adapter;
- D1, D2, D4 and D5 are marked answered, and B10 and B11 are added;
- AC5 now covers the new env keys, and AC8–AC10 are new;
- the stop-and-ask gates gain resume, redeploy-while-paused and `WEB_PORT`;
- the stop-and-report list gains the stop-distance rule;
- stale adapter line citations after E1 are corrected;
- `ak plan validate` passes.

## Findings verified while planning (not in the advice)
- `deploy/vps/11-verify.sh` curls the web host port (`:118-127`) and asserts a listener on `WEB_PORT` (`:173-185`). Dropping `ports:` without changing these would fail the deploy verdict, so Phase 08 changes both.
- `orders` documents do not store `sl_price` (`core/domain/order/entities.py:218-235`). The old Phase 05 check "orders row with sl_price" could never pass. The stop-distance query and the round-trip check now use `trades`/`positions`.
- `check_integrity` returns a weekly report without a grid, and `SYNC_INTERVALS` includes `WEEK_1` (`sync_jobs.py:72-80`). The log line therefore uses `report.get(...)`.
- `BrokerFactory` keeps the live flag as a separate constructor bool. Phase 04 replaces it with `Safeguards`, and the `exness_*` keys in `default_broker_config` become dead and are deleted.
- No DOM test library exists in `web/` (vitest `node` environment, `*.test.ts` only). LIVE Start's confirm decision is pinned through the `moneyHint().real` table test. The dialog wiring is a manual check.

## Unresolved questions
1. E2 closes on 2026-11-02, but Phase 07 requires E2. Phase 10's dates (observation to 2026-10-30, DST check 2026-11-02) cannot hold as written. Can Phase 07 ship with live off before E2 closes?
2. Does `hitnrun2` trail its SL? If it does, `trades.sl_price` misstates the entry stop distance that the Phase 09 pre-check measures.
3. Does the pinned `cloudflared` tag support `tunnel ready` for the healthcheck? Phase 06 step 3 checks this and has a fallback.
4. Does deleting a tunnel public hostname also delete its DNS CNAME? Phase 08 tells the user to delete it if one is left.
5. `margin_percent` units are still unverified. Phase 09 records the value raw.

Status: DONE_WITH_CONCERNS
Summary: The go-live plan is extended in place to ten phases in execution order (04 backend safeguards and sizing, 05 SPA, 06 tunnel code, 08 tunnel cutover; old 04/05/06 became 07/09/10), with every cross-reference, dependency and gate updated, and `ak plan validate` passes.
Concerns/Blockers: The E2 date (2026-11-02) conflicts with Phase 10's observation window and with shipping Phase 07 earlier; the user must decide. The renames are staged but not committed.
